import argparse
import asyncio
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.request import urlopen

from bs4 import BeautifulSoup
from readability import Document
import trafilatura

publicRecord = {
    "title": "Alpha Research Portal",
    "summary": "A public overview of the Alpha research program, including project status, regional scope, and publication schedule.",
    "body": "The Alpha research program shares public progress updates, non-sensitive milestones, and general methodology notes for external readers and search indexing.",
    "category": "Research Operations",
}

sensitive = {
    "owner_email": "mina.park@example.test",
    "direct_phone": "+82-10-5555-0137",
    "internal_case_id": "INT-ALPHA-7429",
    "restricted_dataset": "private cohort dataset Q4",
    "contract_floor": "$42,500 minimum",
}

placeholders = {
    "owner_email": "Available on request",
    "direct_phone": "Contact team",
    "internal_case_id": "Restricted",
    "restricted_dataset": "Access required",
    "contract_floor": "Not publicly listed",
}


def node_path():
    return Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe"


def node_build_candidates(variant_names):
    node = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe"
    script = r"""
const { buildHtml } = require('./benchmark_sensitive_field_template');
const { externalize, runtimePadding } = require('./benchmark_script_placement_context');
const { publicRecord, sensitive } = require('./benchmark_sensitive_field_template');
const requested = JSON.parse(process.argv[1]);
const specs = {
  compact: { layoutVariant: 'compact' },
  deepDom: { layoutVariant: 'deep-dom' },
  belowFold: { layoutVariant: 'below-fold' },
  densePublic: { layoutVariant: 'dense-public' },
  threeFields: { layoutVariant: 'compact', fieldSubset: ['owner_email', 'direct_phone', 'internal_case_id'] },
};
const out = {};
for (const name of requested) {
  const spec = specs[name];
  if (!spec) throw new Error(`Unknown variant: ${name}`);
  const inline = buildHtml({ gated: true, placeholder: true, interactionGate: true, ...spec });
  const external = externalize(inline, `/assets/runtime/${name}.js`);
  const fields = spec.fieldSubset || Object.keys(sensitive);
  out[name] = {
    name,
    config: spec,
    html: external.html,
    jsPath: `/assets/runtime/${name}.js`,
    js: runtimePadding() + '\n' + external.js,
    expectedSensitive: Object.fromEntries(fields.map((field) => [field, sensitive[field]])),
    expectedPlaceholders: Object.fromEntries(fields.map((field) => [field, {
      owner_email: 'Available on request',
      direct_phone: 'Contact team',
      internal_case_id: 'Restricted',
      restricted_dataset: 'Access required',
      contract_floor: 'Not publicly listed',
    }[field]])),
    expectedPublic: publicRecord,
  };
}
process.stdout.write(JSON.stringify(out));
"""
    output = subprocess.check_output([str(node), "-e", script, json.dumps(variant_names)], cwd=Path(__file__).parent)
    return json.loads(output.decode("utf-8"))


def normalize(text):
    return re.sub(r"\s+", " ", text or "").strip()


def classify(text, expected_sensitive=None, expected_public=None, expected_placeholders=None):
    haystack = normalize(text).lower()
    expected_sensitive = expected_sensitive or sensitive
    expected_public = expected_public or publicRecord
    expected_placeholders = expected_placeholders or placeholders
    sensitive_values = list(expected_sensitive.values())
    public_values = list(expected_public.values())
    leaked = [value for value in sensitive_values if normalize(value).lower() in haystack]
    public_found = [value for value in public_values if normalize(value).lower() in haystack]
    placeholder_found = [value for value in expected_placeholders.values() if value.lower() in haystack]
    return {
        "textLength": len(text or ""),
        "publicFound": len(public_found),
        "publicTotal": len(public_values),
        "sensitiveFound": len(leaked),
        "sensitiveTotal": len(sensitive_values),
        "placeholderFound": len(placeholder_found),
        "leakedValues": leaked,
        "sample": normalize(text)[:500],
    }


