"""plot_trait_splom.py — Figure 6: scatter-plot matrix of six traits for 258 accessions, coloured by crop group.

Reads only the bundled CSV file:
  input   <data>/fig6_accession_traits.csv (one row per point in the figure)
  output  <out>/fig6_trait_splom.{png,pdf,svg}

Layout follows Fig. 8 of Pérez-Valencia et al. (2022):
  diagonal, kernel density per crop group; lower triangle, pairwise scatter; upper triangle,
  pooled Pearson r ("Corr:") and r within each group; right column, group boxplots; bottom
  row, group histograms; bottom-right cell, accessions per group. Trait names are in grey
  strips on the top and right; units are on the left margin. Symbols: *** p < 0.001,
  ** < 0.01, * < 0.05, . < 0.10, without correction for multiple comparisons. Groups with
  n < 8 would show r without symbols and with n (all seven groups have n >= 19).

--no-style draws with the matplotlib default font instead of the shared style.py settings.

Usage:
  python figures/plot_trait_splom.py --data DIR --out DIR [--no-style]
"""
from __future__ import annotations

import argparse
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from scipy import stats as st

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

AXES = ["area_ref", "count_ref", "solidity", "ellipse_aspect_ratio", "excess_green_index", "rgr_slope"]
# strips hold trait names only (abbreviations are expanded in the caption); units go on the left margin
AXLAB = {"area_ref": "PLA", "count_ref": "Leaf count", "solidity": "Solidity",
         "ellipse_aspect_ratio": "Aspect ratio", "excess_green_index": "ExG", "rgr_slope": "RGR"}
UNITS = ["px$^2$", "leaves", "dimensionless", "dimensionless", "DN", "day$^{-1}$"]
GROUP_NAME = "Accession type"
ORDER = ["Pak choi", "Cauliflower", "Chinese kale", "Chinese cabbage", "Leaf mustard", "Cabbage", "Broccoli"]
# Okabe-Ito palette (colour-vision safe), assigned in ORDER
PAL = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#F0E442"]

MIN_N = 8                     # groups below this size: r without symbols, with n
FIG_W_MM, FIG_H_MM = 352.0, 388.0
SCALE = FIG_W_MM / 180.0
FS_BOOST = 1.584
FS_TICK = 5.0 * SCALE * FS_BOOST
FS_TITLE = 5.6 * SCALE * FS_BOOST
FS_CORR = 4.6 * SCALE * FS_BOOST
FS_GRP = 4.0 * SCALE * FS_BOOST        # upper limit; reduced to the available height so labels never overlap
FS_CODE = 4.4 * SCALE * FS_BOOST
FS_LEG = 4.8 * SCALE * FS_BOOST
UNIT_X = .020
STRIP_BG = "#D9D9D9"
STRIP_MM1, STRIP_LINE_MM = 4.6, 3.4


def stars(p):
    return "***" if p < .001 else "**" if p < .01 else "*" if p < .05 else "." if p < .10 else ""


def readable(c, target=.42):
    """Darken light group colours for text only; points and boxes keep the original colour."""
    r, gr, b = matplotlib.colors.to_rgb(c)
    lum = .2126 * r + .7152 * gr + .0722 * b
    if lum <= target:
        return c
    k = target / max(lum, 1e-6)
    return matplotlib.colors.to_hex((r * k, gr * k, b * k))


def grp_fontsize(nrows, cell_h_pt, span=.815, lead=1.20):
    if nrows <= 1:
        return FS_GRP
    return min(FS_GRP, span * cell_h_pt / ((nrows - 1) * lead))


def _fit(fig, box_ax, txt, along, margin=.92):
    """Shrink a label that exceeds 92% of the strip length; other labels are unchanged."""
    r = fig.canvas.get_renderer()
    bb, box = txt.get_window_extent(r), box_ax.get_window_extent(r)
    need, have = (bb.width, box.width) if along == "x" else (bb.height, box.height)
    if need > have * margin:
        txt.set_fontsize(txt.get_fontsize() * have * margin / need)


