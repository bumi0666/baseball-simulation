const zlib = require("node:zlib");
const { performance } = require("node:perf_hooks");

const publicRecord = {
  title: "Alpha Research Portal",
  summary:
    "A public overview of the Alpha research program, including project status, regional scope, and publication schedule.",
  body:
    "The Alpha research program shares public progress updates, non-sensitive milestones, and general methodology notes for external readers and search indexing.",
  category: "Research Operations",
};

const sensitive = {
  owner_email: "mina.park@example.test",
  direct_phone: "+82-10-5555-0137",
  internal_case_id: "INT-ALPHA-7429",
  restricted_dataset: "private cohort dataset Q4",
  contract_floor: "$42,500 minimum",
};

const fieldLabels = {
  owner_email: "Contact",
  direct_phone: "Desk",
  internal_case_id: "Reference",
  restricted_dataset: "Dataset",
  contract_floor: "Terms",
};

const placeholders = {
  owner_email: "Available on request",
  direct_phone: "Contact team",
  internal_case_id: "Restricted",
  restricted_dataset: "Access required",
  contract_floor: "Not publicly listed",
};

function syntheticField(index) {
  const n = String(index + 1).padStart(3, "0");
  const placeholderCycle = Object.values(placeholders);
  return {
    field: `sensitive_field_${n}`,
    label: `Detail ${n}`,
    value: `restricted value ${n} alpha ${((index * 7919) % 100000).toString().padStart(5, "0")}`,
    placeholder: placeholderCycle[index % placeholderCycle.length],
  };
}

function fieldSet({ fieldSubset = null, fieldCount = null } = {}) {
  if (fieldCount == null) {
    const fields = fieldSubset || Object.keys(fieldLabels);
    return {
      fields,
      labels: Object.fromEntries(fields.map((field) => [field, fieldLabels[field]])),
      values: Object.fromEntries(fields.map((field) => [field, sensitive[field]])),
      placeholders: Object.fromEntries(fields.map((field) => [field, placeholders[field]])),
    };
  }

  const count = Number(fieldCount);
  if (!Number.isInteger(count) || count < 1) throw new Error(`fieldCount must be a positive integer: ${fieldCount}`);
  const generated = Array.from({ length: count }, (_, index) => syntheticField(index));
  return {
    fields: generated.map((item) => item.field),
    labels: Object.fromEntries(generated.map((item) => [item.field, item.label])),
    values: Object.fromEntries(generated.map((item) => [item.field, item.value])),
    placeholders: Object.fromEntries(generated.map((item) => [item.field, item.placeholder])),
  };
}

function encodeValue(value, key) {
  return [...String(value)].map((char, index) => char.charCodeAt(0) ^ ((key + index * 23) & 255));
}

function sensitiveNeutralForSalt(salt) {
  return salt ^ salt;
}

function sensitiveDecodeForSalt(codes, key, salt) {
  const neutral = sensitiveNeutralForSalt(salt);
  return codes
    .map((code, index) => String.fromCharCode((code ^ neutral) ^ ((key + index * 23) & 255)))
    .join("");
}

