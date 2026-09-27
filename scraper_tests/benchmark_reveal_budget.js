const fs = require("node:fs");
const http = require("node:http");
const { performance } = require("node:perf_hooks");

const { publicRecord } = require("./benchmark_sensitive_field_template");

const outArg = process.argv.includes("--out") ? process.argv[process.argv.indexOf("--out") + 1] : null;

const FIELD_COUNT = Number(process.env.FIELD_COUNT || 5);
const PAGE_COUNT = Number(process.env.PAGE_COUNT || 80);
const BUDGET_FIELDS = Number(process.env.BUDGET_FIELDS || 25);
const WINDOW_MS = Number(process.env.WINDOW_MS || 10 * 60 * 1000);

function fieldName(index) {
  return `field_${String(index + 1).padStart(2, "0")}`;
}

function pageRecord(pageIndex) {
  const n = String(pageIndex + 1).padStart(3, "0");
  const fields = Object.fromEntries(
    Array.from({ length: FIELD_COUNT }, (_, index) => [
      fieldName(index),
      `restricted page ${n} value ${String(index + 1).padStart(2, "0")}`,
    ]),
  );
  const placeholders = Object.fromEntries(
    Object.keys(fields).map((field, index) => [field, ["Available on request", "Contact team", "Restricted"][index % 3]]),
  );
  return { id: `page-${n}`, fields, placeholders };
}

const pages = Array.from({ length: PAGE_COUNT }, (_, index) => pageRecord(index));

class RevealBudget {
  constructor({ budgetFields, windowMs, keyMode }) {
    this.budgetFields = budgetFields;
    this.windowMs = windowMs;
    this.keyMode = keyMode;
    this.events = new Map();
  }

  keyFor({ session, ip }) {
    if (this.keyMode === "session") return `session:${session || "anon"}`;
    if (this.keyMode === "ip") return `ip:${ip || "0.0.0.0"}`;
    return `session:${session || "anon"}|ip:${ip || "0.0.0.0"}`;
  }

  prune(key, now) {
    const cutoff = now - this.windowMs;
    const list = (this.events.get(key) || []).filter((event) => event.t >= cutoff);
    this.events.set(key, list);
    return list;
  }

  tryReveal({ session, ip, fieldCount, now }) {
    if (this.keyMode === "dual") {
      const sessionDecision = this.tryRevealForKey({ key: `session:${session || "anon"}`, fieldCount, now, commit: false });
      const ipDecision = this.tryRevealForKey({ key: `ip:${ip || "0.0.0.0"}`, fieldCount, now, commit: false });
      if (!sessionDecision.allowed || !ipDecision.allowed) {
        return {
          allowed: false,
          key: `dual:${session || "anon"}|${ip || "0.0.0.0"}`,
          requested: fieldCount,
          session: sessionDecision,
          ip: ipDecision,
          remaining: Math.min(sessionDecision.remaining, ipDecision.remaining),
          used: Math.max(sessionDecision.used, ipDecision.used),
        };
      }
      const committedSession = this.tryRevealForKey({ key: `session:${session || "anon"}`, fieldCount, now, commit: true });
      const committedIp = this.tryRevealForKey({ key: `ip:${ip || "0.0.0.0"}`, fieldCount, now, commit: true });
      return {
        allowed: true,
        key: `dual:${session || "anon"}|${ip || "0.0.0.0"}`,
        requested: fieldCount,
        session: committedSession,
        ip: committedIp,
        remaining: Math.min(committedSession.remaining, committedIp.remaining),
        used: Math.max(committedSession.used, committedIp.used),
      };
    }
    const key = this.keyFor({ session, ip });
    return this.tryRevealForKey({ key, fieldCount, now, commit: true });
  }

  tryRevealForKey({ key, fieldCount, now, commit }) {
    const list = this.prune(key, now);
    const used = list.reduce((sum, event) => sum + event.fields, 0);
    const remaining = Math.max(0, this.budgetFields - used);
    if (fieldCount > remaining) {
      return { allowed: false, key, used, remaining, requested: fieldCount };
    }
    if (commit) {
      list.push({ t: now, fields: fieldCount });
      this.events.set(key, list);
    }
    return { allowed: true, key, used: used + fieldCount, remaining: remaining - fieldCount, requested: fieldCount };
  }
}

