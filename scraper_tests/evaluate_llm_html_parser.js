const fs = require("node:fs/promises");
const path = require("node:path");
const { page, record, decoys } = require("./structural_churn_server");

const samples = Number(process.env.SAMPLES || 6);
const provider = process.env.LLM_PROVIDER || "openai";
const model =
  process.env.LLM_MODEL ||
  (provider === "anthropic"
    ? "claude-3-5-sonnet-latest"
    : provider === "gemini"
      ? "gemini-2.5-flash"
      : "gpt-4.1-mini");
const fields = Object.keys(record);

const modes = {
  stable: { churn: false, reorder: false },
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

function parseArgs(argv) {
  const args = argv.slice(2);
  const outIndex = args.indexOf("--out");
  const modeIndex = args.indexOf("--mode");
  const limitIndex = args.indexOf("--limit");
  return {
    out: outIndex >= 0 ? args[outIndex + 1] : null,
    mode: modeIndex >= 0 ? args[modeIndex + 1] : null,
    limit: limitIndex >= 0 ? Number(args[limitIndex + 1]) : null,
    listGeminiModels: args.includes("--list-gemini-models"),
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

function hasControl(value) {
  return typeof value === "string" && /[\u0400-\u04ff\u202a-\u202e\u2066-\u2069\u200b\u200c\u200d\u2060\ufeff]/.test(value);
}

function classifyField(field, actual) {
  if (actual == null || actual === "") return "missing";
  if (actual === record[field]) return "exact";
  if (sameValue(actual, record[field])) return "restored";
  if (sameValue(actual, decoys[field])) return "decoy";
  if (hasControl(actual)) return "confusable_or_control";
  return "wrong";
}

function summarize(results) {
  const byMode = {};
  const total = makeBucket();

  for (const result of results) {
    byMode[result.mode] ||= makeBucket();
    const bucket = byMode[result.mode];
    bucket.rows += 1;
    total.rows += 1;

    if (result.error) {
      bucket.invalid_json += fields.length;
      total.invalid_json += fields.length;
      continue;
    }

    for (const field of fields) {
      const status = result.field_status[field];
      bucket[status] += 1;
      total[status] += 1;
    }
  }

  for (const bucket of [total, ...Object.values(byMode)]) {
    bucket.fields = bucket.rows * fields.length;
    bucket.exactRate = rate(bucket.exact, bucket.fields);
    bucket.acceptableRate = rate(bucket.exact + bucket.restored, bucket.fields);
  }

  return { total, byMode };
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

function rate(numerator, denominator) {
  return denominator ? Number((numerator / denominator).toFixed(4)) : 0;
}

function promptFor(html) {
  return `Extract the visible record from this HTML source. Return only JSON with exactly these keys: project, launch_window, dataset. Use null for missing fields.

HTML:
${html}`;
}

function extractJson(text) {
  const trimmed = text.trim();
  try {
    return JSON.parse(trimmed);
  } catch {
    const match = trimmed.match(/\{[\s\S]*\}/);
    if (!match) throw new Error(`No JSON object found in model output: ${trimmed.slice(0, 200)}`);
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
        {
          role: "system",
          content: "You extract structured data from HTML. Return only valid JSON.",
        },
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
      max_tokens: 300,
      temperature: 0,
      system: "You extract structured data from HTML. Return only valid JSON.",
      messages: [{ role: "user", content: promptFor(html) }],
    }),
  });
  if (!response.ok) throw new Error(`Anthropic ${response.status}: ${await response.text()}`);
  const data = await response.json();
  const text = data.content.map((part) => part.text || "").join("");
  return extractJson(text);
}

async function callGemini(html) {
  if (!process.env.GEMINI_API_KEY) throw new Error("GEMINI_API_KEY is required.");
  const baseUrl = process.env.GEMINI_BASE_URL || "https://generativelanguage.googleapis.com/v1beta";
  const url = `${baseUrl}/models/${encodeURIComponent(model)}:generateContent?key=${encodeURIComponent(process.env.GEMINI_API_KEY)}`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      generationConfig: {
        temperature: 0,
        responseMimeType: "application/json",
      },
      contents: [
        {
          role: "user",
          parts: [
            {
              text: `You extract structured data from HTML. Return only valid JSON.\n\n${promptFor(html)}`,
            },
          ],
        },
      ],
    }),
  });
  if (!response.ok) throw new Error(`Gemini ${response.status}: ${await response.text()}`);
  const data = await response.json();
  const text = data.candidates?.[0]?.content?.parts?.map((part) => part.text || "").join("") || "";
  return extractJson(text);
}

async function listGeminiModels() {
  if (!process.env.GEMINI_API_KEY) throw new Error("GEMINI_API_KEY is required.");
  const baseUrl = process.env.GEMINI_BASE_URL || "https://generativelanguage.googleapis.com/v1beta";
  const response = await fetch(
    `${baseUrl}/models?key=${encodeURIComponent(process.env.GEMINI_API_KEY)}`,
  );
  if (!response.ok) throw new Error(`Gemini models.list ${response.status}: ${await response.text()}`);
  const data = await response.json();
  const models = (data.models || [])
    .filter((item) => (item.supportedGenerationMethods || []).includes("generateContent"))
    .map((item) => ({
      name: item.name,
      displayName: item.displayName,
      supportedGenerationMethods: item.supportedGenerationMethods,
    }));
  console.log(JSON.stringify({ models }, null, 2));
}

function buildRows(selectedMode, limit) {
  const selectedModes = selectedMode ? { [selectedMode]: modes[selectedMode] } : modes;
  if (selectedMode && !modes[selectedMode]) {
    throw new Error(`Unknown mode: ${selectedMode}`);
  }

  const rows = [];
  for (const [mode, options] of Object.entries(selectedModes)) {
    for (let i = 0; i < samples; i += 1) {
      const seed = `session-${i}`;
      rows.push({ mode, seed, html: page(seed, options) });
    }
  }
  return limit ? rows.slice(0, limit) : rows;
}

async function main() {
  const { out, mode, limit, listGeminiModels: shouldListGeminiModels } = parseArgs(process.argv);
  if (shouldListGeminiModels) {
    await listGeminiModels();
    return;
  }
  const rows = buildRows(mode, limit);
  const callModel =
    provider === "anthropic" ? callAnthropic : provider === "gemini" ? callGemini : callOpenAI;
  const results = [];

  for (const [index, row] of rows.entries()) {
    process.stderr.write(`[${index + 1}/${rows.length}] ${provider}/${model} ${row.mode} ${row.seed}\n`);
    const result = {
      provider,
      model,
      mode: row.mode,
      seed: row.seed,
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
    expected: record,
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