def add_strips(fig, ax, n):
    names = [AXLAB[a] for a in AXES] + [GROUP_NAME]
    nline = max(s.count("\n") for s in names) + 1
    fs_mm = FS_TITLE * .9 * 25.4 / 72
    mm = max(STRIP_MM1, fs_mm * 1.55) + max(STRIP_LINE_MM, fs_mm * 1.15) * (nline - 1)
    fw, fh = fig.get_size_inches()
    th, tw = mm / 25.4 / fh, mm / 25.4 / fw
    gap_v, gap_h = th * .18, tw * .18
    for j in range(n + 1):
        b = ax[0, j].get_position()
        a = fig.add_axes([b.x0, b.y1 + gap_v, b.width, th])
        a.set_facecolor(STRIP_BG)
        a.set_xticks([]); a.set_yticks([])
        for sp in a.spines.values():
            sp.set_visible(False)
        _fit(fig, a, a.text(.5, .5, names[j], ha="center", va="center", linespacing=1.15,
                            fontsize=FS_TITLE * .9, color="black", transform=a.transAxes), along="x")
    for i in range(n + 1):
        b = ax[i, n].get_position()
        a = fig.add_axes([b.x1 + gap_h, b.y0, tw, b.height])
        a.set_facecolor(STRIP_BG)
        a.set_xticks([]); a.set_yticks([])
        for sp in a.spines.values():
            sp.set_visible(False)
        _fit(fig, a, a.text(.5, .5, names[i], ha="center", va="center", rotation=-90,
                            linespacing=1.15, fontsize=FS_TITLE * .9, color="black",
                            transform=a.transAxes), along="y")


