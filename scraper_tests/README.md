# Scraper extraction checks

This folder compares static HTML extraction against browser-rendered extraction for common text obfuscation experiments.

Current fixture cases:

- Comments, hidden mirror text, zero-width characters, and CSS visual ordering.
- CSS pseudo-element text, canvas-rendered text, open/closed Shadow DOM.
- ARIA labels, `template`/`noscript`/`inert`, delayed JavaScript rendering.
- Fragmented spans, bidi control characters, and Unicode confusables.
- Combination cases for confusables plus fragmentation, DOM order plus hidden noise, and CSS visual reconstruction plus hidden decoys.

## Static parser

Uses bundled Python plus `lxml`; no external install is needed in the Codex runtime.

```powershell
& 'C:\Users\jungseobum\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\scraper_tests\extract_static.py
```

## Rendered browser parser

Install Playwright in a local Node environment, then run:

```powershell
npm install --save-dev playwright
npx playwright install chromium
node .\scraper_tests\extract_rendered_playwright.js
```

The rendered script reports three extraction styles:

- `innerText`: browser-visible text in DOM traversal order.
- `visible-dom`: text nodes whose parent elements appear visible in the viewport.
- `visual-order`: visible block text sorted by rendered position.

The distinction matters because `innerText` filters many hidden elements, but does not necessarily reconstruct the exact visual reading order for CSS-reordered layouts. `visual-order` is closer to what a headless crawler could do if it intentionally uses layout information.

Some visible text still requires specialized extraction:

- CSS `content` needs pseudo-element inspection or OCR.
- Canvas text needs OCR or app-specific instrumentation.
- Closed Shadow DOM is visible on screen but unavailable to ordinary JavaScript traversal.

## LLM parser evaluation

`llm_parser_fixture.html` repeats the same target record across obfuscation variants:

```json
{
  "project": "Alpha project",
  "launch_window": "Friday morning",
  "dataset": "private dataset"
}
```

Generate extracted text first:

```powershell
& 'C:\Users\jungseobum\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\scraper_tests\extract_static.py --json .\scraper_tests\llm_parser_fixture.html > .\scraper_tests\static_llm_inputs.json

cd .\scraper_tests
$env:Path = 'C:\Users\jungseobum\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:Path
& 'C:\Users\jungseobum\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' .\extract_rendered_playwright.js --json .\llm_parser_fixture.html > .\rendered_llm_inputs.json
```

Then run the LLM parser:

```powershell
$env:OPENAI_API_KEY = '...'
$env:OPENAI_MODEL = 'gpt-4.1-mini'
node .\evaluate_llm_parser.js .\rendered_llm_inputs.json --out .\rendered_llm_results.json
node .\evaluate_llm_parser.js .\static_llm_inputs.json --out .\static_llm_results.json
```

To send the original HTML directly to an LLM:

```powershell
cd .\scraper_tests
$env:SAMPLES = '6'
$env:LLM_PROVIDER = 'openai'
$env:LLM_MODEL = 'gpt-4.1-mini'
$env:OPENAI_API_KEY = '...'
node .\evaluate_llm_html_parser.js --out .\openai_html_results.json
```

For Anthropic:

```powershell
$env:LLM_PROVIDER = 'anthropic'
$env:LLM_MODEL = 'claude-3-5-sonnet-latest'
$env:ANTHROPIC_API_KEY = '...'
node .\evaluate_llm_html_parser.js --out .\anthropic_html_results.json
```

For Gemini:

```powershell
$env:LLM_PROVIDER = 'gemini'
$env:LLM_MODEL = 'gemini-2.5-flash'
$env:GEMINI_API_KEY = '...'
node .\evaluate_llm_html_parser.js --out .\gemini_html_results.json
```

If a Gemini model name fails, list the models available to your API key:

```powershell
node .\evaluate_llm_html_parser.js --list-gemini-models
```

Use `--mode splitOnly` or `--mode splitPlusDecoyZeroWidth` to run one condition at a time.

For larger multi-record HTML:

```powershell
$env:LLM_PROVIDER = 'gemini'
$env:LLM_MODEL = 'gemini-2.5-flash'
$env:GEMINI_API_KEY = '...'
$env:RECORDS = '12'
$env:SAMPLES = '3'
node .\evaluate_llm_large_html_parser.js --out .\gemini_large_html_results.json
```

Useful single-mode runs:

```powershell
node .\evaluate_llm_large_html_parser.js --mode splitOnly --out .\gemini_large_split_only.json
node .\evaluate_llm_large_html_parser.js --mode splitPlusDecoyZeroWidthProse --out .\gemini_large_hard.json
```

The evaluator labels each field as:

- `exact`: exact expected string.
- `restored`: normalized value matches the expected value, meaning the LLM repaired spacing or Unicode damage.
- `confusable_or_control`: the answer keeps Cyrillic lookalikes, bidi controls, or zero-width characters.
- `decoy`: the answer chose a planted false value.
- `missing`: the field is null or absent.
- `wrong`: any other incorrect value.

