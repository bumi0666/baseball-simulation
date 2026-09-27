const path = require("node:path");

const { chromium } = require("playwright");

const root = __dirname;
const jsonOutput = process.argv.includes("--json");
const args = process.argv.slice(2).filter((arg) => arg !== "--json");
const fixture = args[0]
  ? path.resolve(args[0])
  : path.join(root, "fixture.html");
const zeroWidthRe = /[\u200b\u200c\u200d\u2060\ufeff]/g;
const bidiRe = /[\u202a-\u202e\u2066-\u2069]/g;

function normalize(text, stripZeroWidth = false) {
  const value = stripZeroWidth ? text.replace(zeroWidthRe, "") : text;
  return value.replace(/\s+/g, " ").trim();
}

function describe(label, text) {
  const zeroWidthCount = (text.match(zeroWidthRe) || []).length;
  const bidiCount = (text.match(bidiRe) || []).length;
  const preview = text.length > 120 ? `${text.slice(0, 120)}...` : text;
  console.log(
    `${label.padEnd(18)} chars=${String(text.length).padStart(3)} zero_width=${String(zeroWidthCount).padStart(2)} bidi=${String(bidiCount).padStart(2)} text=${preview}`,
  );
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 900, height: 700 } });
  await page.goto(`file://${fixture}`);
  await page.waitForTimeout(1000);

  const cases = await page.$$eval("section.case", (sections) =>
    sections.map((section) => {
      const walker = document.createTreeWalker(
        section,
        NodeFilter.SHOW_TEXT,
        {
          acceptNode(node) {
            const parent = node.parentElement;
            if (!parent) return NodeFilter.FILTER_REJECT;
            const style = window.getComputedStyle(parent);
            const rects = parent.getClientRects();
            const hidden =
              style.display === "none" ||
              style.visibility === "hidden" ||
              Number(style.opacity) === 0 ||
              rects.length === 0 ||
              [...rects].every(
                (rect) =>
                  rect.width === 0 ||
                  rect.height === 0 ||
                  rect.right <= 0 ||
                  rect.bottom <= 0,
              );
            return hidden ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
          },
        },
      );

      const textNodes = [];
      while (walker.nextNode()) {
        textNodes.push(walker.currentNode.nodeValue);
      }

      const visualBlocks = [
        ...section.querySelectorAll(
          "h1, p:not(.inline-visual):not(.fragmented), button, canvas, [inert], .record > .label, .record > div:not(.label):not(:has(span)), .record > div:not(.label) span, .inline-visual span, .fragmented span, .grid-rebuild span",
        ),
      ]
        .map((el) => {
          const style = window.getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          if (
            style.display === "none" ||
            style.visibility === "hidden" ||
            Number(style.opacity) === 0 ||
            rect.width === 0 ||
            rect.height === 0 ||
            rect.right <= 0 ||
            rect.bottom <= 0
          ) {
            return null;
          }
          return { top: rect.top, left: rect.left, text: el.innerText };
        })
        .filter(Boolean)
        .sort((a, b) => a.top - b.top || a.left - b.left)
        .map((item) => item.text);

      const pseudoTexts = [...section.querySelectorAll("*")]
        .flatMap((el) => {
          return ["::before", "::after"]
            .map((pseudo) => window.getComputedStyle(el, pseudo).content)
            .filter((content) => content && content !== "none" && content !== "normal")
            .map((content) => content.replace(/^["']|["']$/g, ""));
        });

      const openShadowTexts = [...section.querySelectorAll("*")]
        .filter((el) => el.shadowRoot)
        .map((el) => el.shadowRoot.innerText || el.shadowRoot.textContent || "");

      const ariaLabels = [...section.querySelectorAll("[aria-label]")]
        .filter((el) => el.getAttribute("aria-hidden") !== "true")
        .map((el) => el.getAttribute("aria-label"));

      return {
        id: section.id,
        innerText: section.innerText,
        visibleDomText: textNodes.join(" "),
        visualOrderText: visualBlocks.join(" "),
        pseudoAwareText: [section.innerText, ...pseudoTexts].join(" "),
        openShadowText: openShadowTexts.join(" "),
        ariaLabelText: ariaLabels.join(" "),
      };
    }),
  );

  const rows = [];
  for (const item of cases) {
    const measurements = [
      ["rendered-innerText", normalize(item.innerText)],
      ["rendered-visible-dom", normalize(item.visibleDomText)],
      ["rendered-visual-order", normalize(item.visualOrderText)],
    ];
    const pseudoAwareText = normalize(item.pseudoAwareText);
    const openShadowText = normalize(item.openShadowText);
    const ariaLabelText = normalize(item.ariaLabelText);
    if (pseudoAwareText !== normalize(item.innerText)) {
      measurements.push(["rendered-pseudo-aware", pseudoAwareText]);
    }
    if (openShadowText) measurements.push(["rendered-open-shadow", openShadowText]);
    if (ariaLabelText) measurements.push(["rendered-aria-label", ariaLabelText]);

    for (const [extractor, text] of measurements) {
      rows.push({ case_id: item.id, extractor, text });
    }
  }

  if (jsonOutput) {
    console.log(JSON.stringify({ fixture, rows }, null, 2));
    await browser.close();
    return;
  }

  console.log(`fixture=${fixture}`);
  for (const item of cases) {
    console.log(`\n[${item.id}]`);
    const innerText = normalize(item.innerText);
    const visibleDomText = normalize(item.visibleDomText);
    const visualOrderText = normalize(item.visualOrderText);
    const pseudoAwareText = normalize(item.pseudoAwareText);
    const openShadowText = normalize(item.openShadowText);
    const ariaLabelText = normalize(item.ariaLabelText);
    describe("innerText", innerText);
    describe("visible-dom", visibleDomText);
    describe("visual-order", visualOrderText);
    if (pseudoAwareText !== innerText) describe("pseudo-aware", pseudoAwareText);
    if (openShadowText) describe("open-shadow", openShadowText);
    if (ariaLabelText) describe("aria-label", ariaLabelText);
    describe("zero-width-clean", normalize(innerText, true));
  }

  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
