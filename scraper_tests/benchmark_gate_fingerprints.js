const zlib = require("node:zlib");
const { performance } = require("node:perf_hooks");

const { chromium } = require("playwright");
const { buildHtml: buildPureHtml } = require("./evaluate_llm_pure_gap_scale");
const { buildHtml: buildInteractionHtml } = require("./benchmark_interaction_gate");

const variants = {
  stable: () => buildPureHtml("stable", "fingerprint"),
  fontMetricPure: () => buildPureHtml("fontMetricPure", "fingerprint"),
  selfRefPure: () => buildPureHtml("selfRefPure", "fingerprint"),
  interactionGate: () => buildInteractionHtml(),
};

const suspiciousPatterns = {
  measureText: /measureText\s*\(/g,
  getBoundingClientRect: /getBoundingClientRect\s*\(/g,
  devicePixelRatio: /devicePixelRatio/g,
  scrollListener: /addEventListener\s*\(\s*["']scroll/g,
  pointerListener: /pointerenter|pointerover|mousemove|mouseenter/g,
  focusListener: /addEventListener\s*\(\s*["']focus/g,
  encodedPayload: /<script[^>]+type=["']application\/json["'][^>]*>/g,
  xorOperator: /\^/g,
  fromCharCode: /fromCharCode/g,
  emptySlot: /class=["'][^"']*\bslot\b[^"']*["'][^>]*>\s*<\/span>/g,
};

function countMatches(html, pattern) {
  return (html.match(pattern) || []).length;
}

function entropy(text) {
  const counts = new Map();
  for (const char of text) counts.set(char, (counts.get(char) || 0) + 1);
  let value = 0;
  for (const count of counts.values()) {
    const p = count / text.length;
    value -= p * Math.log2(p);
  }
  return Number(value.toFixed(4));
}

function sourceFingerprint(html) {
  const rawBytes = Buffer.byteLength(html, "utf8");
  const gzipBytes = zlib.gzipSync(html).length;
  const numberMatches = html.match(/-?\d+(?:\.\d+)?/g) || [];
  const inlineScriptBytes = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].reduce(
    (sum, match) => sum + Buffer.byteLength(match[1] || "", "utf8"),
    0,
  );
  const patternCounts = Object.fromEntries(
    Object.entries(suspiciousPatterns).map(([name, pattern]) => [name, countMatches(html, pattern)]),
  );
  const suspiciousApiCount = Object.entries(patternCounts)
    .filter(([name]) => !["encodedPayload", "emptySlot"].includes(name))
    .reduce((sum, [, count]) => sum + count, 0);

  return {
    rawBytes,
    gzipBytes,
    compressionRatio: Number((gzipBytes / rawBytes).toFixed(4)),
    inlineScriptBytes,
    inlineScriptRatio: Number((inlineScriptBytes / rawBytes).toFixed(4)),
    numberTokenCount: numberMatches.length,
    numberTokenDensityPerKb: Number((numberMatches.length / (rawBytes / 1024)).toFixed(2)),
    entropyBitsPerChar: entropy(html),
    patternCounts,
    suspiciousApiCount,
    sourceFingerprintScore:
      suspiciousApiCount +
      patternCounts.encodedPayload * 3 +
      patternCounts.emptySlot * 0.25 +
      Math.min(20, Math.round(numberMatches.length / 50)) +
      Math.min(20, Math.round(inlineScriptBytes / 1000)),
  };
}

function instrument(html) {
  const script = `<script>
    window.__fp = { mutations: 0, cls: 0, longTasks: 0, longTaskMs: 0, startedAt: performance.now() };
    new MutationObserver((records) => { window.__fp.mutations += records.length; })
      .observe(document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true });
    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (!entry.hadRecentInput) window.__fp.cls += entry.value || 0;
        }
      }).observe({ type: "layout-shift", buffered: true });
    } catch {}
    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          window.__fp.longTasks += 1;
          window.__fp.longTaskMs += entry.duration || 0;
        }
      }).observe({ type: "longtask", buffered: true });
    } catch {}
  </script>`;
  return html.replace(/<head>/i, `<head>${script}`);
}

async function waitForTextCompletion(page, timeoutMs = 1000) {
  const start = performance.now();
  let emptySlots = 0;
  let totalSlots = 0;
  while (performance.now() - start < timeoutMs) {
    const state = await page.evaluate(() => {
      const slots = [...document.querySelectorAll(".slot")];
      return {
        totalSlots: slots.length,
        emptySlots: slots.filter((slot) => !slot.textContent.trim()).length,
      };
    });
    emptySlots = state.emptySlots;
    totalSlots = state.totalSlots;
    if (totalSlots === 0 || emptySlots === 0) {
      return {
        totalSlots,
        emptySlots,
        completed: true,
        timeToTextCompleteMs: Number((performance.now() - start).toFixed(3)),
      };
    }
    await page.waitForTimeout(10);
  }
  return {
    totalSlots,
    emptySlots,
    completed: false,
    timeToTextCompleteMs: timeoutMs,
  };
}

async function renderFingerprint(html) {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
  const start = performance.now();
  await page.setContent(instrument(html), { waitUntil: "load" });
  const loadMs = performance.now() - start;
  const textState = await waitForTextCompletion(page);
  await page.waitForTimeout(50);
  const runtime = await page.evaluate(() => ({
    mutations: window.__fp?.mutations || 0,
    cumulativeLayoutShift: Number((window.__fp?.cls || 0).toFixed(6)),
    longTasks: window.__fp?.longTasks || 0,
    longTaskMs: Number((window.__fp?.longTaskMs || 0).toFixed(3)),
    bodyTextLength: document.body.innerText.length,
    emptyTextNodes: [...document.querySelectorAll(".slot")].filter((slot) => !slot.textContent.trim()).length,
    nodeCount: document.querySelectorAll("*").length,
    scriptCount: document.scripts.length,
  }));
  await browser.close();
  return {
    loadMs: Number(loadMs.toFixed(3)),
    ...textState,
    ...runtime,
    renderFingerprintScore:
      (textState.completed ? 0 : 20) +
      Math.min(20, textState.emptySlots) +
      Math.min(20, Math.round(runtime.mutations / 25)) +
      Math.min(20, Math.round(runtime.longTaskMs / 10)) +
      (runtime.cumulativeLayoutShift > 0.01 ? 10 : 0),
  };
}

async function main() {
  const results = {};
  for (const [name, build] of Object.entries(variants)) {
    const html = build();
    results[name] = {
      source: sourceFingerprint(html),
      render: await renderFingerprint(html),
    };
  }
  console.log(JSON.stringify({ variants: Object.keys(variants), results }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
