const fs = require("node:fs");
const { performance } = require("node:perf_hooks");
let chromium;
try {
  ({ chromium } = require("playwright"));
} catch (error) {
  ({ chromium } = require("C:/Users/jungseobum/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright"));
}
const { buildHtml, fieldSet } = require("./benchmark_sensitive_field_template");

const outArg = process.argv.includes("--out") ? process.argv[process.argv.indexOf("--out") + 1] : null;
const iterations = Number(process.env.ITERATIONS || 3);
const fieldCount = Number(process.env.FIELD_COUNT || 5);
const dwellMs = Number(process.env.DWELL_MS || 650);
const chromePath = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";

const scenarios = [
  "noInteraction",
  "pointerenterOnly",
  "clickOnly",
  "hoverThenImmediateClick",
  "hoverDwellClick",
  "normalMouseUser",
  "keyboardImmediate",
  "keyboardDwell",
  "normalKeyboardUser",
  "bruteForceDispatchAll",
  "bruteForceDwellAll",
];

const expectedPass = new Set(["hoverDwellClick", "normalMouseUser", "keyboardDwell", "normalKeyboardUser"]);

function normalize(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function score(extracted, expectedValues) {
  const statuses = {};
  let exact = 0;
  let placeholder = 0;
  let missing = 0;
  let wrong = 0;

  for (const [field, expected] of Object.entries(expectedValues)) {
    const actual = normalize(extracted[field]);
    if (!actual) {
      statuses[field] = "missing";
      missing += 1;
    } else if (actual === expected) {
      statuses[field] = "exact";
      exact += 1;
    } else if (/available|contact team|restricted|access required|not publicly listed/i.test(actual)) {
      statuses[field] = "placeholder";
      placeholder += 1;
    } else {
      statuses[field] = "wrong";
      wrong += 1;
    }
  }

  const fields = Object.keys(expectedValues).length;
  return {
    fields,
    exact,
    placeholder,
    missing,
    wrong,
    leakageRate: Number((exact / fields).toFixed(4)),
    safeFailureRate: Number(((placeholder + missing) / fields).toFixed(4)),
    statuses,
  };
}

async function extract(page) {
  return page.locator(".value").evaluateAll((nodes) =>
    Object.fromEntries(nodes.map((node) => [node.dataset.k, node.textContent.trim()])),
  );
}

async function moveInsideSection(page) {
  const box = await page.locator(".details").boundingBox();
  if (!box) return;
  await page.mouse.move(box.x + 20, box.y + 20);
  await page.mouse.move(box.x + 80, box.y + 26);
  await page.mouse.move(box.x + 140, box.y + 32);
}

async function runScenario(page, scenario) {
  const stats = { events: 0, attemptedElements: 0 };
  const section = page.locator(".details");

  if (scenario === "noInteraction") return stats;

  if (scenario === "pointerenterOnly") {
    await section.dispatchEvent("pointerenter", { bubbles: true, clientX: 100, clientY: 100, pointerType: "mouse" });
    stats.events += 1;
    return stats;
  }

  if (scenario === "clickOnly") {
    await section.click({ force: true });
    stats.events += 1;
    return stats;
  }

  if (scenario === "hoverThenImmediateClick") {
    await section.hover({ force: true });
    await moveInsideSection(page);
    await section.click({ force: true });
    stats.events += 5;
    return stats;
  }

  if (scenario === "hoverDwellClick") {
    await section.hover({ force: true });
    await moveInsideSection(page);
    await page.waitForTimeout(dwellMs);
    await section.click({ force: true });
    stats.events += 5;
    return stats;
  }

  if (scenario === "normalMouseUser") {
    const box = await section.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + 18, { steps: 8 });
    await page.waitForTimeout(dwellMs);
    await page.mouse.move(box.x + box.width / 2 + 32, box.y + 24, { steps: 4 });
    await page.mouse.click(box.x + box.width / 2 + 32, box.y + 24);
    stats.events += 14;
    return stats;
  }

  if (scenario === "keyboardImmediate") {
    await section.focus();
    await page.keyboard.press("Enter");
    stats.events += 2;
    return stats;
  }

  if (scenario === "keyboardDwell") {
    await section.focus();
    await page.waitForTimeout(dwellMs);
    await page.keyboard.press("Enter");
    stats.events += 2;
    return stats;
  }

  if (scenario === "normalKeyboardUser") {
    await page.keyboard.press("Tab");
    await page.waitForTimeout(dwellMs);
    await page.keyboard.press("Enter");
    stats.events += 2;
    return stats;
  }

  if (scenario === "bruteForceDispatchAll") {
    const result = await page.evaluate(async () => {
      let events = 0;
      let attemptedElements = 0;
      for (const element of [...document.querySelectorAll("body *")]) {
        const rect = element.getBoundingClientRect();
        const clientX = Math.max(1, Math.round(rect.left + Math.min(10, Math.max(1, rect.width / 2))));
        const clientY = Math.max(1, Math.round(rect.top + Math.min(10, Math.max(1, rect.height / 2))));
        element.dispatchEvent(new PointerEvent("pointerenter", { bubbles: true, clientX, clientY, pointerType: "mouse" }));
        element.dispatchEvent(new PointerEvent("pointermove", { bubbles: true, clientX: clientX + 3, clientY: clientY + 1, pointerType: "mouse" }));
        element.dispatchEvent(new PointerEvent("pointermove", { bubbles: true, clientX: clientX + 6, clientY: clientY + 2, pointerType: "mouse" }));
        element.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: clientX + 6, clientY: clientY + 2 }));
        attemptedElements += 1;
        events += 4;
        await new Promise((resolve) => requestAnimationFrame(resolve));
      }
      return { events, attemptedElements };
    });
    Object.assign(stats, result);
    return stats;
  }

  if (scenario === "bruteForceDwellAll") {
    const result = await page.evaluate(async (waitMs) => {
      let events = 0;
      let attemptedElements = 0;
      for (const element of [...document.querySelectorAll("body *")]) {
        const rect = element.getBoundingClientRect();
        const clientX = Math.max(1, Math.round(rect.left + Math.min(10, Math.max(1, rect.width / 2))));
        const clientY = Math.max(1, Math.round(rect.top + Math.min(10, Math.max(1, rect.height / 2))));
        element.dispatchEvent(new PointerEvent("pointerenter", { bubbles: true, clientX, clientY, pointerType: "mouse" }));
        element.dispatchEvent(new PointerEvent("pointermove", { bubbles: true, clientX: clientX + 3, clientY: clientY + 1, pointerType: "mouse" }));
        element.dispatchEvent(new PointerEvent("pointermove", { bubbles: true, clientX: clientX + 6, clientY: clientY + 2, pointerType: "mouse" }));
        await new Promise((resolve) => setTimeout(resolve, waitMs));
        element.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: clientX + 6, clientY: clientY + 2 }));
        attemptedElements += 1;
        events += 4;
        await new Promise((resolve) => requestAnimationFrame(resolve));
      }
      return { events, attemptedElements };
    }, dwellMs);
    Object.assign(stats, result);
    return stats;
  }

  throw new Error(`Unknown scenario: ${scenario}`);
}

