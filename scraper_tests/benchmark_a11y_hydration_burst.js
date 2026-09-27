const fs = require("node:fs");
const http = require("node:http");

const { chromium } = require("playwright");
const { buildHtml, fieldSet } = require("./benchmark_sensitive_field_template");

const outArg = process.argv.includes("--out") ? process.argv[process.argv.indexOf("--out") + 1] : null;
const countsArg = process.argv.includes("--counts") ? process.argv[process.argv.indexOf("--counts") + 1] : "5,10,25,50,100";
const FIELD_COUNTS = countsArg
  .split(",")
  .map((item) => Number(item.trim()))
  .filter((item) => Number.isInteger(item) && item > 0);

function stats(values) {
  const sorted = values.slice().sort((a, b) => a - b);
  const pick = (p) => sorted[Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * p))] || 0;
  return {
    min: Number((sorted[0] || 0).toFixed(3)),
    median: Number(pick(0.5).toFixed(3)),
    p90: Number(pick(0.9).toFixed(3)),
    max: Number((sorted[sorted.length - 1] || 0).toFixed(3)),
  };
}

function makeVariant(fieldCount) {
  return {
    fieldCount,
    mode: "valueLive",
    html: buildHtml({ gated: true, placeholder: true, interactionGate: true, fieldCount, liveRegionMode: "value" }),
    expected: fieldSet({ fieldCount }).values,
  };
}

function makeVariants() {
  return FIELD_COUNTS.flatMap((fieldCount) => [
    makeVariant(fieldCount),
    {
      fieldCount,
      mode: "sectionLive",
      html: buildHtml({ gated: true, placeholder: true, interactionGate: true, fieldCount, liveRegionMode: "section" }),
      expected: fieldSet({ fieldCount }).values,
    },
  ]);
}

function startServer(variants) {
  const byName = new Map(variants.map((variant) => [`${variant.mode}-${variant.fieldCount}`, variant]));
  const server = http.createServer((req, res) => {
    const name = new URL(req.url, "http://localhost").pathname.replace(/^\/+/, "") || `${variants[0].mode}-${variants[0].fieldCount}`;
    const variant = byName.get(name);
    if (!variant) {
      res.writeHead(404);
      res.end("not found");
      return;
    }
    res.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
    res.end(variant.html);
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      resolve({ server, baseUrl: `http://127.0.0.1:${server.address().port}` });
    });
  });
}

async function measure(page, url, expectedValues) {
  await page.goto(url, { waitUntil: "load" });
  await page.evaluate(() => {
    window.__valueUpdates = [];
    const values = new Set([...document.querySelectorAll(".value")]);
    const observer = new MutationObserver((mutations) => {
      const now = performance.now();
      for (const mutation of mutations) {
        const target = mutation.type === "characterData" ? mutation.target.parentElement : mutation.target;
        if (!values.has(target)) continue;
        window.__valueUpdates.push({
          t: now,
          field: target.dataset.k || null,
          text: target.textContent || "",
        });
      }
    });
    observer.observe(document.querySelector(".details"), {
      subtree: true,
      childList: true,
      characterData: true,
    });
    window.__valueObserver = observer;
  });

  await page.evaluate((expected) => {
    const section = document.querySelector(".details");
    section.dispatchEvent(new PointerEvent("pointerenter", { bubbles: true, pointerType: "mouse" }));
    section.click();
    return new Promise((resolve) => {
      const deadline = performance.now() + 1000;
      const tick = () => {
        const text = document.body.innerText || "";
        if (expected.every((value) => text.includes(value)) || performance.now() > deadline) {
          requestAnimationFrame(() => resolve());
        } else {
          requestAnimationFrame(tick);
        }
      };
      tick();
    });
  }, Object.values(expectedValues));

  return page.evaluate((expected) => {
    window.__valueObserver.disconnect();
    const updates = window.__valueUpdates;
    const byField = new Map();
    for (const update of updates) byField.set(update.field, update);
    const times = [...byField.values()].map((update) => update.t).sort((a, b) => a - b);
    const gaps = times.slice(1).map((time, index) => time - times[index]);
    const burstDuration = times.length ? times[times.length - 1] - times[0] : 0;
    const bodyText = document.body.innerText || "";
    return {
      expectedFields: Object.keys(expected).length,
      changedFields: byField.size,
      sensitiveVisible: Object.values(expected).filter((value) => bodyText.includes(value)).length,
      mutationRecords: updates.length,
      firstUpdateAtMs: times.length ? Number(times[0].toFixed(3)) : null,
      burstDurationMs: Number(burstDuration.toFixed(3)),
      maxInterUpdateGapMs: Number((gaps.length ? Math.max(...gaps) : 0).toFixed(3)),
      sameFrameLikely: burstDuration <= 16.7,
      fieldsPerMs: burstDuration > 0 ? Number((byField.size / burstDuration).toFixed(3)) : null,
      liveNodeCount: document.querySelectorAll('[aria-live], [role="status"]').length,
      statusText: document.querySelector("[data-status]")?.textContent || null,
      statusMentionsFields: /contact|desk|reference|dataset|terms|sensitive|restricted|field/i.test(
        document.querySelector("[data-status]")?.textContent || "",
      ),
    };
  }, expectedValues);
}

