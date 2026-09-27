const crypto = require("node:crypto");
const { performance } = require("node:perf_hooks");

const { chromium } = require("playwright");
const { buildHtml, expectedRecords, fields, modes } = require("./evaluate_llm_pure_gap_scale");

const iterations = Number(process.env.ITERATIONS || 10);
const selectedModes = (process.env.MODES || "stable,fontMetricPure,selfRefPure")
  .split(",")
  .map((mode) => mode.trim())
  .filter(Boolean);

const browserConfigs = [
  { name: "chromium-900x700-dsf1", viewport: { width: 900, height: 700 }, deviceScaleFactor: 1 },
  { name: "chromium-1200x900-dsf1", viewport: { width: 1200, height: 900 }, deviceScaleFactor: 1 },
  { name: "chromium-900x700-dsf2", viewport: { width: 900, height: 700 }, deviceScaleFactor: 2 },
  { name: "chromium-420x900-dsf3", viewport: { width: 420, height: 900 }, deviceScaleFactor: 3 },
];

function normalize(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function labelFor(field) {
  return field.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function stripHtml(html) {
  return normalize(
    html
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<[^>]+>/g, " "),
  );
}

function parseRecordsFromText(text) {
  const normalized = normalize(text);
  const records = [];
  for (const idMatch of normalized.matchAll(/\bR\d{3}\b/g)) {
    const id = idMatch[0];
    const start = idMatch.index;
    const next = normalized.slice(start + id.length).search(/\bR\d{3}\b/);
    const chunk = next >= 0 ? normalized.slice(start, start + id.length + next) : normalized.slice(start);
    const record = { id };
    for (const field of fields) {
      const label = labelFor(field).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const nextLabels = fields
        .filter((other) => other !== field)
        .map((other) => labelFor(other).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
        .join("|");
      const match = chunk.match(new RegExp(`${label}:\\s*([\\s\\S]*?)(?=\\s+(?:${nextLabels}):|$)`, "i"));
      record[field] = normalize(match?.[1] || "");
    }
    records.push(record);
  }
  return records;
}

function classify(actual, expected) {
  if (actual == null || actual === "") return "missing";
  if (actual === expected) return "exact";
  if (normalize(actual).toLowerCase() === normalize(expected).toLowerCase()) return "restored";
  return "wrong";
}

function scoreRecords(parsedRecords, expected) {
  const byId = new Map(parsedRecords.map((record) => [record.id, record]));
  const bucket = {
    fields: expected.length * fields.length,
    exact: 0,
    restored: 0,
    missing: 0,
    wrong: 0,
    parsedCount: parsedRecords.length,
    failureSamples: [],
  };
  for (const expectedRecord of expected) {
    const actualRecord = byId.get(expectedRecord.id) || {};
    for (const field of fields) {
      const status = classify(actualRecord[field], expectedRecord[field]);
      bucket[status] += 1;
      if (status !== "exact" && bucket.failureSamples.length < 6) {
        bucket.failureSamples.push({
          id: expectedRecord.id,
          field,
          expected: expectedRecord[field],
          actual: actualRecord[field],
          status,
        });
      }
    }
  }
  bucket.exactRate = Number((bucket.exact / bucket.fields).toFixed(4));
  bucket.leakageRate = Number(((bucket.exact + bucket.restored) / bucket.fields).toFixed(4));
  bucket.safeFailureRate = Number((bucket.missing / bucket.fields).toFixed(4));
  bucket.unsafeFailureRate = Number((bucket.wrong / bucket.fields).toFixed(4));
  return bucket;
}

function hashRecords(records) {
  return crypto.createHash("sha256").update(JSON.stringify(records)).digest("hex").slice(0, 16);
}

function percentile(sorted, p) {
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * p))];
}

function summarizeTimes(times) {
  const sorted = [...times].sort((a, b) => a - b);
  const avg = sorted.reduce((sum, value) => sum + value, 0) / sorted.length;
  return {
    avgMs: Number(avg.toFixed(3)),
    p50Ms: Number(percentile(sorted, 0.5).toFixed(3)),
    p95Ms: Number(percentile(sorted, 0.95).toFixed(3)),
  };
}

