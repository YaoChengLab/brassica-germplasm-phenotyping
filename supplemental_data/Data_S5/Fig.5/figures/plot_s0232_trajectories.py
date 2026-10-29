"""plot_s0232_trajectories.py — Figure 5b–d and Figure S3 panels: four s0232 plants, three leaf selections.

  fig5_b_leaf_count, fig5_c_area, fig5_d_solidity   Figure 5b–d: leaf count, projected leaf area, solidity
  fig_s3_a_circularity_2 … fig_s3_i_glcm_idm        Figure S3a–i: daily trajectories of nine per-image traits
  fig_s3_j_rgr_slope … fig_s3_m_circ_peak          Figure S3j–m: four time-series features, one value per plant

Reads only the bundled CSV files:
  input   <data>/s0232_daily_by_plant.csv, <data>/s0232_timeseries_features.csv
  output  <out>/<names above>.{png,pdf,svg}
Usage:
  python figures/plot_s0232_trajectories.py --data DIR --out DIR
  python figures/plot_s0232_trajectories.py --only fig5      # Figure 5b–d only; --only s3 for Figure S3 only

Drawing:
  - Lines are the mean of four plants; bands are ±1 SD among plants (each plant is first
    averaged over all images of the day).
  - All three selections have bands; the automatic and reviewed bands largely overlap.
  - Panels are written separately without panel letters; letters and the shared Figure S3
    legend were added during figure assembly.
  - Panels j–m: small points are plants; large points and error bars are the mean ±1 SD of
    four plants. Each feature has its own y axis.
"""
from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from style import FORMATS, LS_REVIEW, SEL_COLOR as COL, SEL_LABEL as LAB, style

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)            # analysis folder: data/ and output/ are here
SEL = ("raw", "auto", "qc")
GRID, MM, XLABEL = "#e6e6e6", 1 / 25.4, "Days after sowing (DAS)"

FIG5 = [("leaf_count", "Leaf count", 1.0, "fig5_b_leaf_count", "upper left"),
        ("area_pixels", "Projected leaf area (10$^3$ px$^2$)", 1e-3, "fig5_c_area", "upper left"),
        ("solidity", "Solidity", 1.0, "fig5_d_solidity", "upper right")]
S3 = [("circularity_2", "Circularity 2", 1.0),
      ("ellipse_aspect_ratio", "Aspect ratio", 1.0), ("perimeter_pixels", "Plant perimeter (10$^3$ px)", 1e-3),
      ("convex_hull_area_pixels", "Convex hull area (10$^3$ px$^2$)", 1e-3),
      ("excess_red_index", "ExR (DN)", 1.0), ("excess_green_index", "ExG (DN)", 1.0),
      ("chroma", "Chroma", 1.0), ("pixel_entropy", "Pixel entropy", 1.0), ("glcm_idm", "GLCM IDM", 1.0)]
TS = [("rgr_slope", "d$^{-1}$"), ("emg_rate", "leaves d$^{-1}$"), ("sol_rise", "dimensionless"),
      ("circ_peak", "dimensionless")]



