"""plot_dead_plant.py — Figure S4: four plants of a Chinese cabbage accession in 2025B08; plant 2 died.

  fig_s4_a_area                  panel a: projected leaf area of the 12:00 image of each day, four plants
  fig_s4_b_leaf_count            panel b: leaf count, as above
  fig_s4_c_plant{1..4}_das{DAS}  panel c: 20 single-plant image tiles (four plants x five days, 12:00);
                                 cyan outlines are leaves kept after manual review; PNG only

Panels a, b and c use the same 12:00 image of each day; the five days of panel c are drawn
as large open circles in panels a and b, so each circle is the value of that tile.
Row labels, column labels and panel letters were added during figure assembly.

Data:
  data/dead_plant_s0124_noon.csv     four plants x the 12:00 image of each day: leaf count, projected leaf area
  data/dead_plant_s0124_tiles.json   for the 20 tiles: image file name, counts and polygons of leaves kept after review
  data/dead_plant_images/            the 20 source images; not included in this package, so panel c
                                     is skipped unless the folder is supplied

Usage:
  python figures/plot_dead_plant.py --data DIR --out DIR
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon
from PIL import Image

from style import FORMATS, XLABEL_DAS, style

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Okabe–Ito; plant 2 (died) in vermilion with a thicker line
COLOR = {1: "#0072B2", 2: "#D55E00", 3: "#009E73", 4: "#CC79A7"}
OUTLINE = "#00E5FF"
PANEL = (8.2 / 2.54, 5.6 / 2.54)          # panels a and b have the same size
AXES_RECT = [0.17, 0.19, 0.79, 0.77]      # fixed margins, equal plot areas
TILE_IN = 2.0                             # 600 px image saved as 2 in at 300 dpi, without resampling


def save(fig, out, stem, dpi=600, formats=FORMATS):
    for ext in formats:
        fig.savefig(os.path.join(out, f"{stem}.{ext}"), dpi=dpi)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    ap.add_argument("--out", default=os.path.join(ROOT, "output", "Supp.Fig.S4"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    noon = list(csv.DictReader(open(os.path.join(a.data, "dead_plant_s0124_noon.csv"), encoding="utf-8")))
    tiles = json.load(open(os.path.join(a.data, "dead_plant_s0124_tiles.json"), encoding="utf-8"))["tiles"]
    shown_das = sorted({t["das"] for t in tiles})

    series = defaultdict(dict)
    for r in noon:
        for col in ("area", "leaf_count"):
            series[(int(r["replicate"]), col)][int(r["das"])] = float(r[col])
    for t in tiles:                                     # each circle must equal its tile's value
        assert series[(t["replicate"], "leaf_count")][t["das"]] == t["n_kept_after_review"], t["image"]

    for stem, col, ylab, scale, ymax in [("fig_s4_a_area", "area", "Projected leaf area (10$^3$ px$^2$)", 1e3, 95),
                                         ("fig_s4_b_leaf_count", "leaf_count", "Leaf count", 1, None)]:
        fig = plt.figure(figsize=PANEL)
        ax = fig.add_axes(AXES_RECT)
        style(ax)
        for rep in (1, 3, 4, 2):                       # plant 2 drawn on top
            s = series[(rep, col)]
            x = sorted(s)
            ax.plot(x, [s[d] / scale for d in x], color=COLOR[rep], lw=1.8 if rep == 2 else 1.0,
                    marker="o", ms=2.2 if rep == 2 else 1.6, label=f"Plant {rep}")
            ax.plot(shown_das, [s[d] / scale for d in shown_das], ls="none", marker="o", ms=6.0,
                    mfc="white", mec=COLOR[rep], mew=1.2, zorder=4)
            ax.plot(shown_das, [s[d] / scale for d in shown_das], ls="none", marker="o",
                    ms=2.2 if rep == 2 else 1.6, color=COLOR[rep], zorder=5)
        ax.set_xlabel(XLABEL_DAS)
        ax.set_ylabel(ylab)
        ax.set_xlim(11, 40)
        ax.set_ylim(0, ymax)
        if col == "area":
            h, l = ax.get_legend_handles_labels()
            order = [l.index(x) for x in ("Plant 1", "Plant 2", "Plant 3", "Plant 4")]
            ax.legend([h[i] for i in order], [l[i] for i in order], frameon=False, fontsize=7, loc="upper left")
        save(fig, a.out, stem)

    img_dir = os.path.join(a.data, "dead_plant_images")
    if not os.path.isdir(img_dir):
        print("panel c skipped: data/dead_plant_images/ is not included in this package")
        return
    for t in tiles:
        img = np.asarray(Image.open(os.path.join(img_dir, t["image"])).convert("RGB"))
        fig = plt.figure(figsize=(TILE_IN, TILE_IN))
        ax = fig.add_axes([0, 0, 1, 1])
        ax.imshow(img, interpolation="none")
        for pts in t["kept_polygons"]:
            ax.add_patch(Polygon(pts, closed=True, fill=False, ec=OUTLINE, lw=1.4))
        ax.set_xlim(-0.5, img.shape[1] - 0.5)
        ax.set_ylim(img.shape[0] - 0.5, -0.5)
        ax.axis("off")
        # image tiles carry no text, so only PNG is written
        save(fig, a.out, f"fig_s4_c_plant{t['replicate']}_das{t['das']}", dpi=img.shape[1] / TILE_IN,
             formats=("png",))
        print(f"plant {t['replicate']} DAS {t['das']}: {t['n_kept_after_review']} kept after review "
              f"({t['n_kept_automatic']} automatic, {t['n_detections']} detections)")


if __name__ == "__main__":
    main()
