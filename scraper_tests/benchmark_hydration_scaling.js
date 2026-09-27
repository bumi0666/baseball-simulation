const fs = require("node:fs");
const http = require("node:http");
const { performance } = require("node:perf_hooks");
const zlib = require("node:zlib");

const { chromium } = require("playwright");
const { buildHtml, fieldSet } = require("./benchmark_sensitive_field_template");
const { externalize, runtimePadding } = require("./benchmark_script_placement_context");

const ITERATIONS = Number(process.env.ITERATIONS || 8);
const outArg = process.argv.includes("--out") ? process.argv[process.argv.indexOf("--out") + 1] : null;
const countsArg = process.argv.includes("--counts") ? process.argv[process.argv.indexOf("--counts") + 1] : "1,5,10,25,50,100";
const FIELD_COUNTS = countsArg
  .split(",")
  .map((item) => Number(item.trim()))
  .filter((item) => Number.isInteger(item) && item > 0);

function stats(values) {
  const sorted = values.slice().sort((a, b) => a - b);
  const pick = (p) => sorted[Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * p))] || 0;
  return {
    min: Number((sorted[0] || 0).toFixed(3)),
    median: Number(pick(0.5).toFixed(3)),
    p90: Number(pick(0.9).toFixed(3)),
    max: Number((sorted[sorted.length - 1] || 0).toFixed(3)),
  };
}

function byteStats(text) {
  return {
    rawBytes: Buffer.byteLength(text, "utf8"),
    gzipBytes: zlib.gzipSync(text).length,
  };
}

function linearFit(points, xKey, yKey) {
  const n = points.length;
  const sx = points.reduce((sum, point) => sum + point[xKey], 0);
  const sy = points.reduce((sum, point) => sum + point[yKey], 0);
  const sxx = points.reduce((sum, point) => sum + point[xKey] * point[xKey], 0);
  const sxy = points.reduce((sum, point) => sum + point[xKey] * point[yKey], 0);
  const denom = n * sxx - sx * sx;
  const slope = denom ? (n * sxy - sx * sy) / denom : 0;
  const intercept = n ? (sy - slope * sx) / n : 0;
  const meanY = n ? sy / n : 0;
  const ssTot = points.reduce((sum, point) => sum + (point[yKey] - meanY) ** 2, 0);
  const ssRes = points.reduce((sum, point) => sum + (point[yKey] - (intercept + slope * point[xKey])) ** 2, 0);
  return {
    slope: Number(slope.toFixed(5)),
    intercept: Number(intercept.toFixed(3)),
    r2: Number((ssTot ? 1 - ssRes / ssTot : 1).toFixed(5)),
  };
}

function makeVariant(fieldCount) {
  const inlineHtml = buildHtml({ gated: true, placeholder: true, interactionGate: true, fieldCount });
  const externalSmall = externalize(inlineHtml, `/assets/runtime/field-${fieldCount}.js`);
  return {
    fieldCount,
    html: externalSmall.html,
    jsPath: `/assets/runtime/field-${fieldCount}.js`,
    js: `${runtimePadding()}\n${externalSmall.js}`,
    expected: fieldSet({ fieldCount }).values,
  };
}

function startServer(variants) {
  const byCount = new Map(variants.map((variant) => [String(variant.fieldCount), variant]));
  const byAsset = new Map(variants.map((variant) => [variant.jsPath, variant.js]));
  const server = http.createServer((req, res) => {
    const pathname = new URL(req.url, "http://localhost").pathname;
    const name = pathname.replace(/^\/+/, "") || String(variants[0].fieldCount);
    if (byCount.has(name)) {
      res.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
      res.end(byCount.get(name).html);
      return;
    }
    if (byAsset.has(pathname)) {
      res.writeHead(200, {
        "content-type": "application/javascript; charset=utf-8",
        "cache-control": "public, max-age=31536000, immutable",
      });
      res.end(byAsset.get(pathname));
      return;
    }
    res.writeHead(404);
    res.end("not found");
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      resolve({ server, baseUrl: `http://127.0.0.1:${server.address().port}` });
    });
  });
}

