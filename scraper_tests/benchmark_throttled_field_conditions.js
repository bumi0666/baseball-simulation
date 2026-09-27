const fs = require("node:fs");
const http = require("node:http");
const { performance } = require("node:perf_hooks");
const zlib = require("node:zlib");

const { chromium } = require("playwright");
const { buildHtml, sensitive } = require("./benchmark_sensitive_field_template");
const { externalize, runtimePadding } = require("./benchmark_script_placement_context");

const ITERATIONS = Number(process.env.ITERATIONS || 8);
const outArg = process.argv.includes("--out") ? process.argv[process.argv.indexOf("--out") + 1] : null;

const profiles = {
  fastDesktop: {
    viewport: { width: 1200, height: 900 },
    deviceScaleFactor: 1,
    isMobile: false,
    cpuRate: 1,
    network: null,
  },
  midMobile4gCpu4: {
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    cpuRate: 4,
    network: {
      latency: 80,
      downloadThroughput: (1.6 * 1024 * 1024) / 8,
      uploadThroughput: (750 * 1024) / 8,
    },
  },
  slowMobile3gCpu6: {
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    cpuRate: 6,
    network: {
      latency: 300,
      downloadThroughput: (400 * 1024) / 8,
      uploadThroughput: (400 * 1024) / 8,
    },
  },
};

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

function makeVariants() {
  const inlineHtml = buildHtml({ gated: true, placeholder: true, interactionGate: true });
  const external = externalize(inlineHtml, "/assets/runtime/risk-events.js");
  return {
    plain: { html: buildHtml({ gated: false }), assets: {} },
    externalRuntimeLike: {
      html: external.html,
      assets: { "/assets/runtime/risk-events.js": `${runtimePadding()}\n${external.js}` },
    },
  };
}

function startServer(variants) {
  const server = http.createServer((req, res) => {
    const path = new URL(req.url, "http://localhost").pathname;
    const acceptsGzip = /\bgzip\b/.test(req.headers["accept-encoding"] || "");
    const send = (status, headers, body) => {
      if (acceptsGzip && status === 200) {
        res.writeHead(status, { ...headers, "content-encoding": "gzip" });
        res.end(zlib.gzipSync(body));
        return;
      }
      res.writeHead(status, headers);
      res.end(body);
    };
    const variant = variants[path.replace(/^\/+/, "") || "plain"];
    if (variant) {
      send(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" }, variant.html);
      return;
    }
    for (const entry of Object.values(variants)) {
      if (entry.assets[path]) {
        send(
          200,
          {
            "content-type": "application/javascript; charset=utf-8",
            "cache-control": "public, max-age=31536000, immutable",
          },
          entry.assets[path],
        );
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

async function applyThrottling(page, profile) {
  const client = await page.context().newCDPSession(page);
  if (profile.cpuRate && profile.cpuRate !== 1) {
    await client.send("Emulation.setCPUThrottlingRate", { rate: profile.cpuRate });
  }
  if (profile.network) {
    await client.send("Network.enable");
    await client.send("Network.emulateNetworkConditions", {
      offline: false,
      latency: profile.network.latency,
      downloadThroughput: profile.network.downloadThroughput,
      uploadThroughput: profile.network.uploadThroughput,
    });
  }
}

async function measure(page, url) {
  await page.addInitScript(() => {
    window.__field = { cls: 0, longTasks: 0, longTaskMs: 0, resources: [] };
    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (!entry.hadRecentInput) window.__field.cls += entry.value || 0;
        }
      }).observe({ type: "layout-shift", buffered: true });
    } catch {}
    try {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          window.__field.longTasks += 1;
          window.__field.longTaskMs += entry.duration || 0;
        }
      }).observe({ type: "longtask", buffered: true });
    } catch {}
    try {
      new PerformanceObserver((list) => {
        window.__field.resources.push(...list.getEntries().map((entry) => ({
          name: entry.name,
          duration: entry.duration || 0,
          transferSize: entry.transferSize || 0,
          encodedBodySize: entry.encodedBodySize || 0,
          decodedBodySize: entry.decodedBodySize || 0,
        })));
      }).observe({ type: "resource", buffered: true });
    } catch {}
  });

  const started = performance.now();
  await page.goto(url, { waitUntil: "load", timeout: 30000 });
  const gotoMs = performance.now() - started;
  await page.waitForTimeout(250);

  const textReadyMs = await page.evaluate((expected) => {
    const start = performance.now();
    return new Promise((resolve) => {
      const done = () => expected.every((value) => document.body.innerText.includes(value));
      if (done()) {
        resolve(performance.now() - start);
        return;
      }
      const observer = new MutationObserver(() => {
        if (done()) {
          observer.disconnect();
          resolve(performance.now() - start);
        }
      });
      observer.observe(document.documentElement, { subtree: true, childList: true, characterData: true });
      setTimeout(() => {
        observer.disconnect();
        resolve(2000);
      }, 2000);
    });
  }, Object.values(sensitive));

  return page.evaluate(({ gotoMs, textReadyMs }) => {
    const nav = performance.getEntriesByType("navigation")[0];
    const paints = Object.fromEntries(performance.getEntriesByType("paint").map((entry) => [entry.name, entry.startTime]));
    const scriptResources = window.__field.resources
      .filter((entry) => entry.name.endsWith(".js"))
      .map((entry) => ({
        duration: Number(entry.duration.toFixed(3)),
        decodedBodySize: entry.decodedBodySize,
        transferSize: entry.transferSize,
      }));
    return {
      gotoMs: Number(gotoMs.toFixed(3)),
      domContentLoadedMs: nav ? Number(nav.domContentLoadedEventEnd.toFixed(3)) : null,
      loadMs: nav ? Number(nav.loadEventEnd.toFixed(3)) : null,
      fcpMs: paints["first-contentful-paint"] || null,
      textReadyMs: Number(textReadyMs.toFixed(3)),
      cls: Number((window.__field.cls || 0).toFixed(6)),
      longTasks: window.__field.longTasks || 0,
      longTaskMs: Number((window.__field.longTaskMs || 0).toFixed(3)),
      scriptResources,
      sensitiveVisible: [...document.querySelectorAll(".value")].filter((node) => node.textContent.trim()).length,
      placeholdersVisible: [
        "Available on request",
        "Contact team",
        "Restricted",
        "Access required",
        "Not publicly listed",
      ].filter((value) => document.body.innerText.includes(value)).length,
    };
  }, { gotoMs, textReadyMs });
}

