const crypto = require("node:crypto");
const { chromium, firefox, webkit } = require("playwright");
const {
  buildHtml,
  computeBrowserSaltWithPage,
  leakage,
  renderShell,
  sensitiveRows,
  sensitive,
} = require("./benchmark_render_keyed_sensitive_field");

const browserTypes = { chromium, firefox, webkit };

const configs = [
  { name: "chromium-900x700-dsf1", browser: "chromium", viewport: { width: 900, height: 700 }, deviceScaleFactor: 1 },
  { name: "chromium-900x700-dsf2", browser: "chromium", viewport: { width: 900, height: 700 }, deviceScaleFactor: 2 },
  { name: "chromium-1200x900-dsf1", browser: "chromium", viewport: { width: 1200, height: 900 }, deviceScaleFactor: 1 },
  { name: "chromium-420x900-dsf3", browser: "chromium", viewport: { width: 420, height: 900 }, deviceScaleFactor: 3 },
  { name: "chromium-css-zoom-90", browser: "chromium", viewport: { width: 900, height: 700 }, deviceScaleFactor: 1, cssZoom: 0.9 },
  { name: "chromium-css-zoom-110", browser: "chromium", viewport: { width: 900, height: 700 }, deviceScaleFactor: 1, cssZoom: 1.1 },
  { name: "chromium-css-zoom-125", browser: "chromium", viewport: { width: 900, height: 700 }, deviceScaleFactor: 1, cssZoom: 1.25 },
  { name: "chromium-serif", browser: "chromium", viewport: { width: 900, height: 700 }, deviceScaleFactor: 1, fontFamily: "Georgia, serif" },
  { name: "chromium-monospace", browser: "chromium", viewport: { width: 900, height: 700 }, deviceScaleFactor: 1, fontFamily: "Consolas, monospace" },
  { name: "firefox-900x700-dsf1", browser: "firefox", viewport: { width: 900, height: 700 }, deviceScaleFactor: 1 },
  { name: "webkit-900x700-dsf1", browser: "webkit", viewport: { width: 900, height: 700 }, deviceScaleFactor: 1 },
];

function hash(value) {
  return crypto.createHash("sha256").update(String(value)).digest("hex").slice(0, 16);
}

function normalize(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

function compareComponents(base, current) {
  const out = {};
  for (const key of Object.keys(base)) {
    out[key] = current[key] - base[key];
  }
  return out;
}

function scoreVisibleText(text) {
  const leak = leakage(text);
  const lower = normalize(text).toLowerCase();
  const wrongish = Object.values(sensitive).filter((value) => !lower.includes(value.toLowerCase())).length;
  return {
    sensitiveExact: leak.leaked,
    sensitiveTotal: leak.total,
    exactRate: Number((leak.leaked / leak.total).toFixed(4)),
    falseNegativeRate: Number((wrongish / leak.total).toFixed(4)),
  };
}

async function openPage(config, html) {
  const type = browserTypes[config.browser];
  const browser = await type.launch({ headless: true });
  const page = await browser.newPage({
    viewport: config.viewport,
    deviceScaleFactor: config.deviceScaleFactor,
  });
  const preStyle = [
    config.cssZoom ? `body { zoom: ${config.cssZoom}; }` : "",
    config.fontFamily ? `body { font-family: ${config.fontFamily} !important; }` : "",
  ].filter(Boolean).join("\n");
  const content = preStyle ? html.replace("</style>", `${preStyle}\n  </style>`) : html;
  await page.setContent(content, { waitUntil: "load" });
  return { browser, page };
}

async function measureConfig(config, html, baseComponents) {
  try {
    const { browser, page } = await openPage(config, html);
    const saltInfo = await computeBrowserSaltWithPage(page);
    await page.waitForTimeout(50);
    const text = await page.locator("body").innerText();
    await browser.close();
    return {
      config: config.name,
      browser: config.browser,
      salt: saltInfo.salt,
      saltHash: hash(saltInfo.salt),
      components: saltInfo.components,
      componentDelta: baseComponents ? compareComponents(baseComponents, saltInfo.components) : null,
      score: scoreVisibleText(text),
    };
  } catch (error) {
    return {
      config: config.name,
      browser: config.browser,
      error: String(error.message || error),
    };
  }
}

async function main() {
  const calibrationShell = renderShell(sensitiveRows());
  const baseOpen = await openPage(configs[0], calibrationShell);
  const baseSaltInfo = await computeBrowserSaltWithPage(baseOpen.page);
  await baseOpen.browser.close();

  const keyedHtml = buildHtml(baseSaltInfo.salt);
  const results = [];
  for (const config of configs) {
    results.push(await measureConfig(config, keyedHtml, baseSaltInfo.components));
  }

  const valid = results.filter((result) => !result.error);
  const exact = valid.filter((result) => result.score.exactRate === 1).length;
  console.log(
    JSON.stringify(
      {
        calibration: {
          config: configs[0].name,
          salt: baseSaltInfo.salt,
          saltHash: hash(baseSaltInfo.salt),
          components: baseSaltInfo.components,
        },
        testedConfigs: configs.length,
        validConfigs: valid.length,
        legitimateExactRate: valid.length ? Number((exact / valid.length).toFixed(4)) : 0,
        falseNegativeRate: valid.length ? Number((1 - exact / valid.length).toFixed(4)) : 1,
        uniqueSaltCount: new Set(valid.map((result) => result.salt)).size,
        results,
      },
      null,
      2,
    ),
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