def read(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def series(daily, trait, sel, scale):
    """Mean ±1 SD (ddof=1) of four plants; one value per plant and day."""
    by_day = defaultdict(list)
    for r in daily:
        if r["selection"] == sel and r[trait] != "":
            by_day[int(r["das"])].append(float(r[trait]) * scale)
    days = sorted(by_day)
    m = np.array([np.mean(by_day[d]) for d in days])
    sd = np.array([np.std(by_day[d], ddof=1) if len(by_day[d]) > 1 else 0.0 for d in days])
    return np.array(days), m, sd


def trajectories(ax, daily, trait, scale, lw):
    for z, v in enumerate(SEL):
        x, m, sd = series(daily, trait, v, scale)
        ax.fill_between(x, m - sd, m + sd, color=COL[v], alpha=0.12, lw=0, zorder=z)
        ax.plot(x, m, color=COL[v], lw=lw[v], ls=LS_REVIEW if v == "qc" else "-",
                dash_capstyle="round" if v == "qc" else "butt", zorder=3 + z, label=LAB[v])


def save(fig, out, stem):
    for ext in FORMATS:
        fig.savefig(os.path.join(out, f"{stem}.{ext}"), dpi=600)
    plt.close(fig)
    print(f"  {stem}.png / .pdf / .svg")


def fig5(daily, out):
    for trait, ylab, scale, stem, loc in FIG5:
        fig = plt.figure(figsize=(3.35, 2.5))
        ax = fig.add_axes([0.175, 0.195, 0.805, 0.775])
        trajectories(ax, daily, trait, scale, {"raw": 1.9, "auto": 2.2, "qc": 2.2})
        ax.set_xlabel(XLABEL, labelpad=4)
        ax.set_ylabel(ylab, labelpad=4)
        ax.set_ylim(bottom=0)
        style(ax)
        ax.legend(frameon=False, fontsize=6.6, loc=loc, handlelength=2.8, borderpad=0.1, labelspacing=0.35)
        save(fig, out, stem)


def s3_panels(daily, out):
    for k, (trait, ylab, scale) in enumerate(S3):
        fig = plt.figure(figsize=(58 * MM, 46 * MM))
        ax = fig.add_axes([0.25, 0.2, 0.71, 0.74])                 # same position for all nine panels
        trajectories(ax, daily, trait, scale, {"raw": 1.4, "auto": 1.6, "qc": 1.6})
        ax.set_xlabel("DAS", fontsize=7, labelpad=1)
        ax.set_ylabel(ylab, fontsize=7, labelpad=2)
        ax.tick_params(labelsize=6.5)
        style(ax)
        save(fig, out, f"fig_s3_{'abcdefghi'[k]}_{trait}")


def s3_timeseries(feats, out):
    off = np.array([-0.27, -0.15, 0.15, 0.27])                    # two plants on each side
    for k, (feat, unit) in enumerate(TS):
        fig = plt.figure(figsize=(43 * MM, 52 * MM))               # four panels plus three 2 mm gaps = 178 mm
        ax = fig.add_axes([0.27, 0.36, 0.69, 0.54])                # same position for all four panels
        for i, v in enumerate(SEL):
            y = np.array([float(r[feat]) for r in sorted(feats, key=lambda r: r["rel"])
                          if r["selection"] == v and r[feat] != ""])
            ax.scatter(i + off[:len(y)], y, s=9, color=COL[v], alpha=0.8, edgecolors="none", zorder=2)
            ax.errorbar(i, y.mean(), yerr=y.std(ddof=1), fmt="o", ms=4.5, color=COL[v],
                        ecolor=COL[v], elinewidth=1.2, capsize=0, zorder=3)
        ax.set_xticks(range(3), [LAB[v] for v in SEL], fontsize=6, rotation=35, ha="right",
                      rotation_mode="anchor")
        ax.set_xlim(-0.6, 2.6)
        ax.set_title(feat, fontsize=7, pad=3)
        ax.set_ylabel(unit, fontsize=7, labelpad=2)
        ax.tick_params(labelsize=6.5)
        style(ax)
        save(fig, out, f"fig_s3_{'jklm'[k]}_{feat}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    ap.add_argument("--out", default=None,
                    help="output folder for both figures; default output/Fig.5/ and output/Supp.Fig.S3/")
    ap.add_argument("--only", choices=("fig5", "s3", "all"), default="all",
                    help="fig5: Figure 5b–d only; s3: Figure S3 only")
    a = ap.parse_args()
    out5 = a.out or os.path.join(ROOT, "output", "Fig.5")
    out3 = a.out or os.path.join(ROOT, "output", "Supp.Fig.S3")
    for d in (out5, out3):
        os.makedirs(d, exist_ok=True)
    daily = read(os.path.join(a.data, "s0232_daily_by_plant.csv"))
    if a.only in ("fig5", "all"):
        fig5(daily, out5)
    if a.only in ("s3", "all"):
        s3_panels(daily, out3)
        s3_timeseries(read(os.path.join(a.data, "s0232_timeseries_features.csv")), out3)


if __name__ == "__main__":
    main()
