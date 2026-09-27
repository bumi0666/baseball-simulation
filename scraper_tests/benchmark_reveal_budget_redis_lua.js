const fs = require("node:fs");
const net = require("node:net");
const { performance } = require("node:perf_hooks");

const outArg = process.argv.includes("--out") ? process.argv[process.argv.indexOf("--out") + 1] : null;

const HOST = process.env.REDIS_HOST || "127.0.0.1";
const PORT = Number(process.env.REDIS_PORT || 6379);
const REQUESTS = Number(process.env.REQUESTS || 1000);
const CONCURRENCY = Number(process.env.CONCURRENCY || 50);
const ROUNDS = Number(process.env.ROUNDS || 8);
const FIELD_COUNT = Number(process.env.FIELD_COUNT || 5);
const BUDGET_FIELDS = Number(process.env.BUDGET_FIELDS || 1000000);
const WINDOW_SECONDS = Number(process.env.WINDOW_SECONDS || 600);
const IDENTITY_COUNT = Number(process.env.IDENTITY_COUNT || 5);

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

  async ready() {
    if (this.socket.readyState === "open") return;
    await new Promise((resolve, reject) => {
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
    if (count === -1) return { value: null, offset: next };
    const values = [];
    let cursor = next;
    for (let index = 0; index < count; index += 1) {
      const parsed = parseResp(buffer, cursor);
      if (!parsed) return null;
      values.push(parsed.value);
      cursor = parsed.offset;
    }
    return { value: values, offset: cursor };
  }
  return { error: true, value: `Unsupported RESP type ${type}`, offset: buffer.length };
}

function percentile(values, pct) {
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((pct / 100) * sorted.length) - 1));
  return Number(sorted[index].toFixed(4));
}

function summarize(values) {
  return {
    count: values.length,
    min: percentile(values, 0),
    p50: percentile(values, 50),
    p95: percentile(values, 95),
    p99: percentile(values, 99),
    max: percentile(values, 100),
  };
}

class InMemoryDualBudget {
  constructor() {
    this.used = new Map();
  }

  async tryReveal({ session, ip, fields }) {
    const sessionKey = `session:${session}`;
    const ipKey = `ip:${ip}`;
    const sessionUsed = this.used.get(sessionKey) || 0;
    const ipUsed = this.used.get(ipKey) || 0;
    if (sessionUsed + fields > BUDGET_FIELDS || ipUsed + fields > BUDGET_FIELDS) return false;
    this.used.set(sessionKey, sessionUsed + fields);
    this.used.set(ipKey, ipUsed + fields);
    return true;
  }
}

class RedisLuaDualBudget {
  constructor({ namespace, sha, pool }) {
    this.namespace = namespace;
    this.sha = sha;
    this.pool = pool;
    this.cursor = 0;
  }

  async tryReveal({ session, ip, fields }) {
    const conn = this.pool[this.cursor % this.pool.length];
    this.cursor += 1;
    const result = await conn.send([
      "EVALSHA",
      this.sha,
      "2",
      `${this.namespace}:session:${session}`,
      `${this.namespace}:ip:${ip}`,
      fields,
      BUDGET_FIELDS,
      WINDOW_SECONDS,
    ]);
    return result[0] === 1;
  }
}

async function runRound({ label, makeBudget }) {
  const budget = await makeBudget();
  let cursor = 0;
  let allowed = 0;
  const latencies = [];
  const started = performance.now();

  async function worker(workerId) {
    while (cursor < REQUESTS) {
      cursor += 1;
      const itemStarted = performance.now();
      const ok = await budget.tryReveal({
        session: `s${workerId % IDENTITY_COUNT}`,
        ip: `10.0.0.${(workerId % IDENTITY_COUNT) + 1}`,
        fields: FIELD_COUNT,
      });
      latencies.push(performance.now() - itemStarted);
      if (ok) allowed += 1;
    }
  }

  await Promise.all(Array.from({ length: CONCURRENCY }, (_, index) => worker(index)));
  return {
    label,
    allowed,
    blocked: REQUESTS - allowed,
    totalMs: Number((performance.now() - started).toFixed(3)),
    perRevealMs: summarize(latencies),
  };
}

async function runScenario({ label, makeBudget }) {
  const rows = [];
  for (let round = 0; round < ROUNDS; round += 1) rows.push(await runRound({ label, makeBudget }));
  return {
    label,
    rounds: ROUNDS,
    totalMs: summarize(rows.map((row) => row.totalMs)),
    perRevealMs: {
      p50: percentile(rows.map((row) => row.perRevealMs.p50), 50),
      p95: percentile(rows.map((row) => row.perRevealMs.p95), 50),
      p99: percentile(rows.map((row) => row.perRevealMs.p99), 50),
    },
    allowed: summarize(rows.map((row) => row.allowed)),
    raw: rows,
  };
}

async function makeRedisPool(size) {
  const pool = Array.from({ length: size }, () => new RedisConnection());
  await Promise.all(pool.map((conn) => conn.ready()));
  return pool;
}

async function main() {
  const setup = new RedisConnection();
  await setup.ready();
  const pong = await setup.send(["PING"]);
  const sha = await setup.send(["SCRIPT", "LOAD", LUA_DUAL_BUDGET]);
  setup.close();

  const pool = await makeRedisPool(CONCURRENCY);

  const scenarios = [
    await runScenario({
      label: "inMemoryAtomicDual",
      makeBudget: async () => new InMemoryDualBudget(),
    }),
    await runScenario({
      label: "redisLuaDual",
      makeBudget: async () => {
        const namespace = `budget:${Date.now()}:${Math.random().toString(16).slice(2)}`;
        return new RedisLuaDualBudget({ namespace, sha, pool });
      },
    }),
  ];

  pool.forEach((conn) => conn.close());

  const report = {
    generatedAt: new Date().toISOString(),
    redis: { host: HOST, port: PORT, ping: pong, scriptSha: sha },
    config: {
      requests: REQUESTS,
      concurrency: CONCURRENCY,
      rounds: ROUNDS,
      fieldCount: FIELD_COUNT,
      budgetFields: BUDGET_FIELDS,
      windowSeconds: WINDOW_SECONDS,
      identityCount: IDENTITY_COUNT,
    },
    scenarios,
  };

  const output = JSON.stringify(report, null, 2);
  if (outArg) fs.writeFileSync(outArg, `${output}\n`, "utf8");
  console.log(output);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
