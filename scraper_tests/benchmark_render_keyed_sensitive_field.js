const zlib = require("node:zlib");
const { chromium } = require("playwright");
const { JSDOM } = require("jsdom");
const { publicRecord, sensitive } = require("./benchmark_sensitive_field_template");

const labels = {
  owner_email: "Contact",
  direct_phone: "Desk",
  internal_case_id: "Reference",
  restricted_dataset: "Dataset",
  contract_floor: "Terms",
};

const placeholders = {
  owner_email: "Available on request",
  direct_phone: "Contact team",
  internal_case_id: "Restricted",
  restricted_dataset: "Access required",
  contract_floor: "Not publicly listed",
};

const syntheticSalts = [
  "0|0|0|0|1",
  "1|0|0|0|1",
  "17|23|29|31|1",
  "91|101|103|107|1",
  "255|257|263|269|2",
  "1024|2048|4096|8192|3",
];

function htmlEscape(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function hash32(text) {
  let value = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    value ^= text.charCodeAt(i);
    value = Math.imul(value, 16777619);
  }
  return value >>> 0;
}

function byteFor(salt, field, index) {
  let value = hash32(`${salt}|${field}|${index}`);
  value ^= value >>> 16;
  value = Math.imul(value, 2246822519);
  value ^= value >>> 13;
  return value & 255;
}

function encodeValue(value, salt, field) {
  return [...String(value)].map((char, index) => char.charCodeAt(0) ^ byteFor(salt, field, index));
}

function decodeValue(codes, salt, field) {
  return codes.map((code, index) => String.fromCharCode(code ^ byteFor(salt, field, index))).join("");
}

