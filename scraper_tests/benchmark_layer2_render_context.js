const fs = require("node:fs");
const { performance } = require("node:perf_hooks");
const zlib = require("node:zlib");

const { chromium } = require("playwright");
const { buildHtml, fieldSet } = require("./benchmark_sensitive_field_template");

const outArg = process.argv.includes("--out") ? process.argv[process.argv.indexOf("--out") + 1] : null;
const ITERATIONS = Number(process.env.ITERATIONS || 5);

const renderGuards = ["none", "simple", "quorum"];
const layouts = ["compact", "below-fold"];
const actions = ["noInteraction", "eventNoScroll", "scrollOnly", "scrollThenEvent", "locatorClick"];

function byteStats(text) {
  return {
    rawBytes: Buffer.byteLength(text, "utf8"),
    gzipBytes: zlib.gzipSync(text).length,
  };
}

function sourceFingerprint(html) {
  return {
    ...byteStats(html),
    getComputedStyle: (html.match(/getComputedStyle/g) || []).length,
    getBoundingClientRect: (html.match(/getBoundingClientRect/g) || []).length,
    elementFromPoint: (html.match(/elementFromPoint/g) || []).length,
    requestAnimationFrame: (html.match(/requestAnimationFrame/g) || []).length,
    fontsReady: (html.match(/document\.fonts|fonts\.ready/g) || []).length,
    ariaLive: (html.match(/aria-live/g) || []).length,
  };
}

function makeCases() {
  return layouts.flatMap((layoutVariant) =>
    renderGuards.map((renderGuard) => {
      const html = buildHtml({
        gated: true,
        placeholder: true,
        interactionGate: true,
        layoutVariant,
        liveRegionMode: "section",
        renderGuard,
      });
      return {
        id: `${layoutVariant}:${renderGuard}`,
        layoutVariant,
        renderGuard,
        html,
        expected: fieldSet().values,
        fingerprint: sourceFingerprint(html),
      };
    }),
  );
}

async function applyAction(page, action) {
  if (action === "noInteraction") return;
  if (action === "eventNoScroll") {
    await page.evaluate(() => {
      const section = document.querySelector(".details");
      if (!section) return;
      section.dispatchEvent(new PointerEvent("pointerenter", { bubbles: true, pointerType: "mouse" }));
      section.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
    });
    return;
  }
  if (action === "scrollOnly") {
    await page.evaluate(() => document.querySelector(".details")?.scrollIntoView({ block: "center" }));
    return;
  }
  if (action === "scrollThenEvent") {
    await page.evaluate(() => document.querySelector(".details")?.scrollIntoView({ block: "center" }));
    await page.waitForTimeout(30);
    await page.evaluate(() => {
      const section = document.querySelector(".details");
      if (!section) return;
      section.dispatchEvent(new PointerEvent("pointerenter", { bubbles: true, pointerType: "mouse" }));
      section.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
    });
    return;
  }
  if (action === "locatorClick") {
    await page.locator(".details").click({ timeout: 2000 });
  }
}

async function measure(browser, testCase, action) {
  const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
  const started = performance.now();
  await page.setContent(testCase.html, { waitUntil: "load" });
  const loadMs = performance.now() - started;
  const before = await classifyPage(page, testCase.expected);
  const actionStart = performance.now();
  let actionError = null;
  try {
    await applyAction(page, action);
  } catch (error) {
    actionError = String(error.message || error);
  }
  await page.waitForTimeout(120);
  const actionMs = performance.now() - actionStart;
  const after = await classifyPage(page, testCase.expected);
  const diagnostics = await page.evaluate(() => {
    const section = document.querySelector(".details");
    const rect = section?.getBoundingClientRect();
    const center = rect
      ? {
          x: rect.left + rect.width / 2,
          y: rect.top + Math.min(rect.height / 2, 24),
        }
      : null;
    const top = center ? document.elementFromPoint(center.x, center.y) : null;
    return {
      scrollY: window.scrollY,
      rect: rect
        ? {
            top: Number(rect.top.toFixed(2)),
            left: Number(rect.left.toFixed(2)),
            width: Number(rect.width.toFixed(2)),
            height: Number(rect.height.toFixed(2)),
          }
        : null,
      centerInViewport: center
        ? center.x >= 0 && center.y >= 0 && center.x <= window.innerWidth && center.y <= window.innerHeight
        : false,
      hitInsideSection: !!(top && section && (top === section || section.contains(top))),
      statusText: document.querySelector("[data-status]")?.textContent || null,
    };
  });
  await page.close();
  return {
    layoutVariant: testCase.layoutVariant,
    renderGuard: testCase.renderGuard,
    action,
    loadMs: Number(loadMs.toFixed(3)),
    actionMs: Number(actionMs.toFixed(3)),
    actionError,
    before,
    after,
    diagnostics,
  };
}