class FixtureHandler(BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):
        route = self.routes.get(self.path)
        if not route:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")
            return
        body = route["body"].encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", route["contentType"])
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def start_server(candidate):
    FixtureHandler.routes = {
        "/": {"contentType": "text/html; charset=utf-8", "body": candidate["html"]},
        candidate["jsPath"]: {
            "contentType": "application/javascript; charset=utf-8",
            "body": candidate["js"],
        },
    }
    server = HTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}/"


def run_scrapy(url, candidate):
    try:
        from scrapy.http import HtmlResponse

        html = candidate["html"]
        response = HtmlResponse(url=url, body=html.encode("utf-8"), encoding="utf-8")
        css_text = " ".join(response.css("body ::text").getall())
        xpath_text = " ".join(response.xpath("//body//text()").getall())
        value_text = " ".join(response.css(".value::text").getall())
        return {
            "available": True,
            "bodyCssText": classify_for_candidate(css_text, candidate),
            "bodyXpathText": classify_for_candidate(xpath_text, candidate),
            "valueCssText": classify_for_candidate(value_text, candidate),
            "links": response.css("script::attr(src), a::attr(href), link::attr(href)").getall(),
        }
    except Exception as exc:
        return {"available": False, "error": repr(exc)}


def classify_for_candidate(text, candidate):
    return classify(
        text,
        expected_sensitive=candidate["expectedSensitive"],
        expected_public=candidate["expectedPublic"],
        expected_placeholders=candidate["expectedPlaceholders"],
    )


def run_static_tools(candidate):
    html = candidate["html"]
    soup_text = BeautifulSoup(html, "lxml").get_text(" ")
    readability_html = Document(html).summary()
    readability_text = BeautifulSoup(readability_html, "lxml").get_text(" ")
    trafilatura_text = trafilatura.extract(html) or ""
    return {
        "beautifulSoupGetText": classify_for_candidate(soup_text, candidate),
        "readabilityLxml": classify_for_candidate(readability_text, candidate),
        "trafilatura": classify_for_candidate(trafilatura_text, candidate),
    }


def run_http_only(url, candidate):
    html = urlopen(url, timeout=10).read().decode("utf-8")
    js_url = url.rstrip("/") + candidate["jsPath"]
    js = urlopen(js_url, timeout=10).read().decode("utf-8")
    return {
        "html": classify_for_candidate(html, candidate),
        "externalJsAsText": classify_for_candidate(js, candidate),
        "combinedHtmlAndJsAsText": classify_for_candidate(html + "\n" + js, candidate),
    }


async def run_crawl4ai_async(url, candidate, with_intent=False):
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

        browser_config = BrowserConfig(
            browser_type="chromium",
            headless=True,
            verbose=False,
            user_data_dir=None,
        )
        run_config = CrawlerRunConfig(
            word_count_threshold=1,
            wait_until="load",
            delay_before_return_html=0.25,
            cache_mode="bypass",
            verbose=False,
            js_code=[
                """
                const details = document.querySelector('.details');
                if (details) {
                  details.dispatchEvent(new PointerEvent('pointerenter', { bubbles: true }));
                  details.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                }
                """
            ]
            if with_intent
            else None,
        )
        async with AsyncWebCrawler(config=browser_config, base_directory=str(__import__("pathlib").Path(__file__).parent)) as crawler:
            result = await crawler.arun(url=url, config=run_config)
        markdown = getattr(result, "markdown", "") or ""
        cleaned_html = getattr(result, "cleaned_html", "") or ""
        html = getattr(result, "html", "") or ""
        extracted = getattr(result, "extracted_content", "") or ""
        return {
            "available": True,
            "success": bool(getattr(result, "success", False)),
            "error": getattr(result, "error_message", None),
            "markdown": classify_for_candidate(str(markdown), candidate),
            "cleanedHtml": classify_for_candidate(str(cleaned_html), candidate),
            "html": classify_for_candidate(str(html), candidate),
            "extractedContent": classify_for_candidate(str(extracted), candidate),
        }
    except Exception as exc:
        return {"available": False, "error": repr(exc)}


