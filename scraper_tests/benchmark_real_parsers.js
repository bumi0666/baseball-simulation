const cheerio = require("cheerio");
const { JSDOM } = require("jsdom");
const { Readability } = require("@mozilla/readability");
const { page, record } = require("./structural_churn_server");

const samples = Number(process.env.SAMPLES || 24);

function normalize(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

function parseFromText(text) {
  const normalized = normalize(text);
  const output = {};
  const patterns = {
    project: /Project:\s*([^:]+?)(?=\s+Launch window:|\s+Dataset:|$)/i,
    launch_window: /Launch window:\s*([^:]+?)(?=\s+Project:|\s+Dataset:|$)/i,
    dataset: /Dataset:\s*([^:]+?)(?=\s+Project:|\s+Launch window:|$)/i,
  };
  for (const [field, pattern] of Object.entries(patterns)) {
    output[field] = normalize(normalized.match(pattern)?.[1] || "");
  }
  return output;
}

function isExact(parsed) {
  return Object.entries(record).every(([field, expected]) => parsed[field] === expected);
}

function learnClassTemplate(html) {
  const $ = cheerio.load(html);
  const template = {};
  $("[data-field]").each((_, row) => {
    const field = $(row).attr("data-field");
    const rowClass = $(row).attr("class");
    const value = $(row).find("[data-v]").first();
    const valueClass = value.attr("class");
    if (field && rowClass && valueClass) {
      template[field] = { rowClass, valueClass };
    }
  });
  return template;
}

function classTemplateParser(template, html) {
  const $ = cheerio.load(html);
  const output = {};
  for (const [field, rule] of Object.entries(template)) {
    output[field] = normalize($(`.${rule.rowClass} .${rule.valueClass}`).first().text());
  }
  return output;
}

const parsers = {
  "cheerio-text": (html) => parseFromText(cheerio.load(html)("body").text()),
  "cheerio-css-aware-text": (html) => {
    const $ = cheerio.load(html);
    $(".hidden-decoy").remove();
    return parseFromText($("body").text());
  },
  "cheerio-data-attrs": (html) => {
    const $ = cheerio.load(html);
    const output = {};
    $("[data-field]").each((_, row) => {
      const field = $(row).attr("data-field");
      output[field] = normalize($(row).find("[data-v]").first().text());
    });
    return output;
  },
  "jsdom-innerText": (html) => {
    const dom = new JSDOM(html);
    return parseFromText(dom.window.document.body.textContent);
  },
  readability: (html) => {
    const dom = new JSDOM(html, { url: "https://example.test/record" });
    const article = new Readability(dom.window.document).parse();
    return parseFromText(article?.textContent || "");
  },
};

const modes = {
  stable: { churn: false, reorder: false },
  reorderOnly: { churn: false, reorder: true },
  churnOnly: { churn: true, reorder: false },
  reorderPlusChurn: { churn: true, reorder: true },
  splitOnly: { churn: false, adversarial: true, semanticAnchors: false },
  splitPlusDecoy: { churn: false, adversarial: true, hiddenDecoy: true, semanticAnchors: false },
  splitPlusZeroWidth: { churn: false, adversarial: true, zeroWidth: true, semanticAnchors: false },
  splitPlusDecoyZeroWidth: {
    churn: false,
    adversarial: true,
    hiddenDecoy: true,
    zeroWidth: true,
    semanticAnchors: false,
  },
  splitPlusChurnDecoyZeroWidth: {
    churn: true,
    adversarial: true,
    hiddenDecoy: true,
    zeroWidth: true,
    semanticAnchors: false,
  },
};

function runParserSet(modeOptions) {
  const results = Object.fromEntries(
    Object.keys(parsers).map((name) => [name, { exact: 0, rate: 0, failures: [] }]),
  );

  for (let i = 0; i < samples; i += 1) {
    const seed = `session-${i}`;
    const html = page(seed, modeOptions);
    for (const [name, parser] of Object.entries(parsers)) {
      const parsed = parser(html);
      const exact = isExact(parsed);
      if (exact) {
        results[name].exact += 1;
      } else if (results[name].failures.length < 3) {
        results[name].failures.push({ seed, parsed });
      }
    }
  }

  for (const result of Object.values(results)) {
    result.rate = Number((result.exact / samples).toFixed(4));
  }
  return results;
}

function runTemplateReuse() {
  const baselineTemplate = learnClassTemplate(page("train", modes.stable));
  const reorderTemplate = learnClassTemplate(page("train", modes.reorderOnly));
  const churnTemplate = learnClassTemplate(page("train", modes.churnOnly));
  const results = {
    baselineTemplateOnBaseline: { exact: 0, rate: 0 },
    baselineTemplateOnReorder: { exact: 0, rate: 0 },
    baselineTemplateOnChurn: { exact: 0, rate: 0 },
    baselineTemplateOnReorderChurn: { exact: 0, rate: 0 },
    reorderTemplateOnOtherReorder: { exact: 0, rate: 0 },
    oneChurnedTemplateOnOtherChurned: { exact: 0, rate: 0 },
  };

  for (let i = 0; i < samples; i += 1) {
    const seed = `session-${i}`;
    if (isExact(classTemplateParser(baselineTemplate, page(seed, modes.stable)))) {
      results.baselineTemplateOnBaseline.exact += 1;
    }
    if (isExact(classTemplateParser(baselineTemplate, page(seed, modes.reorderOnly)))) {
      results.baselineTemplateOnReorder.exact += 1;
    }
    if (isExact(classTemplateParser(baselineTemplate, page(seed, modes.churnOnly)))) {
      results.baselineTemplateOnChurn.exact += 1;
    }
    if (isExact(classTemplateParser(baselineTemplate, page(seed, modes.reorderPlusChurn)))) {
      results.baselineTemplateOnReorderChurn.exact += 1;
    }
    if (isExact(classTemplateParser(reorderTemplate, page(seed, modes.reorderOnly)))) {
      results.reorderTemplateOnOtherReorder.exact += 1;
    }
    if (isExact(classTemplateParser(churnTemplate, page(seed, modes.churnOnly)))) {
      results.oneChurnedTemplateOnOtherChurned.exact += 1;
    }
  }

  for (const result of Object.values(results)) {
    result.rate = Number((result.exact / samples).toFixed(4));
  }
  return results;
}

function main() {
  console.log(JSON.stringify(
    {
      samples,
      templateReuse: runTemplateReuse(),
      parserResults: Object.fromEntries(
        Object.entries(modes).map(([name, options]) => [name, runParserSet(options)]),
      ),
    },
    null,
    2,
  ));
}

main();
