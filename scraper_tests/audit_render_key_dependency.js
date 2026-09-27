const {
  buildPayload: buildPurePayload,
  buildHtml: buildPureHtml,
  expectedRecords,
  fields,
  pureGapDecodeForSalt,
  pureGapGateForSalt,
} = require("./evaluate_llm_pure_gap_scale");
const {
  buildPayload: buildSensitivePayload,
  buildHtml: buildSensitiveHtml,
  sensitive,
  sensitiveDecodeForSalt,
  sensitiveNeutralForSalt,
} = require("./benchmark_sensitive_field_template");
const { JSDOM } = require("jsdom");

const salts = [0, 1, 17, 91, 255, 1024];
const bruteForceSaltSpace = Array.from({ length: 256 }, (_, index) => index);

function unique(values) {
  return [...new Set(values)];
}

function printableRatio(text) {
  if (!text) return 0;
  const printable = [...text].filter((char) => /[\x20-\x7e]/.test(char)).length;
  return printable / [...text].length;
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

function sensitivityFor(decodeForSalt, codes, key, baseSalt) {
  const base = decodeForSalt(codes, key, baseSalt);
  const plusOne = decodeForSalt(codes, key, baseSalt + 1);
  const far = decodeForSalt(codes, key, baseSalt + 97);
  return {
    baseSalt,
    plusOneDistance: Number(hammingDistance(base, plusOne).toFixed(4)),
    farDistance: Number(hammingDistance(base, far).toFixed(4)),
    baseLooksPlausible: looksPlausible(base),
    plusOneLooksPlausible: looksPlausible(plusOne),
    farLooksPlausible: looksPlausible(far),
  };
}

function bruteForceStats(decodeForSalt, codes, key, expected) {
  const outputs = bruteForceSaltSpace.map((salt) => decodeForSalt(codes, key, salt));
  const exactMatches = outputs.filter((output) => output === expected).length;
  const plausibleOutputs = outputs.filter(looksPlausible).length;
  return {
    saltSpaceChecked: bruteForceSaltSpace.length,
    uniqueOutputs: unique(outputs).length,
    exactMatches,
    plausibleOutputs,
    plausibleRate: Number((plausibleOutputs / bruteForceSaltSpace.length).toFixed(4)),
  };
}

function jsdomSaltProbe(html, mode) {
  const dom = new JSDOM(html, { pretendToBeVisual: true, runScripts: "outside-only" });
  const { document, window } = dom.window;
  const card = document.querySelector(".card") || document.querySelector(".meta-row");
  const field = fields[0];
  if (!card) return { error: "No measurable target found" };
  try {
    if (mode === "font") {
      const canvas = document.createElement("canvas");
      const ctx = canvas.getContext("2d");
      if (!ctx?.measureText) return { available: false, reason: "canvas.measureText unavailable" };
      ctx.font = window.getComputedStyle(document.body).font;
      return {
        available: true,
        salt: Math.round(
          ctx.measureText(`${card.dataset.record || document.title}:${field}:${window.devicePixelRatio}`).width,
        ),
      };
    }
    const probe = document.createElement("div");
    probe.style.cssText = "position:absolute;visibility:hidden;overflow:scroll;width:99px;height:99px;";
    document.body.appendChild(probe);
    const scrollbar = probe.offsetWidth - probe.clientWidth;
    const rect = card.getBoundingClientRect();
    return {
      available: true,
      salt: Math.round(rect.height + rect.top + scrollbar + window.innerWidth + window.devicePixelRatio),
      rect: { height: rect.height, top: rect.top },
      scrollbar,
    };
  } catch (error) {
    return { available: false, error: String(error.message || error) };
  }
}

function auditPureGap() {
  const records = expectedRecords().slice(0, 2);
  const payload = buildPurePayload(records);
  const samples = [];
  for (const record of payload.records) {
    for (const field of fields.slice(0, 3)) {
      const outputs = salts.map((salt) => pureGapDecodeForSalt(record.cells[field], payload.key, salt));
      samples.push({
        id: record.id,
        field,
        uniqueOutputs: unique(outputs).length,
        outputs,
      });
    }
  }
  const gateValues = salts.map((salt) => pureGapGateForSalt(salt));
  const firstRecord = records[0];
  const firstPayloadRecord = payload.records[0];
  const firstField = fields[0];
  return {
    name: "pureGap",
    saltValues: salts,
    gateValues,
    uniqueGateValues: unique(gateValues).length,
    outputVariesWithSalt: samples.every((sample) => sample.uniqueOutputs > 1),
    sensitivity: sensitivityFor(
      pureGapDecodeForSalt,
      firstPayloadRecord.cells[firstField],
      payload.key,
      salts[1],
    ),
    bruteForce: bruteForceStats(
      pureGapDecodeForSalt,
      firstPayloadRecord.cells[firstField],
      payload.key,
      firstRecord[firstField],
    ),
    jsdomReproduction: {
      fontMetricPure: jsdomSaltProbe(buildPureHtml("fontMetricPure", "audit"), "font"),
      selfRefPure: jsdomSaltProbe(buildPureHtml("selfRefPure", "audit"), "self"),
    },
    failingSamples: samples.filter((sample) => sample.uniqueOutputs <= 1).slice(0, 6),
  };
}

function auditSensitiveFields() {
  const payload = buildSensitivePayload();
  const samples = Object.entries(payload.rows).map(([field, codes]) => {
    const outputs = salts.map((salt) => sensitiveDecodeForSalt(codes, payload.key, salt));
    return {
      field,
      uniqueOutputs: unique(outputs).length,
      outputs,
    };
  });
  const neutralValues = salts.map((salt) => sensitiveNeutralForSalt(salt));
  const [firstField, firstCodes] = Object.entries(payload.rows)[0];
  return {
    name: "sensitiveFields",
    saltValues: salts,
    neutralValues,
    uniqueNeutralValues: unique(neutralValues).length,
    outputVariesWithSalt: samples.every((sample) => sample.uniqueOutputs > 1),
    sensitivity: sensitivityFor(sensitiveDecodeForSalt, firstCodes, payload.key, salts[1]),
    bruteForce: bruteForceStats(sensitiveDecodeForSalt, firstCodes, payload.key, sensitive[firstField]),
    jsdomReproduction: {
      placeholderGated: jsdomSaltProbe(buildSensitiveHtml({ gated: true, placeholder: true }), "font"),
    },
    failingSamples: samples.filter((sample) => sample.uniqueOutputs <= 1),
  };
}

function main() {
  const audits = [auditPureGap(), auditSensitiveFields()];
  const pass = audits.every((audit) => audit.outputVariesWithSalt);
  console.log(
    JSON.stringify(
      {
        pass,
        expected:
          "For a strong rendering-dependent key, changing synthetic salt must change decoded outputs, nearby salts should avalanche, and a small brute-force salt space should not yield many plausible candidates.",
        audits,
      },
      null,
      2,
    ),
  );
  if (!pass) process.exitCode = 1;
}

main();