async function run() {
  const variants = makeVariants();
  const assets = Object.fromEntries(
    Object.entries(variants).map(([name, variant]) => [
      name,
      {
        htmlRawBytes: Buffer.byteLength(variant.html, "utf8"),
        htmlGzipBytes: zlib.gzipSync(variant.html).length,
        jsRawBytes: Object.values(variant.assets).reduce((sum, text) => sum + Buffer.byteLength(text, "utf8"), 0),
        jsGzipBytes: Object.values(variant.assets).reduce((sum, text) => sum + zlib.gzipSync(text).length, 0),
      },
    ]),
  );

  const { server, baseUrl } = await startServer(variants);
  const browser = await chromium.launch({ headless: true });
  const rows = [];
  try {
    for (const [profileName, profile] of Object.entries(profiles)) {
      for (const variantName of Object.keys(variants)) {
        for (let i = 0; i < ITERATIONS; i += 1) {
          const page = await browser.newPage(profile);
          await applyThrottling(page, profile);
          rows.push({
            profile: profileName,
            variant: variantName,
            iteration: i,
            ...(await measure(page, `${baseUrl}/${variantName}`)),
          });
          await page.close();
        }
      }
    }
  } finally {
    await browser.close();
    server.close();
  }

  const grouped = {};
  for (const row of rows) {
    const key = `${row.profile}:${row.variant}`;
    grouped[key] ||= [];
    grouped[key].push(row);
  }
  const summary = Object.fromEntries(
    Object.entries(grouped).map(([key, items]) => [
      key,
      {
        samples: items.length,
        gotoMs: stats(items.map((row) => row.gotoMs)),
        domContentLoadedMs: stats(items.map((row) => row.domContentLoadedMs || 0)),
        loadMs: stats(items.map((row) => row.loadMs || 0)),
        fcpMs: stats(items.map((row) => row.fcpMs || 0)),
        textReadyMs: stats(items.map((row) => row.textReadyMs)),
        longTaskMs: stats(items.map((row) => row.longTaskMs)),
        cls: stats(items.map((row) => row.cls)),
        scriptDurationMs: stats(items.flatMap((row) => row.scriptResources.map((script) => script.duration))),
        lastSample: items[items.length - 1],
      },
    ]),
  );

  const result = {
    generatedAt: new Date().toISOString(),
    iterations: ITERATIONS,
    profiles,
    assets,
    summary,
    rawRows: rows,
    caveats: [
      "Chromium CDP throttling is a lab approximation, not field Core Web Vitals.",
      "Localhost still differs from CDN, TLS, cache, and real mobile radio behavior.",
      "The script is intentionally tiny after gzip; production padding should not be meaningless noise.",
    ],
  };
  const json = JSON.stringify(result, null, 2);
  if (outArg) fs.writeFileSync(outArg, `${json}\n`, "utf8");
  else console.log(json);
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
