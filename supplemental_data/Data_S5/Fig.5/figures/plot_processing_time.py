"""plot_processing_time.py — Figure 5a: processing time per plant for three cumulative workflows.

  fig5_a_processing_time    stacked bars for segmentation, + assignment and + manual review

The values are fixed constants below, not read from a data file, so the published
figure does not drift on rerun. They were measured on 2026-08-18:
  segmentation 59.0 s and assignment 24.2 s: four s0232 plants, 346 images each,
    NVIDIA RTX A2000, batch size 1, including input/output and model loading
  manual review 88 s: median interval between consecutive reviewed plants in 2025B08
Repeated runs gave 83.2 s per plant in total; the split between segmentation and
assignment varied by about ±0.4 s between runs. The unit is one plant's full image
series (346 images over 28 days in 2025B08).

Usage:
  python figures/plot_processing_time.py --out DIR
"""
from __future__ import annotations

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from style import FORMATS, SEL_COLOR, style

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SEGMENTATION, OWNERSHIP, REVIEW = 59.0, 24.2, 88.0
XMAX = 205.0                              # axis drawn to 180; space on the right for total labels

# segment colours match the three leaf selections in Figure 5b–d
SEGMENTS = [("Segmentation", SEGMENTATION, SEL_COLOR["raw"]),
            ("Ownership", OWNERSHIP, SEL_COLOR["auto"]),
            ("Manual review", REVIEW, SEL_COLOR["qc"])]
ARMS = [("Segmentation", 1), ("+ Ownership", 2), ("+ Manual review", 3)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=None, help="unused; accepted for make_all.py")
    ap.add_argument("--out", default=os.path.join(ROOT, "output", "Fig.5"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    fig = plt.figure(figsize=(3.35, 2.5))                     # same size as panels b–d
    ax = fig.add_axes([0.30, 0.195, 0.68, 0.72])
    for y, (_, n_seg) in zip(range(len(ARMS) - 1, -1, -1), ARMS):
        left = 0.0
        for _, val, colour in SEGMENTS[:n_seg]:
            ax.barh(y, val, left=left, height=0.72, color=colour,
                    edgecolor="white", linewidth=0.6, zorder=3)
            ax.text(left + val / 2, y, f"{val:.0f}", ha="center", va="center",
                    fontsize=7, color="white", zorder=4)
            left += val
        ax.text(left + 4, y, f"{left:.0f} s", ha="left", va="center",
                fontsize=7.5, fontweight="bold", zorder=4)
    ax.set_yticks(list(range(len(ARMS) - 1, -1, -1)))
    ax.set_yticklabels([n for n, _ in ARMS], fontsize=7.5)
    ax.set_ylim(-0.6, len(ARMS) - 0.4)
    ax.set_xlim(0, XMAX)
    ax.set_xticks(range(0, 181, 60))
    ax.set_xlabel("Processing time per plant (s)", labelpad=3, fontsize=8)
    style(ax)
    ax.spines["bottom"].set_bounds(0, 180)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    handles = [Patch(facecolor=c, edgecolor="none", label=n) for n, _, c in SEGMENTS]
    ax.legend(handles=handles, frameon=False, fontsize=6.6, ncol=len(SEGMENTS),
              loc="lower right", bbox_to_anchor=(1.01, 1.01),
              handlelength=1.2, handleheight=0.9, borderpad=0.0,
              columnspacing=1.1, handletextpad=0.4)
    for ext in FORMATS:
        fig.savefig(os.path.join(a.out, f"fig5_a_processing_time.{ext}"), dpi=600)
    plt.close(fig)
    print(f"  fig5_a_processing_time.png / .pdf / .svg   (automatic {SEGMENTATION + OWNERSHIP:.0f} s,"
          f" with review {SEGMENTATION + OWNERSHIP + REVIEW:.0f} s)")


if __name__ == "__main__":
    main()
