const fs = require("node:fs");
const { performance } = require("node:perf_hooks");

const outArg = process.argv.includes("--out") ? process.argv[process.argv.indexOf("--out") + 1] : null;

const REQUESTS = Number(process.env.REQUESTS || 1000);
const FIELD_COUNT = Number(process.env.FIELD_COUNT || 5);
const BUDGET_FIELDS = Number(process.env.BUDGET_FIELDS || 1000000);
const ROUNDS = Number(process.env.ROUNDS || 8);
const CONCURRENCY = Number(process.env.CONCURRENCY || 50);
const RTT_PROFILES = (process.env.RTT_PROFILES || "0,0.2,1,5").split(",").map(Number);

function sleep(ms) {
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function percentile(values, pct) {
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((pct / 100) * sorted.length) - 1));
  return Number(sorted[index].toFixed(4));
}

function summarizeLatencies(values) {
  return {
    count: values.length,
    min: percentile(values, 0),
    p50: percentile(values, 50),
    p95: percentile(values, 95),
    p99: percentile(values, 99),
    max: percentile(values, 100),
  };
}

class InMemoryDualAtomicBudget {
  constructor() {
    this.used = new Map();
  }

  tryReveal({ session, ip, fields }) {
    const sessionKey = `session:${session}`;
    const ipKey = `ip:${ip}`;
    const sessionUsed = this.used.get(sessionKey) || 0;
    const ipUsed = this.used.get(ipKey) || 0;
    if (sessionUsed + fields > BUDGET_FIELDS || ipUsed + fields > BUDGET_FIELDS) {
      return { allowed: false };
    }
    this.used.set(sessionKey, sessionUsed + fields);
    this.used.set(ipKey, ipUsed + fields);
    return { allowed: true };
  }
}

class SimulatedRedisLuaDualBudget {
  constructor({ rttMs }) {
    this.used = new Map();
    this.rttMs = rttMs;
  }

  async tryReveal({ session, ip, fields }) {
    await sleep(this.rttMs);
    const sessionKey = `session:${session}`;
    const ipKey = `ip:${ip}`;
    const sessionUsed = this.used.get(sessionKey) || 0;
    const ipUsed = this.used.get(ipKey) || 0;
    if (sessionUsed + fields > BUDGET_FIELDS || ipUsed + fields > BUDGET_FIELDS) {
      return { allowed: false };
    }
    this.used.set(sessionKey, sessionUsed + fields);
    this.used.set(ipKey, ipUsed + fields);
    return { allowed: true };
  }
}

class SimulatedRedisNonAtomicDualBudget {
  constructor({ rttMs }) {
    this.used = new Map();
    this.rttMs = rttMs;
  }

  async tryReveal({ session, ip, fields }) {
    const sessionKey = `session:${session}`;
    const ipKey = `ip:${ip}`;
    await sleep(this.rttMs);
    const sessionUsed = this.used.get(sessionKey) || 0;
    const ipUsed = this.used.get(ipKey) || 0;
    if (sessionUsed + fields > BUDGET_FIELDS || ipUsed + fields > BUDGET_FIELDS) {
      return { allowed: false };
    }
    await sleep(this.rttMs);
    this.used.set(sessionKey, sessionUsed + fields);
    this.used.set(ipKey, ipUsed + fields);
    return { allowed: true };
  }
}

async function runWithConcurrency({ makeBudget, label }) {
  const budget = makeBudget();
  let cursor = 0;
  let allowed = 0;
  const latencies = [];
  const started = performance.now();

  async function worker(workerId) {
    while (cursor < REQUESTS) {
      const index = cursor;
      cursor += 1;
      const itemStarted = performance.now();
      const result = await budget.tryReveal({
        session: `session-${workerId % 5}`,
        ip: `10.0.0.${(workerId % 5) + 1}`,
        fields: FIELD_COUNT,
      });
      latencies.push(performance.now() - itemStarted);
      if (result.allowed) allowed += 1;
    }
  }

  await Promise.all(Array.from({ length: CONCURRENCY }, (_, index) => worker(index)));

  return {
    label,
    allowed,
    blocked: REQUESTS - allowed,
    totalMs: Number((performance.now() - started).toFixed(3)),
    perRevealMs: summarizeLatencies(latencies),
  };
}

async function runScenario({ label, makeBudget }) {
  const rounds = [];
  for (let round = 0; round < ROUNDS; round += 1) {
    rounds.push(await runWithConcurrency({ label, makeBudget }));
  }
  return {
    label,
    rounds: ROUNDS,
    totalMs: summarizeLatencies(rounds.map((row) => row.totalMs)),
    perRevealMs: {
      p50: percentile(rounds.map((row) => row.perRevealMs.p50), 50),
      p95: percentile(rounds.map((row) => row.perRevealMs.p95), 50),
      p99: percentile(rounds.map((row) => row.perRevealMs.p99), 50),
    },
    allowed: summarizeLatencies(rounds.map((row) => row.allowed)),
    raw: rounds,
  };
}

async function main() {
  const scenarios = [];
  scenarios.push(
    await runScenario({
      label: "inMemoryAtomicDual",
      makeBudget: () => new InMemoryDualAtomicBudget(),
    }),
  );

  for (const rttMs of RTT_PROFILES) {
    scenarios.push(
      await runScenario({
        label: `simulatedRedisLuaDual:rtt=${rttMs}ms`,
        makeBudget: () => new SimulatedRedisLuaDualBudget({ rttMs }),
      }),
    );
  }

  for (const rttMs of RTT_PROFILES) {
    scenarios.push(
      await runScenario({
        label: `simulatedRedisNonAtomicDual:rtt=${rttMs}ms`,
        makeBudget: () => new SimulatedRedisNonAtomicDualBudget({ rttMs }),
      }),
    );
  }

  const report = {
    generatedAt: new Date().toISOString(),
    config: {
      requests: REQUESTS,
      fieldCount: FIELD_COUNT,
      budgetFields: BUDGET_FIELDS,
      rounds: ROUNDS,
      concurrency: CONCURRENCY,
      rttProfilesMs: RTT_PROFILES,
    },
    note:
      "Redis is not installed in this local environment. The Redis rows model Lua as one network round trip plus atomic check/commit, and non-atomic GET/check/SET as two round trips with a race window.",
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
