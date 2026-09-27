const http = require("node:http");
const fs = require("node:fs");
const { performance } = require("node:perf_hooks");
const zlib = require("node:zlib");

const { chromium } = require("playwright");
const { buildHtml, sensitive } = require("./benchmark_sensitive_field_template");
const { externalize, runtimePadding } = require("./benchmark_script_placement_context");

const ITERATIONS = Number(process.env.ITERATIONS || 12);
const outArg = process.argv.includes("--out") ? process.argv[process.argv.indexOf("--out") + 1] : null;

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

function makeVariants() {
  const plainHtml = buildHtml({ gated: false });
  const inlineHtml = buildHtml({ gated: true, placeholder: true, interactionGate: true });
  const externalSmall = externalize(inlineHtml, "/assets/runtime/small.js");
  const externalRuntime = {
    html: externalSmall.html.replace("/assets/runtime/small.js", "/assets/runtime/risk-events.js"),
    js: `${runtimePadding()}\n${externalSmall.js}`,
  };

  return {
    plain: { html: plainHtml, assets: {} },
    inlinePlaceholderGated: { html: inlineHtml, assets: {} },
    externalSmall: { html: externalSmall.html, assets: { "/assets/runtime/small.js": externalSmall.js } },
    externalRuntimeLike: {
      html: externalRuntime.html,
      assets: { "/assets/runtime/risk-events.js": externalRuntime.js },
    },
  };
}

