const zlib = require("node:zlib");
const { buildHtml } = require("./benchmark_sensitive_field_template");
const { fingerprint: vendorFingerprint } = (() => {
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
      xorOperator: countMatches(text, /\^/g),
      bitwiseOperators: countMatches(text, /(?:>>>|>>|<<|~|\||&|\^)/g),
      canvasApis: countMatches(text, /canvas|getContext|measureText|toDataURL/g),
      layoutApis: countMatches(text, /getBoundingClientRect|getComputedStyle|devicePixelRatio/g),
      jsonPayload: countMatches(text, /application\/json|JSON\.parse|JSON\.stringify/g),
      numericArrayLike: countMatches(text, /\[[\s\n]*(?:(?:\d{1,5})\s*,\s*){12,}/g),
      base64LikeStrings: countMatches(text, /["'][A-Za-z0-9+/]{24,}={0,2}["']/g),
    };
    return {
      rawBytes,
      gzipBytes: zlib.gzipSync(text).length,
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
  return { fingerprint };
})();

function extractScripts(html) {
  return [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)].map((match, index) => ({
    index,
    attrs: match[1] || "",
    body: match[2] || "",
    full: match[0],
  }));
}

function stripInlineScripts(html) {
  return html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "");
}

function externalize(html, src = "/assets/runtime/telemetry.js") {
  const scripts = extractScripts(html);
  const jsonPayloads = scripts
    .filter((script) => /type=["']application\/json["']/i.test(script.attrs))
    .map((script) => {
      const id = /id=["']([^"']+)["']/i.exec(script.attrs)?.[1] || "page-data";
      return { id, body: script.body.trim() };
    });
  const prelude = jsonPayloads
    .map((payload) => `window.__${payload.id.replace(/[^a-zA-Z0-9_$]/g, "_")}=${payload.body};`)
    .join("\n");
  const js = [
    prelude,
    ...scripts
      .filter((script) => !/type=["']application\/json["']/i.test(script.attrs))
      .map((script) =>
        script.body.replace(
          /JSON\.parse\(document\.querySelector\("#page-data"\)\.textContent\)/g,
          "window.__page_data",
        ),
      ),
  ]
    .filter(Boolean)
    .join("\n");
  const withoutScripts = stripInlineScripts(html).replace(
    "</body>",
    `  <script src="${src}" defer></script>\n</body>`,
  );
  return { html: withoutScripts, js };
}

function runtimePadding(targetBytes = 45000) {
  const modules = [];
  for (let i = 0; i < 180; i += 1) {
    modules.push(`function t${i}(s){try{var n=(s&&s.length)||0;return {i:${i},w:window.innerWidth,h:window.innerHeight,n:n,ts:Date.now()%997};}catch(e){return {i:${i},e:1};}}`);
  }
  modules.push(`function collectRuntimeState(){var r=[];for(var i=0;i<60;i++){r.push((window.innerWidth+i)+"x"+(window.innerHeight+i));}return r.join("|");}`);
  modules.push(`function scheduleFlush(){if("requestIdleCallback" in window){requestIdleCallback(function(){collectRuntimeState();});}else{setTimeout(collectRuntimeState,32);}}`);
  let text = `(function(){\n${modules.join("\n")}\nscheduleFlush();\n})();\n`;
  while (Buffer.byteLength(text, "utf8") < targetBytes) {
    const i = modules.length;
    text += `function p${i}(a){return String(a||"").slice(0,${(i % 17) + 3}).toLowerCase();}\n`;
  }
  return text;
}

function htmlFingerprint(html) {
  const scripts = extractScripts(html);
  const inlineScriptBytes = scripts.reduce((sum, script) => sum + Buffer.byteLength(script.body, "utf8"), 0);
  const rawBytes = Buffer.byteLength(html, "utf8");
  return {
    rawBytes,
    gzipBytes: zlib.gzipSync(html).length,
    inlineScriptBytes,
    inlineScriptRatio: Number((inlineScriptBytes / rawBytes).toFixed(4)),
    inlineScriptCount: scripts.filter((script) => script.body.trim()).length,
    externalScriptCount: (html.match(/<script\b[^>]+\bsrc=/gi) || []).length,
    inlineSuspiciousCounts: vendorFingerprint(scripts.map((script) => script.body).join("\n")).counts,
  };
}

function buildPlacementVariants() {
  const inlineHtml = buildHtml({ gated: true, placeholder: true, interactionGate: true });
  const small = externalize(inlineHtml);
  const padded = {
    html: small.html.replace("/assets/runtime/telemetry.js", "/assets/runtime/risk-events.js"),
    js: `${runtimePadding()}\n${small.js}`,
  };

  const variants = {
    inlinePlaceholderGated: {
      html: htmlFingerprint(inlineHtml),
      js: null,
    },
    externalSmall: {
      html: htmlFingerprint(small.html),
      js: vendorFingerprint(small.js),
    },
    externalRuntimeLike: {
      html: htmlFingerprint(padded.html),
      js: vendorFingerprint(padded.js),
    },
  };

  return variants;
}

function main() {
  const variants = buildPlacementVariants();
  const vendorReference = {
    note: "From previous vendor baseline: rawBytes ranged roughly 1.5KB-417KB; hCaptcha/GTM were 327KB/417KB; FingerprintJS was 39KB. fromCharCode median 1, xor median 29, bitwise median 1416.",
    roughRanges: {
      rawBytes: { min: 1548, medianApprox: 82469, max: 417176 },
      fromCharCode: { min: 0, median: 1, max: 9 },
      xorOperator: { min: 0, median: 29, max: 140 },
      bitwiseOperators: { min: 24, median: 1416, max: 7090 },
    },
  };

  console.log(JSON.stringify({ variants, vendorReference }, null, 2));
}

if (require.main === module) {
  main();
}

module.exports = {
  buildPlacementVariants,
  externalize,
  htmlFingerprint,
  runtimePadding,
  vendorFingerprint,
};
