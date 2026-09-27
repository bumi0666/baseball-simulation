const fs = require("node:fs/promises");
const path = require("node:path");

const provider = process.env.LLM_PROVIDER || "openai";
const model =
  process.env.LLM_MODEL ||
  (provider === "anthropic"
    ? "claude-3-5-sonnet-latest"
    : provider === "gemini"
      ? "gemini-2.5-flash"
      : "gpt-4.1-mini");
const samples = Number(process.env.SAMPLES || 3);
const recordCount = Number(process.env.RECORDS || 12);

const fields = [
  "project",
  "launch_window",
  "dataset",
  "owner",
  "region",
  "budget",
  "status",
  "priority",
];

const modes = {
  stable: { split: false, decoy: false, zeroWidth: false, prose: false },
  splitOnly: { split: true, decoy: false, zeroWidth: false, prose: false },
  splitPlusDecoy: { split: true, decoy: true, zeroWidth: false, prose: false },
  splitPlusZeroWidth: { split: true, decoy: false, zeroWidth: true, prose: false },
  splitPlusDecoyZeroWidth: { split: true, decoy: true, zeroWidth: true, prose: false },
  splitPlusDecoyZeroWidthProse: { split: true, decoy: true, zeroWidth: true, prose: true },
};

function parseArgs(argv) {
  const args = argv.slice(2);
  const outIndex = args.indexOf("--out");
  const modeIndex = args.indexOf("--mode");
  const limitIndex = args.indexOf("--limit");
  return {
    out: outIndex >= 0 ? args[outIndex + 1] : null,
    mode: modeIndex >= 0 ? args[modeIndex + 1] : null,
    limit: limitIndex >= 0 ? Number(args[limitIndex + 1]) : null,
  };
}

function expectedRecords() {
  return Array.from({ length: recordCount }, (_, index) => {
    const n = index + 1;
    return {
      id: `R${String(n).padStart(3, "0")}`,
      project: `Alpha project ${String(n).padStart(2, "0")}`,
      launch_window: [
        "Friday morning",
        "Friday evening",
        "Monday morning",
        "Monday night",
        "Thursday dawn",
        "Sunday noon",
      ][index % 6],
      dataset: ["private dataset", "restricted dataset", "internal dataset"][index % 3],
      owner: ["Mina Park", "Jules Kim", "Noah Choi", "Iris Han"][index % 4],
      region: ["Seoul", "Busan", "Incheon", "Daejeon"][index % 4],
      budget: `$${(12000 + index * 750).toLocaleString("en-US")}`,
      status: ["draft", "approved", "pending", "blocked"][index % 4],
      priority: ["P0", "P1", "P2"][index % 3],
    };
  });
}

function decoyFor(record, field, index) {
  const decoys = {
    project: `Beta project ${String(index + 1).padStart(2, "0")}`,
    launch_window: ["Tuesday morning", "Wednesday evening", "Saturday night"][index % 3],
    dataset: ["public dataset", "sample dataset", "archived dataset"][index % 3],
    owner: ["Alex Moon", "Dana Lee", "Robin Kwon"][index % 3],
    region: ["Tokyo", "Taipei", "Singapore"][index % 3],
    budget: `$${(5000 + index * 600).toLocaleString("en-US")}`,
    status: ["cancelled", "deferred", "review"][index % 3],
    priority: ["P3", "P4", "P5"][index % 3],
  };
  return decoys[field];
}

function zeroWidth(value) {
  return String(value).replace(/([A-Za-z0-9])(?=[A-Za-z0-9])/g, "$1&#8203;");
}

