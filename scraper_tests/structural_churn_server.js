const crypto = require("node:crypto");
const http = require("node:http");

const port = Number(process.env.PORT || 8787);

const record = {
  project: "Alpha project",
  launch_window: "Friday morning",
  dataset: "private dataset",
};

const decoys = {
  project: "Beta project",
  launch_window: "Monday night",
  dataset: "public dataset",
};

function hash(seed, label) {
  return crypto.createHash("sha256").update(`${seed}:${label}`).digest();
}

function pick(seed, label, choices) {
  return choices[hash(seed, label)[0] % choices.length];
}

function className(seed, semantic, churn = true) {
  if (!churn) return semantic.replace(/[^a-z0-9_-]+/gi, "-").toLowerCase();
  return `c_${hash(seed, `class:${semantic}`).subarray(0, 4).toString("hex")}`;
}

function attrs(seed, label, entries, churn = true) {
  if (!churn) {
    return entries.map(([name, value]) => `${name}="${value}"`).join(" ");
  }
  const keyed = entries.map(([name, value], index) => ({
    name,
    value,
    rank: hash(seed, `attr:${label}:${name}:${index}`).readUInt32BE(0),
  }));
  keyed.sort((a, b) => a.rank - b.rank);
  return keyed.map(({ name, value }) => `${name}="${value}"`).join(" ");
}

function wrap(seed, label, html, churn = true) {
  const depth = churn ? 1 + (hash(seed, `depth:${label}`)[0] % 3) : 1;
  let output = html;
  for (let i = 0; i < depth; i += 1) {
    const tag = churn ? pick(seed, `wrap-tag:${label}:${i}`, ["div", "section", "article"]) : "div";
    const cls = className(seed, `wrap-${label}-${i}`, churn);
    output = `<${tag} ${attrs(seed, `wrap-${label}-${i}`, [["class", cls], ["data-layer", String(i)]], churn)}>${output}</${tag}>`;
  }
  return output;
}

function zeroWidth(value) {
  return value.replace(/([A-Za-z])(?=[A-Za-z])/g, "$1&#8203;");
}

function field(seed, key, label, value, churn = true, semantic = true) {
  const rowTag = churn ? pick(seed, `row-tag:${key}`, ["div", "p", "section"]) : "div";
  const labelTag = churn ? pick(seed, `label-tag:${key}`, ["b", "strong", "span"]) : "strong";
  const valueTag = churn ? pick(seed, `value-tag:${key}`, ["span", "em", "i"]) : "span";
  const rowClass = className(seed, `row-${key}`, churn);
  const labelClass = className(seed, `label-${key}`, churn);
  const valueClass = className(seed, `value-${key}`, churn);
  const labelEntries = semantic ? [["class", labelClass], ["data-k", key]] : [["class", labelClass]];
  const valueEntries = semantic ? [["class", valueClass], ["data-v", key]] : [["class", valueClass]];
  const rowEntries = semantic ? [["class", rowClass], ["data-field", key]] : [["class", rowClass]];
  const labelAttrs = attrs(seed, `label-${key}`, labelEntries, churn);
  const valueAttrs = attrs(seed, `value-${key}`, valueEntries, churn);
  const rowAttrs = attrs(seed, `row-${key}`, rowEntries, churn);
  return `<${rowTag} ${rowAttrs}><${labelTag} ${labelAttrs}>${label}</${labelTag}> <${valueTag} ${valueAttrs}>${value}</${valueTag}></${rowTag}>`;
}

function adversarialContent(seed, options, churn) {
  const useDecoys = options.hiddenDecoy === true;
  const useZeroWidth = options.zeroWidth === true;
  const semantic = options.semanticAnchors === true;
  const labels = [
    ["project", "Project:", 1],
    ["launch_window", "Launch window:", 2],
    ["dataset", "Dataset:", 3],
  ];
  const values = [
    ["launch_window", record.launch_window, 2],
    ["project", record.project, 1],
    ["dataset", record.dataset, 3],
  ];

  const labelNodes = labels.map(([key, label, row]) => {
    const cls = className(seed, `adv-label-${key}`, churn);
    const entries = semantic ? [["class", cls], ["data-k", key]] : [["class", cls]];
    return `<span ${attrs(seed, `adv-label-${key}`, entries, churn)} style="grid-row:${row};grid-column:1">${label}</span>`;
  });

  const valueNodes = values.map(([key, value, row]) => {
    const cls = className(seed, `adv-value-${key}`, churn);
    const entries = semantic ? [["class", cls], ["data-v", key]] : [["class", cls]];
    const output = useZeroWidth ? zeroWidth(value) : value;
    return `<span ${attrs(seed, `adv-value-${key}`, entries, churn)} style="grid-row:${row};grid-column:2">${output}</span>`;
  });

  const hiddenNodes = useDecoys
    ? [
        ["launch_window", decoys.launch_window],
        ["project", decoys.project],
        ["dataset", decoys.dataset],
      ].map(([key, value]) => {
        const cls = className(seed, `adv-decoy-${key}`, churn);
        return `<span class="${cls} hidden-decoy" data-decoy="${key}" style="display:none">${value}</span>`;
      })
    : [];

  const domNodes = [
    labelNodes[0],
    labelNodes[1],
    hiddenNodes[0],
    labelNodes[2],
    valueNodes[0],
    hiddenNodes[1],
    valueNodes[1],
    hiddenNodes[2],
    valueNodes[2],
  ].filter(Boolean);

  return `<div class="adversarial-grid">${domNodes.join("\n")}</div>`;
}

