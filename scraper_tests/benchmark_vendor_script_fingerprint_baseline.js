const { buildHtml } = require("./benchmark_sensitive_field_template");

const waitMs = Number(process.env.WAIT_MS || 0);

const defaultScriptUrls = [
  "https://challenges.cloudflare.com/turnstile/v0/api.js",
  "https://www.google.com/recaptcha/api.js",
  "https://js.hcaptcha.com/1/api.js",
  "https://cdn.jsdelivr.net/npm/@fingerprintjs/fingerprintjs@4/dist/fp.min.js",
  "https://browser.sentry-cdn.com/8.54.0/bundle.tracing.min.js",
  "https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX",
  "https://www.google-analytics.com/analytics.js",
];

function urls() {
  if (!process.env.SCRIPT_URLS) return defaultScriptUrls;
  return process.env.SCRIPT_URLS.split(",").map((url) => url.trim()).filter(Boolean);
}

function countMatches(text, pattern) {
  return (text.match(pattern) || []).length;
}

function entropy(text) {
  if (!text) return 0;
  const counts = new Map();
  for (const char of text) counts.set(char, (counts.get(char) || 0) + 1);
  let value = 0;
  for (const count of counts.values()) {
    const p = count / text.length;
    value -= p * Math.log2(p);
  }
  return Number(value.toFixed(4));
}

function longestStringLiteral(text) {
  const strings = [...text.matchAll(/(["'`])((?:\\.|(?!\1)[\s\S]){8,}?)\1/g)].map((match) => match[2]);
  strings.sort((a, b) => b.length - a.length);
  return strings[0]?.length || 0;
}

function fingerprint(text) {
  const rawBytes = Buffer.byteLength(text, "utf8");
  const counts = {
    fromCharCode: countMatches(text, /fromCharCode/g),
    charCodeAt: countMatches(text, /charCodeAt/g),
    atob: countMatches(text, /\batob\b/g),
    btoa: countMatches(text, /\bbtoa\b/g),
    xorOperator: countMatches(text, /\^/g),
    bitwiseOperators: countMatches(text, /(?:>>>|>>|<<|~|\||&|\^)/g),
    typedArrays: countMatches(text, /Uint8Array|Uint16Array|Uint32Array|ArrayBuffer|DataView/g),
    crypto: countMatches(text, /crypto|subtle|randomUUID|getRandomValues/g),
    canvasApis: countMatches(text, /canvas|getContext|measureText|toDataURL/g),
    layoutApis: countMatches(text, /getBoundingClientRect|getComputedStyle|devicePixelRatio/g),
    jsonPayload: countMatches(text, /application\/json|JSON\.parse|JSON\.stringify/g),
    stringArrayLike: countMatches(text, /\[[\s\n]*(?:(?:"[^"]{3,}"|'[^']{3,}')\s*,\s*){5,}/g),
    numericArrayLike: countMatches(text, /\[[\s\n]*(?:(?:\d{1,5})\s*,\s*){12,}/g),
    base64LikeStrings: countMatches(text, /["'][A-Za-z0-9+/]{24,}={0,2}["']/g),
  };
  return {
    rawBytes,
    entropyBitsPerChar: entropy(text),
    longestStringLiteral: longestStringLiteral(text),
    counts,
    densityPerKb: Object.fromEntries(
      Object.entries(counts).map(([key, value]) => [
        key,
        Number((value / Math.max(1, rawBytes / 1024)).toFixed(3)),
      ]),
    ),
  };
}

function extractLocalScripts() {
  const html = buildHtml({ gated: true, placeholder: true });
  return [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)]
    .map((match) => match[1] || "")
    .join("\n");
}

async function fetchScript(url) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
        Accept: "application/javascript,text/javascript,*/*;q=0.8",
      },
    });
    const text = await response.text();
    return {
      url,
      status: response.status,
      contentType: response.headers.get("content-type"),
      error: response.ok ? null : `HTTP ${response.status}`,
      fingerprint: fingerprint(text),
      preview: text.slice(0, 80),
    };
  } catch (error) {
    return {
      url,
      status: null,
      contentType: null,
      error: String(error.message || error),
      fingerprint: null,
    };
  } finally {
    clearTimeout(timeout);
  }
}

function summarize(rows) {
  const ok = rows.filter((row) => row.fingerprint);
  const keys = [
    "fromCharCode",
    "charCodeAt",
    "atob",
    "xorOperator",
    "bitwiseOperators",
    "typedArrays",
    "canvasApis",
    "layoutApis",
    "base64LikeStrings",
  ];
  const summary = {};
  for (const key of keys) {
    const values = ok.map((row) => row.fingerprint.counts[key]).sort((a, b) => a - b);
    if (!values.length) continue;
    summary[key] = {
      min: values[0],
      median: values[Math.floor(values.length / 2)],
      max: values[values.length - 1],
    };
  }
  return summary;
}

async function main() {
  const localScript = extractLocalScripts();
  const rows = [];
  for (const url of urls()) {
    process.stderr.write(`Fetching ${url}\n`);
    rows.push(await fetchScript(url));
    if (waitMs) await new Promise((resolve) => setTimeout(resolve, waitMs));
  }
  const local = {
    label: "local:placeholderGated scripts",
    fingerprint: fingerprint(localScript),
  };
  console.log(
    JSON.stringify(
      {
        local,
        vendorScripts: rows,
        baselineSummary: summarize(rows),
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