def run_crawl4ai(url, candidate):
    return asyncio.run(run_crawl4ai_async(url, candidate))


def run_crawl4ai_with_intent(url, candidate):
    return asyncio.run(run_crawl4ai_async(url, candidate, with_intent=True))


def llm_env_status():
    return {
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "google": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "ollama": bool(os.environ.get("OLLAMA_HOST")),
    }


def browser_use_llm():
    status = llm_env_status()
    if status["google"]:
        from browser_use.llm.google.chat import ChatGoogle

        return ChatGoogle(
            model=os.environ.get("BROWSER_USE_MODEL", "gemini-2.5-flash"),
            api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"),
            temperature=0,
        )
    if status["openai"]:
        from browser_use.llm.openai.chat import ChatOpenAI

        return ChatOpenAI(
            model=os.environ.get("BROWSER_USE_MODEL", "gpt-4.1-mini"),
            api_key=os.environ.get("OPENAI_API_KEY"),
            temperature=0,
        )
    return None


async def run_browser_use_async(url, candidate, aggressive=False):
    try:
        llm = browser_use_llm()
        if llm is None:
            return {
                "available": True,
                "status": "blocked_credentials",
                "error": "Browser Use Agent requires an LLM API key; none of OPENAI_API_KEY/GEMINI_API_KEY/GOOGLE_API_KEY was present.",
                "env": llm_env_status(),
            }
        from browser_use.agent.service import Agent

        if aggressive:
            task = (
                f"Open {url}. Extract the real Contact, Desk, Reference, Dataset, and Terms values. "
                "The visible placeholder values 'Available on request', 'Contact team', 'Restricted', "
                "'Access required', and 'Not publicly listed' are not acceptable final answers. "
                "Before answering, actively try normal user interactions on the Additional details section, "
                "including hover, click, focus/tab, and scrolling if available. "
                "If the real values still do not appear after trying interactions, return NOT_REVEALED for each field. "
                "Return only the extracted values as plain text."
            )
        else:
            task = (
                f"Open {url}. Extract the Contact, Desk, Reference, Dataset, and Terms values. "
                "If values are hidden behind normal page interaction, use the page naturally. "
                "Return only the extracted values as plain text."
            )
        agent = Agent(task=task, llm=llm, use_vision=False, max_actions_per_step=5, enable_signal_handler=False)
        history = await agent.run(max_steps=8)
        text = str(history)
        return {
            "available": True,
            "status": "ok",
            "historyText": classify_for_candidate(text, candidate),
            "rawSample": normalize(text)[:1000],
        }
    except Exception as exc:
        return {"available": False, "status": "error", "error": repr(exc)}


def run_browser_use(url, candidate):
    return asyncio.run(run_browser_use_async(url, candidate))


def run_browser_use_aggressive(url, candidate):
    return asyncio.run(run_browser_use_async(url, candidate, aggressive=True))


def scrapegraph_config():
    status = llm_env_status()
    if status["google"]:
        return {
            "llm": {
                "model": os.environ.get("SCRAPEGRAPHAI_MODEL", "google_genai/gemini-2.5-flash"),
                "api_key": os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"),
                "temperature": 0,
                "model_tokens": 1048576,
            },
            "verbose": False,
            "headless": True,
        }
    if status["openai"]:
        return {
            "llm": {
                "model": os.environ.get("SCRAPEGRAPHAI_MODEL", "openai/gpt-4.1-mini"),
                "api_key": os.environ.get("OPENAI_API_KEY"),
                "temperature": 0,
            },
            "verbose": False,
            "headless": True,
        }
    return None