function page(seed, options = {}) {
  const churn = options.churn !== false;
  const reorder = options.reorder === true;
  const adversarial = options.adversarial === true;
  const titleClass = className(seed, "title", churn);
  const bodyClass = className(seed, "body", churn);
  const fieldDefs = [
    ["project", "Project:", record.project],
    ["launch_window", "Launch window:", record.launch_window],
    ["dataset", "Dataset:", record.dataset],
  ];
  const domOrder = reorder ? [1, 0, 2] : [0, 1, 2];
  const fields = domOrder.map((fieldIndex) => {
    const [key, label, value] = fieldDefs[fieldIndex];
    const item = field(seed, key, label, value, churn, options.semanticAnchors !== false);
    return reorder ? `<div class="visual-row" style="order:${fieldIndex + 1}">${item}</div>` : item;
  });

  const layout = churn ? pick(seed, "layout", ["plain", "wrapped"]) : "plain";
  const content =
    adversarial
      ? adversarialContent(seed, options, churn)
      : layout === "plain"
      ? fields.join("\n")
      : fields.map((item, index) => wrap(seed, `field-${index}`, item, churn)).join("\n");

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Structural Churn Demo</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 40px; line-height: 1.5; }
    .${bodyClass} { max-width: 640px; }
    .${titleClass} { font-size: 24px; margin-bottom: 16px; }
    [data-field] { margin: 8px 0; }
    [data-k] { font-weight: 700; font-style: normal; }
    [data-v] { font-weight: 400; font-style: normal; }
    .visual-order { display: flex; flex-direction: column; }
    .visual-row { display: block; }
    .adversarial-grid { display: grid; grid-template-columns: 150px 1fr; gap: 8px 16px; }
    .adversarial-grid span:nth-child(1),
    .adversarial-grid span:nth-child(2),
    .adversarial-grid span:nth-child(4) { font-weight: 700; }
    .hidden-decoy { display: none; }
  </style>
</head>
<body>
  <main ${attrs(seed, "main", [["class", bodyClass], ["data-seed", seed.slice(0, 10)]], churn)}>
    <h1 ${attrs(seed, "title", [["class", titleClass]], churn)}>Record</h1>
    ${reorder ? `<div class="visual-order">${content}</div>` : content}
  </main>
</body>
</html>`;
}

function createServer() {
  return http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  if (url.pathname !== "/record") {
    res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    res.end("not found");
    return;
  }

  const seed =
    url.searchParams.get("seed") ||
    req.headers["x-session-key"] ||
    crypto.randomBytes(12).toString("hex");
  res.writeHead(200, {
    "content-type": "text/html; charset=utf-8",
    "cache-control": "no-store",
    "x-structural-seed": seed,
  });
  const churn = url.searchParams.get("churn") !== "0";
  const reorder = url.searchParams.get("reorder") === "1";
  const adversarial = url.searchParams.get("adversarial") === "1";
  const hiddenDecoy = url.searchParams.get("hiddenDecoy") === "1";
  const zeroWidth = url.searchParams.get("zeroWidth") === "1";
  const semanticAnchors = url.searchParams.get("semanticAnchors") !== "0";
  res.end(page(seed, { churn, reorder, adversarial, hiddenDecoy, zeroWidth, semanticAnchors }));
  });
}

if (require.main === module) {
  const server = createServer();
  server.listen(port, () => {
    console.log(`structural churn server listening on http://127.0.0.1:${port}/record`);
  });
}

module.exports = { createServer, page, record, decoys };
