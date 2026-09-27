const { performance } = require("node:perf_hooks");
const { chromium } = require("playwright");
const { page, record } = require("./structural_churn_server");

const samples = Number(process.env.SAMPLES || 24);
const iterations = Number(process.env.ITERATIONS || 5000);

function extractByTemplate(html, template) {
  const output = {};
  for (const [field, rule] of Object.entries(template)) {
    const rowPattern = new RegExp(
      `<${rule.rowTag}\\b[^>]*class="${escapeRegex(rule.rowClass)}"[^>]*>[\\s\\S]*?<${rule.valueTag}\\b[^>]*class="${escapeRegex(rule.valueClass)}"[^>]*>([\\s\\S]*?)<\\/${rule.valueTag}>[\\s\\S]*?<\\/${rule.rowTag}>`,
      "i",
    );
    const match = html.match(rowPattern);
    output[field] = match ? stripTags(match[1]) : null;
  }
  return output;
}

function learnTemplate(html) {
  const template = {};
  const rowPattern = /<([a-z0-9-]+)\b([^>]*)data-field="([^"]+)"([^>]*)>([\s\S]*?)<\/\1>/gi;
  let rowMatch;
  while ((rowMatch = rowPattern.exec(html))) {
    const [, rowTag, leftAttrs, field, rightAttrs, inner] = rowMatch;
    const rowClass = attrValue(`${leftAttrs} ${rightAttrs}`, "class");
    const valuePattern = /<([a-z0-9-]+)\b([^>]*)data-v="([^"]+)"([^>]*)>([\s\S]*?)<\/\1>/i;
    const valueMatch = inner.match(valuePattern);
    if (!rowClass || !valueMatch) continue;
    const [, valueTag, valueLeftAttrs, , valueRightAttrs] = valueMatch;
    const valueClass = attrValue(`${valueLeftAttrs} ${valueRightAttrs}`, "class");
    template[field] = { rowTag, rowClass, valueTag, valueClass };
  }
  return template;
}

function attrValue(attrs, name) {
  const match = attrs.match(new RegExp(`\\b${name}="([^"]+)"`, "i"));
  return match ? match[1] : null;
}

