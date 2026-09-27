const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");
const {
  buildHtml,
  publicRecord,
  sensitive,
} = require("./benchmark_sensitive_field_template");
const { buildPlacementVariants } = require("./benchmark_script_placement_context");

const llmResultPath = path.join(__dirname, "gemini_sensitive_template_results.json");
const outJson = path.join(__dirname, "final_candidate_audit.json");
const outMd = path.join(__dirname, "scorecard.md");

function normalize(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

function stripHtml(html) {
  return normalize(
    html
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<[^>]+>/g, " "),
  );
}

function coverage(text, values) {
  const haystack = normalize(text).toLowerCase();
  const foundValues = Object.values(values).filter((value) =>
    haystack.includes(normalize(value).toLowerCase()),
  );
  return {
    found: foundValues.length,
    total: Object.keys(values).length,
    rate: Number((foundValues.length / Object.keys(values).length).toFixed(4)),
    values: foundValues,
  };
}

function placeholders() {
  return {
    owner_email: "Available on request",
    direct_phone: "Contact team",
    internal_case_id: "Restricted",
    restricted_dataset: "Access required",
    contract_floor: "Not publicly listed",
  };
}

function splitValue(value) {
  const text = String(value);
  const a = Math.ceil(text.length / 3);
  const b = Math.ceil((text.length - a) / 2);
  return [text.slice(0, a), text.slice(a, a + b), text.slice(a + b)];
}

function sensitivePartExposure(html) {
  const exposures = Object.entries(sensitive).map(([field, value]) => {
    const parts = splitValue(value);
    const found = parts.filter((part) => part && html.includes(part));
    return { field, found: found.length, total: parts.length };
  });
  const found = exposures.reduce((sum, item) => sum + item.found, 0);
  const total = exposures.reduce((sum, item) => sum + item.total, 0);
  return { found, total, rate: Number((found / total).toFixed(4)), exposures };
}

async function renderedText(html, { interact = false } = {}) {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
  await page.setContent(html, { waitUntil: "load" });
  await page.waitForTimeout(50);
  if (interact) {
    await page.locator(".details").hover({ force: true });
    await page.waitForTimeout(50);
  }
  const text = await page.locator("body").innerText();
  await browser.close();
  return text;
}

function readLlmResult() {
  if (!fs.existsSync(llmResultPath)) return { status: "not_run" };
  const data = JSON.parse(fs.readFileSync(llmResultPath, "utf8"));
  const bucket = data.summary?.byVariant?.placeholderGated;
  if (!bucket) return { status: "missing_placeholderGated", file: llmResultPath };
  return {
    status: "ok",
    provider: data.provider,
    model: data.model,
    leakageRate: bucket.leakageRate,
    safeFailureRate: bucket.safeFailureRate,
    unsafeFailureRate: bucket.unsafeFailureRate,
    raw: bucket,
  };
}

function passFail(condition) {
  return condition ? "pass" : "fail";
}

function buildMarkdown(report) {
  const rows = report.scorecard.map(
    (row) => `| ${row.area} | ${row.status} | ${row.summary} |`,
  );
  return `# Final Candidate Scorecard

Candidate: \`${report.candidate}\`

| Area | Status | Summary |
| --- | --- | --- |
${rows.join("\n")}

## Threat Model

Blocks:
- source-only/static parsers
- LLM-only extraction under the tested Gemini prompt
- no-JS extraction of selected sensitive fields
- render-only crawlers that do not generate user intent events

Does not block:
- code-execution bots that inspect the external JS
- headless browsers that execute the runtime and explore interactions
- targeted analysis of the runtime bundle

## Notes

- Public content remains static/indexable.
- Sensitive fields use non-value placeholders in source.
- Sensitive fields require a user intent event before runtime hydration.
- External runtime-like placement reduces HTML fingerprint, but it is not cryptographic protection.
- Do not impersonate vendor namespaces, URLs, or brands.
`;
}

