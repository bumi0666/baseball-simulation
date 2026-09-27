const fs = require("node:fs");
const http = require("node:http");

const { buildHtml, publicRecord, sensitive } = require("./benchmark_sensitive_field_template");
const { externalize, runtimePadding } = require("./benchmark_script_placement_context");

const outArg = process.argv.includes("--out") ? process.argv[process.argv.indexOf("--out") + 1] : null;

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function splitParts(value) {
  const text = String(value);
  const a = Math.ceil(text.length / 3);
  const b = Math.ceil((text.length - a) / 2);
  return [text.slice(0, a), text.slice(a, a + b), text.slice(a + b)].filter((part) => part.length >= 6);
}

function buildFinalCandidate() {
  const inlineHtml = buildHtml({ gated: true, placeholder: true, interactionGate: true });
  const external = externalize(inlineHtml, "/assets/runtime/risk-events.js");
  return {
    html: external.html,
    js: `${runtimePadding()}\n${external.js}`,
  };
}

function publicJsonLd() {
  return JSON.stringify(
    {
      "@context": "https://schema.org",
      "@type": "Article",
      headline: publicRecord.title,
      description: publicRecord.summary,
      articleSection: publicRecord.category,
    },
    null,
    2,
  );
}

function buildRoutes() {
  const candidate = buildFinalCandidate();
  const safeShell = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${escapeHtml(
    publicRecord.title,
  )}</title><script type="application/ld+json">${publicJsonLd()}</script></head><body><h1>${escapeHtml(
    publicRecord.title,
  )}</h1><p>${escapeHtml(publicRecord.summary)}</p><p>${escapeHtml(publicRecord.body)}</p></body></html>`;
  return {
    "/": { contentType: "text/html; charset=utf-8", body: candidate.html },
    "/assets/runtime/risk-events.js": {
      contentType: "application/javascript; charset=utf-8",
      body: candidate.js,
    },
    "/structured": { contentType: "text/html; charset=utf-8", body: safeShell },
    "/sitemap.xml": {
      contentType: "application/xml; charset=utf-8",
      body: `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.test/alpha</loc><lastmod>2026-07-30</lastmod></url>
</urlset>`,
    },
    "/feed.xml": {
      contentType: "application/rss+xml; charset=utf-8",
      body: `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>${escapeHtml(publicRecord.title)}</title><description>${escapeHtml(
        publicRecord.summary,
      )}</description><item><title>${escapeHtml(publicRecord.title)}</title><description>${escapeHtml(
        publicRecord.body,
      )}</description></item></channel></rss>`,
    },
    "/amp": {
      contentType: "text/html; charset=utf-8",
      body: `<!doctype html><html amp lang="en"><head><meta charset="utf-8"><title>${escapeHtml(
        publicRecord.title,
      )}</title><script async src="https://cdn.ampproject.org/v0.js"></script></head><body><h1>${escapeHtml(
        publicRecord.title,
      )}</h1><p>${escapeHtml(publicRecord.summary)}</p><p>Contact team for restricted details.</p></body></html>`,
    },
    "/print": {
      contentType: "text/html; charset=utf-8",
      body: `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${escapeHtml(
        publicRecord.title,
      )}</title><style>@media print { body { color: #000; } }</style></head><body><h1>${escapeHtml(
        publicRecord.title,
      )}</h1><p>${escapeHtml(publicRecord.body)}</p><dl><dt>Contact</dt><dd>Available on request</dd><dt>Dataset</dt><dd>Access required</dd></dl></body></html>`,
    },
    "/api/public-summary": {
      contentType: "application/json; charset=utf-8",
      body: JSON.stringify({
        title: publicRecord.title,
        summary: publicRecord.summary,
        category: publicRecord.category,
      }),
    },
  };
}

function startServer(routes) {
  const server = http.createServer((req, res) => {
    const path = new URL(req.url, "http://localhost").pathname;
    const route = routes[path];
    if (!route) {
      res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
      res.end("not found");
      return;
    }
    res.writeHead(200, { "content-type": route.contentType, "cache-control": "no-store" });
    res.end(route.body);
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      resolve({ server, baseUrl: `http://127.0.0.1:${server.address().port}` });
    });
  });
}

