from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import trafilatura
from bs4 import BeautifulSoup
from readability import Document


ROOT = Path(__file__).resolve().parent
NODE = os.environ.get(
    "NODE",
    r"C:\Users\jungseobum\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe",
)
ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")


def normalize(text: str | None, strip_zero_width: bool = False) -> str:
    text = text or ""
    if strip_zero_width:
        text = ZERO_WIDTH_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_from_text(text: str) -> dict[str, str]:
    normalized = normalize(text)
    patterns = {
        "project": r"Project:\s*([^:]+?)(?=\s+Launch window:|\s+Dataset:|$)",
        "launch_window": r"Launch window:\s*([^:]+?)(?=\s+Project:|\s+Dataset:|$)",
        "dataset": r"Dataset:\s*([^:]+?)(?=\s+Project:|\s+Launch window:|$)",
    }
    output = {}
    for field, pattern in patterns.items():
        match = re.search(pattern, normalized, flags=re.I)
        output[field] = normalize(match.group(1) if match else "")
    return output


def is_exact(parsed: dict[str, str], expected: dict[str, str]) -> bool:
    return all(parsed.get(field) == value for field, value in expected.items())


def is_restored(parsed: dict[str, str], expected: dict[str, str]) -> bool:
    return all(normalize(parsed.get(field), strip_zero_width=True) == value for field, value in expected.items())


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
    env.setdefault("SAMPLES", "24")
    result = subprocess.run(
        [NODE, str(ROOT / "generate_structural_cases.js")],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    payload = load_cases()
    expected = payload["record"]
    results = defaultdict(lambda: defaultdict(lambda: {"exact": 0, "restored": 0, "failures": []}))

    for row in payload["rows"]:
        for parser_name, parser in PARSERS.items():
            parsed = parser(row["html"])
            bucket = results[row["mode"]][parser_name]
            if is_exact(parsed, expected):
                bucket["exact"] += 1
                bucket["restored"] += 1
            elif is_restored(parsed, expected):
                bucket["restored"] += 1
                if len(bucket["failures"]) < 3:
                    bucket["failures"].append({"seed": row["seed"], "parsed": parsed, "status": "restored"})
            elif len(bucket["failures"]) < 3:
                bucket["failures"].append({"seed": row["seed"], "parsed": parsed, "status": "failed"})

    samples = payload["samples"]
    report = {"samples": samples, "parserResults": {}}
    for mode, parsers in results.items():
        report["parserResults"][mode] = {}
        for parser_name, stats in parsers.items():
            report["parserResults"][mode][parser_name] = {
                "exact": stats["exact"],
                "exactRate": round(stats["exact"] / samples, 4),
                "restored": stats["restored"],
                "restoredRate": round(stats["restored"] / samples, 4),
                "failures": stats["failures"],
            }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
