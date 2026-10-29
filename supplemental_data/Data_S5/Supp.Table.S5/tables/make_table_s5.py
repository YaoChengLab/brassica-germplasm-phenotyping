"""make_table_s5.py — Table S5: test-set performance of the segmentation and keypoint models.

Reads only the bundled data/ folder:
  detection_test.json               in-house YOLO11m-seg on the test split (618 images)
  keypoint_v8_eval_per_leaf.csv     per-leaf evaluation of the base/tip keypoint model;
                                    the test set is the rows with role == "holdout" (73 leaves)
Writes <out>/table_s5.md (Markdown table) and <out>/table_s5.json (table layout).

Endpoint error = err_mean_aligned (mean base/tip distance under the better of the two
matchings, Equations 1-3); swap = was_swapped (Equation 4).
"""
import argparse
import csv
import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)            # analysis folder
_ap = argparse.ArgumentParser()
_ap.add_argument("--data", default=os.path.join(ROOT, "data"))
_ap.add_argument("--out", default=os.path.join(ROOT, "output", "Supp.Table.S5"))
_a = _ap.parse_args()
DATA, OUT = _a.data, _a.out

det = json.load(open(os.path.join(DATA, "detection_test.json"), encoding="utf-8"))
kp = [r for r in csv.DictReader(open(os.path.join(DATA, "keypoint_v8_eval_per_leaf.csv"), encoding="utf-8"))
      if r["role"] == "holdout"]
err = statistics.median(float(r["err_mean_aligned"]) for r in kp)
swap = sum(r["was_swapped"] == "True" for r in kp) / len(kp)
m = det["mask"]

rows = [
    ("Leaf segmentation (in-house YOLO11m-seg)",
     f"{det['images']} single-plant images, {det['instances']:,} leaf polygons", "Mask precision", f"{m['precision']:.3f}"),
    ("", "", "Mask recall", f"{m['recall']:.3f}"),
    ("", "", "Mask mAP50", f"{m['mAP50']:.3f}"),
    ("", "", "Mask mAP50–95", f"{m['mAP50_95']:.3f}"),
    ("Base/tip keypoints (ResNet-18)", f"{len(kp)} leaves", "Median endpoint error (px)", f"{err:.1f}"),
    ("", "", "Base–tip swap rate (%)", f"{100 * swap:.1f}"),
]
HEAD = ["Model", "Test set", "Metric", "Value"]
lines = ["| " + " | ".join(HEAD) + " |", "|---|---|---|---|"]
lines += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows]
os.makedirs(OUT, exist_ok=True)
open(os.path.join(OUT, "table_s5.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
# table layout: an empty cell is merged with the cell above (Model and Test set columns)
spec = {"label": "Table S5", "caption_block": "table_s5",
        "columns": [{"name": h, "width_cm": w, "align": a} for h, w, a in
                    zip(HEAD, (3.9, 4.15, 4.4, 2.2), ("left", "left", "left", "right"))],
        # the rows of each model form one block, separated by a thin rule
        "rows": [{"kind": "body", "block": "seg" if i < 4 else "kp",
                  "cells": [c if c != "" else None for c in r]} for i, r in enumerate(rows)]}
json.dump(spec, open(os.path.join(OUT, "table_s5.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n".join(lines))