function startServer(variants) {
  const server = http.createServer((req, res) => {
    const path = new URL(req.url, "http://localhost").pathname;
    const variantName = path.replace(/^\/+/, "") || "plain";
    const variant = variants[variantName];
    if (variant) {
      res.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
      res.end(variant.html);
      return;
    }
    for (const entry of Object.values(variants)) {
      if (entry.assets[path]) {
        res.writeHead(200, {
          "content-type": "application/javascript; charset=utf-8",
          "cache-control": "public, max-age=31536000, immutable",
        });
        res.end(entry.assets[path]);
        return;
      }
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

async function measurePage(page, url) {
  await page.addInitScript(() => {
    window.__cost = {
      cls: 0,
      longTasks: 0,
      longTaskMs: 0,
      resources: [],
      firstInteractionDelayMs: null,
    };
    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (!entry.hadRecentInput) window.__cost.cls += entry.value || 0;
        }
      }).observe({ type: "layout-shift", buffered: true });
    } catch {}
    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          window.__cost.longTasks += 1;
          window.__cost.longTaskMs += entry.duration || 0;
        }
      }).observe({ type: "longtask", buffered: true });
    } catch {}
    try {
      new PerformanceObserver((list) => {
        window.__cost.resources.push(...list.getEntries().map((entry) => ({
          name: entry.name,
          transferSize: entry.transferSize || 0,
          encodedBodySize: entry.encodedBodySize || 0,
          decodedBodySize: entry.decodedBodySize || 0,
          duration: entry.duration || 0,
        })));
      }).observe({ type: "resource", buffered: true });
    } catch {}
  });

  const started = performance.now();
  await page.goto(url, { waitUntil: "load" });
  const gotoMs = performance.now() - started;
  await page.waitForTimeout(100);
  const textReadyMs = await page.evaluate((expectedValues) => {
    const startedAt = performance.now();
    return new Promise((resolve) => {
      const done = () => {
        const text = document.body.innerText;
        if (expectedValues.every((value) => text.includes(value))) {
          resolve(performance.now() - startedAt);
          return true;
        }
        return false;
      };
      if (done()) return;
      const observer = new MutationObserver(() => {
        if (done()) observer.disconnect();
      });
      observer.observe(document.documentElement, { subtree: true, childList: true, characterData: true });
      setTimeout(() => {
        observer.disconnect();
        resolve(1000);
      }, 1000);
    });
  }, Object.values(sensitive));

  const clickLatencyMs = await page.evaluate(() => {
    return new Promise((resolve) => {
      const target = document.querySelector(".details") || document.body;
      const start = performance.now();
      target.addEventListener(
        "click",
        () => requestAnimationFrame(() => resolve(performance.now() - start)),
        { once: true },
      );
      target.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
    });
  });

  await page.waitForTimeout(100);
  return page.evaluate(({ gotoMs, textReadyMs, clickLatencyMs }) => {
    const nav = performance.getEntriesByType("navigation")[0];
    const paints = Object.fromEntries(performance.getEntriesByType("paint").map((entry) => [entry.name, entry.startTime]));
    const bodyText = document.body.innerText || "";
    const placeholders = [
      "Available on request",
      "Contact team",
      "Restricted",
      "Access required",
      "Not publicly listed",
    ];
    const scripts = [...document.scripts].map((script) => ({
      src: script.src || null,
      inlineBytes: script.src ? 0 : script.textContent.length,
    }));
    return {
      gotoMs,
      domContentLoadedMs: nav ? nav.domContentLoadedEventEnd : null,
      loadMs: nav ? nav.loadEventEnd : null,
      fcpMs: paints["first-contentful-paint"] || null,
      cls: Number((window.__cost.cls || 0).toFixed(6)),
      longTasks: window.__cost.longTasks || 0,
      longTaskMs: Number((window.__cost.longTaskMs || 0).toFixed(3)),
      textReadyMs: Number(textReadyMs.toFixed(3)),
      clickLatencyMs: Number(clickLatencyMs.toFixed(3)),
      nodeCount: document.querySelectorAll("*").length,
      scriptCount: document.scripts.length,
      externalScriptCount: scripts.filter((script) => script.src).length,
      inlineScriptBytes: scripts.reduce((sum, script) => sum + script.inlineBytes, 0),
      sensitiveVisible: [...document.querySelectorAll(".value")].filter((node) => node.textContent.trim()).length,
      placeholdersVisible: placeholders.filter((value) => bodyText.includes(value)).length,
      resourceSummary: {
        count: window.__cost.resources.length,
        transferSize: window.__cost.resources.reduce((sum, entry) => sum + entry.transferSize, 0),
        decodedBodySize: window.__cost.resources.reduce((sum, entry) => sum + entry.decodedBodySize, 0),
        scriptResources: window.__cost.resources
          .filter((entry) => entry.name.endsWith(".js"))
          .map((entry) => ({
            decodedBodySize: entry.decodedBodySize,
            duration: Number(entry.duration.toFixed(3)),
          })),
      },
    };
  }, { gotoMs, textReadyMs, clickLatencyMs });
}

async function browserBench(variants, baseUrl) {
  const browser = await chromium.launch({ headless: true });
  const profiles = {
    desktop: { viewport: { width: 1200, height: 900 }, deviceScaleFactor: 1, isMobile: false },
    mobile: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true },
  };
  const rows = [];
  for (const [profileName, profile] of Object.entries(profiles)) {
    for (const name of Object.keys(variants)) {
      for (let i = 0; i < ITERATIONS; i += 1) {
        const page = await browser.newPage(profile);
        rows.push({ profile: profileName, variant: name, iteration: i, ...(await measurePage(page, `${baseUrl}/${name}`)) });
        await page.close();
      }
    }
  }
  await browser.close();
  return rows;
}

function summarizeRows(rows) {
  const grouped = {};
  for (const row of rows) {
    const key = `${row.profile}:${row.variant}`;
    grouped[key] ||= [];
    grouped[key].push(row);
  }
  return Object.fromEntries(
    Object.entries(grouped).map(([key, items]) => [
      key,
      {
        samples: items.length,
        gotoMs: stats(items.map((row) => row.gotoMs)),
        domContentLoadedMs: stats(items.map((row) => row.domContentLoadedMs || 0)),
        loadMs: stats(items.map((row) => row.loadMs || 0)),
        fcpMs: stats(items.map((row) => row.fcpMs || 0)),
        textReadyMs: stats(items.map((row) => row.textReadyMs)),
        clickLatencyMs: stats(items.map((row) => row.clickLatencyMs)),
        longTaskMs: stats(items.map((row) => row.longTaskMs)),
        cls: stats(items.map((row) => row.cls)),
        medianResourceBytes: stats(items.map((row) => row.resourceSummary.decodedBodySize)),
        lastSample: items[items.length - 1],
      },
    ]),
  );
}

