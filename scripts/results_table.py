"""Write docs/models/results.md: one row per model, from models/<topic>/metrics*.json.

    python scripts/results_table.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "prostate": "PSA of 4.0 or higher at the visit (men 50–69)",
    "heart": "Death from heart disease or stroke within 10 years (adults 40–79)",
    "colorectal": "Ever told they had colon or rectal cancer (adults 45–79)",
}


def rows() -> list[str]:
    out = []
    for topic, target in TARGETS.items():
        f = ROOT / "models" / topic / "metrics.json"
        if not f.exists():
            out.append(f"| {topic} | {target} | not trained yet | | | | |")
            continue
        m = json.loads(f.read_text())
        if topic == "heart":  # src/train_heart.py layout
            t, b = m["model"]["test"], m["baseline_age_sex"]["test"]
            out.append(f"| {topic} | {target} | {t['n']:,} | {t['auc']:.3f} | {b['auc']:.3f} | {t['brier']:.4f} vs {b['brier']:.4f} "
                       f"| {t['predicted_per_1000']:.1f} vs {t['observed_per_1000']:.1f} |")
        else:  # src/train.py layout
            t, b = m["model"], m["baseline_age_group"]
            lo, hi = t["auc_ci95"]
            out.append(f"| {topic} | {target} | {t['n']:,} | {t['auc']:.3f} ({lo:.2f}–{hi:.2f}) | {b['auc']:.3f} "
                       f"| {t['brier']:.4f} vs {b['brier']:.4f} | {1000 * t['mean_predicted']:.1f} vs {1000 * t['observed_rate']:.1f} |")
    return out


def main() -> None:
    text = "\n".join([
        "# Final test-set results",
        "",
        "One run per model on survey cycles it never saw during training or tuning. "
        "Baseline = age and sex only (heart) or 5-year age bands (prostate, colorectal).",
        "",
        "| Model | Predicts | Test people | AUC (95% CI) | Baseline AUC | Brier: model vs baseline | Per 1,000: predicted vs actual |",
        "|---|---|---|---|---|---|---|",
        *rows(),
        "",
        "AUC: 0.5 is a coin flip, 1.0 is perfect. Brier: lower is better. The last column checks calibration.",
        "",
    ])
    (ROOT / "docs" / "models" / "results.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
