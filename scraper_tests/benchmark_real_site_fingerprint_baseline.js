const { chromium } = require("playwright");
const { buildHtml: buildSensitiveTemplate } = require("./benchmark_sensitive_field_template");

const waitMs = Number(process.env.WAIT_MS || 3000);
const urlLimit = Number(process.env.URL_LIMIT || 8);

const defaultUrls = [
  "https://www.wikipedia.org/",
  "https://news.ycombinator.com/",
  "https://developer.mozilla.org/en-US/",
  "https://www.bbc.com/news",
  "https://www.theverge.com/",
  "https://www.apple.com/",
  "https://www.shopify.com/blog",
  "https://stripe.com/",
];

function parseUrls() {
  if (!process.env.URLS) return defaultUrls.slice(0, urlLimit);
  return process.env.URLS.split(",").map((url) => url.trim()).filter(Boolean).slice(0, urlLimit);
}

function countMatches(text, pattern) {
  return (text.match(pattern) || []).length;
}

function sourceStats(html) {
  const rawBytes = Buffer.byteLength(html, "utf8");
  const inlineScriptBytes = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].reduce(
    (sum, match) => sum + Buffer.byteLength(match[1] || "", "utf8"),
    0,
  );
  return {
    rawBytes,
    inlineScriptBytes,
    inlineScriptRatio: rawBytes ? Number((inlineScriptBytes / rawBytes).toFixed(4)) : 0,
    sourcePatternCounts: {
      measureText: countMatches(html, /measureText\s*\(/g),
      getBoundingClientRect: countMatches(html, /getBoundingClientRect\s*\(/g),
      getComputedStyle: countMatches(html, /getComputedStyle\s*\(/g),
      devicePixelRatio: countMatches(html, /devicePixelRatio/g),
      fromCharCode: countMatches(html, /fromCharCode/g),
      atob: countMatches(html, /atob/g),
      xorOperator: countMatches(html, /\^/g),
      jsonPayload: countMatches(html, /type=["']application\/json["']/g),
      emptySlots: countMatches(html, /<span[^>]*>\s*<\/span>/g),
    },
  };
}

function summarizeBaseline(rows) {
  const keys = [
    "measureText",
    "getBoundingClientRect",
    "getComputedStyle",
    "devicePixelRatioReads",
    "atob",
    "mutations",
  ];
  const summary = {};
  for (const key of keys) {
    const values = rows
      .filter((row) => !row.error)
      .map((row) => row.runtime[key])
      .sort((a, b) => a - b);
    if (!values.length) continue;
    summary[key] = {
      min: values[0],
      median: values[Math.floor(values.length / 2)],
      max: values[values.length - 1],
    };
  }
  return summary;
}

async function installInstrumentation(page) {
  await page.addInitScript(instrumentFunction);
}

function instrumentFunction() {
    window.__fpCalls = {
      measureText: 0,
      getBoundingClientRect: 0,
      getComputedStyle: 0,
      devicePixelRatioReads: 0,
      atob: 0,
      mutations: 0,
    };

    const originalAtob = window.atob;
    window.atob = function patchedAtob(...args) {
      window.__fpCalls.atob += 1;
      return originalAtob.apply(this, args);
    };

    const measure = CanvasRenderingContext2D.prototype.measureText;
    CanvasRenderingContext2D.prototype.measureText = function patchedMeasureText(...args) {
      window.__fpCalls.measureText += 1;
      return measure.apply(this, args);
    };

    const rect = Element.prototype.getBoundingClientRect;
    Element.prototype.getBoundingClientRect = function patchedGetBoundingClientRect(...args) {
      window.__fpCalls.getBoundingClientRect += 1;
      return rect.apply(this, args);
    };

    const originalGetComputedStyle = window.getComputedStyle;
    window.getComputedStyle = function patchedGetComputedStyle(...args) {
      window.__fpCalls.getComputedStyle += 1;
      return originalGetComputedStyle.apply(this, args);
    };

    const dprDescriptor = Object.getOwnPropertyDescriptor(window, "devicePixelRatio");
    if (dprDescriptor?.configurable) {
      Object.defineProperty(window, "devicePixelRatio", {
        configurable: true,
        get() {
          window.__fpCalls.devicePixelRatioReads += 1;
          return dprDescriptor.get ? dprDescriptor.get.call(window) : dprDescriptor.value;
        },
      });
    }

    new MutationObserver((records) => {
      window.__fpCalls.mutations += records.length;
    }).observe(document.documentElement, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
    });
}

function injectInstrumentation(html) {
  return html.replace(
    /<head>/i,
    `<head><script>(${instrumentFunction.toString()})();</script>`,
  );
}

async function scanUrl(browser, url) {
  const page = await browser.newPage({ viewport: { width: 1365, height: 768 } });
  await installInstrumentation(page);
  const started = Date.now();
  const row = { label: url, url, error: null, loadMs: null, source: null, runtime: null };
  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(waitMs);
    row.loadMs = Date.now() - started;
    const html = await page.content();
    row.source = sourceStats(html);
    row.runtime = await page.evaluate(() => ({ ...window.__fpCalls }));
  } catch (error) {
    row.error = String(error.message || error);
  } finally {
    await page.close();
  }
  return row;
}

async function scanLocalTemplate(browser) {
  const page = await browser.newPage({ viewport: { width: 1365, height: 768 } });
  const html = injectInstrumentation(buildSensitiveTemplate({ gated: true, placeholder: true }));
  const started = Date.now();
  await page.setContent(html, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(waitMs);
  const source = await page.content();
  const row = {
    label: "local:placeholderGated",
    url: null,
    error: null,
    loadMs: Date.now() - started,
    source: sourceStats(source),
    runtime: await page.evaluate(() => ({ ...window.__fpCalls })),
  };
  await page.close();
  return row;
}

async function main() {
  const urls = parseUrls();
  const browser = await chromium.launch({ headless: true });
  const local = await scanLocalTemplate(browser);
  const realSites = [];
  for (const url of urls) {
    process.stderr.write(`Scanning ${url}\n`);
    realSites.push(await scanUrl(browser, url));
  }
  await browser.close();

  console.log(
    JSON.stringify(
      {
        waitMs,
        local,
        realSites,
        baselineSummary: summarizeBaseline(realSites),
      },
      null,
      2,
    ),
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
