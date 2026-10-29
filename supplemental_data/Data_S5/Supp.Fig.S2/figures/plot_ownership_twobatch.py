"""plot_ownership_twobatch.py — Figure S2 panels: leaf assignment in the two fully reviewed batches.

  fig_s2_a_agreement       both batches: trajectories kept or rejected in review, split by whether
                           the automatic decision agreed
  fig_s2_b_rates_b08       2025B08 false-reject and false-keep rates by days after sowing (DAS)
  fig_s2_c_rates_b09       2025B09, as above
  fig_s2_d_cotyledon_b08   2025B08 false-reject rates of cotyledons and true leaves on the same
                           plant-days (accession lines and the batch total)
  fig_s2_e_cotyledon_b09   2025B09, as above

Reads only the bundled CSV files:
  input   <data>/ownership_twobatch_summary.csv, <data>/ownership_twobatch_by_das.csv,
          <data>/ownership_twobatch_cotyledon.csv
  output  <out>/<names above>.{png,pdf,svg}

Usage:
  python figures/plot_ownership_twobatch.py --data DIR --out DIR

Drawing:
  - One panel per batch, so the false-reject rate staying above the false-keep rate remains visible.
  - Panels are written separately without panel letters; letters and the panel b–c line legend
    were added during figure assembly.
  - Panels in the same row share x and y ranges computed from all data.
  - Panels b–c: false-reject rate = FN / (TP + FN), kept in review but rejected automatically (orange);
    false-keep rate = FP / (FP + TN), rejected in review but kept automatically (blue); Equations
    (6) and (7) in Supplementary Methods S8. The denominators are review decisions, as in panel a.
  - Panel a: each bar is all trajectories kept or rejected in review; grey, automatic decision agrees;
    orange, it differs. The orange parts equal the false-reject and false-keep rates in Table 1.
"""
from __future__ import annotations

import argparse
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from style import FORMATS, style

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)            # analysis folder: data/ and output/ are here
BATCHES = ("2025B08", "2025B09")
XLABEL = "Days after sowing (DAS)"
C_KEEP, C_REJ = "#2166AC", "#D95F02"   # false-keep blue, false-reject orange (colour-vision safe pair)
C_AGREE, C_DIS = "#c8c8c8", C_REJ        # panel a: agreement grey, disagreement in the false-reject orange
INK, GRID, LIGHT = "#1a1a1a", "#e6e6e6", "#b3b3b3"
MM = 1 / 25.4
PANEL_W, PANEL_H = 70 * MM, 52 * MM
AX_RECT = [0.165, 0.205, 0.805, 0.705]     # same plot area for the four 2 x 2 panels

# Accession lines are drawn only for accessions with at least this many reviewed cotyledon
# trajectories; smaller counts give unstable rates. The batch total (black) uses all trajectories.
MIN_COT = 10