function sourceAndServerCosts(variants) {
  const source = Object.fromEntries(
    Object.entries(variants).map(([name, variant]) => {
      const jsBytes = Object.values(variant.assets).reduce((sum, js) => sum + byteStats(js).rawBytes, 0);
      const jsGzipBytes = Object.values(variant.assets).reduce((sum, js) => sum + byteStats(js).gzipBytes, 0);
      return [name, { html: byteStats(variant.html), externalJs: { rawBytes: jsBytes, gzipBytes: jsGzipBytes } }];
    }),
  );

  const buildSamples = {};
  for (const name of ["plain", "inlinePlaceholderGated", "externalRuntimeLike"]) {
    const times = [];
    for (let i = 0; i < 1000; i += 1) {
      const start = performance.now();
      if (name === "plain") buildHtml({ gated: false });
      if (name === "inlinePlaceholderGated") buildHtml({ gated: true, placeholder: true, interactionGate: true });
      if (name === "externalRuntimeLike") {
        const inline = buildHtml({ gated: true, placeholder: true, interactionGate: true });
        const small = externalize(inline, "/assets/runtime/risk-events.js");
        void `${runtimePadding()}\n${small.js}`;
      }
      times.push(performance.now() - start);
    }
    buildSamples[name] = stats(times);
  }

  return { source, serverBuildMs: buildSamples };
}

function accessibilityProbe(html) {
  const hasDetailsLabel = /<section[^>]+aria-label=["']Additional details["']/i.test(html);
  const rowCount = (html.match(/class="meta-row"/g) || []).length;
  const placeholderCount = [
    "Available on request",
    "Contact team",
    "Restricted",
    "Access required",
    "Not publicly listed",
  ].filter((value) => html.includes(value)).length;
  const hoverOnlySignals = /mouseenter|pointerenter|mouseover|:hover/.test(html);
  const focusSignals = /focus|tabindex|button|input|a href/.test(html);
  return {
    hasDetailsLabel,
    rowCount,
    placeholderCount,
    hoverOnlySignals,
    focusSignals,
    note: "Static probe only. It checks whether source exposes safe fallback text and whether this candidate appears hover-only.",
  };
}

async function main() {
  const variants = makeVariants();
  const { server, baseUrl } = await startServer(variants);
  try {
    const rows = await browserBench(variants, baseUrl);
    const result = {
      iterations: ITERATIONS,
      generatedAt: new Date().toISOString(),
      costs: sourceAndServerCosts(variants),
      accessibility: Object.fromEntries(
        Object.entries(variants).map(([name, variant]) => [name, accessibilityProbe(variant.html)]),
      ),
      browserSummary: summarizeRows(rows),
      rawRows: rows,
      interpretation: {
        measured: [
          "local Chromium navigation/load/paint approximations",
          "CLS and long-task observer output",
          "synthetic click-to-next-frame latency, not real INP",
          "local asset transfer size and JS payload size",
          "server-side string-generation microbenchmark",
        ],
        notMeasured: [
          "real Google ranking impact",
          "real field Core Web Vitals from users",
          "cross-device low-end Android performance",
          "production CDN/cache behavior",
          "full WCAG/screen-reader audit",
        ],
      },
    };
    const json = JSON.stringify(result, null, 2);
    if (outArg) {
      fs.writeFileSync(outArg, `${json}\n`, "utf8");
    } else {
      console.log(json);
    }
  } finally {
    server.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
