const fs = require("node:fs");
const net = require("node:net");
const { performance } = require("node:perf_hooks");

const outArg = process.argv.includes("--out") ? process.argv[process.argv.indexOf("--out") + 1] : null;

const HOST = process.env.REDIS_HOST || "127.0.0.1";
const PORT = Number(process.env.REDIS_PORT || 6379);
const ROUNDS = Number(process.env.ROUNDS || 20);
const CONCURRENT_REQUESTS = Number(process.env.CONCURRENT_REQUESTS || 50);
const BUDGET_FIELDS = Number(process.env.BUDGET_FIELDS || 25);
const PREFILL_FIELDS = Number(process.env.PREFILL_FIELDS || 20);
const FIELD_COUNT = Number(process.env.FIELD_COUNT || 5);
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
  constructor() {
    this.buffer = Buffer.alloc(0);
    this.pending = [];
    this.socket = net.createConnection(PORT, HOST);
    this.socket.on("data", (chunk) => this.onData(chunk));
    this.socket.on("error", (error) => {
      while (this.pending.length) this.pending.shift().reject(error);
    });
  }

  ready() {
    if (this.socket.readyState === "open") return Promise.resolve();
    return new Promise((resolve, reject) => {
      this.socket.once("connect", resolve);
      this.socket.once("error", reject);
    });
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

function percentile(values, pct) {
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((pct / 100) * sorted.length) - 1));
  return Number(sorted[index].toFixed(4));
}

function summarize(values) {
  return {
    min: percentile(values, 0),
    p50: percentile(values, 50),
    p95: percentile(values, 95),
    max: percentile(values, 100),
  };
}

async function makePool(size) {
  const pool = Array.from({ length: size }, () => new RedisConnection());
  await Promise.all(pool.map((conn) => conn.ready()));
  return pool;
}

async function setupRound({ namespace, sha }) {
  const conn = new RedisConnection();
  await conn.ready();
  const sessionKey = `${namespace}:session:s1`;
  const ipKey = `${namespace}:ip:10.0.0.1`;
  await conn.send(["DEL", sessionKey, ipKey]);
  await conn.send(["SET", sessionKey, PREFILL_FIELDS, "EX", WINDOW_SECONDS]);
  await conn.send(["SET", ipKey, PREFILL_FIELDS, "EX", WINDOW_SECONDS]);
  conn.close();
  return { sessionKey, ipKey, sha };
}

async function runLuaBoundaryRound({ pool, sha, round }) {
  const namespace = `boundary:lua:${Date.now()}:${round}`;
  const { sessionKey, ipKey } = await setupRound({ namespace, sha });
  const started = performance.now();
  const rows = await Promise.all(
    Array.from({ length: CONCURRENT_REQUESTS }, (_, index) =>
      pool[index % pool.length]
        .send(["EVALSHA", sha, "2", sessionKey, ipKey, FIELD_COUNT, BUDGET_FIELDS, WINDOW_SECONDS])
        .then((result) => ({ allowed: result[0] === 1, result })),
    ),
  );
  const finalSession = Number(await pool[0].send(["GET", sessionKey]));
  const finalIp = Number(await pool[0].send(["GET", ipKey]));
  return {
    label: "redisLuaAtomicBoundary",
    allowed: rows.filter((row) => row.allowed).length,
    blocked: rows.filter((row) => !row.allowed).length,
    finalSession,
    finalIp,
    overBudgetFields: Math.max(0, finalSession - BUDGET_FIELDS, finalIp - BUDGET_FIELDS),
    ms: Number((performance.now() - started).toFixed(3)),
  };
}

async function runNonAtomicBoundaryRound({ pool, sha, round }) {
  const namespace = `boundary:nonatomic:${Date.now()}:${round}`;
  const { sessionKey, ipKey } = await setupRound({ namespace, sha });
  const started = performance.now();
  const rows = await Promise.all(
    Array.from({ length: CONCURRENT_REQUESTS }, async (_, index) => {
      const conn = pool[index % pool.length];
      const sessionUsed = Number(await conn.send(["GET", sessionKey]));
      const ipUsed = Number(await conn.send(["GET", ipKey]));
      if (sessionUsed + FIELD_COUNT > BUDGET_FIELDS || ipUsed + FIELD_COUNT > BUDGET_FIELDS) {
        return { allowed: false };
      }
      await conn.send(["INCRBY", sessionKey, FIELD_COUNT]);
      await conn.send(["INCRBY", ipKey, FIELD_COUNT]);
      return { allowed: true };
    }),
  );
  const finalSession = Number(await pool[0].send(["GET", sessionKey]));
  const finalIp = Number(await pool[0].send(["GET", ipKey]));
  return {
    label: "redisNonAtomicBoundary",
    allowed: rows.filter((row) => row.allowed).length,
    blocked: rows.filter((row) => !row.allowed).length,
    finalSession,
    finalIp,
    overBudgetFields: Math.max(0, finalSession - BUDGET_FIELDS, finalIp - BUDGET_FIELDS),
    ms: Number((performance.now() - started).toFixed(3)),
  };
}

async function main() {
  const setup = new RedisConnection();
  await setup.ready();
  const ping = await setup.send(["PING"]);
  const sha = await setup.send(["SCRIPT", "LOAD", LUA_DUAL_BUDGET]);
  setup.close();

  const pool = await makePool(CONCURRENT_REQUESTS);
  const lua = [];
  const nonAtomic = [];
  for (let round = 0; round < ROUNDS; round += 1) {
    lua.push(await runLuaBoundaryRound({ pool, sha, round }));
    nonAtomic.push(await runNonAtomicBoundaryRound({ pool, sha, round }));
  }
  pool.forEach((conn) => conn.close());

  const report = {
    generatedAt: new Date().toISOString(),
    redis: { host: HOST, port: PORT, ping, scriptSha: sha },
    config: {
      rounds: ROUNDS,
      concurrentRequests: CONCURRENT_REQUESTS,
      budgetFields: BUDGET_FIELDS,
      prefillFields: PREFILL_FIELDS,
      remainingFieldsBeforeRace: BUDGET_FIELDS - PREFILL_FIELDS,
      fieldCount: FIELD_COUNT,
      expectedAllowedAtBoundary: Math.floor((BUDGET_FIELDS - PREFILL_FIELDS) / FIELD_COUNT),
    },
    summaries: {
      redisLuaAtomicBoundary: {
        allowed: summarize(lua.map((row) => row.allowed)),
        overBudgetFields: summarize(lua.map((row) => row.overBudgetFields)),
        finalSession: summarize(lua.map((row) => row.finalSession)),
        ms: summarize(lua.map((row) => row.ms)),
        anyOverBudget: lua.some((row) => row.overBudgetFields > 0),
      },
      redisNonAtomicBoundary: {
        allowed: summarize(nonAtomic.map((row) => row.allowed)),
        overBudgetFields: summarize(nonAtomic.map((row) => row.overBudgetFields)),
        finalSession: summarize(nonAtomic.map((row) => row.finalSession)),
        ms: summarize(nonAtomic.map((row) => row.ms)),
        anyOverBudget: nonAtomic.some((row) => row.overBudgetFields > 0),
      },
    },
    raw: { lua, nonAtomic },
  };

  const output = JSON.stringify(report, null, 2);
  if (outArg) fs.writeFileSync(outArg, `${output}\n`, "utf8");
  console.log(output);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
