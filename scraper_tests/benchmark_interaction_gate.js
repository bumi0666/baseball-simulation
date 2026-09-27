const { performance } = require("node:perf_hooks");

const { chromium } = require("playwright");
const { expectedRecords, fields } = require("./evaluate_llm_pure_gap_scale");

const recordCount = Number(process.env.RECORDS || 12);
const iterations = Number(process.env.ITERATIONS || 3);

const scenarios = [
  "noInteraction",
  "scrollOnly",
  "hoverAllObvious",
  "focusAllFocusable",
  "bruteForceAllElements",
  "knownSequence",
];

function activeRecords() {
  return expectedRecords().slice(0, recordCount);
}

function encodeValue(value, key) {
  return [...String(value)].map((char, index) => char.charCodeAt(0) ^ ((key + index * 31) & 255));
}

function labelFor(field) {
  return field.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function normalize(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function buildPayload(records) {
  const key = 173;
  return {
    key,
    fields,
    records: records.map((record) => ({
      id: record.id,
      cells: Object.fromEntries(fields.map((field) => [field, encodeValue(record[field], key)])),
    })),
  };
}

function buildHtml() {
  const records = activeRecords();
  const payload = JSON.stringify(buildPayload(records));
  const cards = records
    .map((record, recordIndex) => {
      const rows = fields
        .map((field) => {
          return `<div class="row" data-field="${field}">
            <span class="label">${labelFor(field)}:</span>
            <span class="slot" data-field="${field}"></span>
          </div>`;
        })
        .join("\n");
      return `<section class="card" data-record="${record.id}" data-index="${recordIndex}">
        <h2>${record.id}</h2>
        <button class="arm" type="button" aria-label="prepare ${record.id}">Prepare</button>
        <div class="rows">${rows}</div>
      </section>`;
    })
    .join("\n");

  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Interaction gate fixture</title>
  <style>
    body { font: 16px Arial, sans-serif; margin: 32px; color: #202124; line-height: 1.45; }
    .card { border-top: 1px solid #ddd; padding: 14px 0; max-width: 760px; }
    h2 { font-size: 18px; margin: 0 0 10px; }
    .arm { width: 1px; height: 1px; opacity: 0.01; border: 0; padding: 0; margin: 0; }
    .row { display: grid; grid-template-columns: 170px 1fr; gap: 6px 14px; min-height: 24px; }
    .label { font-weight: 700; }
  </style>
</head>
<body>
  <main>
    <h1>Records</h1>
    ${cards}
  </main>
  <script type="application/json" id="payload">${payload}</script>
  <script>
    (() => {
      const payload = JSON.parse(document.querySelector("#payload").textContent);
      const state = new Map();

      function decode(codes) {
        return codes.map((code, index) => String.fromCharCode(code ^ ((payload.key + index * 31) & 255))).join("");
      }

      function getState(card) {
        if (!state.has(card.dataset.record)) {
          state.set(card.dataset.record, { scrolled: false, armed: false, hovered: new Set(), focused: new Set() });
        }
        return state.get(card.dataset.record);
      }

      function maybeReveal(card) {
        const s = getState(card);
        const ready = s.scrolled && s.armed && payload.fields.every((field) => s.hovered.has(field) && s.focused.has(field));
        if (!ready) return;
        const record = payload.records.find((item) => item.id === card.dataset.record);
        card.querySelectorAll(".slot").forEach((slot) => {
          slot.textContent = decode(record.cells[slot.dataset.field]);
        });
      }

      document.addEventListener("scroll", () => {
        document.querySelectorAll(".card").forEach((card) => {
          const rect = card.getBoundingClientRect();
          if (rect.top < window.innerHeight && rect.bottom > 0) getState(card).scrolled = true;
          maybeReveal(card);
        });
      }, { passive: true });

      document.querySelectorAll(".card").forEach((card) => {
        card.querySelector(".arm").addEventListener("pointerenter", () => {
          getState(card).armed = true;
          maybeReveal(card);
        });
        card.querySelectorAll(".row").forEach((row) => {
          row.tabIndex = 0;
          row.addEventListener("pointerenter", () => {
            getState(card).hovered.add(row.dataset.field);
            maybeReveal(card);
          });
          row.addEventListener("focus", () => {
            getState(card).focused.add(row.dataset.field);
            maybeReveal(card);
          });
        });
      });
    })();
  </script>
</body>
</html>`;
}

function classify(actual, expected) {
  if (!actual) return "missing";
  if (actual === expected) return "exact";
  if (normalize(actual).toLowerCase() === normalize(expected).toLowerCase()) return "restored";
  return "wrong";
}

function score(records, expected) {
  const byId = new Map(records.map((record) => [record.id, record]));
  const bucket = {
    fields: expected.length * fields.length,
    exact: 0,
    restored: 0,
    missing: 0,
    wrong: 0,
    parsedCount: records.length,
  };
  for (const expectedRecord of expected) {
    const actual = byId.get(expectedRecord.id) || {};
    for (const field of fields) {
      bucket[classify(actual[field], expectedRecord[field])] += 1;
    }
  }
  bucket.exactRate = Number((bucket.exact / bucket.fields).toFixed(4));
  bucket.leakageRate = Number(((bucket.exact + bucket.restored) / bucket.fields).toFixed(4));
  bucket.safeFailureRate = Number((bucket.missing / bucket.fields).toFixed(4));
  bucket.unsafeFailureRate = Number((bucket.wrong / bucket.fields).toFixed(4));
  return bucket;
}

async function extractRows(page) {
  return page.locator(".card").evaluateAll((cards, fieldNames) => {
    const labelFromField = (field) => field.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
    return cards.map((card) => {
      const record = { id: card.dataset.record };
      [...card.querySelectorAll(".row")].forEach((row) => {
        const label = row.querySelector(".label")?.textContent?.replace(":", "").trim();
        const field = fieldNames.find((candidate) => labelFromField(candidate) === label);
        if (field) record[field] = row.querySelector(".slot")?.textContent?.trim() || "";
      });
      return record;
    });
  }, fields);
}

async function runScenario(page, scenario) {
  const stats = { attemptedElements: 0, events: 0, firstExactAtEvent: null };
  const expected = activeRecords();

  async function recordProgress() {
    const current = score(await extractRows(page), expected);
    if (current.exactRate === 1 && stats.firstExactAtEvent == null) {
      stats.firstExactAtEvent = stats.events;
    }
    return current;
  }

  if (scenario === "noInteraction") return stats;

  if (scenario === "scrollOnly") {
    await page.evaluate(async () => {
      window.scrollTo(0, document.body.scrollHeight);
      await new Promise((resolve) => setTimeout(resolve, 20));
      window.scrollTo(0, 0);
    });
    stats.events += 2;
    await recordProgress();
    return stats;
  }

  if (scenario === "hoverAllObvious") {
    const selectors = [".card", ".row", ".arm"];
    for (const selector of selectors) {
      const count = await page.locator(selector).count();
      for (let i = 0; i < count; i += 1) {
        const locator = page.locator(selector).nth(i);
        await locator.scrollIntoViewIfNeeded();
        await locator.hover({ force: true });
        stats.attemptedElements += 1;
        stats.events += 2;
        await recordProgress();
      }
    }
    return stats;
  }

  if (scenario === "focusAllFocusable") {
    const count = await page.locator("button, [tabindex], input, select, textarea, a[href]").count();
    for (let i = 0; i < count; i += 1) {
      const locator = page.locator("button, [tabindex], input, select, textarea, a[href]").nth(i);
      await locator.scrollIntoViewIfNeeded();
      await locator.focus();
      stats.attemptedElements += 1;
      stats.events += 2;
      await recordProgress();
    }
    return stats;
  }

  if (scenario === "bruteForceAllElements") {
    const result = await page.evaluate(async () => {
      const elements = [...document.querySelectorAll("body *")];
      let events = 0;
      let attemptedElements = 0;
      for (const element of elements) {
        element.scrollIntoView({ block: "center", inline: "center" });
        element.dispatchEvent(new PointerEvent("pointerenter", { bubbles: true }));
        element.dispatchEvent(new MouseEvent("mouseenter", { bubbles: true }));
        if (typeof element.focus === "function") element.focus();
        attemptedElements += 1;
        events += 3;
        await new Promise((resolve) => requestAnimationFrame(resolve));
      }
      return { attemptedElements, events };
    });
    stats.attemptedElements = result.attemptedElements;
    stats.events = result.events;
    await recordProgress();
    return stats;
  }

  if (scenario === "knownSequence") {
    const cards = await page.locator(".card").count();
    for (let cardIndex = 0; cardIndex < cards; cardIndex += 1) {
      const card = page.locator(".card").nth(cardIndex);
      await card.scrollIntoViewIfNeeded();
      stats.events += 1;
      await card.locator(".arm").hover({ force: true });
      stats.events += 1;
      const rows = await card.locator(".row").count();
      for (let rowIndex = 0; rowIndex < rows; rowIndex += 1) {
        const row = card.locator(".row").nth(rowIndex);
        await row.hover({ force: true });
        await row.focus();
        stats.attemptedElements += 1;
        stats.events += 2;
      }
      await recordProgress();
    }
    return stats;
  }

  throw new Error(`Unknown scenario: ${scenario}`);
}

function percentile(sorted, p) {
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * p))];
}

function summarize(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const avg = sorted.reduce((sum, value) => sum + value, 0) / sorted.length;
  return {
    avg: Number(avg.toFixed(3)),
    p50: Number(percentile(sorted, 0.5).toFixed(3)),
    p95: Number(percentile(sorted, 0.95).toFixed(3)),
  };
}

async function measureScenario(scenario) {
  const html = buildHtml();
  const expected = activeRecords();
  const runs = [];
  for (let i = 0; i < iterations; i += 1) {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
    const start = performance.now();
    await page.setContent(html, { waitUntil: "load" });
    await page.waitForTimeout(50);
    const interactionStart = performance.now();
    const interactionStats = await runScenario(page, scenario);
    const interactionMs = performance.now() - interactionStart;
    const rows = await extractRows(page);
    const totalMs = performance.now() - start;
    await browser.close();
    runs.push({
      score: score(rows, expected),
      attemptedElements: interactionStats.attemptedElements,
      events: interactionStats.events,
      firstExactAtEvent: interactionStats.firstExactAtEvent,
      interactionMs: Number(interactionMs.toFixed(3)),
      totalMs: Number(totalMs.toFixed(3)),
    });
  }
  return {
    score: runs[0].score,
    attemptedElements: runs[0].attemptedElements,
    events: runs[0].events,
    firstExactAtEvent: runs[0].firstExactAtEvent,
    interactionMs: summarize(runs.map((run) => run.interactionMs)),
    totalMs: summarize(runs.map((run) => run.totalMs)),
  };
}

async function main() {
  const results = {};
  for (const scenario of scenarios) {
    results[scenario] = await measureScenario(scenario);
  }
  console.log(
    JSON.stringify(
      {
        recordCount,
        fields,
        iterations,
        scenarios,
        results,
      },
      null,
      2,
    ),
  );
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}

module.exports = {
  buildHtml,
};
