const fs = require("node:fs");
const { performance } = require("node:perf_hooks");
let chromium;
try {
  ({ chromium } = require("playwright"));
} catch (error) {
  ({ chromium } = require("C:/Users/jungseobum/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright"));
}
const { buildHtml, fieldSet } = require("./benchmark_sensitive_field_template");

const outArg = process.argv.includes("--out") ? process.argv[process.argv.indexOf("--out") + 1] : null;
const fieldCount = Number(process.env.FIELD_COUNT || 5);
const chromePath = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";

function normalize(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function stripTags(html) {
  return normalize(
    html
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<[^>]+>/g, " "),
  );
}

function sourceString(html) {
  return normalize(html);
}

function scoreText(text, expectedValues) {
  const haystack = normalize(text);
  let exact = 0;
  const fieldStatus = {};
  for (const [field, expected] of Object.entries(expectedValues)) {
    if (haystack.includes(expected)) {
      exact += 1;
      fieldStatus[field] = "exact";
    } else {
      fieldStatus[field] = "missing";
    }
  }
  const fields = Object.keys(expectedValues).length;
  return {
    fields,
    exact,
    missing: fields - exact,
    leakageRate: Number((exact / fields).toFixed(4)),
    fieldStatus,
  };
}

async function renderedText(html, interaction = "none") {
  const browser = await chromium.launch({ headless: true, executablePath: chromePath });
  const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
  await page.setContent(html, { waitUntil: "load" });
  await page.waitForTimeout(50);

  if (interaction === "sequence") {
    const section = page.locator(".details");
    const box = await section.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + 18, { steps: 8 });
    await page.waitForTimeout(650);
    await page.mouse.move(box.x + box.width / 2 + 32, box.y + 24, { steps: 4 });
    await page.mouse.click(box.x + box.width / 2 + 32, box.y + 24);
    await page.waitForTimeout(50);
  }

  const text = await page.locator("body").innerText();
  await browser.close();
  return text;
}

function buildLayer1OnlyHtml(active) {
  const labels = active.fields
    .map((field) => `<div class="meta-row"><span class="label">${active.labels[field]}</span><span class="value" data-k="${field}">${active.placeholders[field]}</span></div>`)
    .join("\n");
  const payload = JSON.stringify(active.values);
  return `<!doctype html>
<html>
<head><meta charset="utf-8"><title>Layer ablation</title></head>
<body>
  <main>
    <h1>Alpha Research Portal</h1>
    <p>Public overview content for indexing.</p>
    <section class="details" tabindex="0">${labels}</section>
  </main>
  <script type="application/json" id="payload">${payload}</script>
  <script>
    (() => {
      const values = JSON.parse(document.querySelector("#payload").textContent);
      document.addEventListener("DOMContentLoaded", () => {
        document.querySelectorAll("[data-k]").forEach((node) => {
          node.textContent = values[node.dataset.k];
        });
      });
    })();
  </script>
</body>
</html>`;
}

function buildLayer2OnlyHtml(active) {
  const labels = active.fields
    .map((field) => `<div class="meta-row"><span class="label">${active.labels[field]}</span><span class="value" data-k="${field}" data-value="${active.values[field]}">${active.placeholders[field]}</span></div>`)
    .join("\n");
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Layer ablation</title>
  <style>body { font: 16px Arial, sans-serif; margin: 32px; } .details { border-top: 1px solid #ddd; padding-top: 14px; }</style>
</head>
<body>
  <main>
    <h1>Alpha Research Portal</h1>
    <p>Public overview content for indexing.</p>
    <section class="details" tabindex="0">${labels}</section>
  </main>
  <script>
    (() => {
      const sectionState = { pointerInside: false, enteredAt: 0, moves: 0, focusedAt: 0, revealed: false };
      function reveal() {
        if (sectionState.revealed) return;
        sectionState.revealed = true;
        document.querySelectorAll("[data-k]").forEach((node) => {
          node.textContent = node.dataset.value;
        });
      }
      document.addEventListener("DOMContentLoaded", () => {
        const section = document.querySelector(".details");
        const contains = (node) => section === node || section.contains(node);
        const visibleTarget = (event) => {
          if (!contains(event.target)) return false;
          if (typeof event.clientX !== "number" || typeof event.clientY !== "number") return true;
          if (event.clientX === 0 && event.clientY === 0) return false;
          return contains(document.elementFromPoint(event.clientX, event.clientY));
        };
        section.addEventListener("pointerenter", (event) => {
          if (!visibleTarget(event)) return;
          sectionState.pointerInside = true;
          sectionState.enteredAt = performance.now();
          sectionState.moves = 0;
        });
        section.addEventListener("pointermove", (event) => {
          if (!sectionState.pointerInside || !visibleTarget(event)) return;
          sectionState.moves += 1;
        });
        section.addEventListener("click", (event) => {
          if (sectionState.pointerInside && sectionState.moves >= 2 && performance.now() - sectionState.enteredAt >= 500 && visibleTarget(event)) reveal();
        });
        section.addEventListener("focusin", () => {
          sectionState.focusedAt = performance.now();
        });
        section.addEventListener("keydown", (event) => {
          if ((event.key === "Enter" || event.key === " ") && performance.now() - sectionState.focusedAt >= 300) reveal();
        });
      });
    })();
  </script>
</body>
</html>`;
}

async function main() {
  const active = fieldSet({ fieldCount });
  const variants = {
    layer1Only: buildLayer1OnlyHtml(active),
    layer2Only: buildLayer2OnlyHtml(active),
    layer1PlusLayer2: buildHtml({
      gated: true,
      placeholder: true,
      interactionGate: true,
      interactionGateMode: "sequence",
      fieldCount,
      liveRegionMode: "section",
    }),
  };

  const started = performance.now();
  const results = [];
  for (const [variant, html] of Object.entries(variants)) {
    const staticFullSource = sourceString(html);
    const staticVisibleText = stripTags(html);
    const renderOnlyText = await renderedText(html, "none");
    const interactedText = await renderedText(html, "sequence");
    results.push({
      variant,
      staticFullSource: scoreText(staticFullSource, active.values),
      staticVisibleText: scoreText(staticVisibleText, active.values),
      renderOnly: scoreText(renderOnlyText, active.values),
      afterSequenceInteraction: scoreText(interactedText, active.values),
    });
  }

  const report = {
    generatedAt: new Date().toISOString(),
    config: { fieldCount },
    elapsedMs: Number((performance.now() - started).toFixed(3)),
    results,
  };
  const output = JSON.stringify(report, null, 2);
  if (outArg) fs.writeFileSync(outArg, `${output}\n`, "utf8");
  console.log(output);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