function stripTags(html) {
  return html.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function isExact(parsed) {
  return Object.entries(record).every(([field, expected]) => parsed[field] === expected);
}

function benchmarkGeneration(churn) {
  const times = [];
  let totalBytes = 0;
  for (let i = 0; i < iterations; i += 1) {
    const seed = `bench-${i}`;
    const start = performance.now();
    const html = page(seed, { churn });
    const elapsed = performance.now() - start;
    times.push(elapsed);
    totalBytes += Buffer.byteLength(html, "utf8");
  }
  times.sort((a, b) => a - b);
  return {
    iterations,
    avgMs: Number((times.reduce((sum, value) => sum + value, 0) / times.length).toFixed(4)),
    p50Ms: Number(percentile(times, 0.5).toFixed(4)),
    p95Ms: Number(percentile(times, 0.95).toFixed(4)),
    avgBytes: Math.round(totalBytes / iterations),
  };
}

function percentile(sorted, p) {
  const index = Math.min(sorted.length - 1, Math.floor(sorted.length * p));
  return sorted[index];
}

async function renderMetrics() {
  const browser = await chromium.launch({ headless: true });
  const pageContext = await browser.newPage({ viewport: { width: 900, height: 500 }, deviceScaleFactor: 1 });
  const seed = "visual-same";
  const baseline = page(seed, { churn: false });
  const churned = page(seed, { churn: true });

  await pageContext.setContent(baseline);
  const baselineText = await pageContext.locator("body").innerText();
  const baselinePng = await pageContext.screenshot({ fullPage: true });
  await pageContext.setContent(churned);
  const churnedText = await pageContext.locator("body").innerText();
  const churnedPng = await pageContext.screenshot({ fullPage: true });
  await browser.close();

  const pixelMetrics = await comparePngPixels(baselinePng, churnedPng);

  return {
    innerTextEqual: normalize(baselineText) === normalize(churnedText),
    screenshotBytesEqual: baselinePng.equals(churnedPng),
    pixelEqual: pixelMetrics.diffPixels === 0,
    pixelDiffRatio: pixelMetrics.diffRatio,
    pixelMaxChannelDelta: pixelMetrics.maxChannelDelta,
  };
}

async function comparePngPixels(leftPng, rightPng) {
  const browser = await chromium.launch({ headless: true });
  const pageContext = await browser.newPage();
  const metrics = await pageContext.evaluate(
    async ({ left, right }) => {
      async function load(src) {
        const image = new Image();
        image.src = src;
        await image.decode();
        return image;
      }

      const leftImage = await load(left);
      const rightImage = await load(right);
      const width = Math.max(leftImage.width, rightImage.width);
      const height = Math.max(leftImage.height, rightImage.height);
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d");
      context.clearRect(0, 0, width, height);
      context.drawImage(leftImage, 0, 0);
      const leftData = context.getImageData(0, 0, width, height).data;
      context.clearRect(0, 0, width, height);
      context.drawImage(rightImage, 0, 0);
      const rightData = context.getImageData(0, 0, width, height).data;

      let diffPixels = 0;
      let maxChannelDelta = 0;
      for (let i = 0; i < leftData.length; i += 4) {
        const dr = Math.abs(leftData[i] - rightData[i]);
        const dg = Math.abs(leftData[i + 1] - rightData[i + 1]);
        const db = Math.abs(leftData[i + 2] - rightData[i + 2]);
        const da = Math.abs(leftData[i + 3] - rightData[i + 3]);
        const maxDelta = Math.max(dr, dg, db, da);
        if (maxDelta > 0) diffPixels += 1;
        if (maxDelta > maxChannelDelta) maxChannelDelta = maxDelta;
      }

      return {
        width,
        height,
        diffPixels,
        diffRatio: Number((diffPixels / (width * height)).toFixed(8)),
        maxChannelDelta,
      };
    },
    {
      left: `data:image/png;base64,${leftPng.toString("base64")}`,
      right: `data:image/png;base64,${rightPng.toString("base64")}`,
    },
  );
  await browser.close();
  return metrics;
}

function normalize(text) {
  return text.replace(/\s+/g, " ").trim();
}

async function main() {
  const baselineTemplate = learnTemplate(page("train", { churn: false }));
  const churnTemplate = learnTemplate(page("train", { churn: true }));
  const crawlerRows = [];

  for (let i = 0; i < samples; i += 1) {
    const seed = `session-${i}`;
    const baselineParsed = extractByTemplate(page(seed, { churn: false }), baselineTemplate);
    const churnParsedWithBaselineTemplate = extractByTemplate(page(seed, { churn: true }), baselineTemplate);
    const churnParsedWithTrainTemplate = extractByTemplate(page(seed, { churn: true }), churnTemplate);

    crawlerRows.push({
      seed,
      baselineWithBaselineTemplate: isExact(baselineParsed),
      churnWithBaselineTemplate: isExact(churnParsedWithBaselineTemplate),
      churnWithTrainTemplate: isExact(churnParsedWithTrainTemplate),
    });
  }

  const count = (key) => crawlerRows.filter((row) => row[key]).length;
  const baselineGeneration = benchmarkGeneration(false);
  const churnGeneration = benchmarkGeneration(true);
  const visual = await renderMetrics();

  console.log(JSON.stringify(
    {
      samples,
      crawler: {
        baselineTemplateOnBaseline: {
          exact: count("baselineWithBaselineTemplate"),
          rate: count("baselineWithBaselineTemplate") / samples,
        },
        baselineTemplateOnChurned: {
          exact: count("churnWithBaselineTemplate"),
          rate: count("churnWithBaselineTemplate") / samples,
        },
        oneChurnedTemplateOnOtherChurned: {
          exact: count("churnWithTrainTemplate"),
          rate: count("churnWithTrainTemplate") / samples,
        },
      },
      server: {
        baseline: baselineGeneration,
        churn: churnGeneration,
        overhead: {
          avgMsDelta: Number((churnGeneration.avgMs - baselineGeneration.avgMs).toFixed(4)),
          avgMsRatio: Number((churnGeneration.avgMs / baselineGeneration.avgMs).toFixed(2)),
          avgBytesDelta: churnGeneration.avgBytes - baselineGeneration.avgBytes,
          avgBytesRatio: Number((churnGeneration.avgBytes / baselineGeneration.avgBytes).toFixed(2)),
        },
      },
      rendering: visual,
      crawlerRows,
    },
    null,
    2,
  ));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
