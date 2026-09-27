const fs = require("node:fs");
const net = require("node:net");
const { performance } = require("node:perf_hooks");

const outArg = process.argv.includes("--out") ? process.argv[process.argv.indexOf("--out") + 1] : null;

const HOST = process.env.REDIS_HOST || "127.0.0.1";
const PORT = Number(process.env.REDIS_PORT || 6379);
const BAD_PORT = Number(process.env.REDIS_BAD_PORT || 6390);
const CONNECT_TIMEOUT_MS = Number(process.env.CONNECT_TIMEOUT_MS || 500);
const FIELD_COUNT = Number(process.env.FIELD_COUNT || 5);
const BUDGET_FIELDS = Number(process.env.BUDGET_FIELDS || 25);
const WINDOW_SECONDS = Number(process.env.WINDOW_SECONDS || 600);

const LUA_DUAL_BUDGET = `
local fields = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
local s = tonumber(redis.call('GET', KEYS[1]) or '0')
local ip = tonumber(redis.call('GET', KEYS[2]) or '0')
if s + fields > limit or ip + fields > limit then
  return {0, s, ip}
end
s = redis.call('INCRBY', KEYS[1], fields)
ip = redis.call('INCRBY', KEYS[2], fields)
if s == fields then redis.call('EXPIRE', KEYS[1], ttl) end
if ip == fields then redis.call('EXPIRE', KEYS[2], ttl) end
return {1, s, ip}
`;

function encodeCommand(parts) {
  return `*${parts.length}\r\n${parts.map((part) => {
    const value = String(part);
    return `$${Buffer.byteLength(value)}\r\n${value}\r\n`;
  }).join("")}`;
}

function parseResp(buffer, offset = 0) {
  if (offset >= buffer.length) return null;
  const type = String.fromCharCode(buffer[offset]);
  const lineEnd = buffer.indexOf("\r\n", offset);
  if (lineEnd === -1) return null;
  const line = buffer.toString("utf8", offset + 1, lineEnd);
  const next = lineEnd + 2;
  if (type === "+") return { value: line, offset: next };
  if (type === "-") return { error: true, value: line, offset: next };
  if (type === ":") return { value: Number(line), offset: next };
  if (type === "$") {
    const length = Number(line);
    if (length === -1) return { value: null, offset: next };
    const end = next + length;
    if (buffer.length < end + 2) return null;
    return { value: buffer.toString("utf8", next, end), offset: end + 2 };
  }
  if (type === "*") {
    const count = Number(line);
    const values = [];
    let cursor = next;
    for (let i = 0; i < count; i += 1) {
      const parsed = parseResp(buffer, cursor);
      if (!parsed) return null;
      values.push(parsed.value);
      cursor = parsed.offset;
    }
    return { value: values, offset: cursor };
  }
  return { error: true, value: `Unsupported RESP type ${type}`, offset: buffer.length };
}

class RedisConnection {
  constructor({ host = HOST, port = PORT, timeoutMs = CONNECT_TIMEOUT_MS } = {}) {
    this.buffer = Buffer.alloc(0);
    this.pending = [];
    this.socket = net.createConnection(port, host);
    this.readyPromise = new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.socket.destroy();
        reject(new Error(`connect timeout after ${timeoutMs}ms`));
      }, timeoutMs);
      this.socket.once("connect", () => {
        clearTimeout(timer);
        resolve();
      });
      this.socket.once("error", (error) => {
        clearTimeout(timer);
        reject(error);
      });
    });
    this.socket.on("data", (chunk) => this.onData(chunk));
    this.socket.on("error", (error) => {
      while (this.pending.length) this.pending.shift().reject(error);
    });
  }

  ready() {
    return this.readyPromise;
  }

  send(parts) {
    return new Promise((resolve, reject) => {
      this.pending.push({ resolve, reject });
      this.socket.write(encodeCommand(parts));
    });
  }

  onData(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    while (this.pending.length) {
      const parsed = parseResp(this.buffer);
      if (!parsed) return;
      this.buffer = this.buffer.subarray(parsed.offset);
      const item = this.pending.shift();
      if (parsed.error) item.reject(new Error(parsed.value));
      else item.resolve(parsed.value);
    }
  }

  close() {
    this.socket.end();
  }
}