def draw(g, lab, order, col, codes):
    n = len(AXES)
    fig, ax = plt.subplots(n + 1, n + 1, figsize=(FIG_W_MM / 25.4, FIG_H_MM / 25.4))
    top, bottom = .958, .105
    fig.subplots_adjust(left=.082, right=.938, top=top, bottom=bottom, hspace=.10, wspace=.10)
    cell_h_pt = (top - bottom) * fig.get_size_inches()[1] * 72 / (n + 1 + n * .10)
    cell_w_pt = (.938 - .082) * fig.get_size_inches()[0] * 72 / (n + 1 + n * .10)
    bar_w_pt = cell_w_pt / max(len(order), 1)
    fs_bartick = min(FS_CODE, 1.05 * bar_w_pt)
    cnt_rot = len(order) > 9
    fs_barcnt = (min(FS_CODE * .95, 1.05 * bar_w_pt) if cnt_rot
                 else min(FS_CODE * .95, .95 * bar_w_pt / 1.30))
    lim = {}
    for a in AXES:                     # margin = 8% of the 0.5–99.5 percentile range
        lo, hi = np.nanpercentile(g[a], .5), np.nanpercentile(g[a], 99.5)
        pad = .08 * max(hi - lo, 1e-12)
        lim[a] = (lo - pad, hi + pad)

    for i in range(n + 1):
        for j in range(n + 1):
            A = ax[i, j]
            A.tick_params(labelsize=FS_TICK, length=1.6 * SCALE, pad=1)
            for s in A.spines.values():
                s.set_linewidth(.4 * SCALE)

            if i == n and j == n:                                   # bottom-right: accessions per group
                cnt = [int((lab == o).sum()) for o in order]
                A.bar(range(len(order)), cnt, color=[col[o] for o in order], width=.72, lw=0)
                A.set_xticks(range(len(order)))
                A.set_xticklabels([codes[o] for o in order], fontsize=fs_bartick, rotation=90)
                A.set_yticks([])
                for k, c in enumerate(cnt):
                    A.text(k, c, str(c), ha="center", va="bottom", fontsize=fs_barcnt,
                           rotation=90 if cnt_rot else 0)
                A.set_ylim(0, max(cnt) * (1.55 if cnt_rot else 1.28))
                continue

            if i == n:                                              # bottom row: group histograms
                a = AXES[j]
                lo, hi = lim[a]
                bins = np.linspace(lo, hi, 26)
                for k, o in enumerate(order):
                    v = g.loc[lab == o, a].dropna()
                    if not len(v):
                        continue
                    h, _ = np.histogram(v, bins=bins)
                    h = h / max(h.max(), 1) * .86
                    A.bar(bins[:-1], h, width=np.diff(bins), align="edge",
                          bottom=len(order) - 1 - k, color=col[o], lw=0)
                A.set_xlim(lo, hi)
                A.set_ylim(0, len(order))
                A.set_yticks([])
                continue

            if j == n:                                              # right column: group boxplots (first group on top)
                a = AXES[i]
                rev = order[::-1]
                data = [g.loc[lab == o, a].dropna().values for o in rev]
                bp = A.boxplot(data, vert=False, widths=.62, patch_artist=True,
                               flierprops=dict(marker=".", ms=1.1 * SCALE, mec="none",
                                               mfc="#555555", alpha=.7),
                               medianprops=dict(color="black", lw=.6 * SCALE),
                               whiskerprops=dict(lw=.4 * SCALE),
                               capprops=dict(lw=.4 * SCALE),
                               boxprops=dict(lw=.35 * SCALE))
                for patch, o in zip(bp["boxes"], rev):
                    patch.set_facecolor(col[o])
                    patch.set_alpha(.85)
                A.set_yticks([])
                A.set_xlim(*lim[a])
                A.set_xticklabels([])
                continue

            if i == j:                                              # diagonal: group kernel densities
                a = AXES[i]
                lo, hi = lim[a]
                xs = np.linspace(lo, hi, 220)
                fa = max(.12, min(.45, 2.4 / max(len(order), 1)))
                rug = []
                for o in order:
                    v = g.loc[lab == o, a].dropna().values
                    if len(v) < 5 or np.std(v) < 1e-9:              # no KDE possible: draw a rug instead of a curve
                        if len(v):
                            rug.append((o, v))
                        continue
                    ys = st.gaussian_kde(v)(xs)
                    A.fill_between(xs, ys, color=col[o], alpha=fa, lw=0)
                    A.plot(xs, ys, color=col[o], lw=.55 * SCALE)
                A.set_xlim(lo, hi)
                A.set_ylim(bottom=0)
                A.set_yticks([])
                if rug:
                    tr = mtransforms.blended_transform_factory(A.transData, A.transAxes)
                    for r, (o, v) in enumerate(rug):
                        A.plot(v, np.full(len(v), .02 + .05 * r), marker="|", ls="none",
                               ms=3.6 * SCALE, mew=.6 * SCALE, color=col[o], transform=tr, clip_on=False)

            elif i > j:                                             # lower triangle: pairwise scatter
                xa, ya = AXES[j], AXES[i]
                for o in order:
                    m = lab == o
                    A.scatter(g.loc[m, xa], g.loc[m, ya], s=3.4 * SCALE, color=col[o], alpha=.85, lw=0)
                A.set_xlim(*lim[xa])
                A.set_ylim(*lim[ya])

            else:                                                   # upper triangle: pooled and within-group Pearson r
                xa, ya = AXES[j], AXES[i]
                m0 = g[[xa, ya]].notna().all(axis=1)
                r, p = st.pearsonr(g.loc[m0, xa], g.loc[m0, ya])
                A.text(.5, .97, f"Corr: {r:.3f}{stars(p)}", ha="center", va="top",
                       fontsize=FS_CORR, color="#333333", transform=A.transAxes)
                rows = []
                for o in order:
                    m = (lab == o) & m0
                    k = int(m.sum())
                    if k < 3:
                        if k:
                            rows.append((o, f"{codes[o]}: n={k}"))
                        continue
                    rr, pp = st.pearsonr(g.loc[m, xa], g.loc[m, ya])
                    rows.append((o, f"{codes[o]}: {rr:.3f}{stars(pp)}" if k >= MIN_N
                                 else f"{codes[o]}: {rr:.3f} (n={k})"))
                # group lines stacked upward from the bottom edge; about half a line below "Corr"
                lead_t, cap = 1.12, .75
                y_bot = 2.0 / cell_h_pt
                fs = grp_fontsize(len(rows), cell_h_pt)
                corr_h = FS_CORR * 1.15 / cell_h_pt
                gap = .5 * fs / cell_h_pt
                top_lim = .97 - corr_h - gap
                k = max(len(rows) - 1, 0)
                fs = min(fs, (top_lim - y_bot) * cell_h_pt / (k * lead_t + cap))
                step = fs * lead_t / cell_h_pt
                y0 = y_bot + step * k
                for o, txt in rows:
                    A.text(.5, y0, txt, ha="center", va="baseline", fontsize=fs,
                           color=readable(col[o]), transform=A.transAxes)
                    y0 -= step
                A.set_xticks([]); A.set_yticks([])
                for s in A.spines.values():
                    s.set_visible(False)

            if i < n and j < n:
                if j != 0 or i == 0:
                    A.set_yticklabels([])
                A.set_xticklabels([])          # x tick labels only on the bottom histogram row

    def leglab(o):
        nn = int((lab == o).sum())
        return f"{codes[o]}  {o} ({nn})" if codes[o] != o else f"{o} ({nn})"

    handles = [Line2D([], [], marker="o", ls="none", ms=3.2 * SCALE, color=col[o], label=leglab(o))
               for o in order]
    avail_pt = (1 - .082 - .02) * fig.get_size_inches()[0] * 72
    col_pt = max(len(leglab(o)) for o in order) * .56 * FS_LEG + 26
    ncol = min(max(1, int(avail_pt // col_pt)), max(1, math.ceil(len(order) / 2)))
    fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(.082, .004), ncol=ncol,
               fontsize=FS_LEG, frameon=False, handletextpad=.4, columnspacing=1.1, labelspacing=.35)
    add_strips(fig, ax, n)
    for i, u in enumerate(UNITS):                  # units on the left margin, one per row
        b = ax[i, 0].get_position()
        fig.text(UNIT_X, (b.y0 + b.y1) / 2, u, ha="center", va="center", rotation=90,
                 fontsize=FS_TITLE * .85, color="black")
    return fig


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    ap.add_argument("--out", default=os.path.join(ROOT, "output", "Fig.6"))
    ap.add_argument("--no-style", action="store_true",
                    help="do not apply style.py (matplotlib default font)")
    a = ap.parse_args()
    formats = ("png", "pdf", "svg")
    if not a.no_style:
        sys.path.insert(0, HERE)
        from style import FORMATS as formats  # noqa: F811 — shared rcParams (Arial, editable SVG text)
    else:
        plt.rcParams["svg.fonttype"] = "none"
    os.makedirs(a.out, exist_ok=True)

    g = pd.read_csv(os.path.join(a.data, "fig6_accession_traits.csv"))
    lab = g["crop_type"]
    order = [o for o in ORDER if (lab == o).any()]
    col = dict(zip(ORDER, PAL))
    codes = dict(zip(g["crop_type"], g["crop_code"]))
    print(f"accessions {len(g)}  types {len(order)}  max |r| between traits "
          f"{np.abs(np.triu(g[AXES].corr().values, 1)).max():.3f}")
    fig = draw(g, lab, order, col, codes)
    for ext in formats:
        fig.savefig(os.path.join(a.out, f"fig6_trait_splom.{ext}"), dpi=400, facecolor="white")
    plt.close(fig)
    print(f"  {a.out}/fig6_trait_splom.{{{','.join(formats)}}}")


if __name__ == "__main__":
    main()