## Structural churn prototype

`structural_churn_server.js` serves the same rendered record while changing request-keyed structural signals:

- class names
- attribute order
- equivalent tag choices such as `b`/`strong`/`span`
- wrapper tag choice and nesting depth

Run the server:

```powershell
cd .\scraper_tests
$env:Path = 'C:\Users\jungseobum\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:Path
node .\structural_churn_server.js
```

Measure multiple session keys:

```powershell
$env:SAMPLES = '12'
node .\measure_structural_churn.js
```

For a serverless local check using the same generator:

```powershell
$env:DIRECT = '1'
node .\measure_structural_churn.js
```

The measurement reports:

- `uniqueText`: whether text extraction stayed stable.
- `uniqueHtml`: how many distinct HTML documents were emitted.
- `uniqueStructure`: how many distinct tag/attribute-name signatures appeared.
- `uniqueClass`: how many distinct class-token signatures appeared.
- `avgClassJaccardWithFirst`: class-token overlap with the first sample.

Run the three-axis benchmark:

```powershell
$env:SAMPLES = '24'
$env:ITERATIONS = '5000'
node .\benchmark_structural_churn.js
```

It reports:

- `crawler`: exact extraction rate for a template learned on stable markup, then reused against stable or churned markup.
- `server`: baseline versus churned generation time and HTML size.
- `rendering`: `innerText` equality and pixel-level screenshot equality between stable and churned markup.

Run real parser checks:

```powershell
$env:SAMPLES = '24'
node .\benchmark_real_parsers.js
```

This compares:

- reusable class-template extraction
- Cheerio text extraction
- Cheerio `data-*` attribute extraction
- JSDOM text extraction
- Mozilla Readability text extraction

In the current fixture, structural churn breaks class-template reuse but does not break pure text extraction or stable semantic `data-*` extraction.

Run Python parser checks:

```powershell
& 'C:\Users\jungseobum\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\benchmark_python_parsers.py
```

This compares:

- BeautifulSoup `.get_text()`
- readability-lxml
- trafilatura

Measure parser cost:

```powershell
$env:ITERATIONS = '120'
node .\benchmark_node_parse_cost.js

$env:ITERATIONS = '40'
& 'C:\Users\jungseobum\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\benchmark_python_parse_cost.py
```

The cost benchmarks report average, p50, and p95 parse time per mode and parser. For heavy parsers, prefer p50/p95 over the first-run-sensitive average.

Run the single-file computational gap benchmark:

```powershell
$env:ITERATIONS = '20'
node .\benchmark_computational_gap.js
```

This writes `computational_gap_fixture.html` and compares static text/DOM parsers with a Playwright rendered extractor. The fixture includes font-metric mapping, CSS overlap encoding, self-reference rendering, and a combined hidden-decoy/rendering-gate case.

Evaluate those computational-gap cases with an LLM:

```powershell
$env:LLM_PROVIDER = 'gemini'
$env:LLM_MODEL = 'gemini-2.5-flash'
$env:SAMPLES = '1'
node .\evaluate_llm_computational_gap.js --out gemini_gap_results.json
```

Optional single-mode run:

```powershell
node .\evaluate_llm_computational_gap.js --mode combined
```

Evaluate decoy-free pure computational-gap cases at a larger record/field scale:

```powershell
$env:LLM_PROVIDER = 'gemini'
$env:LLM_MODEL = 'gemini-2.5-flash'
$env:SAMPLES = '1'
$env:RECORDS = '12'
node .\evaluate_llm_pure_gap_scale.js --out gemini_pure_gap_scale_results.json
```

For an abstention-oriented run:

```powershell
$env:PROMPT_STYLE = 'conservative'
node .\evaluate_llm_pure_gap_scale.js --out gemini_pure_gap_scale_conservative_results.json
```

Modes:

- `stable`
- `fontMetricPure`
- `selfRefPure`

The pure gap evaluator reports `leakageRate`, `safeFailureRate`, and `unsafeFailureRate` in addition to exact/restored/missing/wrong counts.

Evaluate the same pure gap cases after headless browser rendering:

```powershell
$env:RECORDS = '12'
$env:ITERATIONS = '5'
node .\benchmark_headless_pure_gap.js
```

This compares source-text parsing with Playwright-rendered `innerText` and DOM row extraction, checks viewport/device-scale determinism, and reports source parsing, render, extraction, and end-to-end headless timing.

Evaluate interaction-gated extraction:

```powershell
$env:RECORDS = '12'
$env:ITERATIONS = '1'
node .\benchmark_interaction_gate.js
```

This compares no interaction, scroll-only, hover/focus sweeps, all-element brute force, and a known interaction sequence. It reports exact/leakage/safe/unsafe rates plus attempted elements, event count, and interaction timing.

Measure whether the gates leave detectable source/rendering fingerprints:

