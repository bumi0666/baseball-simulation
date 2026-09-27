const fs = require("node:fs");
const { performance } = require("node:perf_hooks");

const outArg = process.argv.includes("--out") ? process.argv[process.argv.indexOf("--out") + 1] : null;

const FIELD_COUNT = Number(process.env.FIELD_COUNT || 5);
const REQUESTS = Number(process.env.REQUESTS || 80);
const BUDGET_FIELDS = Number(process.env.BUDGET_FIELDS || 25);
const JITTER_MS = Number(process.env.JITTER_MS || 3);
const ROUNDS = Number(process.env.ROUNDS || 12);

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function jitter() {
  return Math.floor(Math.random() * JITTER_MS);
}

class NonAtomicBudget {
  constructor() {
    this.used = new Map();
  }

  async tryReveal(key, fields) {
    const usedBefore = this.used.get(key) || 0;
    await sleep(jitter());
    const remaining = BUDGET_FIELDS - usedBefore;
    if (fields > remaining) {
      return { allowed: false, used: usedBefore, remaining: Math.max(0, remaining) };
    }
    await sleep(jitter());
    this.used.set(key, usedBefore + fields);
    return { allowed: true, used: usedBefore + fields, remaining: remaining - fields };
  }
}

class AtomicBudget {
  constructor() {
    this.used = new Map();
  }

  async tryReveal(key, fields) {
    const usedBefore = this.used.get(key) || 0;
    const remaining = BUDGET_FIELDS - usedBefore;
    if (fields > remaining) {
      return { allowed: false, used: usedBefore, remaining: Math.max(0, remaining) };
    }
    this.used.set(key, usedBefore + fields);
    await sleep(jitter());
    return { allowed: true, used: usedBefore + fields, remaining: remaining - fields };
  }
}

class DualAtomicBudget {
  constructor() {
    this.used = new Map();
  }

  get(key) {
    return this.used.get(key) || 0;
  }

  async tryReveal({ session, ip, fields }) {
    const sessionKey = `session:${session}`;
    const ipKey = `ip:${ip}`;
    const sessionUsed = this.get(sessionKey);
    const ipUsed = this.get(ipKey);
    const sessionRemaining = BUDGET_FIELDS - sessionUsed;
    const ipRemaining = BUDGET_FIELDS - ipUsed;
    if (fields > sessionRemaining || fields > ipRemaining) {
      return {
        allowed: false,
        sessionUsed,
        ipUsed,
        remaining: Math.max(0, Math.min(sessionRemaining, ipRemaining)),
      };
    }
    this.used.set(sessionKey, sessionUsed + fields);
    this.used.set(ipKey, ipUsed + fields);
    await sleep(jitter());
    return {
      allowed: true,
      sessionUsed: sessionUsed + fields,
      ipUsed: ipUsed + fields,
      remaining: Math.min(sessionRemaining, ipRemaining) - fields,
    };
  }
}

async function runSingleKeyRound(BudgetClass) {
  const budget = new BudgetClass();
  const started = performance.now();
  const rows = await Promise.all(
    Array.from({ length: REQUESTS }, (_, index) => budget.tryReveal("identity-1", FIELD_COUNT).then((row) => ({ index, ...row }))),
  );
  const ms = performance.now() - started;
  const allowed = rows.filter((row) => row.allowed).length;
  return {
    allowedRequests: allowed,
    blockedRequests: REQUESTS - allowed,
    revealedFields: allowed * FIELD_COUNT,
    overBudgetFields: Math.max(0, allowed * FIELD_COUNT - BUDGET_FIELDS),
    ms: Number(ms.toFixed(3)),
  };
}

async function runDualRound({ rotateSession = false, rotateIp = false } = {}) {
  const budget = new DualAtomicBudget();
  const started = performance.now();
  const rows = await Promise.all(
    Array.from({ length: REQUESTS }, (_, index) => {
      const session = rotateSession ? `s${index}` : "s1";
      const ip = rotateIp ? `10.0.0.${index + 1}` : "10.0.0.1";
      return budget.tryReveal({ session, ip, fields: FIELD_COUNT }).then((row) => ({ index, session, ip, ...row }));
    }),
  );
  const ms = performance.now() - started;
  const allowed = rows.filter((row) => row.allowed).length;
  return {
    rotateSession,
    rotateIp,
    allowedRequests: allowed,
    blockedRequests: REQUESTS - allowed,
    revealedFields: allowed * FIELD_COUNT,
    overBudgetFields: Math.max(0, allowed * FIELD_COUNT - BUDGET_FIELDS),
    ms: Number(ms.toFixed(3)),
  };
}

function summarize(rows) {
  const values = rows.map((row) => row.allowedRequests).sort((a, b) => a - b);
  const fields = rows.map((row) => row.revealedFields).sort((a, b) => a - b);
  return {
    rounds: rows.length,
    allowedRequests: {
      min: values[0],
      median: values[Math.floor((values.length - 1) / 2)],
      max: values[values.length - 1],
    },
    revealedFields: {
      min: fields[0],
      median: fields[Math.floor((fields.length - 1) / 2)],
      max: fields[fields.length - 1],
    },
    anyOverBudget: rows.some((row) => row.overBudgetFields > 0),
    maxOverBudgetFields: Math.max(...rows.map((row) => row.overBudgetFields)),
  };
}

async function main() {
  const nonAtomic = [];
  const atomic = [];
  const dualSame = [];
  const dualRotateSession = [];
  const dualRotateIp = [];
  const dualRotateBoth = [];
  for (let round = 0; round < ROUNDS; round += 1) {
    nonAtomic.push(await runSingleKeyRound(NonAtomicBudget));
    atomic.push(await runSingleKeyRound(AtomicBudget));
    dualSame.push(await runDualRound());
    dualRotateSession.push(await runDualRound({ rotateSession: true }));
    dualRotateIp.push(await runDualRound({ rotateIp: true }));
    dualRotateBoth.push(await runDualRound({ rotateSession: true, rotateIp: true }));
  }

  const report = {
    generatedAt: new Date().toISOString(),
    config: {
      requests: REQUESTS,
      fieldCount: FIELD_COUNT,
      budgetFields: BUDGET_FIELDS,
      expectedAllowedRequests: Math.floor(BUDGET_FIELDS / FIELD_COUNT),
      jitterMs: JITTER_MS,
      rounds: ROUNDS,
    },
    summaries: {
      nonAtomicSingleIdentity: summarize(nonAtomic),
      atomicSingleIdentity: summarize(atomic),
      dualSameSessionSameIp: summarize(dualSame),
      dualRotatingSessionSameIp: summarize(dualRotateSession),
      dualSameSessionRotatingIp: summarize(dualRotateIp),
      dualRotatingBoth: summarize(dualRotateBoth),
    },
    raw: {
      nonAtomic,
      atomic,
      dualSame,
      dualRotateSession,
      dualRotateIp,
      dualRotateBoth,
    },
    redisImplementationNote: {
      requirement:
        "The budget decision and counter update must be a single atomic operation. Redis GET/check followed by INCR/SET is not sufficient under concurrent reveal requests.",
      practicalShape:
        "Use a Lua script or equivalent atomic transaction that checks session and IP buckets, refuses if either would exceed budget, and increments both buckets only when both pass.",
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