async function extractRendered(html, config) {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: config.viewport,
    deviceScaleFactor: config.deviceScaleFactor,
  });
  await page.setContent(html, { waitUntil: "load" });
  await page.waitForTimeout(50);
  const result = await page.evaluate((fieldNames) => {
    const labelFromField = (field) => field.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    ctx.font = getComputedStyle(document.body).font;
    const cards = [...document.querySelectorAll(".card")];
    const domRows = cards.map((card) => {
      const record = { id: card.dataset.record || card.querySelector("h2")?.textContent?.trim() || "" };
      [...card.querySelectorAll(".row")].forEach((row) => {
        const labelText = row.querySelector("b, .label")?.textContent?.replace(":", "").trim();
        const field = fieldNames.find((candidate) => labelFromField(candidate) === labelText);
        if (!field) return;
        const valueNode = row.querySelector("span:not(.label)");
        record[field] = valueNode?.textContent?.trim() || "";
      });
      return record;
    });
    const signals = cards.flatMap((card) =>
      fieldNames.map((field) => {
        const rect = card.getBoundingClientRect();
        return {
          id: card.dataset.record || "",
          field,
          width: Math.round(ctx.measureText(`${card.dataset.record}:${field}:${window.devicePixelRatio}`).width),
          top: Math.round(rect.top),
          height: Math.round(rect.height),
          viewport: `${window.innerWidth}x${window.innerHeight}`,
          dpr: window.devicePixelRatio,
        };
      }),
    );
    return {
      innerText: document.body.innerText,
      domRows,
      signals,
    };
  }, fields);
  await browser.close();
  return {
    renderedInnerText: parseRecordsFromText(result.innerText),
    renderedDomRows: result.domRows,
    signals: result.signals,
  };
}

async function main() {
  const expected = expectedRecords();
  const scoring = {};
  const determinism = {};
  const cost = {};

  for (const mode of selectedModes) {
    if (!modes[mode]) throw new Error(`Unknown mode: ${mode}`);
    const html = buildHtml(mode, "headless-benchmark");
    const sourceRecords = parseRecordsFromText(stripHtml(html));
    scoring[mode] = {
      sourceText: scoreRecords(sourceRecords, expected),
    };

    const baseRendered = await extractRendered(html, browserConfigs[0]);
    scoring[mode].renderedInnerText = scoreRecords(baseRendered.renderedInnerText, expected);
    scoring[mode].renderedDomRows = scoreRecords(baseRendered.renderedDomRows, expected);

    determinism[mode] = [];
    for (const config of browserConfigs) {
      const rendered = await extractRendered(html, config);
      const scored = scoreRecords(rendered.renderedDomRows, expected);
      determinism[mode].push({
        config: config.name,
        hash: hashRecords(rendered.renderedDomRows),
        signalHash: hashRecords(rendered.signals),
        exactRate: scored.exactRate,
        leakageRate: scored.leakageRate,
        safeFailureRate: scored.safeFailureRate,
        unsafeFailureRate: scored.unsafeFailureRate,
      });
    }

    const sourceTimes = [];
    const renderTimes = [];
    const extractTimes = [];
    const endToEndTimes = [];
    for (let i = 0; i < iterations; i += 1) {
      let start = performance.now();
      parseRecordsFromText(stripHtml(html));
      sourceTimes.push(performance.now() - start);

      const fullStart = performance.now();
      const browser = await chromium.launch({ headless: true });
      const page = await browser.newPage({
        viewport: browserConfigs[0].viewport,
        deviceScaleFactor: browserConfigs[0].deviceScaleFactor,
      });
      start = performance.now();
      await page.setContent(html, { waitUntil: "load" });
      await page.waitForTimeout(50);
      renderTimes.push(performance.now() - start);

      start = performance.now();
      await page.evaluate((fieldNames) => {
        const labelFromField = (field) => field.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
        return [...document.querySelectorAll(".card")].map((card) => {
          const record = { id: card.dataset.record || "" };
          [...card.querySelectorAll(".row")].forEach((row) => {
            const labelText = row.querySelector("b, .label")?.textContent?.replace(":", "").trim();
            const field = fieldNames.find((candidate) => labelFromField(candidate) === labelText);
            if (field) record[field] = row.querySelector("span:not(.label)")?.textContent?.trim() || "";
          });
          return record;
        });
      }, fields);
      extractTimes.push(performance.now() - start);
      await browser.close();
      endToEndTimes.push(performance.now() - fullStart);
    }
    cost[mode] = {
      sourceTextParse: summarizeTimes(sourceTimes),
      headlessEndToEndLaunchRenderExtract: summarizeTimes(endToEndTimes),
      headlessSetContentAndWait: summarizeTimes(renderTimes),
      renderedDomExtract: summarizeTimes(extractTimes),
    };
  }

  console.log(
    JSON.stringify(
      {
        iterations,
        recordCount: expected.length,
        fields,
        modes: selectedModes,
        scoring,
        determinism,
        cost,
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