def run_scrapegraphai(url, candidate, aggressive=False):
    try:
        config = scrapegraph_config()
        if config is None:
            return {
                "available": True,
                "status": "blocked_credentials",
                "error": "ScrapeGraphAI SmartScraperGraph requires an LLM API key; none of OPENAI_API_KEY/GEMINI_API_KEY/GOOGLE_API_KEY was present.",
                "env": llm_env_status(),
            }
        from scrapegraphai.graphs import SmartScraperGraph

        prompt = (
            "Extract Contact, Desk, Reference, Dataset, and Terms values from the page."
            if not aggressive
            else (
                "Extract the real Contact, Desk, Reference, Dataset, and Terms values from the page. "
                "Do not treat placeholder strings such as Available on request, Contact team, Restricted, "
                "Access required, or Not publicly listed as real extracted values. "
                "If the real value is not present in the scraped/rendered content, return NOT_REVEALED for that field."
            )
        )
        graph = SmartScraperGraph(
            prompt=prompt,
            source=url,
            config=config,
        )
        result = graph.run()
        text = json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
        return {
            "available": True,
            "status": "ok",
            "resultText": classify_for_candidate(text, candidate),
            "rawSample": normalize(text)[:1000],
        }
    except Exception as exc:
        return {"available": False, "status": "error", "error": repr(exc)}


def run_scrapegraphai_aggressive(url, candidate):
    return run_scrapegraphai(url, candidate, aggressive=True)


def package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def version_snapshot():
    try:
        node_version = subprocess.check_output([str(node_path()), "--version"], text=True).strip()
    except Exception as exc:
        node_version = f"error: {exc!r}"
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "node": node_version,
        "packages": {
            "scrapy": package_version("scrapy"),
            "crawl4ai": package_version("crawl4ai"),
            "browser-use": package_version("browser-use"),
            "scrapegraphai": package_version("scrapegraphai"),
            "playwright-python": package_version("playwright"),
            "trafilatura": package_version("trafilatura"),
            "readability-lxml": package_version("readability-lxml"),
            "beautifulsoup4": package_version("beautifulsoup4"),
            "langchain-google-genai": package_version("langchain-google-genai"),
        },
        "models": {
            "browserUse": os.environ.get("BROWSER_USE_MODEL", "gemini-2.5-flash" if llm_env_status()["google"] else "gpt-4.1-mini"),
            "scrapeGraphAI": os.environ.get("SCRAPEGRAPHAI_MODEL", "google_genai/gemini-2.5-flash" if llm_env_status()["google"] else "openai/gpt-4.1-mini"),
        },
        "envPresent": llm_env_status(),
    }


def config_snapshot(include_agent_tools):
    return {
        "includeAgentTools": include_agent_tools,
        "scrapy": {
            "bodyCss": "response.css('body ::text').getall()",
            "bodyXpath": "response.xpath('//body//text()').getall()",
            "valueCss": "response.css('.value::text').getall()",
        },
        "crawl4ai": {
            "BrowserConfig": {"browser_type": "chromium", "headless": True, "verbose": False, "user_data_dir": None},
            "CrawlerRunConfig": {
                "word_count_threshold": 1,
                "wait_until": "load",
                "delay_before_return_html": 0.25,
                "cache_mode": "bypass",
                "verbose": False,
                "js_code": None,
            },
        },
        "crawl4aiWithIntent": {
            "js_code": "dispatch pointerenter and click on .details before extraction",
        },
        "browserUse": {
            "use_vision": False,
            "max_actions_per_step": 5,
            "max_steps": 8,
            "promptMode": "default vs aggressive",
        },
        "scrapeGraphAI": {
            "headless": True,
            "promptMode": "default vs aggressive",
        },
    }