function renderShell(body, extra = "") {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>${htmlEscape(publicRecord.title)}</title>
  <meta name="description" content="${htmlEscape(publicRecord.summary)}">
  <style>
    body { font: 16px Arial, sans-serif; margin: 32px; color: #202124; line-height: 1.5; }
    main { max-width: 760px; }
    h1 { font-size: 28px; margin: 0 0 12px; }
    .summary { font-size: 18px; margin: 0 0 18px; }
    .content { margin: 0 0 24px; }
    .details { border-top: 1px solid #ddd; padding-top: 14px; }
    .meta-row { display: grid; grid-template-columns: 150px 1fr; min-height: 24px; gap: 12px; }
    .label { font-weight: 700; }
  </style>
</head>
<body>
  <main>
    <article>
      <h1>${htmlEscape(publicRecord.title)}</h1>
      <p class="summary">${htmlEscape(publicRecord.summary)}</p>
      <p class="content">${htmlEscape(publicRecord.body)}</p>
      <p class="category">Category: ${htmlEscape(publicRecord.category)}</p>
      <section class="details" aria-label="Additional details">
        ${body}
      </section>
    </article>
  </main>
  ${extra}
</body>
</html>`;
}

function sensitiveRows() {
  return Object.entries(labels)
    .map(
      ([field, label]) =>
        `<div class="meta-row"><span class="label">${htmlEscape(label)}</span><span class="value" data-k="${field}">${htmlEscape(placeholders[field])}</span></div>`,
    )
    .join("\n");
}

async function computeBrowserSalt(html) {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 900, height: 700 }, deviceScaleFactor: 1 });
  await page.setContent(html, { waitUntil: "load" });
  const salt = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    ctx.font = getComputedStyle(document.body).font;
    const row = document.querySelector(".meta-row");
    const main = document.querySelector("main");
    const rowRect = row.getBoundingClientRect();
    const mainRect = main.getBoundingClientRect();
    const a = Math.round(ctx.measureText(document.title).width * 100);
    const b = Math.round(ctx.measureText(document.querySelector(".summary").textContent).width * 100);
    const c = Math.round(rowRect.height * 100);
    const d = Math.round(mainRect.width * 100);
    const e = Math.round(window.devicePixelRatio * 100);
    return `${a}|${b}|${c}|${d}|${e}`;
  });
  await browser.close();
  return salt;
}

async function computeBrowserSaltWithPage(page) {
  return page.evaluate(() => {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    ctx.font = getComputedStyle(document.body).font;
    const row = document.querySelector(".meta-row");
    const main = document.querySelector("main");
    const rowRect = row.getBoundingClientRect();
    const mainRect = main.getBoundingClientRect();
    const a = Math.round(ctx.measureText(document.title).width * 100);
    const b = Math.round(ctx.measureText(document.querySelector(".summary").textContent).width * 100);
    const c = Math.round(rowRect.height * 100);
    const d = Math.round(mainRect.width * 100);
    const e = Math.round(window.devicePixelRatio * 100);
    return {
      salt: `${a}|${b}|${c}|${d}|${e}`,
      components: {
        titleWidth100: a,
        summaryWidth100: b,
        rowHeight100: c,
        mainWidth100: d,
        dpr100: e,
      },
    };
  });
}

function buildHtml(renderSalt) {
  const payload = {
    rows: Object.fromEntries(
      Object.entries(sensitive).map(([field, value]) => [field, encodeValue(value, renderSalt, field)]),
    ),
  };
  const script = `<script type="application/json" id="page-data">${JSON.stringify(payload)}</script>
  <script>
    (() => {
      const data = JSON.parse(document.querySelector("#page-data").textContent);
      function h(text) {
        let value = 2166136261;
        for (let i = 0; i < text.length; i += 1) {
          value ^= text.charCodeAt(i);
          value = Math.imul(value, 16777619);
        }
        return value >>> 0;
      }
      function b(salt, field, index) {
        let value = h(salt + "|" + field + "|" + index);
        value ^= value >>> 16;
        value = Math.imul(value, 2246822519);
        value ^= value >>> 13;
        return value & 255;
      }
      function salt() {
        const canvas = document.createElement("canvas");
        const ctx = canvas.getContext("2d");
        ctx.font = getComputedStyle(document.body).font;
        const row = document.querySelector(".meta-row");
        const main = document.querySelector("main");
        const rowRect = row.getBoundingClientRect();
        const mainRect = main.getBoundingClientRect();
        return [
          Math.round(ctx.measureText(document.title).width * 100),
          Math.round(ctx.measureText(document.querySelector(".summary").textContent).width * 100),
          Math.round(rowRect.height * 100),
          Math.round(mainRect.width * 100),
          Math.round(window.devicePixelRatio * 100)
        ].join("|");
      }
      function read(codes, field, saltValue) {
        return codes.map((code, index) => String.fromCharCode(code ^ b(saltValue, field, index))).join("");
      }
      document.addEventListener("DOMContentLoaded", () => {
        const saltValue = salt();
        document.querySelectorAll("[data-k]").forEach((node) => {
          node.textContent = read(data.rows[node.dataset.k], node.dataset.k, saltValue);
        });
      });
    })();
  </script>`;
  return renderShell(sensitiveRows(), script);
}

function stripHtml(html) {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function leakage(text) {
  const lower = text.toLowerCase();
  const leaked = Object.values(sensitive).filter((value) => lower.includes(value.toLowerCase()));
  return { leaked: leaked.length, total: Object.keys(sensitive).length, rate: leaked.length / Object.keys(sensitive).length };
}

function printableRatio(text) {
  const chars = [...String(text)];
  return chars.filter((char) => /[\x20-\x7e]/.test(char)).length / Math.max(1, chars.length);
}

function looksPlausible(text) {
  return printableRatio(text) > 0.9 && /[A-Za-z0-9@$+.-]/.test(text);
}

function hammingDistance(a, b) {
  const left = [...String(a)];
  const right = [...String(b)];
  const max = Math.max(left.length, right.length);
  let distance = Math.abs(left.length - right.length);
  for (let i = 0; i < Math.min(left.length, right.length); i += 1) {
    if (left[i] !== right[i]) distance += 1;
  }
  return max ? distance / max : 0;
}

function auditPayload(renderSalt) {
  const firstField = Object.keys(sensitive)[0];
  const codes = encodeValue(sensitive[firstField], renderSalt, firstField);
  const outputs = syntheticSalts.map((salt) => decodeValue(codes, salt, firstField));
  const bruteSalts = Array.from({ length: 256 }, (_, index) => String(index));
  const bruteOutputs = bruteSalts.map((salt) => decodeValue(codes, salt, firstField));
  return {
    field: firstField,
    trueSalt: renderSalt,
    syntheticUniqueOutputs: new Set(outputs).size,
    plusOneDistance: Number(hammingDistance(decodeValue(codes, renderSalt, firstField), decodeValue(codes, `${renderSalt}|x`, firstField)).toFixed(4)),
    syntheticOutputsLookPlausible: outputs.filter(looksPlausible).length,
    bruteForce256: {
      exactMatches: bruteOutputs.filter((output) => output === sensitive[firstField]).length,
      uniqueOutputs: new Set(bruteOutputs).size,
      plausibleOutputs: bruteOutputs.filter(looksPlausible).length,
    },
  };
}

async function renderedLeakage(html) {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 900, height: 700 }, deviceScaleFactor: 1 });
  await page.setContent(html, { waitUntil: "load" });
  await page.waitForTimeout(50);
  const text = await page.locator("body").innerText();
  await browser.close();
  return leakage(text);
}

function jsdomProbe(html) {
  const dom = new JSDOM(html, { pretendToBeVisual: true });
  const { document, window } = dom.window;
  try {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx?.measureText) return { canReproduce: false, reason: "canvas.measureText unavailable" };
    return { canReproduce: true };
  } catch (error) {
    return { canReproduce: false, error: String(error.message || error) };
  }
}

async function main() {
  const calibrationShell = renderShell(sensitiveRows());
  const renderSalt = await computeBrowserSalt(calibrationShell);
  const html = buildHtml(renderSalt);
  const sourceText = stripHtml(html);
  const rendered = await renderedLeakage(html);
  const rawBytes = Buffer.byteLength(html, "utf8");
  const gzipBytes = zlib.gzipSync(html).length;
  console.log(
    JSON.stringify(
      {
        renderSalt,
        source: {
          leakage: leakage(sourceText),
          rawBytes,
          gzipBytes,
          patterns: {
            fromCharCode: (html.match(/fromCharCode/g) || []).length,
            xorOperator: (html.match(/\^/g) || []).length,
            measureText: (html.match(/measureText/g) || []).length,
            jsonPayload: (html.match(/application\/json/g) || []).length,
          },
        },
        rendered: {
          leakage: rendered,
        },
        audit: auditPayload(renderSalt),
        jsdomProbe: jsdomProbe(html),
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
  computeBrowserSalt,
  computeBrowserSaltWithPage,
  decodeValue,
  encodeValue,
  labels,
  leakage,
  placeholders,
  publicRecord,
  renderShell,
  sensitive,
  sensitiveRows,
};