function htmlEscape(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function labelFor(field) {
  return field
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function renderRecord(record, index, options) {
  if (!options.split) {
    const rows = fields
      .map((field) => `<div class="row"><b>${labelFor(field)}:</b> <span>${htmlEscape(record[field])}</span></div>`)
      .join("\n");
    return `<section class="card"><h2>${record.id}</h2>${rows}</section>`;
  }

  const labelNodes = fields.map((field, fieldIndex) => {
    return `<span class="label" style="grid-row:${fieldIndex + 1};grid-column:1">${labelFor(field)}:</span>`;
  });
  const valueOrder = [2, 5, 0, 7, 1, 6, 3, 4];
  const valueNodes = valueOrder.map((fieldIndex) => {
    const field = fields[fieldIndex];
    const rawValue = options.zeroWidth ? zeroWidth(record[field]) : htmlEscape(record[field]);
    return `<span class="value" style="grid-row:${fieldIndex + 1};grid-column:2">${rawValue}</span>`;
  });
  const decoyNodes = options.decoy
    ? fields.map((field, fieldIndex) => {
        return `<span class="hidden-decoy" style="display:none" data-decoy="${field}">${htmlEscape(decoyFor(record, field, index))}</span>`;
      })
    : [];
  const prose = options.prose
    ? `<p class="memo">Planning note ${index + 1}: adjacent candidate windows include ${decoyFor(record, "launch_window", index)} and ${record.launch_window}; adjacent datasets mention ${decoyFor(record, "dataset", index)}.</p>`
    : "";
  const domNodes = [
    labelNodes[0],
    labelNodes[1],
    decoyNodes[1],
    labelNodes[2],
    valueNodes[0],
    labelNodes[3],
    decoyNodes[2],
    valueNodes[1],
    labelNodes[4],
    valueNodes[2],
    decoyNodes[0],
    labelNodes[5],
    valueNodes[3],
    labelNodes[6],
    decoyNodes[5],
    valueNodes[4],
    labelNodes[7],
    valueNodes[5],
    decoyNodes[6],
    valueNodes[6],
    decoyNodes[7],
    valueNodes[7],
    decoyNodes[3],
    decoyNodes[4],
  ].filter(Boolean);

  return `<section class="card"><h2>${record.id}</h2>${prose}<div class="grid">${domNodes.join("\n")}</div></section>`;
}

function buildHtml(modeName, seed) {
  const options = modes[modeName];
  const records = expectedRecords();
  const body = records.map((record, index) => renderRecord(record, index, options)).join("\n");
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Large HTML Parser Evaluation ${modeName} ${seed}</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 32px; line-height: 1.45; }
    .card { border-top: 1px solid #ddd; padding: 16px 0; max-width: 760px; }
    h2 { font-size: 18px; margin: 0 0 10px; }
    .row { margin: 4px 0; }
    .grid { display: grid; grid-template-columns: 170px 1fr; gap: 6px 14px; }
    .label { font-weight: 700; }
    .hidden-decoy { display: none; }
    .memo { color: #444; max-width: 680px; }
  </style>
</head>
<body>
  <main data-mode="${modeName}" data-seed="${seed}">
    <h1>Records</h1>
    ${body}
  </main>
</body>
</html>`;
}

function promptFor(html) {
  return `Extract the visible records from this HTML source. Return only JSON in this exact shape:
{"records":[{"id":"R001","project":"...","launch_window":"...","dataset":"...","owner":"...","region":"...","budget":"...","status":"...","priority":"..."}]}

Rules:
- Return one object per visible record id.
- Ignore hidden elements such as display:none.
- Preserve the visible field values, but normalize invisible zero-width characters if present.
- Do not include explanatory text.

HTML:
${html}`;
}

function extractJson(text) {
  const trimmed = text.trim();
  try {
    return JSON.parse(trimmed);
  } catch {
    const match = trimmed.match(/\{[\s\S]*\}/);
    if (!match) throw new Error(`No JSON object found: ${trimmed.slice(0, 200)}`);
    return JSON.parse(match[0]);
  }
}

async function callOpenAI(html) {
  if (!process.env.OPENAI_API_KEY) throw new Error("OPENAI_API_KEY is required.");
  const baseUrl = process.env.OPENAI_BASE_URL || "https://api.openai.com/v1";
  const response = await fetch(`${baseUrl}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
    },
    body: JSON.stringify({
      model,
      temperature: 0,
      response_format: { type: "json_object" },
      messages: [
        { role: "system", content: "You extract structured data from HTML. Return only valid JSON." },
        { role: "user", content: promptFor(html) },
      ],
    }),
  });
  if (!response.ok) throw new Error(`OpenAI ${response.status}: ${await response.text()}`);
  const data = await response.json();
  return extractJson(data.choices[0].message.content);
}

async function callAnthropic(html) {
  if (!process.env.ANTHROPIC_API_KEY) throw new Error("ANTHROPIC_API_KEY is required.");
  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": process.env.ANTHROPIC_API_KEY,
      "anthropic-version": process.env.ANTHROPIC_VERSION || "2023-06-01",
    },
    body: JSON.stringify({
      model,
      max_tokens: 6000,
      temperature: 0,
      system: "You extract structured data from HTML. Return only valid JSON.",
      messages: [{ role: "user", content: promptFor(html) }],
    }),
  });
  if (!response.ok) throw new Error(`Anthropic ${response.status}: ${await response.text()}`);
  const data = await response.json();
  return extractJson(data.content.map((part) => part.text || "").join(""));
}

async function callGemini(html) {
  if (!process.env.GEMINI_API_KEY) throw new Error("GEMINI_API_KEY is required.");
  const baseUrl = process.env.GEMINI_BASE_URL || "https://generativelanguage.googleapis.com/v1beta";
  const url = `${baseUrl}/models/${encodeURIComponent(model)}:generateContent?key=${encodeURIComponent(process.env.GEMINI_API_KEY)}`;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      generationConfig: {
        temperature: 0,
        responseMimeType: "application/json",
      },
      contents: [{ role: "user", parts: [{ text: `Return only valid JSON.\n\n${promptFor(html)}` }] }],
    }),
  });
  if (!response.ok) throw new Error(`Gemini ${response.status}: ${await response.text()}`);
  const data = await response.json();
  const text = data.candidates?.[0]?.content?.parts?.map((part) => part.text || "").join("") || "";
  return extractJson(text);
}