function htmlForPage(record) {
  const rows = Object.entries(record.placeholders)
    .map(
      ([field, value]) =>
        `<div class="meta-row"><span class="label">${field}</span><span class="value" data-k="${field}">${value}</span></div>`,
    )
    .join("\n");
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>${publicRecord.title} ${record.id}</title>
  <style>
    body { font: 16px Arial, sans-serif; margin: 32px; line-height: 1.5; }
    main { max-width: 760px; }
    .meta-row { display: grid; grid-template-columns: 150px 1fr; gap: 12px; min-height: 24px; }
    .label { font-weight: 700; }
  </style>
</head>
<body>
  <main>
    <h1>${publicRecord.title}</h1>
    <p>${publicRecord.summary}</p>
    <section class="details" data-page="${record.id}" tabindex="0">
      ${rows}
    </section>
  </main>
  <script>
    let pending = false;
    async function reveal() {
      if (pending) return;
      pending = true;
      const res = await fetch("/reveal", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ page: document.querySelector(".details").dataset.page })
      });
      if (res.ok) {
        const data = await res.json();
        for (const [field, value] of Object.entries(data.fields || {})) {
          const node = document.querySelector('[data-k="' + field + '"]');
          if (node) node.textContent = value;
        }
      }
      pending = false;
    }
    document.querySelector(".details").addEventListener("click", reveal);
    document.querySelector(".details").addEventListener("focusin", reveal);
  </script>
</body>
</html>`;
}

function identityFromRequest(req) {
  const cookie = req.headers.cookie || "";
  const session = /(?:^|;\s*)sid=([^;]+)/.exec(cookie)?.[1] || req.headers["x-session-id"] || "anon";
  const ip = req.headers["x-forwarded-for"] || req.socket.remoteAddress || "127.0.0.1";
  return { session: String(session), ip: String(ip).split(",")[0].trim() };
}

function startServer({ keyMode }) {
  const budget = new RevealBudget({ budgetFields: BUDGET_FIELDS, windowMs: WINDOW_MS, keyMode });
  const requestLog = [];
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, "http://localhost");
    const identity = identityFromRequest(req);
    if (url.pathname.startsWith("/page/")) {
      const id = url.pathname.split("/").pop();
      const record = pages.find((page) => page.id === id);
      if (!record) {
        res.writeHead(404);
        res.end("not found");
        return;
      }
      const body = htmlForPage(record);
      res.writeHead(200, {
        "content-type": "text/html; charset=utf-8",
        "set-cookie": `sid=${identity.session}; Path=/; SameSite=Lax`,
        "cache-control": "no-store",
      });
      res.end(body);
      return;
    }
    if (url.pathname === "/reveal" && req.method === "POST") {
      let raw = "";
      req.setEncoding("utf8");
      for await (const chunk of req) raw += chunk;
      const body = raw ? JSON.parse(raw) : {};
      const record = pages.find((page) => page.id === body.page);
      if (!record) {
        res.writeHead(404, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: "unknown page" }));
        return;
      }
      const now = Date.now();
      const decision = budget.tryReveal({
        ...identity,
        fieldCount: Object.keys(record.fields).length,
        now,
      });
      requestLog.push({ t: now, identity, page: record.id, decision });
      if (!decision.allowed) {
        res.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" });
        res.end(JSON.stringify({ allowed: false, fields: {}, placeholderOnly: true, decision }));
        return;
      }
      res.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" });
      res.end(JSON.stringify({ allowed: true, fields: record.fields, decision }));
      return;
    }
    if (url.pathname === "/_log") {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify(requestLog));
      return;
    }
    res.writeHead(404);
    res.end("not found");
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve({ server, budget, baseUrl: `http://127.0.0.1:${server.address().port}` }));
  });
}

async function reveal(baseUrl, { pageId, session, ip }) {
  const started = performance.now();
  const response = await fetch(`${baseUrl}/reveal`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "cookie": `sid=${session}`,
      "x-session-id": session,
      "x-forwarded-for": ip,
    },
    body: JSON.stringify({ page: pageId }),
  });
  const data = await response.json();
  return {
    pageId,
    session,
    ip,
    status: response.status,
    allowed: !!data.allowed,
    fieldsReturned: Object.keys(data.fields || {}).length,
    ms: Number((performance.now() - started).toFixed(3)),
    remaining: data.decision?.remaining ?? null,
    used: data.decision?.used ?? null,
  };
}

