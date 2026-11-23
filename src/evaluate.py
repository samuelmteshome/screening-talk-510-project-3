"""Metrics and plots shared by every topic: AUC, Brier score, calibration in
risk groups, bootstrap intervals and results by subgroup."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

PREDICTED_COLOR = "#2a78d6"  # categorical slot 1 (blue)
OBSERVED_COLOR = "#eb6834"   # categorical slot 2 (orange)
INK, MUTED, GRID = "#0b0b0b", "#6b6a63", "#e4e3de"


def _auc(y, p, w=None) -> float:
    return float(roc_auc_score(y, p, sample_weight=w)) if len(np.unique(y)) == 2 else float("nan")


def metrics(y, p, w=None) -> dict[str, float]:
    """AUC, Brier score, observed rate and mean prediction."""
    y, p = np.asarray(y), np.asarray(p)
    return {
        "n": int(len(y)),
        "auc": _auc(y, p, w),
        "brier": float(brier_score_loss(y, p, sample_weight=w)),
        "observed_rate": float(np.average(y, weights=w)),
        "mean_predicted": float(np.average(p, weights=w)),
    }


def brier_skill(model_brier: float, baseline_brier: float) -> float:
    """Share of the baseline's Brier score removed by the model (0 = no better)."""
    return float(1 - model_brier / baseline_brier) if baseline_brier > 0 else float("nan")


def bootstrap_auc_ci(y, p, seed: int, n_boot: int = 500, level: float = 0.95) -> tuple[float, float]:
    """Percentile bootstrap interval for the AUC."""
    y, p = np.asarray(y), np.asarray(p)
    rng = np.random.default_rng(seed)
    aucs = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        if len(np.unique(y[idx])) == 2:
            aucs.append(roc_auc_score(y[idx], p[idx]))
    if not aucs:
        return float("nan"), float("nan")
    lo, hi = np.percentile(aucs, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return float(lo), float(hi)


def calibration_table(y, p, groups: int = 5) -> pd.DataFrame:
    """Predicted vs observed rate in equal-size risk groups (lowest to highest)."""
    frame = pd.DataFrame({"y": np.asarray(y), "p": np.asarray(p)})
    frame["group"] = pd.qcut(frame["p"].rank(method="first"), groups, labels=False) + 1
    table = frame.groupby("group").agg(n=("y", "size"), predicted=("p", "mean"), observed=("y", "mean"))
    return table.reset_index()


def subgroup_table(df: pd.DataFrame, y, p, column: str) -> pd.DataFrame:
    """Metrics for each value of ``column`` (e.g. race_eth), for the ethics section."""
    frame = df[[column]].assign(y=np.asarray(y), p=np.asarray(p))
    rows = [{column: key, **metrics(g["y"], g["p"])} for key, g in frame.groupby(column)]
    return pd.DataFrame(rows)


def plot_calibration(table: pd.DataFrame, path: str | Path, title: str) -> Path:
    """Grouped bars: mean predicted vs observed rate in each risk group."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 4), dpi=150)
    x = np.arange(len(table))
    width = 0.38
    ax.bar(x - width / 2 - 0.01, table["predicted"] * 100, width, color=PREDICTED_COLOR, label="Predicted")
    ax.bar(x + width / 2 + 0.01, table["observed"] * 100, width, color=OBSERVED_COLOR, label="Observed")
    for i, row in table.iterrows():
        ax.text(i + width / 2 + 0.01, row["observed"] * 100, f"{row['observed'] * 100:.0f}%",
                ha="center", va="bottom", fontsize=8, color=MUTED)
    ax.set_xticks(x, [f"{g}\n(n={n})" for g, n in zip(table["group"], table["n"])], fontsize=8, color=MUTED)
    ax.set_xlabel("Risk group (1 = lowest predicted risk)", fontsize=9, color=MUTED)
    ax.set_ylabel("Rate (%)", fontsize=9, color=MUTED)
    ax.set_title(title, fontsize=10, color=INK, loc="left")
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(axis="y", colors=MUTED, labelsize=8, length=0)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    path = Path(path)
    fig.savefig(path)
    plt.close(fig)
    return path
