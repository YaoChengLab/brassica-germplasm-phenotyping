"""make_table1_s6.py — Table S6, and its subset Table 1: automatic leaf assignment against manual review, two batches.

Reads only the bundled data/ folder:
  ownership_twobatch_summary.csv        per-batch counts, ratios and per-image detection counts
  ownership_twobatch_by_accession.csv   per-accession counts (ranges of agreement and the two disagreement rates)
  ownership_twobatch_cotyledon.csv      pooled false-reject rates, cotyledon vs true leaf
Writes <out>/table1_s6.md (Markdown table) and <out>/table1_s6.json (table layout).
Table 1 in the main text reports a subset of these rows.

The four counts are not repeated here; Figure S2a shows them as bars.
"""
import argparse
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)            # analysis folder
_ap = argparse.ArgumentParser()
_ap.add_argument("--data", default=os.path.join(ROOT, "data"))
_ap.add_argument("--out", default=os.path.join(ROOT, "output", "Table.1"))
_a = _ap.parse_args()
DATA, OUT = _a.data, _a.out
BATCHES = ("2025B08", "2025B09")


def read(name):
    return list(csv.DictReader(open(os.path.join(DATA, name), encoding="utf-8")))


summ = {r["batch"]: r for r in read("ownership_twobatch_summary.csv")}
acc = read("ownership_twobatch_by_accession.csv")
cot = {(r["batch"], r["class"]): r for r in read("ownership_twobatch_cotyledon.csv") if r["cultivar"] == "pooled"}


def f(b, k, nd):
    return f"{float(summ[b][k]):.{nd}f}"


def pooled(k):         # agreement / false_reject_rate / false_keep_rate (precomputed, 0–1) -> %
    return lambda b: f"{100 * float(summ[b][k]):.1f}"


def rng(b, k):
    v = [100 * float(r[k]) for r in acc if r["batch"] == b]
    return f"{min(v):.1f}–{max(v):.1f}"


def per_image(which):
    return lambda b: f"{float(summ[b][f'detections_per_image_{which}']):.2f}"


def cotyledon(klass):
    return lambda b: f"{100 * float(cot[(b, klass)]['false_reject_rate']):.1f}"


def images_per_day(which):
    return lambda b: f"{float(summ[b][f'median_images_per_day_{which}']):g}"


def header(b):      # group heading row: value cells are left empty
    return ""


# One value per cell. Each row is (label, value function, kind, block):
#   kind: body = ordinary row, group = heading row (empty value cells), sub = indented sub-row
#   block: content section (sample, detections, agreement, review, accessions, cotyledons);
#   sections are separated by a rule in the table layout.
# Only Plants / accessions holds two values in one cell.
rows = [
    ("Plants / accessions", lambda b: f"{summ[b]['plants']} / {summ[b]['accessions']}", "body", "sample"),
    ("Leaf-day trajectories", lambda b: f"{int(summ[b]['n']):,}", "body", "sample"),
    ("Detections per image (mean)", header, "group", "det"),
    ("Before ownership assignment", per_image("raw"), "sub", "det"),
    ("After automatic ownership", per_image("auto"), "sub", "det"),
    ("After manual review", per_image("reviewed"), "sub", "det"),
    ("Detections removed by automatic ownership (%)", lambda b: f(b, "removed_by_ownership_pct", 1), "body", "det"),
    ("Agreement (%)", lambda b: f"{100 * float(summ[b]['agreement']):.2f}", "body", "agree"),
    # disagreement rates in both directions; denominators are review decisions, as in Figure S2a
    ("False-reject rate (%)", pooled("false_reject_rate"), "body", "agree"),
    ("False-keep rate (%)", pooled("false_keep_rate"), "body", "agree"),
    ("Images per day of a trajectory (median)", header, "group", "review"),
    ("Changed in manual review", images_per_day("changed"), "sub", "review"),
    ("Left unchanged", images_per_day("unchanged"), "sub", "review"),
    ("Per-accession agreement (%, range)", lambda b: rng(b, "agreement"), "body", "acc"),
    ("Per-accession false-reject rate (%, range)", lambda b: rng(b, "false_reject_rate"), "body", "acc"),
    ("Per-accession false-keep rate (%, range)", lambda b: rng(b, "false_keep_rate"), "body", "acc"),
    ("False-reject rate on plant-days with cotyledons (%)", header, "group", "frr"),
    ("Cotyledons", cotyledon("cotyledon"), "sub", "frr"),
    ("True leaves", cotyledon("true_leaf"), "sub", "frr"),
]
lines = ["| | " + " | ".join(BATCHES) + " |", "|---|" + "---|" * len(BATCHES)]
lines += [f"| {label} | " + " | ".join(fn(b) for b in BATCHES) + " |" for label, fn, _, _ in rows]
os.makedirs(OUT, exist_ok=True)
open(os.path.join(OUT, "table1_s6.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
spec = {"label": "Table S6", "caption_block": "table1_s6",
        "columns": [{"name": "", "width_cm": 7.65, "align": "left"}] +
                   [{"name": b, "width_cm": 3.5, "align": "center"} for b in BATCHES],
        "rows": [{"kind": kind, "block": block, "cells": [label] + [fn(b) for b in BATCHES]}
                 for label, fn, kind, block in rows]}
json.dump(spec, open(os.path.join(OUT, "table1_s6.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n".join(lines))