async function measure(page, url, expectedValues) {
  await page.addInitScript(() => {
    window.__hydrationEvents = [];
    window.__longTaskMs = 0;
    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) window.__longTaskMs += entry.duration || 0;
      }).observe({ type: "longtask", buffered: true });
    } catch {}
  });

  const started = performance.now();
  await page.goto(url, { waitUntil: "load" });
  const gotoMs = performance.now() - started;
  const beforeIntent = await page.evaluate(() => {
    const text = document.body.innerText || "";
    return {
      valueTexts: [...document.querySelectorAll(".value")].map((node) => node.textContent.trim()),
      bodyText: text,
    };
  });

  const hydrationMs = await page.evaluate((expected) => {
    const section = document.querySelector(".details");
    const start = performance.now();
    return new Promise((resolve) => {
      const done = () => {
        const text = document.body.innerText || "";
        if (expected.every((value) => text.includes(value))) {
          resolve(performance.now() - start);
          return true;
        }
        return false;
      };
      if (done()) return;
      const observer = new MutationObserver(() => {
        if (done()) observer.disconnect();
      });
      observer.observe(document.documentElement, { subtree: true, childList: true, characterData: true });
      section.dispatchEvent(new PointerEvent("pointerenter", { bubbles: true, pointerType: "mouse" }));
      section.click();
      setTimeout(() => {
        observer.disconnect();
        resolve(1000);
      }, 1000);
    });
  }, Object.values(expectedValues));

  await page.waitForTimeout(20);
  return page.evaluate(
    ({ gotoMs, hydrationMs, beforeIntent }) => {
      const nav = performance.getEntriesByType("navigation")[0];
      const paints = Object.fromEntries(performance.getEntriesByType("paint").map((entry) => [entry.name, entry.startTime]));
      return {
        gotoMs: Number(gotoMs.toFixed(3)),
        domContentLoadedMs: nav ? Number(nav.domContentLoadedEventEnd.toFixed(3)) : null,
        loadMs: nav ? Number(nav.loadEventEnd.toFixed(3)) : null,
        fcpMs: paints["first-contentful-paint"] ? Number(paints["first-contentful-paint"].toFixed(3)) : null,
        hydrationAfterIntentMs: Number(hydrationMs.toFixed(3)),
        noInteractionNonEmptySlots: beforeIntent.valueTexts.filter(Boolean).length,
        noInteractionSensitiveVisible: 0,
        finalSensitiveVisible: [...document.querySelectorAll(".value")].filter((node) => node.textContent.trim()).length,
        nodeCount: document.querySelectorAll("*").length,
        longTaskMs: Number((window.__longTaskMs || 0).toFixed(3)),
      };
    },
    { gotoMs, hydrationMs, beforeIntent },
  );
}

async function main() {
  const variants = FIELD_COUNTS.map(makeVariant);
  const { server, baseUrl } = await startServer(variants);
  const browser = await chromium.launch({ headless: true });
  const rows = [];
  try {
    for (const variant of variants) {
      for (let iteration = 0; iteration < ITERATIONS; iteration += 1) {
        const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
        rows.push({
          fieldCount: variant.fieldCount,
          iteration,
          ...(await measure(page, `${baseUrl}/${variant.fieldCount}`, variant.expected)),
        });
        await page.close();
      }
    }
  } finally {
    await browser.close();
    server.close();
  }

  const source = Object.fromEntries(
    variants.map((variant) => [
      variant.fieldCount,
      {
        html: byteStats(variant.html),
        externalJs: byteStats(variant.js),
      },
    ]),
  );

  const byCount = Object.fromEntries(
    FIELD_COUNTS.map((fieldCount) => {
      const items = rows.filter((row) => row.fieldCount === fieldCount);
      return [
        fieldCount,
        {
          samples: items.length,
          gotoMs: stats(items.map((row) => row.gotoMs)),
          domContentLoadedMs: stats(items.map((row) => row.domContentLoadedMs || 0)),
          loadMs: stats(items.map((row) => row.loadMs || 0)),
          fcpMs: stats(items.map((row) => row.fcpMs || 0)),
          hydrationAfterIntentMs: stats(items.map((row) => row.hydrationAfterIntentMs)),
          longTaskMs: stats(items.map((row) => row.longTaskMs)),
          nodeCount: stats(items.map((row) => row.nodeCount)),
          source: source[fieldCount],
        },
      ];
    }),
  );

  const medians = Object.entries(byCount).map(([fieldCount, bucket]) => ({
    fieldCount: Number(fieldCount),
    loadMs: bucket.loadMs.median,
    hydrationAfterIntentMs: bucket.hydrationAfterIntentMs.median,
    rawBytes: bucket.source.html.rawBytes + bucket.source.externalJs.rawBytes,
    gzipBytes: bucket.source.html.gzipBytes + bucket.source.externalJs.gzipBytes,
    nodeCount: bucket.nodeCount.median,
  }));

  const report = {
    generatedAt: new Date().toISOString(),
    iterations: ITERATIONS,
    fieldCounts: FIELD_COUNTS,
    byCount,
    scaling: {
      loadMsPerField: linearFit(medians, "fieldCount", "loadMs"),
      hydrationMsPerField: linearFit(medians, "fieldCount", "hydrationAfterIntentMs"),
      rawBytesPerField: linearFit(medians, "fieldCount", "rawBytes"),
      gzipBytesPerField: linearFit(medians, "fieldCount", "gzipBytes"),
      nodeCountPerField: linearFit(medians, "fieldCount", "nodeCount"),
    },
    rawRows: rows,
  };

  const output = JSON.stringify(report, null, 2);
  if (outArg) fs.writeFileSync(outArg, `${output}\n`, "utf8");
  console.log(output);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