function percentile(values, pct) {
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((pct / 100) * sorted.length) - 1));
  return Number(sorted[index].toFixed(3));
}

function summarize(values) {
  return { p50: percentile(values, 50), p95: percentile(values, 95), max: percentile(values, 100) };
}

function classifyOutcome({ scenario, leakageRate }) {
  const shouldPass = expectedPass.has(scenario);
  if (shouldPass && leakageRate === 1) return "intended-pass";
  if (shouldPass && leakageRate < 1) return "false-negative";
  if (!shouldPass && leakageRate === 0) return "blocked";
  return "bypass";
}

async function measure({ mode, scenario }) {
  const active = fieldSet({ fieldCount });
  const html = buildHtml({
    gated: true,
    placeholder: true,
    interactionGate: true,
    interactionGateMode: mode,
    fieldCount,
    liveRegionMode: "section",
  });
  const rows = [];

  for (let i = 0; i < iterations; i += 1) {
    const browser = await chromium.launch({ headless: true, executablePath: chromePath });
    const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
    await page.setContent(html, { waitUntil: "load" });
    await page.waitForTimeout(50);
    const started = performance.now();
    const stats = await runScenario(page, scenario);
    await page.waitForTimeout(30);
    const interactionMs = performance.now() - started;
    const extracted = await extract(page);
    await browser.close();
    rows.push({
      score: score(extracted, active.values),
      events: stats.events,
      attemptedElements: stats.attemptedElements,
      interactionMs: Number(interactionMs.toFixed(3)),
    });
  }

  return {
    mode,
    scenario,
    expectedPass: expectedPass.has(scenario),
    outcome: classifyOutcome({ scenario, leakageRate: rows[0].score.leakageRate }),
    score: rows[0].score,
    leakageRateAcrossRuns: summarize(rows.map((row) => row.score.leakageRate)),
    exactAcrossRuns: summarize(rows.map((row) => row.score.exact)),
    outcomeCounts: rows.reduce((counts, row) => {
      const outcome = classifyOutcome({ scenario, leakageRate: row.score.leakageRate });
      counts[outcome] = (counts[outcome] || 0) + 1;
      return counts;
    }, {}),
    events: rows[0].events,
    attemptedElements: rows[0].attemptedElements,
    interactionMs: summarize(rows.map((row) => row.interactionMs)),
  };
}

async function main() {
  const results = [];
  for (const mode of ["simple", "sequence"]) {
    for (const scenario of scenarios) {
      console.error(`[${mode}] ${scenario}`);
      results.push(await measure({ mode, scenario }));
    }
  }

  const report = {
    generatedAt: new Date().toISOString(),
    config: { iterations, fieldCount, dwellMs },
    results,
    byMode: Object.fromEntries(
      ["simple", "sequence"].map((mode) => [
        mode,
        Object.fromEntries(results.filter((row) => row.mode === mode).map((row) => [row.scenario, row.score])),
      ]),
    ),
  };

  const output = JSON.stringify(report, null, 2);
  if (outArg) fs.writeFileSync(outArg, `${output}\n`, "utf8");
  console.log(output);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