```powershell
$env:RECORDS = '12'
node .\benchmark_gate_fingerprints.js
```

This reports suspicious API usage, encoded payload density, empty slots, raw/gzip size, text-completion timing, mutation counts, and simple relative fingerprint scores. Scores are heuristic and intended for comparing local variants, not as absolute detection probabilities.

Compare the sensitive-field template against a small real-site fingerprint baseline:

```powershell
$env:URL_LIMIT = '8'
$env:WAIT_MS = '3000'
node .\benchmark_real_site_fingerprint_baseline.js
```

You can override the tested sites with a comma-separated `URLS` environment variable. The scanner instruments runtime calls to selected layout/font APIs and also counts suspicious source patterns. Treat the result as a rough baseline, since a small URL set is not a statistically representative web sample.

Compare against public anti-bot/adtech/widget script fingerprints:

```powershell
node .\benchmark_vendor_script_fingerprint_baseline.js
```

Compare inline versus external script placement context:

```powershell
node .\benchmark_script_placement_context.js
```

This simulates `inlinePlaceholderGated`, `externalSmall`, and `externalRuntimeLike` layouts. It separates HTML fingerprint from external JS fingerprint and compares the JS size/operator density against the vendor-script baseline. The runtime-like variant is only a local context simulation; do not impersonate vendor namespaces or URLs.

Audit whether a claimed rendering-dependent key actually depends on the rendering salt:

```powershell
node .\audit_render_key_dependency.js
```

This intentionally fails for the current prototype because the synthetic salt cancels out algebraically. The audit also reports local sensitivity to `salt + 1`, the number of unique/plausible outputs across a 256-salt brute-force space, and whether jsdom can approximate the salt source. A true rendering-dependent implementation should make decoded outputs vary with salt, show high sensitivity to nearby salt changes, avoid tiny brute-forceable output spaces, and resist no-browser salt reproduction.

Try a calibrated render-keyed sensitive-field variant:

```powershell
node .\benchmark_render_keyed_sensitive_field.js
```

This computes a browser salt from `measureText`, layout dimensions, and device scale, encodes sensitive fields against that salt, then verifies source leakage, rendered visibility, salt sensitivity, small brute-force resistance, and jsdom no-browser reproduction. This is a local calibration experiment; environment variation can break legitimate rendering unless handled separately.

Measure whether that render-keyed variant survives normal environment variation:

```powershell
node .\benchmark_render_key_environment_stability.js
```

This calibrates the payload in one Chromium desktop environment, then reopens the same payload under different Chromium viewport, device scale, CSS zoom, and font-family settings, plus Firefox/WebKit when installed. It reports salt component drift, legitimate exact rate, and false-negative rate for normal users.

Evaluate a practical template where only selected sensitive fields are gated:

```powershell
node .\benchmark_sensitive_field_template.js
```

This compares plain HTML with pages where public title/body/summary/category remain static and indexable, while five sensitive fields are runtime-filled. It includes both empty-slot and non-value-placeholder variants and reports public-content coverage, sensitive-value leakage, placeholder extraction, rendered visibility, size, and simple source fingerprints.

The sensitive-field benchmark also includes a `hydrationLikeGated` variant that removes the JSON numeric payload, XOR, `fromCharCode`, `measureText`, and `devicePixelRatio` patterns. It uses data attributes, non-value placeholders, and `IntersectionObserver`-style lazy hydration. Because the sensitive strings are split into source-visible fragments, run the LLM check before treating it as protective:

```powershell
$env:LLM_PROVIDER = 'gemini'
$env:LLM_MODEL = 'gemini-2.5-flash'
node .\evaluate_llm_sensitive_template.js --out gemini_sensitive_template_results.json
```

### OSS crawler product checks

Run real open-source crawler packages against controlled local variants of the final candidate:

```powershell
& 'C:\Users\jungseobum\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\benchmark_oss_crawlers.py --out oss_crawler_results.json
```

For a faster, no-LLM run that still covers Scrapy, Crawl4AI, static parsers, and HTTP-only extraction across page variants:

```powershell
& 'C:\Users\jungseobum\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\benchmark_oss_crawlers.py --skip-agent-tools --out oss_crawler_variant_results.json
```

The harness records Python/Node/package versions, model names, tool configurations, prompt modes, and page variants (`compact`, `deepDom`, `belowFold`, `densePublic`, `threeFields`) in the output JSON. Browser Use and ScrapeGraphAI require an LLM key such as `GEMINI_API_KEY`; without one they are recorded as `blocked_credentials`.

The same benchmark also includes adversarial label/value split modes:

- `splitOnly`
- `splitPlusDecoy`
- `splitPlusZeroWidth`
- `splitPlusDecoyZeroWidth`
- `splitPlusChurnDecoyZeroWidth`

These remove stable semantic anchors, visually rejoin labels and values with CSS grid, and optionally add hidden decoys or zero-width characters.
