const { page, record } = require("./structural_churn_server");

const samples = Number(process.env.SAMPLES || 24);

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

const rows = [];
for (const [mode, options] of Object.entries(modes)) {
  for (let i = 0; i < samples; i += 1) {
    const seed = `session-${i}`;
    rows.push({ mode, seed, html: page(seed, options) });
  }
}

console.log(JSON.stringify({ samples, record, rows }));