async function classifyPage(page, expected) {
  return page.evaluate((expectedValues) => {
    const text = document.body.innerText || "";
    const values = Object.values(expectedValues);
    const sensitiveFound = values.filter((value) => text.includes(value));
    const placeholders = [
      "Available on request",
      "Contact team",
      "Restricted",
      "Access required",
      "Not publicly listed",
    ].filter((value) => text.includes(value));
    return {
      sensitiveFound: sensitiveFound.length,
      sensitiveTotal: values.length,
      placeholderFound: placeholders.length,
      leakedValues: sensitiveFound,
    };
  }, expected);
}

function summarize(rows) {
  const byLayoutGuardAction = {};
  for (const row of rows) {
    const key = `${row.layoutVariant}:${row.renderGuard}:${row.action}`;
    byLayoutGuardAction[key] ||= {
      runs: 0,
      leaks: 0,
      fullLeaks: 0,
      actionErrors: 0,
      loadMs: [],
      actionMs: [],
    };
    const bucket = byLayoutGuardAction[key];
    bucket.runs += 1;
    if (row.after.sensitiveFound > 0) bucket.leaks += 1;
    if (row.after.sensitiveFound === row.after.sensitiveTotal) bucket.fullLeaks += 1;
    if (row.actionError) bucket.actionErrors += 1;
    bucket.loadMs.push(row.loadMs);
    bucket.actionMs.push(row.actionMs);
  }
  for (const bucket of Object.values(byLayoutGuardAction)) {
    bucket.leakRate = Number((bucket.leaks / bucket.runs).toFixed(4));
    bucket.fullLeakRate = Number((bucket.fullLeaks / bucket.runs).toFixed(4));
    bucket.medianLoadMs = median(bucket.loadMs);
    bucket.medianActionMs = median(bucket.actionMs);
    delete bucket.loadMs;
    delete bucket.actionMs;
  }
  return { byLayoutGuardAction };
}

function median(values) {
  const sorted = values.slice().sort((a, b) => a - b);
  return Number((sorted[Math.floor((sorted.length - 1) / 2)] || 0).toFixed(3));
}

async function main() {
  const cases = makeCases();
  const browser = await chromium.launch({ headless: true });
  const rows = [];
  try {
    for (const testCase of cases) {
      for (const action of actions) {
        for (let iteration = 0; iteration < ITERATIONS; iteration += 1) {
          rows.push({ iteration, ...(await measure(browser, testCase, action)) });
        }
      }
    }
  } finally {
    await browser.close();
  }

  const report = {
    generatedAt: new Date().toISOString(),
    iterations: ITERATIONS,
    renderGuards,
    layouts,
    actions,
    fingerprints: Object.fromEntries(cases.map((testCase) => [testCase.id, testCase.fingerprint])),
    summary: summarize(rows),
    rawRows: rows,
    interpretation: {
      none: "No layer-2 render-context attestation; any interaction event can reveal values.",
      simple: "Checks basic rect/style readiness. This binds hydration to DOM layout existence but not viewport hit-testing.",
      quorum:
        "Checks rect/style, font readiness, two-frame layout stability, viewport position, and elementFromPoint hit-test before hydration.",
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
