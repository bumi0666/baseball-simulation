const fs = require("node:fs");
const path = require("node:path");
const { performance } = require("node:perf_hooks");

const cheerio = require("cheerio");
const { JSDOM } = require("jsdom");
const { chromium } = require("playwright");

const iterations = Number(process.env.ITERATIONS || 30);
const fixturePath = path.join(__dirname, "computational_gap_fixture.html");

const expected = {
  project: "Alpha project",
  launch_window: "Friday morning",
  dataset: "private dataset",
};

const decoy = {
  project: "Omega project",
  launch_window: "Monday night",
  dataset: "public dataset",
};

const caseIds = ["stable", "font-metric", "css-overlap", "self-ref", "combined"];

function normalize(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

function parseFromText(text) {
  const normalized = normalize(text);
  return {
    project: normalize(
      normalized.match(/Project:\s*([^:]+?)(?=\s+Launch window:|\s+Dataset:|$)/i)?.[1] || "",
    ),
    launch_window: normalize(
      normalized.match(/Launch window:\s*([^:]+?)(?=\s+Project:|\s+Dataset:|$)/i)?.[1] || "",
    ),
    dataset: normalize(
      normalized.match(/Dataset:\s*([^:]+?)(?=\s+Project:|\s+Launch window:|$)/i)?.[1] || "",
    ),
  };
}

function score(parsed) {
  const fields = Object.keys(expected);
  const exact = fields.filter((field) => parsed[field] === expected[field]).length;
  const decoys = fields.filter((field) => parsed[field] === decoy[field]).length;
  const missing = fields.filter((field) => !parsed[field]).length;
  return { exact, decoys, missing, rate: Number((exact / fields.length).toFixed(4)) };
}

function encodeValue(value, key) {
  return [...value].map((char, index) => char.charCodeAt(0) ^ ((key + index * 17) & 255));
}

function encodedPack() {
  const key = 91;
  const fields = Object.keys(expected);
  return {
    key,
    fields,
    labels: {
      project: "Project:",
      launch_window: "Launch window:",
      dataset: "Dataset:",
    },
    slots: Object.fromEntries(
      fields.map((field) => [
        field,
        [
          { q: encodeValue(decoy[field], key), t: "m0" },
          { q: encodeValue(expected[field], key), t: "m1" },
        ],
      ]),
    ),
  };
}

function renderFixture() {
  const pack = JSON.stringify(encodedPack());
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Computational gap fixture</title>
  <style>
    body { font: 16px Arial, sans-serif; margin: 24px; color: #202124; }
    section.case { margin: 0 0 28px; padding: 0; }
    h2 { font-size: 18px; margin: 0 0 10px; }
    .row { display: grid; grid-template-columns: 150px 260px; gap: 12px; height: 26px; align-items: baseline; }
    .label { font-weight: 700; }
    .overlap-board { position: relative; width: 460px; height: 86px; }
    .overlap-board span {
      position: absolute;
      display: block;
      background: white;
      line-height: 22px;
      padding: 0 2px;
    }
    .overlap-board .x0 { color: #fff; background: #fff; z-index: 1; }
    .overlap-board .x1 { color: #202124; z-index: 4; }
    .combined-source { position: absolute; left: -9999px; top: 0; }
  </style>
</head>
<body>
  <main>
    <section class="case" id="stable">
      <h2>Stable baseline</h2>
      <p>Project: Alpha project Launch window: Friday morning Dataset: private dataset</p>
    </section>

    <section class="case computed" id="font-metric">
      <h2>Font metric mapping</h2>
      <div class="row"><span class="label">Project:</span><span class="slot" data-field="project"></span></div>
      <div class="row"><span class="label">Launch window:</span><span class="slot" data-field="launch_window"></span></div>
      <div class="row"><span class="label">Dataset:</span><span class="slot" data-field="dataset"></span></div>
    </section>

    <section class="case" id="css-overlap">
      <h2>CSS overlap encoding</h2>
      <div class="overlap-board">
        <span class="x0" data-field="project" data-pack="0" style="left:0;top:0"></span>
        <span class="x0" data-field="launch_window" data-pack="0" style="left:0;top:28px"></span>
        <span class="x0" data-field="dataset" data-pack="0" style="left:0;top:56px"></span>
        <span class="x1" data-visible-text data-field="project" data-pack="1" style="left:0;top:0"></span>
        <span class="x1" data-visible-text data-field="launch_window" data-pack="1" style="left:0;top:28px"></span>
        <span class="x1" data-visible-text data-field="dataset" data-pack="1" style="left:0;top:56px"></span>
      </div>
    </section>

    <section class="case computed" id="self-ref">
      <h2>Self reference ordering</h2>
      <div class="row"><span class="label">Project:</span><span class="slot" data-field="project"></span></div>
      <div class="row"><span class="label">Launch window:</span><span class="slot" data-field="launch_window"></span></div>
      <div class="row"><span class="label">Dataset:</span><span class="slot" data-field="dataset"></span></div>
    </section>

    <section class="case computed" id="combined">
      <h2>Combined rendering gate</h2>
      <div class="combined-source">
        Project: Omega project Launch window: Monday night Dataset: public dataset
      </div>
      <div class="row"><span class="label">Project:</span><span class="slot" data-field="project"></span></div>
      <div class="row"><span class="label">Launch window:</span><span class="slot" data-field="launch_window"></span></div>
      <div class="row"><span class="label">Dataset:</span><span class="slot" data-field="dataset"></span></div>
    </section>
  </main>

  <script type="application/json" id="payload">${pack}</script>

  <script>
    (() => {
      const payload = JSON.parse(document.querySelector("#payload").textContent);

      function decode(entry) {
        return entry.q
          .map((code, index) => String.fromCharCode(code ^ ((payload.key + index * 17) & 255)))
          .join("");
      }

      function hash(text) {
        let value = 2166136261;
        for (let i = 0; i < text.length; i += 1) {
          value ^= text.charCodeAt(i);
          value = Math.imul(value, 16777619);
        }
        return value >>> 0;
      }

      function materialize(field, entryIndex) {
        const entry = payload.slots[field][entryIndex];
        return payload.labels[field] + " " + decode(entry);
      }

      function targetIndex(field, salt) {
        const candidates = payload.slots[field];
        const anchor = hash(decode(candidates[1])) ^ salt;
        let best = 0;
        let bestDistance = Infinity;
        candidates.forEach((candidate, index) => {
          const distance = Math.abs((hash(decode(candidate)) ^ salt) - anchor);
          if (distance < bestDistance) {
            best = index;
            bestDistance = distance;
          }
        });
        return best;
      }

      function chooseByFontMetric(section) {
        const canvas = document.createElement("canvas");
        const ctx = canvas.getContext("2d");
        ctx.font = getComputedStyle(document.body).font;
        section.querySelectorAll(".slot").forEach((slot) => {
          const field = slot.dataset.field;
          const width = Math.round(ctx.measureText(field + ":" + section.id).width);
          slot.textContent = decode(payload.slots[field][targetIndex(field, width)]);
        });
      }

      function fillOverlap(section) {
        section.querySelectorAll("[data-pack]").forEach((node) => {
          node.textContent = materialize(node.dataset.field, Number(node.dataset.pack));
        });
      }

      function chooseBySelfReference(section) {
        const probe = document.createElement("div");
        probe.style.cssText = "position:absolute;visibility:hidden;overflow:scroll;width:99px;height:99px;";
        document.body.appendChild(probe);
        const scrollbar = probe.offsetWidth - probe.clientWidth;
        const seed = (section.getBoundingClientRect().height + scrollbar + window.innerWidth) % 2;
        document.body.removeChild(probe);
        section.querySelectorAll(".slot").forEach((slot) => {
          const field = slot.dataset.field;
          slot.textContent = decode(payload.slots[field][targetIndex(field, seed)]);
        });
      }

      document.addEventListener("DOMContentLoaded", () => {
        chooseByFontMetric(document.querySelector("#font-metric"));
        fillOverlap(document.querySelector("#css-overlap"));
        chooseBySelfReference(document.querySelector("#self-ref"));
        chooseByFontMetric(document.querySelector("#combined"));
      });
    })();
  </script>
</body>
</html>`;
}

function extractCaseHtml(html, id) {
  const $ = cheerio.load(html);
  return `<!doctype html>
<html>
<head>${$("head").html()}</head>
<body>${$(`#${id}`).prop("outerHTML")}
${$("body > script").prop("outerHTML") || ""}
</body>
</html>`;
}

const staticParsers = {
  "cheerio-body-text": (html, selector = "body") => parseFromText(cheerio.load(html)(selector).text()),
  "cheerio-visible-ish": (html, selector = "body") => {
    const $ = cheerio.load(html);
    $("script, style, .decoy, .combined-source").remove();
    return parseFromText($(selector).text());
  },
  "jsdom-no-script": (html, selector = "body") => {
    const dom = new JSDOM(html);
    return parseFromText(dom.window.document.querySelector(selector)?.textContent || "");
  },
};

async function renderedRows(html) {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
  await page.setContent(html, { waitUntil: "load" });
  await page.waitForTimeout(100);

  const rows = await page.$$eval("section.case", (sections) =>
    sections.map((section) => {
      const topMostTexts = [...section.querySelectorAll("[data-visible-text], .row")]
        .map((el) => {
          const rect = el.getBoundingClientRect();
          const x = rect.left + Math.min(rect.width - 1, Math.max(1, rect.width / 2));
          const y = rect.top + Math.min(rect.height - 1, Math.max(1, rect.height / 2));
          const top = document.elementFromPoint(x, y);
          if (top !== el && !el.contains(top)) return "";
          const style = getComputedStyle(el);
          if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) {
            return "";
          }
          return el.innerText || el.textContent || "";
        })
        .filter(Boolean)
        .join(" ");

      return {
        id: section.id,
        innerText: section.innerText,
        topMostText: topMostTexts,
      };
    }),
  );

  await browser.close();
  return rows;
}

function time(fn) {
  const start = performance.now();
  const value = fn();
  return { value, ms: performance.now() - start };
}

function summarize(times) {
  const sorted = [...times].sort((a, b) => a - b);
  const avg = sorted.reduce((sum, value) => sum + value, 0) / sorted.length;
  return {
    avgMs: Number(avg.toFixed(4)),
    p50Ms: Number(sorted[Math.floor(sorted.length * 0.5)].toFixed(4)),
    p95Ms: Number(sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))].toFixed(4)),
  };
}

async function main() {
  const html = renderFixture();
  fs.writeFileSync(fixturePath, html);

  const staticResults = {};
  for (const [name, parser] of Object.entries(staticParsers)) {
    staticResults[name] = {};
    for (const id of caseIds) {
      const parsed = parser(html, `#${id}`);
      staticResults[name][id] = { parsed, score: score(parsed) };
    }
  }

  const rendered = await renderedRows(html);
  const renderedResults = Object.fromEntries(
    rendered.map((row) => [
      row.id,
      {
        innerText: { parsed: parseFromText(row.innerText), score: score(parseFromText(row.innerText)) },
        topMostText: { parsed: parseFromText(row.topMostText), score: score(parseFromText(row.topMostText)) },
      },
    ]),
  );

  const staticCost = {};
  for (const [name, parser] of Object.entries(staticParsers)) {
    const times = [];
    for (let i = 0; i < iterations; i += 1) {
      times.push(time(() => parser(html)).ms);
    }
    staticCost[name] = summarize(times);
  }

  const renderTimes = [];
  for (let i = 0; i < Math.max(3, Math.min(iterations, 12)); i += 1) {
    const start = performance.now();
    await renderedRows(html);
    renderTimes.push(performance.now() - start);
  }

  console.log(
    JSON.stringify(
      {
        fixture: fixturePath,
        expected,
        iterations,
        staticResults,
        renderedResults,
        cost: {
          staticParsers: staticCost,
          playwrightFullRenderAndExtract: summarize(renderTimes),
        },
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
  caseIds,
  decoy,
  expected,
  extractCaseHtml,
  renderFixture,
};
