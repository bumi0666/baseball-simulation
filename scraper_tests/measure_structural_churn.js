const crypto = require("node:crypto");
const { page } = require("./structural_churn_server");

const defaultUrl = process.env.URL || "http://127.0.0.1:8787/record";
const samples = Number(process.env.SAMPLES || 12);

function normalizeText(html) {
  return html
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function structuralSignature(html) {
  const tags = [...html.matchAll(/<\/?([a-z0-9-]+)([^>]*)>/gi)].map((match) => {
    const tag = match[1].toLowerCase();
    const attrs = [...match[2].matchAll(/\s([a-z0-9:-]+)(?:=("[^"]*"|'[^']*'|[^\s>]+))?/gi)]
      .map((attr) => attr[1].toLowerCase())
      .join(",");
    return `${match[0][1] === "/" ? "/" : ""}${tag}[${attrs}]`;
  });
  return tags.join(" ");
}

function classTokens(html) {
  return [...html.matchAll(/\bclass="([^"]+)"/gi)].flatMap((match) => match[1].split(/\s+/));
}

function digest(value) {
  return crypto.createHash("sha256").update(value).digest("hex").slice(0, 16);
}

function jaccard(a, b) {
  const left = new Set(a);
  const right = new Set(b);
  const intersection = [...left].filter((item) => right.has(item)).length;
  const union = new Set([...left, ...right]).size;
  return union === 0 ? 1 : intersection / union;
}

async function main() {
  const rows = [];
  for (let i = 0; i < samples; i += 1) {
    let seed = `session-${i}`;
    let html;
    if (process.env.DIRECT === "1") {
      html = page(seed);
    } else {
      const response = await fetch(defaultUrl, { headers: { "x-session-key": seed } });
      html = await response.text();
      seed = response.headers.get("x-structural-seed");
    }
    const text = normalizeText(html);
    const signature = structuralSignature(html);
    rows.push({
      index: i,
      seed,
      htmlHash: digest(html),
      textHash: digest(text),
      structureHash: digest(signature),
      classHash: digest(classTokens(html).join(" ")),
      text,
      classes: classTokens(html),
    });
  }

  const uniqueText = new Set(rows.map((row) => row.textHash)).size;
  const uniqueHtml = new Set(rows.map((row) => row.htmlHash)).size;
  const uniqueStructure = new Set(rows.map((row) => row.structureHash)).size;
  const uniqueClass = new Set(rows.map((row) => row.classHash)).size;
  const classSimilarities = [];
  for (let i = 1; i < rows.length; i += 1) {
    classSimilarities.push(jaccard(rows[0].classes, rows[i].classes));
  }

  const avgClassJaccard =
    classSimilarities.reduce((sum, value) => sum + value, 0) / Math.max(classSimilarities.length, 1);

  console.log(JSON.stringify(
    {
      url: defaultUrl,
      samples,
      uniqueText,
      uniqueHtml,
      uniqueStructure,
      uniqueClass,
      avgClassJaccardWithFirst: Number(avgClassJaccard.toFixed(4)),
      rows: rows.map(({ classes, text, ...row }) => ({
        ...row,
        classCount: classes.length,
        textPreview: text,
      })),
    },
    null,
    2,
  ));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
