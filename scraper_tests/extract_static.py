from __future__ import annotations

import re
import sys
import json
from pathlib import Path

from lxml import html


ROOT = Path(__file__).resolve().parent
ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
BIDI_RE = re.compile("[\u202a-\u202e\u2066-\u2069]")


def normalize(text: str, strip_zero_width: bool = False) -> str:
    if strip_zero_width:
        text = ZERO_WIDTH_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def naive_text(node) -> str:
    return normalize(" ".join(node.itertext()))


def css_aware_text(node) -> str:
    hidden_classes = {"hidden-display", "hidden-opacity", "hidden-offscreen"}
    clone = html.fromstring(html.tostring(node, encoding="unicode"))

    for element in list(clone.iter()):
        classes = set((element.get("class") or "").split())
        style = (element.get("style") or "").replace(" ", "").lower()
        hidden_by_class = bool(classes & hidden_classes)
        hidden_by_style = (
            "display:none" in style
            or "visibility:hidden" in style
            or "opacity:0" in style
            or "left:-" in style
        )
        if hidden_by_class or hidden_by_style:
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)

    return normalize(" ".join(clone.itertext()))


def describe(label: str, text: str) -> str:
    zero_width_count = len(ZERO_WIDTH_RE.findall(text))
    bidi_count = len(BIDI_RE.findall(text))
    preview = text[:120] + ("..." if len(text) > 120 else "")
    return f"{label:18} chars={len(text):3} zero_width={zero_width_count:2} bidi={bidi_count:2} text={preview}"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    json_output = "--json" in sys.argv
    args = [arg for arg in sys.argv[1:] if arg != "--json"]
    fixture = Path(args[0]) if args else ROOT / "fixture.html"
    doc = html.parse(str(fixture)).getroot()

    rows = []
    for section in doc.xpath("//section[contains(concat(' ', normalize-space(@class), ' '), ' case ')]"):
        case_id = section.get("id")
        naive = naive_text(section)
        aware = css_aware_text(section)
        rows.append(
            {
                "case_id": case_id,
                "extractor": "static-naive",
                "text": naive,
            }
        )
        rows.append(
            {
                "case_id": case_id,
                "extractor": "static-css-aware",
                "text": aware,
            }
        )

    if json_output:
        print(json.dumps({"fixture": str(fixture), "rows": rows}, ensure_ascii=False, indent=2))
        return 0

    print(f"fixture={fixture}")
    for section in doc.xpath("//section[contains(concat(' ', normalize-space(@class), ' '), ' case ')]"):
        case_id = section.get("id")
        naive = naive_text(section)
        aware = css_aware_text(section)
        stripped = normalize(naive, strip_zero_width=True)

        print()
        print(f"[{case_id}]")
        print(describe("naive", naive))
        print(describe("css-aware", aware))
        print(describe("zero-width-clean", stripped))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