async function main() {
  const inlineHtml = buildHtml({ gated: true, placeholder: true, interactionGate: true });
  const sourceText = stripHtml(inlineHtml);
  const renderedNoInteraction = await renderedText(inlineHtml);
  const renderedAfterIntent = await renderedText(inlineHtml, { interact: true });
  const placement = buildPlacementVariants();
  const externalRuntime = placement.externalRuntimeLike;
  const llm = readLlmResult();

  const source = {
    publicCoverage: coverage(sourceText, publicRecord),
    sensitiveLeakage: coverage(sourceText, sensitive),
    sensitivePartExposure: sensitivePartExposure(inlineHtml),
    placeholderCoverage: coverage(sourceText, placeholders()),
  };
  const render = {
    noInteraction: {
      publicCoverage: coverage(renderedNoInteraction, publicRecord),
      sensitiveVisibility: coverage(renderedNoInteraction, sensitive),
      placeholderVisibility: coverage(renderedNoInteraction, placeholders()),
    },
    afterIntent: {
      publicCoverage: coverage(renderedAfterIntent, publicRecord),
      sensitiveVisibility: coverage(renderedAfterIntent, sensitive),
      placeholderAfterRender: coverage(renderedAfterIntent, placeholders()),
    },
  };
  const placementAudit = {
    html: externalRuntime.html,
    js: externalRuntime.js,
  };

  const scorecard = [
    {
      area: "Public SEO Content",
      status: passFail(source.publicCoverage.rate === 1),
      summary: `source publicCoverage=${source.publicCoverage.rate}`,
    },
    {
      area: "Source Sensitive Leakage",
      status: passFail(source.sensitiveLeakage.rate === 0 && source.sensitivePartExposure.rate === 0),
      summary: `full=${source.sensitiveLeakage.rate}, parts=${source.sensitivePartExposure.rate}`,
    },
    {
      area: "Safe Placeholder",
      status: passFail(source.placeholderCoverage.rate === 1),
      summary: `placeholderCoverage=${source.placeholderCoverage.rate}`,
    },
    {
      area: "No-Interaction Render Gate",
      status: passFail(
        render.noInteraction.publicCoverage.rate === 1 &&
          render.noInteraction.sensitiveVisibility.rate === 0 &&
          render.noInteraction.placeholderVisibility.rate === 1,
      ),
      summary: `public=${render.noInteraction.publicCoverage.rate}, sensitive=${render.noInteraction.sensitiveVisibility.rate}, placeholders=${render.noInteraction.placeholderVisibility.rate}`,
    },
    {
      area: "After-Intent Rendered UX",
      status: passFail(
        render.afterIntent.publicCoverage.rate === 1 &&
          render.afterIntent.sensitiveVisibility.rate === 1 &&
          render.afterIntent.placeholderAfterRender.rate === 0,
      ),
      summary: `public=${render.afterIntent.publicCoverage.rate}, sensitive=${render.afterIntent.sensitiveVisibility.rate}, placeholders=${render.afterIntent.placeholderAfterRender.rate}`,
    },
    {
      area: "LLM-only Extraction",
      status: passFail(llm.status === "ok" && llm.leakageRate === 0 && llm.safeFailureRate === 1),
      summary:
        llm.status === "ok"
          ? `${llm.provider}/${llm.model}: leakage=${llm.leakageRate}, safe=${llm.safeFailureRate}, unsafe=${llm.unsafeFailureRate}`
          : `status=${llm.status}`,
    },
    {
      area: "HTML Placement Fingerprint",
      status: passFail(
        placementAudit.html.inlineScriptBytes === 0 &&
          placementAudit.html.externalScriptCount === 1 &&
          Object.values(placementAudit.html.inlineSuspiciousCounts).every((value) => value === 0),
      ),
      summary: `inlineScriptBytes=${placementAudit.html.inlineScriptBytes}, externalScriptCount=${placementAudit.html.externalScriptCount}`,
    },
    {
      area: "External Runtime Context",
      status: passFail(
        placementAudit.js.rawBytes >= 39000 &&
          placementAudit.js.counts.fromCharCode <= 1 &&
          placementAudit.js.counts.bitwiseOperators >= 1000,
      ),
      summary: `jsBytes=${placementAudit.js.rawBytes}, fromCharCode=${placementAudit.js.counts.fromCharCode}, bitwise=${placementAudit.js.counts.bitwiseOperators}`,
    },
  ];

  const report = {
    candidate: "placeholderGated + non-value placeholders + interaction gate + external runtime-like placement",
    generatedAt: new Date().toISOString(),
    source,
    render,
    llm,
    placement: placementAudit,
    scorecard,
    threatModel: {
      blocks: ["source-only parser", "LLM-only tested parser", "no-JS extraction", "render-only crawler without user intent events"],
      doesNotBlock: ["code-execution bot", "headless browser with interaction exploration", "targeted runtime analysis"],
    },
  };

  fs.writeFileSync(outJson, JSON.stringify(report, null, 2));
  fs.writeFileSync(outMd, buildMarkdown(report));
  console.log(JSON.stringify(report, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
