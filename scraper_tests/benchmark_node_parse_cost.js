const { performance } = require("node:perf_hooks");
const cheerio = require("cheerio");
const { JSDOM } = require("jsdom");
const { Readability } = require("@mozilla/readability");
const { page } = require("./structural_churn_server");

const iterations = Number(process.env.ITERATIONS || 300);

const modes = {
  stable: { churn: false, reorder: false },
  reorderOnly: { churn: false, reorder: true },
  churnOnly: { churn: true, reorder: false },
  reorderPlusChurn: { churn: true, reorder: true },
  splitOnly: { churn: false, adversarial: true, semanticAnchors: false },
  splitPlusDecoy: { churn: false, adversarial: true, hiddenDecoy: true, semanticAnchors: false },
  splitPlusZeroWidth: { churn: false, adversarial: true, zeroWidth: true, semanticAnchors: false },
  splitPlusDecoyZeroWidth: {
    churn: false,
    adversarial: true,
    hiddenDecoy: true,
    zeroWidth: true,
    semanticAnchors: false,
  },
  splitPlusChurnDecoyZeroWidth: {
    churn: true,
    adversarial: true,
    hiddenDecoy: true,
    zeroWidth: true,
    semanticAnchors: false,
  },
};

function normalize(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

function parseFromText(text) {
  const normalized = normalize(text);
  return {
    project: normalized.match(/Project:\s*([^:]+?)(?=\s+Launch window:|\s+Dataset:|$)/i)?.[1] || "",
    launch_window:
      normalized.match(/Launch window:\s*([^:]+?)(?=\s+Project:|\s+Dataset:|$)/i)?.[1] || "",
    dataset: normalized.match(/Dataset:\s*([^:]+?)(?=\s+Project:|\s+Launch window:|$)/i)?.[1] || "",
  };
}

const parsers = {
  "cheerio-text": (html) => parseFromText(cheerio.load(html)("body").text()),
  "cheerio-css-aware-text": (html) => {
    const $ = cheerio.load(html);
    $(".hidden-decoy").remove();
    return parseFromText($("body").text());
  },
  "cheerio-data-attrs": (html) => {
    const $ = cheerio.load(html);
    const output = {};
    $("[data-field]").each((_, row) => {
      const field = $(row).attr("data-field");
      output[field] = normalize($(row).find("[data-v]").first().text());
    });
    return output;
  },
  "jsdom-text": (html) => {
    const dom = new JSDOM(html);
    return parseFromText(dom.window.document.body.textContent);
  },
  readability: (html) => {
    const dom = new JSDOM(html, { url: "https://example.test/record" });
    const article = new Readability(dom.window.document).parse();
    return parseFromText(article?.textContent || "");
  },
};

function percentile(sorted, p) {
  const index = Math.min(sorted.length - 1, Math.floor(sorted.length * p));
  return sorted[index];
}

function summarize(times) {
  times.sort((a, b) => a - b);
  const avg = times.reduce((sum, value) => sum + value, 0) / times.length;
  return {
    avgMs: Number(avg.toFixed(4)),
    p50Ms: Number(percentile(times, 0.5).toFixed(4)),
    p95Ms: Number(percentile(times, 0.95).toFixed(4)),
  };
}

function measure(parser, htmls) {
  const times = [];
  for (const html of htmls) {
    const start = performance.now();
    parser(html);
    times.push(performance.now() - start);
  }
  return summarize(times);
}

function main() {
  const report = { iterations, results: {} };
  for (const [mode, options] of Object.entries(modes)) {
    const htmls = Array.from({ length: iterations }, (_, index) => page(`cost-${index}`, options));
    const avgBytes = Math.round(
      htmls.reduce((sum, html) => sum + Buffer.byteLength(html, "utf8"), 0) / htmls.length,
    );
    report.results[mode] = { avgBytes, parsers: {} };
    for (const [parserName, parser] of Object.entries(parsers)) {
      report.results[mode].parsers[parserName] = measure(parser, htmls);
    }
  }

  const stable = report.results.stable.parsers;
  for (const modeResult of Object.values(report.results)) {
    for (const [parserName, stats] of Object.entries(modeResult.parsers)) {
      stats.avgRatioVsStable = Number((stats.avgMs / stable[parserName].avgMs).toFixed(2));
    }
  }

  console.log(JSON.stringify(report, null, 2));
}

main();