function scanText(label, text) {
  const haystack = String(text).toLowerCase();
  const fullLeaks = Object.entries(sensitive)
    .filter(([, value]) => haystack.includes(String(value).toLowerCase()))
    .map(([field, value]) => ({ field, value }));
  const partLeaks = Object.entries(sensitive).map(([field, value]) => {
    const parts = splitParts(value);
    const foundParts = parts.filter((part) => haystack.includes(part.toLowerCase()));
    const significant = foundParts.length >= 2 || foundParts.some((part) => part.length >= 12);
    return {
      field,
      found: foundParts.length,
      total: parts.length,
      foundParts,
      significant,
    };
  });
  const apiHints = [
    ...String(text).matchAll(/\bfetch\s*\(\s*["'`]([^"'`]+)["'`]/g),
    ...String(text).matchAll(/\bXMLHttpRequest\b/g),
    ...String(text).matchAll(/["'`]([^"'`]*(?:\/api\/|graphql)[^"'`]*)["'`]/gi),
  ].map((match) => match[1] || match[0]);
  const structuredDataScripts = [...String(text).matchAll(/<script\b[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi)].map(
    (match) => match[1],
  );
  return {
    label,
    rawBytes: Buffer.byteLength(String(text), "utf8"),
    fullLeaks,
    partLeaks,
    apiHints: [...new Set(apiHints)],
    structuredDataScripts: structuredDataScripts.length,
    structuredDataLeaks: structuredDataScripts.flatMap((script, index) => scanText(`${label}#ldjson-${index}`, script).fullLeaks),
  };
}

async function fetchRoute(baseUrl, path) {
  const response = await fetch(`${baseUrl}${path}`);
  return {
    path,
    status: response.status,
    contentType: response.headers.get("content-type"),
    body: await response.text(),
  };
}

async function run() {
  const routes = buildRoutes();
  const { server, baseUrl } = await startServer(routes);
  try {
    const responses = [];
    for (const path of Object.keys(routes)) {
      responses.push(await fetchRoute(baseUrl, path));
    }
    const routeAudits = responses.map((response) => ({
      path: response.path,
      status: response.status,
      contentType: response.contentType,
      ...scanText(response.path, response.body),
    }));
    const sourceDiscovery = scanText("combined deployed surfaces", responses.map((response) => response.body).join("\n"));
    const leakRoutes = routeAudits.filter((route) => route.fullLeaks.length || route.structuredDataLeaks.length);
    const partExposureRoutes = routeAudits.filter((route) => route.partLeaks.some((entry) => entry.significant));
    const apiHintRoutes = routeAudits.filter((route) => route.apiHints.length);
    const output = {
      generatedAt: new Date().toISOString(),
      auditedRoutes: Object.keys(routes),
      summary: {
        fullLeakRoutes: leakRoutes.map((route) => route.path),
        partExposureRoutes: partExposureRoutes.map((route) => ({
          path: route.path,
          fields: route.partLeaks.filter((entry) => entry.found > 0),
        })),
        apiHintRoutes: apiHintRoutes.map((route) => ({ path: route.path, apiHints: route.apiHints })),
        structuredDataScriptCount: routeAudits.reduce((sum, route) => sum + route.structuredDataScripts, 0),
        pass:
          leakRoutes.length === 0 &&
          partExposureRoutes.length === 0 &&
          apiHintRoutes.length === 0 &&
          sourceDiscovery.fullLeaks.length === 0,
      },
      routeAudits,
      interpretation: {
        covered:
          "Audits the deployed page, external JS, JSON-LD sample, sitemap, RSS, AMP, print view, and public API sample for plaintext sensitive values and obvious API endpoint hints.",
        notCovered:
          "Does not discover real production endpoints, mobile app APIs, authenticated GraphQL schemas, CDN logs, backups, or third-party caches. Those require environment-specific crawling and access-control review.",
      },
    };
    const json = JSON.stringify(output, null, 2);
    if (outArg) fs.writeFileSync(outArg, `${json}\n`, "utf8");
    else console.log(json);
  } finally {
    server.close();
  }
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
