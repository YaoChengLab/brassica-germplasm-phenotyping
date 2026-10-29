"""stats_fig6.py — the statistics quoted in Section 2.6 for the traits of Fig. 6.

Reads only the two Fig. 6 tables:
  input   <data>/fig6_accession_traits.csv (one row per accession, one point of Fig. 6)
          <data>/fig6_plant_traits.csv     (one row per plant; used for the reference days)
  output  <out>/fig6_stats_summary.csv      accessions, crop types, multi-batch accessions, reference days
          <out>/fig6_stats_correlation.csv  Pearson r for the 15 trait pairs, on the plotted (original) scale
          <out>/fig6_stats_kruskal.csv      Kruskal–Wallis test of each trait across crop types
          <out>/fig6_stats_medians.csv      accessions and the six trait medians per crop type

Definitions, as in Supplementary Methods S9:
  - Pearson r across the 258 accessions, on the original units of Fig. 6 (not log-transformed),
    the same values as printed in the upper triangle of the figure.
  - Kruskal–Wallis H with k crop types (df = k − 1); p_bonferroni = min(1, 6p) for the six traits.
  - Effect size eta2_H = (H − k + 1) / (n − k), n = number of accessions.

Usage:
  python tables/stats_fig6.py                 # default data/ -> output/Fig.6/
  python stats_fig6.py --data DIR --out DIR
"""
import argparse
import itertools
import os

import pandas as pd
from scipy import stats as st

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

TRAITS = ["area_ref", "count_ref", "solidity", "ellipse_aspect_ratio", "excess_green_index", "rgr_slope"]
N_TESTS = len(TRAITS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    ap.add_argument("--out", default=os.path.join(ROOT, "output", "Fig.6"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    g = pd.read_csv(os.path.join(a.data, "fig6_accession_traits.csv"))
    plants = pd.read_csv(os.path.join(a.data, "fig6_plant_traits.csv"))
    if g[TRAITS].isna().any().any():
        raise SystemExit("missing trait values in fig6_accession_traits.csv")
    n, k = len(g), g["crop_type"].nunique()

    ref = plants.groupby("batch")["das_ref"].agg(["min", "max"])
    if (ref["min"] != ref["max"]).any():
        raise SystemExit("das_ref differs within a batch")
    summary = pd.DataFrame([
        ("accessions", n), ("crop_types", k), ("plants", len(plants)),
        ("accessions_in_more_than_one_batch", int((g["n_batches"] > 1).sum())),
        ("reference_day_min_das", int(ref["min"].min())), ("reference_day_max_das", int(ref["max"].max())),
    ], columns=["quantity", "value"])

    corr = []
    for x, y in itertools.combinations(TRAITS, 2):
        r, p = st.pearsonr(g[x], g[y])
        corr.append({"trait_x": x, "trait_y": y, "r": r, "abs_r": abs(r), "p_uncorrected": p})
    corr = pd.DataFrame(corr)

    kw = []
    for t in TRAITS:
        h, p = st.kruskal(*[s[t].to_numpy() for _, s in g.groupby("crop_type")])
        kw.append({"trait": t, "H": h, "df": k - 1, "p": p, "p_bonferroni": min(1.0, N_TESTS * p),
                   "eta2_H": (h - k + 1) / (n - k), "n_accessions": n, "k_crop_types": k})
    kw = pd.DataFrame(kw)

    med = g.groupby(["crop_type", "crop_code"])[TRAITS].median()
    med.insert(0, "n_accessions", g.groupby(["crop_type", "crop_code"]).size())
    med = med.reset_index().sort_values("n_accessions", ascending=False)

    for name, df in (("summary", summary), ("correlation", corr), ("kruskal", kw), ("medians", med)):
        df.to_csv(os.path.join(a.out, f"fig6_stats_{name}.csv"), index=False, lineterminator="\n")
    print(f"accessions {n}  crop types {k}  reference days {summary.value[4]}-{summary.value[5]} DAS")
    print(f"  {a.out}/fig6_stats_{{summary,correlation,kruskal,medians}}.csv")


if __name__ == "__main__":
    main()
