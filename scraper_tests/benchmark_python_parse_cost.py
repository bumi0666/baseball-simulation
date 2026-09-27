from __future__ import annotations

import json
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

import trafilatura
from bs4 import BeautifulSoup
from readability import Document


ROOT = Path(__file__).resolve().parent
NODE = os.environ.get(
    "NODE",
    r"C:\Users\jungseobum\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe",
)
ITERATIONS = int(os.environ.get("ITERATIONS", "80"))


def normalize(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_from_text(text: str) -> dict[str, str]:
    normalized = normalize(text)
    patterns = {
        "project": r"Project:\s*([^:]+?)(?=\s+Launch window:|\s+Dataset:|$)",
        "launch_window": r"Launch window:\s*([^:]+?)(?=\s+Project:|\s+Dataset:|$)",
        "dataset": r"Dataset:\s*([^:]+?)(?=\s+Project:|\s+Launch window:|$)",
    }
    return {
        field: normalize(match.group(1) if (match := re.search(pattern, normalized, flags=re.I)) else "")
        for field, pattern in patterns.items()
    }


def bs4_get_text(html: str) -> dict[str, str]:
    return parse_from_text(BeautifulSoup(html, "html.parser").get_text(" "))


def readability_lxml(html: str) -> dict[str, str]:
    summary = Document(html).summary(html_partial=True)
    return parse_from_text(BeautifulSoup(summary, "html.parser").get_text(" "))


def trafilatura_extract(html: str) -> dict[str, str]:
    extracted = trafilatura.extract(html, include_comments=False, include_tables=True) or ""
    return parse_from_text(extracted)


PARSERS = {
    "beautifulsoup-get-text": bs4_get_text,
    "readability-lxml": readability_lxml,
    "trafilatura": trafilatura_extract,
}


def load_cases() -> dict:
    env = os.environ.copy()
    env["SAMPLES"] = str(ITERATIONS)
    result = subprocess.run(
        [NODE, str(ROOT / "generate_structural_cases.js")],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout)
    by_mode: dict[str, list[str]] = {}
    for row in payload["rows"]:
        by_mode.setdefault(row["mode"], []).append(row["html"])
    return by_mode


def percentile(values: list[float], p: float) -> float:
    values = sorted(values)
    index = min(len(values) - 1, int(len(values) * p))
    return values[index]


def summarize(times: list[float]) -> dict[str, float]:
    return {
        "avgMs": round(statistics.fmean(times), 4),
        "p50Ms": round(percentile(times, 0.5), 4),
        "p95Ms": round(percentile(times, 0.95), 4),
    }


def measure(parser, htmls: list[str]) -> dict[str, float]:
    times = []
    for html in htmls:
        start = time.perf_counter()
        parser(html)
        times.append((time.perf_counter() - start) * 1000)
    return summarize(times)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    cases = load_cases()
    report = {"iterations": ITERATIONS, "results": {}}
    for mode, htmls in cases.items():
        avg_bytes = round(sum(len(html.encode("utf-8")) for html in htmls) / len(htmls))
        report["results"][mode] = {"avgBytes": avg_bytes, "parsers": {}}
        for parser_name, parser in PARSERS.items():
            report["results"][mode]["parsers"][parser_name] = measure(parser, htmls)

    stable = report["results"]["stable"]["parsers"]
    for mode_result in report["results"].values():
        for parser_name, stats in mode_result["parsers"].items():
            stats["avgRatioVsStable"] = round(stats["avgMs"] / stable[parser_name]["avgMs"], 2)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