async function loadScript(conn) {
  return conn.send(["SCRIPT", "LOAD", LUA_DUAL_BUDGET]);
}

async function evalBudget(conn, sha, namespace) {
  return conn.send([
    "EVALSHA",
    sha,
    "2",
    `${namespace}:session:s1`,
    `${namespace}:ip:10.0.0.1`,
    FIELD_COUNT,
    BUDGET_FIELDS,
    WINDOW_SECONDS,
  ]);
}

async function revealWithNoscriptRetry(conn, sha, namespace) {
  try {
    const result = await evalBudget(conn, sha, namespace);
    return { result, sha, reloaded: false };
  } catch (error) {
    if (!String(error.message).includes("NOSCRIPT")) throw error;
    const reloadedSha = await loadScript(conn);
    const result = await evalBudget(conn, reloadedSha, namespace);
    return { result, sha: reloadedSha, reloaded: true };
  }
}

async function testNoscriptRecovery() {
  const conn = new RedisConnection();
  await conn.ready();
  const ping = await conn.send(["PING"]);
  const sha = await loadScript(conn);
  const beforeFlush = await evalBudget(conn, sha, `ops:before:${Date.now()}`);
  await conn.send(["SCRIPT", "FLUSH"]);
  const started = performance.now();
  const recovered = await revealWithNoscriptRetry(conn, sha, `ops:after:${Date.now()}`);
  const ms = performance.now() - started;
  conn.close();
  return {
    ping,
    originalSha: sha,
    beforeFlushAllowed: beforeFlush[0] === 1,
    reloaded: recovered.reloaded,
    recoveredAllowed: recovered.result[0] === 1,
    recoveredSha: recovered.sha,
    recoveryMs: Number(ms.toFixed(3)),
  };
}

async function revealWithFailurePolicy({ policy }) {
  const started = performance.now();
  try {
    const conn = new RedisConnection({ port: BAD_PORT });
    await conn.ready();
    const sha = await loadScript(conn);
    const result = await evalBudget(conn, sha, `ops:bad:${Date.now()}`);
    conn.close();
    return { policy, allowed: result[0] === 1, degraded: false, error: null, ms: Number((performance.now() - started).toFixed(3)) };
  } catch (error) {
    return {
      policy,
      allowed: policy === "fail-open",
      degraded: true,
      error: error.message,
      ms: Number((performance.now() - started).toFixed(3)),
    };
  }
}

async function main() {
  const noscriptRecovery = await testNoscriptRecovery();
  const failurePolicies = [
    await revealWithFailurePolicy({ policy: "fail-closed" }),
    await revealWithFailurePolicy({ policy: "fail-open" }),
  ];

  const report = {
    generatedAt: new Date().toISOString(),
    config: {
      host: HOST,
      port: PORT,
      badPort: BAD_PORT,
      connectTimeoutMs: CONNECT_TIMEOUT_MS,
      fieldCount: FIELD_COUNT,
      budgetFields: BUDGET_FIELDS,
      windowSeconds: WINDOW_SECONDS,
    },
    noscriptRecovery,
    failurePolicies,
    interpretation: {
      noscript:
        "A production client should catch NOSCRIPT, SCRIPT LOAD the Lua body, and retry the failed reveal once.",
      failClosed:
        "Protects sensitive fields during Redis outage but may hide values from legitimate users.",
      failOpen:
        "Preserves UX during Redis outage but disables the reveal-budget layer for that interval.",
    },
  };

  const output = JSON.stringify(report, null, 2);
  if (outArg) fs.writeFileSync(outArg, `${output}\n`, "utf8");
  console.log(output);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
