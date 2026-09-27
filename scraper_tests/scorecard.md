# Final Candidate Scorecard

Candidate: `placeholderGated + non-value placeholders + interaction gate + external runtime-like placement`

| Area | Status | Summary |
| --- | --- | --- |
| Public SEO Content | pass | source publicCoverage=1 |
| Source Sensitive Leakage | pass | full=0, parts=0 |
| Safe Placeholder | pass | placeholderCoverage=1 |
| No-Interaction Render Gate | pass | public=1, sensitive=0, placeholders=1 |
| After-Intent Rendered UX | pass | public=1, sensitive=1, placeholders=0 |
| LLM-only Extraction | pass | gemini/gemini-2.5-flash: leakage=0, safe=1, unsafe=0 |
| HTML Placement Fingerprint | pass | inlineScriptBytes=0, externalScriptCount=1 |
| External Runtime Context | pass | jsBytes=46849, fromCharCode=1, bitwise=1251 |

## Threat Model

Blocks:
- source-only/static parsers
- LLM-only extraction under the tested Gemini prompt
- no-JS extraction of selected sensitive fields
- render-only crawlers that do not generate user intent events

Does not block:
- code-execution bots that inspect the external JS
- headless browsers that execute the runtime and explore interactions
- targeted analysis of the runtime bundle

## Notes

- Public content remains static/indexable.
- Sensitive fields use non-value placeholders in source.
- Sensitive fields require a user intent event before runtime hydration.
- External runtime-like placement reduces HTML fingerprint, but it is not cryptographic protection.
- Do not impersonate vendor namespaces, URLs, or brands.