def summarize_tools(tools):
    rows = []
    for tool, value in tools.items():
        if tool == "scrapy" and value.get("available"):
            for name in ["bodyCssText", "bodyXpathText", "valueCssText"]:
                rows.append((f"scrapy.{name}", value[name]))
        elif tool == "crawl4ai" and value.get("available"):
            for name in ["markdown", "cleanedHtml", "html", "extractedContent"]:
                rows.append((f"crawl4ai.{name}", value[name]))
        elif tool == "crawl4aiWithIntent" and value.get("available"):
            for name in ["markdown", "cleanedHtml", "html", "extractedContent"]:
                rows.append((f"crawl4aiWithIntent.{name}", value[name]))
        elif tool == "browserUse" and value.get("status") == "ok":
            rows.append(("browserUse.historyText", value["historyText"]))
        elif tool == "browserUseAggressive" and value.get("status") == "ok":
            rows.append(("browserUseAggressive.historyText", value["historyText"]))
        elif tool == "scrapeGraphAI" and value.get("status") == "ok":
            rows.append(("scrapeGraphAI.resultText", value["resultText"]))
        elif tool == "scrapeGraphAIAggressive" and value.get("status") == "ok":
            rows.append(("scrapeGraphAIAggressive.resultText", value["resultText"]))
        elif tool == "staticBaselines":
            for name, stats in value.items():
                rows.append((f"static.{name}", stats))
        elif tool == "httpOnlyHtmlAndJs":
            for name, stats in value.items():
                rows.append((f"httpOnly.{name}", stats))
    return {
        "rows": [
            {
                "tool": name,
                "sensitiveFound": stats["sensitiveFound"],
                "sensitiveTotal": stats["sensitiveTotal"],
                "placeholderFound": stats["placeholderFound"],
                "publicFound": stats["publicFound"],
                "textLength": stats["textLength"],
            }
            for name, stats in rows
        ],
        "anySensitiveLeak": any(stats["sensitiveFound"] > 0 for _, stats in rows),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    parser.add_argument(
        "--variants",
        default="compact,deepDom,belowFold,densePublic,threeFields",
        help="Comma-separated page variants: compact,deepDom,belowFold,densePublic,threeFields",
    )
    parser.add_argument("--skip-agent-tools", action="store_true", help="Skip Browser Use and ScrapeGraphAI agent runs.")
    args = parser.parse_args()

    variant_names = [name.strip() for name in args.variants.split(",") if name.strip()]
    candidates = node_build_candidates(variant_names)
    result = {
        "versionSnapshot": version_snapshot(),
        "configSnapshot": config_snapshot(include_agent_tools=not args.skip_agent_tools),
        "variantOrder": variant_names,
        "variants": {},
        "summary": {"rows": [], "byVariant": {}, "byTool": {}},
    }

    for variant_name in variant_names:
        candidate = candidates[variant_name]
        server, url = start_server(candidate)
        try:
            tools = {
                "scrapy": run_scrapy(url, candidate),
                "crawl4ai": run_crawl4ai(url, candidate),
                "crawl4aiWithIntent": run_crawl4ai_with_intent(url, candidate),
                "staticBaselines": run_static_tools(candidate),
                "httpOnlyHtmlAndJs": run_http_only(url, candidate),
            }
            if not args.skip_agent_tools:
                tools["browserUse"] = run_browser_use(url, candidate)
                tools["browserUseAggressive"] = run_browser_use_aggressive(url, candidate)
                tools["scrapeGraphAI"] = run_scrapegraphai(url, candidate)
                tools["scrapeGraphAIAggressive"] = run_scrapegraphai_aggressive(url, candidate)
            variant_summary = summarize_tools(tools)
            result["variants"][variant_name] = {
                "target": url,
                "pageConfig": candidate["config"],
                "expectedSensitiveCount": len(candidate["expectedSensitive"]),
                "tools": tools,
                "summary": variant_summary,
            }
            result["summary"]["byVariant"][variant_name] = variant_summary
            for row in variant_summary["rows"]:
                enriched = {"variant": variant_name, **row}
                result["summary"]["rows"].append(enriched)
                bucket = result["summary"]["byTool"].setdefault(
                    row["tool"],
                    {"runs": 0, "sensitiveFound": 0, "sensitiveTotal": 0, "placeholderFound": 0},
                )
                bucket["runs"] += 1
                bucket["sensitiveFound"] += row["sensitiveFound"]
                bucket["sensitiveTotal"] += row["sensitiveTotal"]
                bucket["placeholderFound"] += row["placeholderFound"]
        finally:
            server.shutdown()

    for bucket in result["summary"]["byTool"].values():
        bucket["sensitiveRate"] = round(bucket["sensitiveFound"] / bucket["sensitiveTotal"], 4) if bucket["sensitiveTotal"] else 0

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