function normalize(value) {
  if (typeof value !== "string") return "";
  return value
    .normalize("NFKC")
    .replace(/[\u200b\u200c\u200d\u2060\ufeff]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function classify(actual, expected, modeOptions, recordIndex, field) {
  if (actual == null || actual === "") return "missing";
  if (actual === expected) return "exact";
  if (normalize(actual).toLowerCase() === normalize(expected).toLowerCase()) return "restored";
  if (modeOptions.decoy && normalize(actual).toLowerCase() === normalize(decoyFor({}, field, recordIndex)).toLowerCase()) {
    return "decoy";
  }
  if (/[\u200b\u200c\u200d\u2060\ufeff]/.test(String(actual))) return "confusable_or_control";
  return "wrong";
}

function score(parsed, expected, modeOptions) {
  const parsedRecords = Array.isArray(parsed?.records) ? parsed.records : [];
  const byId = new Map(parsedRecords.map((record) => [record.id, record]));
  const fieldStatus = {};
  const samples = [];
  for (const [index, expectedRecord] of expected.entries()) {
    const actualRecord = byId.get(expectedRecord.id) || {};
    for (const field of fields) {
      const key = `${expectedRecord.id}.${field}`;
      const status = classify(actualRecord[field], expectedRecord[field], modeOptions, index, field);
      fieldStatus[key] = status;
      if (status !== "exact" && samples.length < 5) {
        samples.push({ id: expectedRecord.id, field, expected: expectedRecord[field], actual: actualRecord[field], status });
      }
    }
  }
  return { fieldStatus, failureSamples: samples };
}

function makeBucket() {
  return {
    rows: 0,
    fields: 0,
    exact: 0,
    restored: 0,
    confusable_or_control: 0,
    decoy: 0,
    missing: 0,
    wrong: 0,
    invalid_json: 0,
  };
}

function summarize(results) {
  const total = makeBucket();
  const byMode = {};
  for (const result of results) {
    byMode[result.mode] ||= makeBucket();
    for (const bucket of [total, byMode[result.mode]]) {
      bucket.rows += 1;
      bucket.fields += recordCount * fields.length;
    }
    if (result.error) {
      total.invalid_json += recordCount * fields.length;
      byMode[result.mode].invalid_json += recordCount * fields.length;
      continue;
    }
    for (const status of Object.values(result.field_status)) {
      total[status] += 1;
      byMode[result.mode][status] += 1;
    }
  }
  for (const bucket of [total, ...Object.values(byMode)]) {
    bucket.exactRate = bucket.fields ? Number((bucket.exact / bucket.fields).toFixed(4)) : 0;
    bucket.acceptableRate = bucket.fields ? Number(((bucket.exact + bucket.restored) / bucket.fields).toFixed(4)) : 0;
  }
  return { total, byMode };
}

function parseArgs() {
  const args = process.argv.slice(2);
  const outIndex = args.indexOf("--out");
  const modeIndex = args.indexOf("--mode");
  const limitIndex = args.indexOf("--limit");
  return {
    out: outIndex >= 0 ? args[outIndex + 1] : null,
    mode: modeIndex >= 0 ? args[modeIndex + 1] : null,
    limit: limitIndex >= 0 ? Number(args[limitIndex + 1]) : null,
  };
}

async function main() {
  const { out, mode, limit } = parseArgs();
  if (mode && !modes[mode]) throw new Error(`Unknown mode: ${mode}`);
  const selectedModes = mode ? { [mode]: modes[mode] } : modes;
  const expected = expectedRecords();
  const callModel =
    provider === "anthropic" ? callAnthropic : provider === "gemini" ? callGemini : callOpenAI;
  const rows = [];
  for (const [modeName, options] of Object.entries(selectedModes)) {
    for (let i = 0; i < samples; i += 1) {
      rows.push({ mode: modeName, seed: `session-${i}`, options });
    }
  }
  const limitedRows = limit ? rows.slice(0, limit) : rows;
  const results = [];
  for (const [index, row] of limitedRows.entries()) {
    process.stderr.write(`[${index + 1}/${limitedRows.length}] ${provider}/${model} ${row.mode} ${row.seed}\n`);
    const result = {
      provider,
      model,
      mode: row.mode,
      seed: row.seed,
      recordCount,
      parsedCount: 0,
      field_status: {},
      failureSamples: [],
      error: null,
    };
    try {
      const html = buildHtml(row.mode, row.seed);
      const parsed = await callModel(html);
      result.parsedCount = Array.isArray(parsed?.records) ? parsed.records.length : 0;
      const scored = score(parsed, expected, row.options);
      result.field_status = scored.fieldStatus;
      result.failureSamples = scored.failureSamples;
    } catch (error) {
      result.error = String(error.message || error);
    }
    results.push(result);
  }
  const report = {
    provider,
    model,
    samples,
    recordCount,
    fields,
    summary: summarize(results),
    results,
  };
  const output = JSON.stringify(report, null, 2);
  if (out) await fs.writeFile(path.resolve(out), output, "utf8");
  console.log(output);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
