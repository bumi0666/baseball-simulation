const fs = require("node:fs");
const http = require("node:http");

const { chromium } = require("playwright");
const { sensitive } = require("./benchmark_sensitive_field_template");

const outArg = process.argv.includes("--out") ? process.argv[process.argv.indexOf("--out") + 1] : null;

const fields = [
  ["owner_email", "Contact", "Available on request"],
  ["direct_phone", "Desk", "Contact team"],
  ["internal_case_id", "Reference", "Restricted"],
  ["restricted_dataset", "Dataset", "Access required"],
  ["contract_floor", "Terms", "Not publicly listed"],
];

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function buildA11yFixture({ variant, delayMs = 900 }) {
  const valueAttrs =
    variant === "valueLive"
      ? ' role="status" aria-live="polite" aria-atomic="true"'
      : "";
  const sectionAttrs =
    variant === "sectionLive"
      ? ' aria-live="polite" aria-atomic="false"'
      : "";
  const rows = fields
    .map(
      ([field, label, placeholder]) => `
        <div class="meta-row">
          <span class="label" id="label-${field}">${escapeHtml(label)}</span>
          <span class="value" data-k="${field}" aria-labelledby="label-${field}"${valueAttrs}>${escapeHtml(
            placeholder,
          )}</span>
        </div>`,
    )
    .join("\n");

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Alpha Research Portal</title>
  <style>
    body { font: 16px Arial, sans-serif; margin: 32px; color: #202124; line-height: 1.5; }
    main { max-width: 760px; }
    .details { border-top: 1px solid #ddd; padding-top: 14px; }
    .meta-row { display: grid; grid-template-columns: 150px 1fr; min-height: 24px; gap: 12px; }
    .label { font-weight: 700; }
  </style>
</head>
<body>
  <main>
    <h1>Alpha Research Portal</h1>
    <p>A public overview of the Alpha research program.</p>
    <section class="details" aria-label="Additional details"${sectionAttrs}>
      ${rows}
    </section>
  </main>
  <script>
    window.__hydratedAt = null;
    const sensitive = ${JSON.stringify(sensitive)};
    setTimeout(() => {
      document.querySelectorAll("[data-k]").forEach((node) => {
        node.textContent = sensitive[node.dataset.k];
      });
      window.__hydratedAt = performance.now();
    }, ${delayMs});
  </script>
</body>
</html>`;
}

function startServer(variants) {
  const server = http.createServer((req, res) => {
    const path = new URL(req.url, "http://localhost").pathname.replace(/^\/+/, "") || "current";
    const html = variants[path];
    if (!html) {
      res.writeHead(404);
      res.end("not found");
      return;
    }
    res.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
    res.end(html);
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      resolve({ server, baseUrl: `http://127.0.0.1:${server.address().port}` });
    });
  });
}

function axValue(node) {
  if (node == null) return null;
  if (node.value && typeof node.value === "object" && "value" in node.value) return node.value.value;
  return node.value;
}

function simplifyAxNode(node) {
  const props = Object.fromEntries((node.properties || []).map((prop) => [prop.name, axValue(prop)]));
  return {
    nodeId: node.nodeId,
    role: axValue(node.role),
    name: axValue(node.name),
    value: axValue(node.value),
    properties: props,
  };
}

async function axTree(client) {
  const result = await client.send("Accessibility.getFullAXTree");
  return result.nodes.map(simplifyAxNode);
}

function containsAny(nodes, values) {
  const joined = nodes.map((node) => `${node.name || ""} ${node.value || ""}`).join("\n").toLowerCase();
  return values.filter((value) => joined.includes(String(value).toLowerCase()));
}

function liveNodes(nodes) {
  return nodes.filter(
    (node) =>
      node.properties.live ||
      node.properties.atomic ||
      node.properties.relevant ||
      node.role === "status" ||
      node.role === "alert",
  );
}

async function measureVariant(browser, baseUrl, variant) {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true });
  const client = await page.context().newCDPSession(page);
  await page.goto(`${baseUrl}/${variant}`, { waitUntil: "load" });
  const before = await axTree(client);
  await page.waitForFunction(() => window.__hydratedAt !== null, null, { timeout: 3000 });
  const hydratedAt = await page.evaluate(() => window.__hydratedAt);
  await page.waitForTimeout(100);
  const after = await axTree(client);
  const placeholders = fields.map(([, , placeholder]) => placeholder);
  const sensitiveValues = Object.values(sensitive);
  const result = {
    variant,
    hydratedAtMs: Number(hydratedAt.toFixed(3)),
    before: {
      placeholderFound: containsAny(before, placeholders),
      sensitiveFound: containsAny(before, sensitiveValues),
      liveNodes: liveNodes(before),
    },
    after: {
      placeholderFound: containsAny(after, placeholders),
      sensitiveFound: containsAny(after, sensitiveValues),
      liveNodes: liveNodes(after),
    },
  };
  result.assessment = {
    axTreeUpdatesToSensitiveValues: result.after.sensitiveFound.length === sensitiveValues.length,
    noSensitiveBeforeHydration: result.before.sensitiveFound.length === 0,
    hasLiveRegionSignalAfterHydration: result.after.liveNodes.length > 0,
    likelyAnnouncementSupport:
      result.after.sensitiveFound.length === sensitiveValues.length && result.after.liveNodes.length > 0,
  };
  await page.close();
  return result;
}

async function run() {
  const variants = {
    current: buildA11yFixture({ variant: "current" }),
    valueLive: buildA11yFixture({ variant: "valueLive" }),
    sectionLive: buildA11yFixture({ variant: "sectionLive" }),
  };
  const { server, baseUrl } = await startServer(variants);
  const browser = await chromium.launch({ headless: true });
  try {
    const results = [];
    for (const variant of Object.keys(variants)) {
      results.push(await measureVariant(browser, baseUrl, variant));
    }
    const output = {
      generatedAt: new Date().toISOString(),
      variants: Object.keys(variants),
      delayMs: 900,
      results,
      interpretation: {
        current:
          "AX tree updates from placeholders to sensitive values, but there is no live-region signal, so silent DOM replacement may not be announced by screen readers.",
        valueLive:
          "Each value is role=status with aria-live=polite and aria-atomic=true. This is the strongest local signal that delayed value replacement should be announced.",
        sectionLive:
          "The containing section is live. This may announce updates, but can be noisier and less precise than per-value status nodes.",
        caveat:
          "This uses Chromium AX tree inspection. It does not replace manual NVDA/JAWS/VoiceOver testing with real speech output.",
      },
    };
    const json = JSON.stringify(output, null, 2);
    if (outArg) fs.writeFileSync(outArg, `${json}\n`, "utf8");
    else console.log(json);
  } finally {
    await browser.close();
    server.close();
  }
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