async function main() {
  const variants = makeVariants();
  const { server, baseUrl } = await startServer(variants);
  const browser = await chromium.launch({ headless: true });
  const rows = [];
  try {
    for (const variant of variants) {
      for (let iteration = 0; iteration < 5; iteration += 1) {
        const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true });
        rows.push({
          fieldCount: variant.fieldCount,
          mode: variant.mode,
          iteration,
          ...(await measure(page, `${baseUrl}/${variant.mode}-${variant.fieldCount}`, variant.expected)),
        });
        await page.close();
      }
    }
  } finally {
    await browser.close();
    server.close();
  }

  const byCount = Object.fromEntries(
    FIELD_COUNTS.map((fieldCount) => [
      fieldCount,
      Object.fromEntries(
        ["valueLive", "sectionLive"].map((mode) => {
          const items = rows.filter((row) => row.fieldCount === fieldCount && row.mode === mode);
          return [
            mode,
            {
              samples: items.length,
              changedFields: stats(items.map((row) => row.changedFields)),
              burstDurationMs: stats(items.map((row) => row.burstDurationMs)),
              maxInterUpdateGapMs: stats(items.map((row) => row.maxInterUpdateGapMs)),
              sameFrameRate: Number((items.filter((row) => row.sameFrameLikely).length / items.length).toFixed(4)),
              fieldsPerMsMedian: stats(items.map((row) => row.fieldsPerMs || row.changedFields)),
              liveNodeCount: stats(items.map((row) => row.liveNodeCount)),
              statusMentionsFields: items.some((row) => row.statusMentionsFields),
              statusTexts: [...new Set(items.map((row) => row.statusText).filter(Boolean))],
            },
          ];
        }),
      ),
    ]),
  );

  const report = {
    generatedAt: new Date().toISOString(),
    fieldCounts: FIELD_COUNTS,
    byCount,
    sourceStatusFingerprint: Object.fromEntries(
      variants.map((variant) => {
        const statusElement = variant.html.match(/<div class="sr-only"[^>]*data-status[^>]*>([\s\S]*?)<\/div>/i);
        const statusScript = variant.html.match(/status\.textContent\s*=\s*"([^"]*)"/i);
        const statusText = [statusElement?.[1] || "", statusScript?.[1] || ""].join(" ");
        return [
          `${variant.mode}-${variant.fieldCount}`,
          {
            statusStringPresent: statusText.includes("Details updated."),
            fieldNamesInStatus: /Contact|Desk|Reference|Dataset|Terms/.test(statusText),
            fieldCountInStatus: new RegExp(`\\b${variant.fieldCount}\\b`).test(statusText),
            sensitiveIntentWordsInStatus: /sensitive|restricted|protected/i.test(statusText),
          },
        ];
      }),
    ),
    rawRows: rows,
    interpretation: {
      measured:
        "Mutation timing for the current interaction-gated template. This measures DOM update burst shape, not actual screen-reader speech output.",
      risk:
        "When many aria-live/status nodes update inside one frame, assistive technologies may coalesce, reorder, skip, or interrupt announcements depending on browser and screen-reader implementation.",
    },
  };
  const output = JSON.stringify(report, null, 2);
  if (outArg) fs.writeFileSync(outArg, `${output}\n`, "utf8");
  console.log(output);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
