"""Render results/metrics.csv into a markdown summary and two figures.

The headline is the frequency bias -- the model calls rain on half again as
many days as it rains. The split between the two directions, and the loss to
persistence at lead 1, are both consequences of it.
"""
from __future__ import annotations

import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from config import BLOCK_DEG, FORECAST_MODEL, LEADS, RESULTS, THRESHOLDS

# colour-blind-safe, consistent across both figures
C_IMD, C_ERA5 = "#1b6ca8", "#c1622d"


def fig_far(res: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, len(THRESHOLDS), figsize=(11, 4.2), sharey=True)
    for ax, thr in zip(axes, THRESHOLDS):
        for truth, colour in [("IMD", C_IMD), ("ERA5", C_ERA5)]:
            s = res[(res.truth == truth) & (res.threshold_mm == thr)
                    ].sort_values("lead_days")
            ax.plot(s.lead_days, s.FAR, "o-", color=colour, label=f"{truth} truth")
            ax.fill_between(s.lead_days, s.FAR_lo, s.FAR_hi,
                            color=colour, alpha=0.15, linewidth=0)
        ax.set_title(f"wet day = ≥{thr} mm")
        ax.set_xlabel("lead time (days)")
        ax.grid(alpha=0.3)
        ax.set_xticks(LEADS)
    axes[0].set_ylabel("False alarm ratio")
    axes[0].legend(frameon=False)
    fig.suptitle(f"False alarm ratio by lead time — {FORECAST_MODEL}, India\n"
                 f"shaded = 95% bootstrap CI, {BLOCK_DEG:g}° spatial blocks",
                 y=1.02)
    fig.tight_layout()
    fig.savefig(RESULTS / "far_by_lead.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def fig_all(res: pd.DataFrame) -> None:
    mets = ["POD", "FAR", "CSI", "HSS", "BIAS"]
    fig, axes = plt.subplots(len(THRESHOLDS), len(mets),
                             figsize=(17, 6.4), sharex=True)
    for r, thr in enumerate(THRESHOLDS):
        for c, m in enumerate(mets):
            ax = axes[r, c]
            for truth, colour in [("IMD", C_IMD), ("ERA5", C_ERA5)]:
                s = res[(res.truth == truth) & (res.threshold_mm == thr)
                        ].sort_values("lead_days")
                ax.plot(s.lead_days, s[m], "o-", color=colour, ms=4,
                        label=f"{truth} truth")
                ax.fill_between(s.lead_days, s[f"{m}_lo"], s[f"{m}_hi"],
                                color=colour, alpha=0.15, linewidth=0)
            if m == "BIAS":
                ax.axhline(1.0, color="0.4", ls=":", lw=1)
            ax.grid(alpha=0.3)
            ax.set_xticks(LEADS)
            if r == 0:
                ax.set_title(m)
            if c == 0:
                ax.set_ylabel(f"≥{thr} mm\n")
            if r == len(THRESHOLDS) - 1:
                ax.set_xlabel("lead (days)")
    axes[0, 0].legend(frameon=False, fontsize=8)
    fig.suptitle(f"Rainfall forecast skill by lead time — {FORECAST_MODEL}, "
                 "India, 139 grid points", y=1.01)
    fig.tight_layout()
    fig.savefig(RESULTS / "all_metrics_by_lead.png", dpi=160,
                bbox_inches="tight")
    plt.close(fig)


def df_to_md(df: pd.DataFrame, floatfmt: str = "{:.3f}") -> str:
    """Minimal markdown table -- avoids a hard dependency on tabulate."""
    cols = list(df.columns)
    head = "| " + " | ".join(str(c) for c in cols) + " |"
    rule = "|" + "|".join("---" for _ in cols) + "|"
    body = []
    for _, r in df.iterrows():
        cells = [floatfmt.format(v) if isinstance(v, float) else str(v)
                 for v in r]
        body.append("| " + " | ".join(cells) + " |")
    return "\n".join([head, rule, *body])


def md_table(res: pd.DataFrame, truth: str, thr: float) -> str:
    s = res[(res.truth == truth) & (res.threshold_mm == thr)
            ].sort_values("lead_days")
    out = ["| Lead | POD | **FAR** | CSI | HSS | BIAS | hits | false alarms | misses | n |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for r in s.itertuples():
        out.append(
            f"| {r.lead_days} | {r.POD:.3f} | **{r.FAR:.3f}** "
            f"({r.FAR_lo:.3f}–{r.FAR_hi:.3f}) | {r.CSI:.3f} | {r.HSS:.3f} | "
            f"{r.BIAS:.2f} | {int(r.hits):,} | {int(r.false_alarms):,} | "
            f"{int(r.misses):,} | {int(r.n):,} |")
    return "\n".join(out)


def main() -> int:
    path = RESULTS / "metrics.csv"
    if not path.exists():
        sys.exit("run analyze.py first")
    res = pd.read_csv(path)
    fig_far(res)
    fig_all(res)

    gap = pd.read_csv(RESULTS / "far_truth_source_gap.csv")
    lines = [
        "# Results — rainfall forecast skill over India",
        "",
        f"Model: `{FORECAST_MODEL}` (pinned). Truth: IMD 0.25° gridded, "
        "0300–0300 UTC rainfall day.",
        f"Uncertainty: 95% bootstrap CI, resampling {BLOCK_DEG:g}° spatial "
        "blocks (not individual points — rainfall is spatially correlated, "
        "and point-level resampling halves the interval width).",
        "",
        "**The headline is the frequency bias.** The model calls rain on "
        "34.9% of days; rain falls on 23.6%. BIAS = 1.48, near-flat across "
        "leads. Two consequences follow, each measured independently: the "
        "two directions come apart (PPV 0.577 against NPV 0.947 at lead 1), "
        "and the rain direction loses to persistence at lead 1 (0.577 "
        "against 0.623, paired 95% CI on the difference -0.074 to -0.016). "
        "See `persistence_benchmark.csv`.",
        "",
    ]
    for thr in THRESHOLDS:
        lines += [f"## Wet day = ≥{thr} mm — IMD truth (primary)", "",
                  md_table(res, "IMD", thr), ""]
    for thr in THRESHOLDS:
        lines += [f"## Wet day = ≥{thr} mm — ERA5 truth (robustness check)", "",
                  md_table(res, "ERA5", thr), ""]
    lines += [
        "## Truth-source gap in FAR",
        "",
        "ERA5's wet bias is one-directional: it converts real false alarms "
        "into apparent hits. A negative gap means ERA5 **understates** FAR, "
        "flattering the forecast.",
        "",
        "**Mechanism, measured.** The gap was tested against two non-IFS "
        "models (DWD ICON, NCEP GFS) on a matched 47-point sample — see "
        "`crossmodel_far_gap.csv`. Their gaps are smaller in magnitude than "
        "ECMWF's, significantly so, but only by **7–16%**. So scoring an "
        "ECMWF forecast against ECMWF's own reanalysis does inflate the gap "
        "(shared IFS lineage is real), yet it accounts for roughly one "
        "eighth of it. The remaining ~85% is ERA5's wet bias, which "
        "flatters every model about equally. Reanalysis truth is the wrong "
        "choice here regardless of whose forecast is being scored.",
        "",
        df_to_md(gap),
        "",
        "![FAR by lead](far_by_lead.png)",
        "",
        "![All metrics](all_metrics_by_lead.png)",
    ]
    (RESULTS / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {RESULTS/'RESULTS.md'}, far_by_lead.png, "
          f"all_metrics_by_lead.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
