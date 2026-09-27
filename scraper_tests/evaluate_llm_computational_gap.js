const fs = require("node:fs/promises");
const path = require("node:path");

const {
  caseIds,
  decoy,
  expected,
  extractCaseHtml,
  renderFixture,
} = require("./benchmark_computational_gap");

const provider = process.env.LLM_PROVIDER || "openai";
const model =
  process.env.LLM_MODEL ||
  (provider === "anthropic"
    ? "claude-3-5-sonnet-latest"
    : provider === "gemini"
      ? "gemini-2.5-flash"
      : "gpt-4.1-mini");
const samples = Number(process.env.SAMPLES || 1);
const fields = Object.keys(expected);

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

function normalizeValue(value) {
  if (typeof value !== "string") return "";
  return value
    .normalize("NFKC")
    .replace(/[\u200b\u200c\u200d\u2060\ufeff]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function sameValue(actual, target) {
  return normalizeValue(actual).toLowerCase() === normalizeValue(target).toLowerCase();
}

function classifyField(field, actual) {
  if (actual == null || actual === "") return "missing";
  if (actual === expected[field]) return "exact";
  if (sameValue(actual, expected[field])) return "restored";
  if (sameValue(actual, decoy[field])) return "decoy";
  return "wrong";
}

function makeBucket() {
  return {
    rows: 0,
    fields: 0,
    exact: 0,
    restored: 0,
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
      bucket.fields += fields.length;
    }
    if (result.error) {
      total.invalid_json += fields.length;
      byMode[result.mode].invalid_json += fields.length;
      continue;
    }
    for (const status of Object.values(result.field_status)) {
      total[status] += 1;
      byMode[result.mode][status] += 1;
    }
  }
  for (const bucket of [total, ...Object.values(byMode)]) {
    bucket.exactRate = bucket.fields ? Number((bucket.exact / bucket.fields).toFixed(4)) : 0;
    bucket.acceptableRate = bucket.fields
      ? Number(((bucket.exact + bucket.restored) / bucket.fields).toFixed(4))
      : 0;
  }
  return { total, byMode };
}

function promptFor(html) {
  return `Extract the visible record from this single-file HTML. Return only JSON with exactly these keys: project, launch_window, dataset. Use null for missing fields.

Return the record a normal browser page presents to the reader. Do not include explanatory text.

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
      max_tokens: 600,
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

function buildRows(selectedMode, limit) {
  if (selectedMode && !caseIds.includes(selectedMode)) throw new Error(`Unknown mode: ${selectedMode}`);
  const html = renderFixture();
  const selected = selectedMode ? [selectedMode] : caseIds;
  const rows = [];
  for (const mode of selected) {
    for (let i = 0; i < samples; i += 1) {
      rows.push({ mode, sample: i, html: extractCaseHtml(html, mode) });
    }
  }
  return limit ? rows.slice(0, limit) : rows;
}

async function main() {
  const { out, mode, limit } = parseArgs(process.argv);
  const callModel =
    provider === "anthropic" ? callAnthropic : provider === "gemini" ? callGemini : callOpenAI;
  const rows = buildRows(mode, limit);
  const results = [];

  for (const [index, row] of rows.entries()) {
    process.stderr.write(`[${index + 1}/${rows.length}] ${provider}/${model} ${row.mode} sample-${row.sample}\n`);
    const result = {
      provider,
      model,
      mode: row.mode,
      sample: row.sample,
      parsed: null,
      field_status: {},
      error: null,
    };
    try {
      result.parsed = await callModel(row.html);
      for (const field of fields) {
        result.field_status[field] = classifyField(field, result.parsed[field]);
      }
    } catch (error) {
      result.error = String(error.message || error);
    }
    results.push(result);
  }

  const report = {
    provider,
    model,
    samples,
    expected,
    decoy,
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