async function runScenario({ keyMode, scenario }) {
  const { server, baseUrl } = await startServer({ keyMode });
  const rows = [];
  try {
    if (scenario === "singleSequential") {
      for (const page of pages) rows.push(await reveal(baseUrl, { pageId: page.id, session: "s1", ip: "10.0.0.1" }));
    }
    if (scenario === "singleParallel") {
      rows.push(
        ...(await Promise.all(pages.map((page) => reveal(baseUrl, { pageId: page.id, session: "s1", ip: "10.0.0.1" })))),
      );
    }
    if (scenario === "rotatingSessionSameIp") {
      for (let i = 0; i < pages.length; i += 1) {
        rows.push(await reveal(baseUrl, { pageId: pages[i].id, session: `s${i + 1}`, ip: "10.0.0.1" }));
      }
    }
    if (scenario === "rotatingIpSameSession") {
      for (let i = 0; i < pages.length; i += 1) {
        rows.push(await reveal(baseUrl, { pageId: pages[i].id, session: "s1", ip: `10.0.0.${i + 1}` }));
      }
    }
    if (scenario === "rotatingBoth") {
      for (let i = 0; i < pages.length; i += 1) {
        rows.push(await reveal(baseUrl, { pageId: pages[i].id, session: `s${i + 1}`, ip: `10.0.0.${i + 1}` }));
      }
    }
    if (scenario === "normalSparse") {
      const sparsePages = pages.slice(0, 3);
      for (const page of sparsePages) rows.push(await reveal(baseUrl, { pageId: page.id, session: "human1", ip: "10.0.0.9" }));
    }
  } finally {
    server.close();
  }
  return { keyMode, scenario, rows, summary: summarizeRows(rows) };
}

function summarizeRows(rows) {
  const allowed = rows.filter((row) => row.allowed);
  const blocked = rows.filter((row) => !row.allowed);
  const revealedFields = allowed.reduce((sum, row) => sum + row.fieldsReturned, 0);
  const firstBlockedIndex = rows.findIndex((row) => !row.allowed);
  return {
    attempts: rows.length,
    allowedAttempts: allowed.length,
    blockedAttempts: blocked.length,
    allowedRate: Number((allowed.length / rows.length).toFixed(4)),
    revealedFields,
    requestedFields: rows.length * FIELD_COUNT,
    revealedFieldRate: Number((revealedFields / (rows.length * FIELD_COUNT)).toFixed(4)),
    pagesUntilFirstBlock: firstBlockedIndex < 0 ? null : firstBlockedIndex,
    medianRevealMs: median(rows.map((row) => row.ms)),
  };
}

function median(values) {
  const sorted = values.slice().sort((a, b) => a - b);
  return Number((sorted[Math.floor((sorted.length - 1) / 2)] || 0).toFixed(3));
}

function sourceLeakAudit() {
  const html = htmlForPage(pages[0]);
  const expectedValues = Object.values(pages[0].fields);
  const leaked = expectedValues.filter((value) => html.includes(value));
  return {
    htmlContainsSensitiveValues: leaked.length,
    htmlContainsPlaceholders: Object.values(pages[0].placeholders).filter((value) => html.includes(value)).length,
    revealEndpointMentioned: html.includes("/reveal"),
    note: "This budget-layer prototype moves plaintext sensitive values to the server-side reveal endpoint. It protects source text but introduces an endpoint that must be authenticated/rate-limited in production.",
  };
}

async function main() {
  const keyModes = ["session", "ip", "sessionIp", "dual"];
  const scenarios = [
    "singleSequential",
    "singleParallel",
    "rotatingSessionSameIp",
    "rotatingIpSameSession",
    "rotatingBoth",
    "normalSparse",
  ];
  const results = [];
  for (const keyMode of keyModes) {
    for (const scenario of scenarios) {
      results.push(await runScenario({ keyMode, scenario }));
    }
  }
  const report = {
    generatedAt: new Date().toISOString(),
    config: {
      pageCount: PAGE_COUNT,
      fieldCount: FIELD_COUNT,
      budgetFields: BUDGET_FIELDS,
      windowMs: WINDOW_MS,
    },
    sourceLeakAudit: sourceLeakAudit(),
    results,
    matrix: Object.fromEntries(results.map((result) => [`${result.keyMode}:${result.scenario}`, result.summary])),
    interpretation: {
      session:
        "Session-only budgets stop a single cookie identity but are bypassed by rotating sessions on the same IP.",
      ip: "IP-only budgets stop session rotation but are bypassed by rotating IPs and can affect shared NAT/proxy users.",
      sessionIp:
        "A single combined session|IP key is bypassed by rotating either component, so it is weaker than independent budgets for adversarial rotation.",
      dual:
        "Independent session and IP budgets must both allow the reveal. This stops session-only and IP-only rotation, but not simultaneous rotation of both identities.",
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