def read(data, name):
    with open(os.path.join(data, name), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def new_panel():
    fig = plt.figure(figsize=(PANEL_W, PANEL_H))
    return fig, fig.add_axes(AX_RECT)


def save(fig, out, stem):
    for ext in FORMATS:
        fig.savefig(os.path.join(out, f"{stem}.{ext}"), dpi=600)
    plt.close(fig)
    print(f"  {out}/{stem}.png / .pdf / .svg")


def panel_agreement(summary):
    """Panel a: each bar is all trajectories kept or rejected in review, split into agreement and disagreement."""
    fig = plt.figure(figsize=(143 * MM, 50 * MM))
    ax = fig.add_axes([0.29, 0.17, 0.62, 0.66])
    labels, ys, y = [], [], 0.0
    for b in BATCHES:
        s = {k: int(r[k]) for r in summary if r["batch"] == b for k in ("TP", "FP", "FN", "TN")}
        y0 = y
        for cls, agree, dis in (("Kept in review", s["TP"], s["FN"]),
                                ("Rejected in review", s["TN"], s["FP"])):
            n = agree + dis
            pa, pd_ = 100 * agree / n, 100 * dis / n
            ax.barh(y, pa, color=C_AGREE, height=0.62, edgecolor="none")
            ax.barh(y, pd_, left=pa, color=C_DIS, height=0.62, edgecolor="none")
            ax.text(pa / 2, y, f"{pa:.1f}%", ha="center", va="center", fontsize=7, color=INK)
            ax.text(101.2, y, f"{pd_:.1f}%", ha="left", va="center", fontsize=7, color=C_DIS)
            labels.append(f"{cls} (n = {n:,})")
            ys.append(y)
            y += 1
        ax.text(0, y0 - 0.62, b, transform=ax.get_yaxis_transform(),
                ha="left", va="bottom", fontsize=8, fontweight="bold", color=INK)
        y += 0.9
    ax.set_yticks(ys, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Leaf-day trajectories (%)", labelpad=3)
    style(ax)
    ax.grid(axis="y", visible=False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    h = [plt.Rectangle((0, 0), 1, 1, color=C_AGREE), plt.Rectangle((0, 0), 1, 1, color=C_DIS)]
    fig.legend(h, ["Automatic decision agrees", "Automatic decision differs"], loc="upper center",
               ncol=2, frameon=False, fontsize=7, bbox_to_anchor=(0.62, 1.0), handlelength=1.2)
    return fig


def rates(r):
    """(false-reject rate, false-keep rate) in %, precomputed in the data (Equations 6 and 7)."""
    return 100 * float(r["false_reject_rate"]), 100 * float(r["false_keep_rate"])


def panel_rates(by_das, b, xlim, ylim):
    fig, ax = new_panel()
    rr = [r for r in by_das if r["batch"] == b]
    x = [int(r["das"]) for r in rr]
    for i, c in ((0, C_REJ), (1, C_KEEP)):
        ax.plot(x, [rates(r)[i] for r in rr], color=c, lw=1.4)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_xlabel(XLABEL, labelpad=3)
    ax.set_ylabel("Rate (%)", labelpad=3)
    ax.set_title(b, fontsize=8, color=INK, pad=3)
    style(ax)
    return fig


def cot_rates(cot, b, cv):
    g = {r["class"]: r for r in cot if r["batch"] == b and r["cultivar"] == cv}
    return g["true_leaf"], g["cotyledon"]


def panel_cotyledon(cot, b, ytop):
    fig, ax = new_panel()
    shown = 0
    for cv in sorted({r["cultivar"] for r in cot if r["batch"] == b and r["cultivar"] != "pooled"}):
        leaf, coty = cot_rates(cot, b, cv)
        if int(coty["manual_keep"]) < MIN_COT or int(leaf["manual_keep"]) == 0:
            continue
        shown += 1
        y = [100 * float(leaf["false_reject_rate"]), 100 * float(coty["false_reject_rate"])]
        ax.plot([0, 1], y, color=LIGHT, lw=0.7, zorder=1)
        ax.scatter([0, 1], y, s=7, color=LIGHT, zorder=2, linewidths=0)
    leaf, coty = cot_rates(cot, b, "pooled")
    y = [100 * float(leaf["false_reject_rate"]), 100 * float(coty["false_reject_rate"])]
    ax.plot([0, 1], y, color=INK, lw=1.6, zorder=3)
    ax.scatter([0, 1], y, s=24, color=INK, zorder=4, edgecolor="white", linewidth=0.6)
    for x, v, ha, dx in ((0, y[0], "right", -0.07), (1, y[1], "left", 0.07)):
        ax.text(x + dx, v, f"{v:.1f}%", ha=ha, va="center", fontsize=7, color=INK, zorder=5,
                bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none"))
    print(f"  cotyledon panel {b}: {shown} accessions drawn (>= {MIN_COT} cotyledon trajectories)")
    ax.set_xticks([0, 1], ["True leaf", "Cotyledon"])
    ax.set_xlim(-0.45, 1.45)
    ax.set_ylim(0, ytop)
    ax.set_ylabel("False-reject rate (%)", labelpad=3)
    ax.set_title(b, fontsize=8, color=INK, pad=3)
    style(ax)
    ax.grid(axis="x", visible=False)
    return fig


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    ap.add_argument("--out", default=os.path.join(ROOT, "output", "Supp.Fig.S2"))
    args = ap.parse_args()
    summary = read(args.data, "ownership_twobatch_summary.csv")
    by_das = read(args.data, "ownership_twobatch_by_das.csv")
    cot = read(args.data, "ownership_twobatch_cotyledon.csv")
    os.makedirs(args.out, exist_ok=True)

    das_all = [int(r["das"]) for r in by_das]
    xlim = (min(das_all) - 0.5, max(das_all) + 0.5)
    ylim = (0, 5 * np.ceil(max(max(rates(r)) for r in by_das) / 5 + 0.1))
    drawn = [100 * float(r["false_reject_rate"]) for r in cot if r["cultivar"] != "pooled"
             and int(cot_rates(cot, r["batch"], r["cultivar"])[1]["manual_keep"]) >= MIN_COT]
    ytop = 5 * np.ceil(max(drawn) / 5 + 0.2)

    save(panel_agreement(summary), args.out, "fig_s2_a_agreement")
    save(panel_rates(by_das, "2025B08", xlim, ylim), args.out, "fig_s2_b_rates_b08")
    save(panel_rates(by_das, "2025B09", xlim, ylim), args.out, "fig_s2_c_rates_b09")
    save(panel_cotyledon(cot, "2025B08", ytop), args.out, "fig_s2_d_cotyledon_b08")
    save(panel_cotyledon(cot, "2025B09", ytop), args.out, "fig_s2_e_cotyledon_b09")


if __name__ == "__main__":
    main()
