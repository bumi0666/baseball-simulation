const fs = require("node:fs/promises");
const path = require("node:path");

const expected = {
  project: "Alpha project",
  launch_window: "Friday morning",
  dataset: "private dataset",
};

const decoys = {
  project: ["Beta project"],
  launch_window: ["Monday night"],
  dataset: ["public dataset"],
};

const fields = Object.keys(expected);
const baseUrl = process.env.OPENAI_BASE_URL || "https://api.openai.com/v1";
const model = process.env.OPENAI_MODEL || "gpt-4.1-mini";

function usage() {
  console.log(`Usage:
  node evaluate_llm_parser.js <extractions.json> [--limit N] [--out results.json]

Environment:
  OPENAI_API_KEY    required
  OPENAI_MODEL      default: gpt-4.1-mini
  OPENAI_BASE_URL   default: https://api.openai.com/v1`);
}

function parseArgs(argv) {
  const args = argv.slice(2);
  const input = args.find((arg) => !arg.startsWith("--"));
  const limitIndex = args.indexOf("--limit");
  const outIndex = args.indexOf("--out");
  return {
    input,
    limit: limitIndex >= 0 ? Number(args[limitIndex + 1]) : null,
    out: outIndex >= 0 ? args[outIndex + 1] : null,
  };
}

function normalizeValue(value) {
  if (typeof value !== "string") return "";
  return value.normalize("NFKC").replace(/[\u200b\u200c\u200d\u2060\ufeff]/g, "").replace(/\s+/g, " ").trim();
}

function sameValue(actual, target) {
  return normalizeValue(actual).toLowerCase() === normalizeValue(target).toLowerCase();
}

function hasConfusableOrControl(value) {
  if (typeof value !== "string") return false;
  return /[\u0400-\u04ff\u202a-\u202e\u2066-\u2069\u200b\u200c\u200d\u2060\ufeff]/.test(value);
}

function classifyField(field, actual) {
  if (actual == null || actual === "") return "missing";
  if (actual === expected[field]) return "exact";
  if (sameValue(actual, expected[field])) return "restored";
  if (decoys[field].some((value) => sameValue(actual, value))) return "decoy";
  if (hasConfusableOrControl(actual)) return "confusable_or_control";
  return "wrong";
}

function summarize(results) {
  const summary = {
    rows: results.length,
    fields: results.length * fields.length,
    exact: 0,
    restored: 0,
    confusable_or_control: 0,
    decoy: 0,
    missing: 0,
    wrong: 0,
    invalid_json: 0,
  };

  for (const result of results) {
    if (result.error) {
      summary.invalid_json += fields.length;
      continue;
    }
    for (const field of fields) {
      summary[result.field_status[field]] += 1;
    }
  }

  return summary;
}

async function callParser(text) {
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
          content:
            "Extract structured data from the user's text. Return only JSON with keys project, launch_window, dataset. Use null for missing fields.",
        },
        {
          role: "user",
          content: text,
        },
      ],
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`LLM request failed: ${response.status} ${body}`);
  }

  const data = await response.json();
  return JSON.parse(data.choices[0].message.content);
}

async function main() {
  const { input, limit, out } = parseArgs(process.argv);
  if (!input) {
    usage();
    process.exit(1);
  }
  if (!process.env.OPENAI_API_KEY) {
    throw new Error("OPENAI_API_KEY is required for LLM parser evaluation.");
  }

  const payload = JSON.parse(await fs.readFile(input, "utf8"));
  const rows = limit ? payload.rows.slice(0, limit) : payload.rows;
  const results = [];

  for (const [index, row] of rows.entries()) {
    process.stderr.write(`[${index + 1}/${rows.length}] ${row.case_id} / ${row.extractor}\n`);
    const result = {
      case_id: row.case_id,
      extractor: row.extractor,
      input_text: row.text,
      parsed: null,
      field_status: {},
      error: null,
    };

    try {
      result.parsed = await callParser(row.text);
      for (const field of fields) {
        result.field_status[field] = classifyField(field, result.parsed[field]);
      }
    } catch (error) {
      result.error = String(error.message || error);
    }

    results.push(result);
  }

  const report = {
    fixture: payload.fixture,
    model,
    expected,
    summary: summarize(results),
    results,
  };

  const output = JSON.stringify(report, null, 2);
  if (out) {
    await fs.writeFile(path.resolve(out), output, "utf8");
  }
  console.log(output);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