function htmlEscape(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function buildPayload(values = sensitive) {
  const key = 119;
  return {
    key,
    rows: Object.fromEntries(
      Object.entries(values).map(([field, value]) => [field, encodeValue(value, key)]),
    ),
  };
}

function splitValue(value) {
  const text = String(value);
  const a = Math.ceil(text.length / 3);
  const b = Math.ceil((text.length - a) / 2);
  return [text.slice(0, a), text.slice(a, a + b), text.slice(a + b)];
}

function base64Encode(value) {
  return Buffer.from(String(value), "utf8").toString("base64");
}

function splitBase64(value) {
  return splitValue(base64Encode(value));
}

function buildHtml({
  gated = true,
  placeholder = false,
  interactionGate = false,
  hydrationLike = false,
  base64Payload = false,
  base64SplitPayload = false,
  fieldSubset = null,
  fieldCount = null,
  layoutVariant = "compact",
  liveRegionMode = "value",
  renderGuard = "none",
  interactionGateMode = "simple",
} = {}) {
  const active = fieldSet({ fieldSubset, fieldCount });
  const activeFields = active.fields;
  const sensitiveRows = activeFields
    .map((field) => [field, active.labels[field]])
    .map(([field, label]) => {
      const parts = splitValue(active.values[field]);
      const b64Parts = splitBase64(active.values[field]);
      const attrs = base64Payload
        ? ` data-k="${field}" data-config="${htmlEscape(base64Encode(active.values[field]))}"`
        : base64SplitPayload
          ? ` data-k="${field}" data-config="${htmlEscape(b64Parts[1])}" data-ref="${htmlEscape(b64Parts[0])}" data-state="${htmlEscape(b64Parts[2])}"`
          : hydrationLike
        ? ` data-k="${field}" data-config="${htmlEscape(parts[1])}" data-ref="${htmlEscape(parts[0])}" data-state="${htmlEscape(parts[2])}"`
        : ` data-k="${field}"`;
      const liveAttrs = gated && placeholder && liveRegionMode === "value"
        ? ` role="status" aria-live="polite" aria-atomic="true"`
        : "";
      const value = gated
        ? `<span class="value"${attrs}${liveAttrs}>${placeholder ? htmlEscape(active.placeholders[field]) : ""}</span>`
        : `<span class="value">${htmlEscape(active.values[field])}</span>`;
      const row = `<div class="meta-row"><span class="label">${htmlEscape(label)}</span>${value}</div>`;
      return layoutVariant === "deep-dom"
        ? `<div class="row-shell"><div class="row-inner"><div class="row-leaf">${row}</div></div></div>`
        : row;
    })
    .join("\n");

  const publicBody =
    layoutVariant === "dense-public"
      ? `${publicRecord.body} Additional public notes describe governance cadence, reporting frequency, regional scope, publication review, and non-sensitive methodology boundaries. These paragraphs intentionally increase surrounding text without exposing restricted operational details.`
      : publicRecord.body;
  const preDetails =
    layoutVariant === "below-fold"
      ? `<div class="spacer" aria-hidden="true"></div><p class="content">Further public context appears before the additional details section.</p>`
      : "";
  const renderGuardHelpers = renderGuard === "simple"
    ? `
      function simpleRenderReady(section) {
        const rect = section.getBoundingClientRect();
        const style = getComputedStyle(section);
        return rect.width > 240 && rect.height > 20 && style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity) > 0;
      }
      async function renderReady(section) {
        return simpleRenderReady(section);
      }`
    : renderGuard === "quorum"
      ? `
      function containsOrIs(root, node) {
        return root === node || (root && node && root.contains(node));
      }
      function simpleRenderReady(section) {
        const rect = section.getBoundingClientRect();
        const style = getComputedStyle(section);
        return rect.width > 240 && rect.height > 20 && style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity) > 0;
      }
      async function quorumRenderReady(section) {
        if (!simpleRenderReady(section)) return false;
        if (document.fonts && document.fonts.ready) await document.fonts.ready.catch(() => {});
        const first = section.getBoundingClientRect();
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        const second = section.getBoundingClientRect();
        const stable = Math.abs(first.top - second.top) < 1 && Math.abs(first.left - second.left) < 1 && Math.abs(first.width - second.width) < 1 && Math.abs(first.height - second.height) < 1;
        if (!stable) return false;
        const cx = second.left + second.width / 2;
        const cy = second.top + Math.min(second.height / 2, 24);
        const inViewport = cx >= 0 && cy >= 0 && cx <= window.innerWidth && cy <= window.innerHeight;
        if (!inViewport) return false;
        const top = document.elementFromPoint(cx, cy);
        return containsOrIs(section, top);
      }
      async function renderReady(section) {
        return quorumRenderReady(section);
      }`
      : `
      async function renderReady() {
        return true;
      }`;

  const payload = base64Payload || base64SplitPayload
    ? `<script>
    (() => {
      function ready(section) {
        const rect = section.getBoundingClientRect();
        return rect.width > 240 && rect.height > 20 && getComputedStyle(section).display !== "none";
      }
      function text(node) {
        const encoded = [node.dataset.ref || "", node.dataset.config || "", node.dataset.state || ""].join("");
        return decodeURIComponent(escape(atob(encoded)));
      }
      function apply(section) {
        if (!ready(section)) return;
        section.querySelectorAll("[data-k]").forEach((node) => {
          node.textContent = text(node);
        });
      }
      document.addEventListener("DOMContentLoaded", () => {
        const section = document.querySelector(".details");
        if (!("IntersectionObserver" in window)) {
          apply(section);
          return;
        }
        const observer = new IntersectionObserver((entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              apply(entry.target);
              observer.disconnect();
            }
          });
        }, { rootMargin: "80px" });
        observer.observe(section);
      });
    })();
  </script>`
    : hydrationLike
    ? `<script>
    (() => {
      function ready(section) {
        const rect = section.getBoundingClientRect();
        const style = getComputedStyle(section);
        return rect.width > 240 && rect.height > 20 && style.display !== "none";
      }
      function apply(section) {
        if (!ready(section)) return;
        section.querySelectorAll("[data-k]").forEach((node) => {
          node.textContent = [node.dataset.ref, node.dataset.config, node.dataset.state].join("");
        });
      }
      document.addEventListener("DOMContentLoaded", () => {
        const section = document.querySelector(".details");
        if (!("IntersectionObserver" in window)) {
          apply(section);
          return;
        }
        const observer = new IntersectionObserver((entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              apply(entry.target);
              observer.disconnect();
            }
          });
        }, { rootMargin: "80px" });
        observer.observe(section);
      });
    })();
  </script>`
    : gated
    ? `<script type="application/json" id="page-data">${JSON.stringify(buildPayload(active.values))}</script>
  <script>
    (() => {
      const data = JSON.parse(document.querySelector("#page-data").textContent);
      let revealed = false;
      let pending = false;
      function read(codes) {
        const canvas = document.createElement("canvas");
        const ctx = canvas.getContext("2d");
        ctx.font = getComputedStyle(document.body).font;
        const salt = Math.round(ctx.measureText(document.title + ":" + window.devicePixelRatio).width);
        const neutral = salt ^ salt;
        return codes
          .map((code, index) => String.fromCharCode((code ^ neutral) ^ ((data.key + index * 23) & 255)))
          .join("");
      }
      ${renderGuardHelpers}
      async function reveal() {
        if (revealed || pending) return;
        const section = document.querySelector(".details");
        if (!section) return;
        pending = true;
        const ready = await renderReady(section);
        pending = false;
        if (!ready || revealed) return;
        revealed = true;
        document.querySelectorAll("[data-k]").forEach((node) => {
          node.textContent = read(data.rows[node.dataset.k]);
        });
        ${liveRegionMode === "section" ? `
        const status = document.querySelector("[data-status]");
        if (status) status.textContent = "Details updated.";
        ` : ""}
      }
      document.addEventListener("DOMContentLoaded", () => {
        const section = document.querySelector(".details");
        if (!section) return;
        ${interactionGate && interactionGateMode === "sequence" ? `
        section.tabIndex = 0;
        const gate = { pointerInside: false, enteredAt: 0, moves: 0, focusedAt: 0 };
        const contains = (node) => section === node || section.contains(node);
        const visibleTarget = (event) => {
          if (!contains(event.target)) return false;
          if (typeof event.clientX !== "number" || typeof event.clientY !== "number") return true;
          if (event.clientX === 0 && event.clientY === 0) return false;
          const top = document.elementFromPoint(event.clientX, event.clientY);
          return contains(top);
        };
        const pointerReady = (event) => (
          gate.pointerInside &&
          gate.moves >= 2 &&
          performance.now() - gate.enteredAt >= 500 &&
          visibleTarget(event)
        );
        const keyboardReady = () => gate.focusedAt > 0 && performance.now() - gate.focusedAt >= 300;
        section.addEventListener("pointerenter", (event) => {
          if (!visibleTarget(event)) return;
          gate.pointerInside = true;
          gate.enteredAt = performance.now();
          gate.moves = 0;
        });
        section.addEventListener("pointerleave", () => {
          gate.pointerInside = false;
          gate.moves = 0;
        });
        section.addEventListener("pointermove", (event) => {
          if (!gate.pointerInside || !visibleTarget(event)) return;
          gate.moves += 1;
        });
        section.addEventListener("click", (event) => {
          if (pointerReady(event)) reveal();
        });
        section.addEventListener("focusin", () => {
          gate.focusedAt = performance.now();
        });
        section.addEventListener("keydown", (event) => {
          if ((event.key === "Enter" || event.key === " ") && keyboardReady()) reveal();
        });
        ` : interactionGate ? `
        section.tabIndex = 0;
        section.addEventListener("pointerenter", reveal);
        section.addEventListener("focusin", reveal);
        section.addEventListener("click", reveal);
        section.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") reveal();
        });
        ` : "reveal();"}
      });
    })();
  </script>`
    : "";

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>${htmlEscape(publicRecord.title)}</title>
  <meta name="description" content="${htmlEscape(publicRecord.summary)}">
  <style>
    body { font: 16px Arial, sans-serif; margin: 32px; color: #202124; line-height: 1.5; }
    main { max-width: 760px; }
    h1 { font-size: 28px; margin: 0 0 12px; }
    .summary { font-size: 18px; margin: 0 0 18px; }
    .content { margin: 0 0 24px; }
    .details { border-top: 1px solid #ddd; padding-top: 14px; }
    .meta-row { display: grid; grid-template-columns: 150px 1fr; min-height: 24px; gap: 12px; }
    .label { font-weight: 700; }
    .row-shell, .row-inner, .row-leaf { display: contents; }
    .spacer { height: 1200px; }
    .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
  </style>
</head>
<body>
  <main>
    <article>
      <h1>${htmlEscape(publicRecord.title)}</h1>
      <p class="summary">${htmlEscape(publicRecord.summary)}</p>
      <p class="content">${htmlEscape(publicBody)}</p>
      <p class="category">Category: ${htmlEscape(publicRecord.category)}</p>
      ${preDetails}
      <section class="details" aria-label="Additional details">
        ${sensitiveRows}
      </section>
      ${gated && placeholder && liveRegionMode === "section" ? `<div class="sr-only" role="status" aria-live="polite" aria-atomic="true" data-status></div>` : ""}
    </article>
  </main>
  ${payload}
</body>
</html>`;
}

function normalize(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

function stripHtml(html) {
  return normalize(
    html
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<[^>]+>/g, " "),
  );
}

function publicCoverage(text) {
  const haystack = normalize(text).toLowerCase();
  const values = Object.values(publicRecord);
  const found = values.filter((value) => haystack.includes(normalize(value).toLowerCase())).length;
  return { found, total: values.length, rate: Number((found / values.length).toFixed(4)) };
}

function sensitiveLeakage(text, values = sensitive) {
  const haystack = normalize(text).toLowerCase();
  const expected = Object.values(values);
  const leaked = expected.filter((value) => haystack.includes(normalize(value).toLowerCase()));
  return { leaked: leaked.length, total: expected.length, rate: Number((leaked.length / expected.length).toFixed(4)), values: leaked };
}

function sensitivePartExposure(html, values = sensitive) {
  const exposures = Object.entries(values).map(([field, value]) => {
    const parts = splitValue(value);
    const found = parts.filter((part) => part && html.includes(part));
    return { field, found: found.length, total: parts.length };
  });
  const found = exposures.reduce((sum, item) => sum + item.found, 0);
  const total = exposures.reduce((sum, item) => sum + item.total, 0);
  return { found, total, rate: Number((found / total).toFixed(4)), exposures };
}

function placeholderExtraction(text, placeholderValues = placeholders) {
  const haystack = normalize(text).toLowerCase();
  const values = Object.values(placeholderValues);
  const found = values.filter((value) => haystack.includes(normalize(value).toLowerCase()));
  return { found: found.length, total: values.length, rate: Number((found.length / values.length).toFixed(4)), values: found };
}

function sourceFingerprint(html) {
  const rawBytes = Buffer.byteLength(html, "utf8");
  const gzipBytes = zlib.gzipSync(html).length;
  return {
    rawBytes,
    gzipBytes,
    inlineScriptBytes: [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].reduce(
      (sum, match) => sum + Buffer.byteLength(match[1] || "", "utf8"),
      0,
    ),
    emptyValueSlots: (html.match(/class="value" data-k="[^"]+">\s*<\/span>/g) || []).length,
    placeholderSlots: Object.values(placeholders).filter((value) => html.includes(value)).length,
    encodedPayloads: (html.match(/type="application\/json"/g) || []).length,
    suspiciousApis:
      (html.match(/measureText|getComputedStyle|devicePixelRatio|fromCharCode|\^|IntersectionObserver|atob/g) || []).length,
    sourcePatterns: {
      measureText: (html.match(/measureText/g) || []).length,
      getComputedStyle: (html.match(/getComputedStyle/g) || []).length,
      devicePixelRatio: (html.match(/devicePixelRatio/g) || []).length,
      fromCharCode: (html.match(/fromCharCode/g) || []).length,
      xorOperator: (html.match(/\^/g) || []).length,
      jsonPayload: (html.match(/type="application\/json"/g) || []).length,
      intersectionObserver: (html.match(/IntersectionObserver/g) || []).length,
      atob: (html.match(/atob/g) || []).length,
    },
    numberTokens: (html.match(/-?\d+(?:\.\d+)?/g) || []).length,
  };
}

async function renderedText(html) {
  const { chromium } = require("playwright");
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
  const start = performance.now();
  await page.setContent(html, { waitUntil: "load" });
  await page.waitForTimeout(50);
  const text = await page.locator("body").innerText();
  const ms = performance.now() - start;
  await browser.close();
  return { text, ms: Number(ms.toFixed(3)) };
}

async function main() {
  const plainHtml = buildHtml({ gated: false });
  const gatedHtml = buildHtml({ gated: true });
  const placeholderHtml = buildHtml({ gated: true, placeholder: true });
  const hydrationHtml = buildHtml({ gated: true, placeholder: true, hydrationLike: true });
  const base64Html = buildHtml({ gated: true, placeholder: true, base64Payload: true });
  const base64SplitHtml = buildHtml({ gated: true, placeholder: true, base64SplitPayload: true });
  const plainSource = stripHtml(plainHtml);
  const gatedSource = stripHtml(gatedHtml);
  const placeholderSource = stripHtml(placeholderHtml);
  const hydrationSource = stripHtml(hydrationHtml);
  const base64Source = stripHtml(base64Html);
  const base64SplitSource = stripHtml(base64SplitHtml);
  const plainRendered = await renderedText(plainHtml);
  const gatedRendered = await renderedText(gatedHtml);
  const placeholderRendered = await renderedText(placeholderHtml);
  const hydrationRendered = await renderedText(hydrationHtml);
  const base64Rendered = await renderedText(base64Html);
  const base64SplitRendered = await renderedText(base64SplitHtml);

  console.log(
    JSON.stringify(
      {
        variants: [
          "plain",
          "emptySlotGated",
          "placeholderGated",
          "hydrationLikeGated",
          "base64Payload",
          "base64SplitPayload",
        ],
        publicRecord,
        sensitiveFieldCount: Object.keys(sensitive).length,
        source: {
          plain: {
            publicCoverage: publicCoverage(plainSource),
            sensitiveLeakage: sensitiveLeakage(plainSource),
            sensitivePartExposure: sensitivePartExposure(plainHtml),
            placeholderExtraction: placeholderExtraction(plainSource),
            fingerprint: sourceFingerprint(plainHtml),
          },
          emptySlotGated: {
            publicCoverage: publicCoverage(gatedSource),
            sensitiveLeakage: sensitiveLeakage(gatedSource),
            sensitivePartExposure: sensitivePartExposure(gatedHtml),
            placeholderExtraction: placeholderExtraction(gatedSource),
            fingerprint: sourceFingerprint(gatedHtml),
          },
          placeholderGated: {
            publicCoverage: publicCoverage(placeholderSource),
            sensitiveLeakage: sensitiveLeakage(placeholderSource),
            sensitivePartExposure: sensitivePartExposure(placeholderHtml),
            placeholderExtraction: placeholderExtraction(placeholderSource),
            fingerprint: sourceFingerprint(placeholderHtml),
          },
          hydrationLikeGated: {
            publicCoverage: publicCoverage(hydrationSource),
            sensitiveLeakage: sensitiveLeakage(hydrationSource),
            sensitivePartExposure: sensitivePartExposure(hydrationHtml),
            placeholderExtraction: placeholderExtraction(hydrationSource),
            fingerprint: sourceFingerprint(hydrationHtml),
          },
          base64Payload: {
            publicCoverage: publicCoverage(base64Source),
            sensitiveLeakage: sensitiveLeakage(base64Source),
            sensitivePartExposure: sensitivePartExposure(base64Html),
            placeholderExtraction: placeholderExtraction(base64Source),
            fingerprint: sourceFingerprint(base64Html),
          },
          base64SplitPayload: {
            publicCoverage: publicCoverage(base64SplitSource),
            sensitiveLeakage: sensitiveLeakage(base64SplitSource),
            sensitivePartExposure: sensitivePartExposure(base64SplitHtml),
            placeholderExtraction: placeholderExtraction(base64SplitSource),
            fingerprint: sourceFingerprint(base64SplitHtml),
          },
        },
        rendered: {
          plain: {
            publicCoverage: publicCoverage(plainRendered.text),
            sensitiveLeakage: sensitiveLeakage(plainRendered.text),
            placeholderExtraction: placeholderExtraction(plainRendered.text),
            renderMs: plainRendered.ms,
          },
          emptySlotGated: {
            publicCoverage: publicCoverage(gatedRendered.text),
            sensitiveLeakage: sensitiveLeakage(gatedRendered.text),
            placeholderExtraction: placeholderExtraction(gatedRendered.text),
            renderMs: gatedRendered.ms,
          },
          placeholderGated: {
            publicCoverage: publicCoverage(placeholderRendered.text),
            sensitiveLeakage: sensitiveLeakage(placeholderRendered.text),
            placeholderExtraction: placeholderExtraction(placeholderRendered.text),
            renderMs: placeholderRendered.ms,
          },
          hydrationLikeGated: {
            publicCoverage: publicCoverage(hydrationRendered.text),
            sensitiveLeakage: sensitiveLeakage(hydrationRendered.text),
            placeholderExtraction: placeholderExtraction(hydrationRendered.text),
            renderMs: hydrationRendered.ms,
          },
          base64Payload: {
            publicCoverage: publicCoverage(base64Rendered.text),
            sensitiveLeakage: sensitiveLeakage(base64Rendered.text),
            placeholderExtraction: placeholderExtraction(base64Rendered.text),
            renderMs: base64Rendered.ms,
          },
          base64SplitPayload: {
            publicCoverage: publicCoverage(base64SplitRendered.text),
            sensitiveLeakage: sensitiveLeakage(base64SplitRendered.text),
            placeholderExtraction: placeholderExtraction(base64SplitRendered.text),
            renderMs: base64SplitRendered.ms,
          },
        },
      },
      null,
      2,
    ),
  );
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}

module.exports = {
  buildHtml,
  buildPayload,
  encodeValue,
  fieldSet,
  publicRecord,
  sensitive,
  sensitiveDecodeForSalt,
  sensitiveNeutralForSalt,
};
