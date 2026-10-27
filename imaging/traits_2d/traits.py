"""traits.py — batch 2D trait extraction that applies the leaf-to-plant assignment and review decisions.

Writes a staging CSV whose columns match the database table trait_observations; it does not
write to the database (platform/ingest/load.py does).

  - CPU only: rasterises the leaf polygons in the existing frames.json; it does not run the
    segmentation models or re-crop the images.
  - Assignment = effective_keep: the review decision in qc.sqlite where one exists, otherwise
    the automatic keep decision in frames.json.
  - leaf_count = number of retained leaves (not connected components of the union mask, which
    merges touching leaves).
  - Output: one row per image with the plant key (treatment is resolved from the database at
    load time), provenance columns and every trait column of trait_observations (COLUMN_MAP
    below is the single mapping).
  - The staging CSV goes to out/ (not tracked by git).

Usage (from the repository root):
  python imaging/traits_2d/traits.py --batch 2025B08 [--limit-plants N] [--limit-frames N]
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import QC_DB, QC_DATA, OUT, RASPI_ROOT, require_batch_code  # noqa: E402
from traits_2d.extractor_2d import PlantTraitExtractor2D as E  # noqa: E402

# ---- Constants ----
RASPI = Path(RASPI_ROOT)           # single-plant images (same root as core.py)
CANVAS = 600
MIN_AREA = 3                       # minimum contour area passed to the extractor
PIPELINE_VERSION = "traits_2d@2026-07-13"
TS_RE = re.compile(r"(\d{12})")

# ---- Plant key and provenance columns (staging prefix) ----
KEY_COLS = [
    "batch_code", "cultivar_code", "replicate_code", "plant_type",   # plant key (without treatment_code)
    "sensor_code", "observation_timestamp", "day_after_sewing",       # position and time
]
PROV_COLS = ["qc_status", "pipeline_version", "run_at", "old_plant_id", "frame_stem"]

# ---- Trait columns of trait_observations (excluding the 6 key columns id, plant_id,
#      sensor_id, observation_timestamp, day_after_sewing, image_file and the 4 provenance
#      columns; listed in table order) ----
#      mer_angle (orientation angle, which depends on how the plant is rotated, so not a
#      stable trait) is no longer produced. The database column still exists and stays empty.
DB_TRAIT_COLS = [
    "leaf_count", "leaf_area", "area_pixels", "bounding_box_area", "perimeter_pixels",
    "convex_hull_area_pixels", "convex_hull_perimeter", "extent", "plant_height", "plant_width",
    "equivalent_diameter", "eccentricity", "radial_symmetry",
    "solidity", "circularity_1", "circularity_2", "canopy_porosity", "eccentricity_eigenvalue_ratio",
    "sift_keypoint_count", "multiscale_straightness", "combined_simple_connectivity",
    "fuzzy_rectangularity", "major_axis_length", "minor_axis_length", "ellipse_aspect_ratio",
    "ellipse_center_x", "ellipse_center_y", "ellipse_angle_degrees",
    "min_radius_from_centroid", "std_radius_from_centroid",
    "red_channel", "green_channel", "blue_channel", "red_green_ratio", "blue_green_ratio",
    "blue_red_ratio", "excess_green_index", "excess_green_minus_red", "excess_red_index",
    "green_index", "green_leaf_index", "green_difference", "green_difference_variant", "greenness",
    "hue", "saturation", "lightness", "chroma", "chroma_prime",
    "anthocyanin_chroma_basic", "anthocyanin_chroma_difference", "anthocyanin_chroma_ratio",
    "brightness", "cive", "dgci", "mgrvi", "ndyi", "ngrdi", "rgbvi", "triangular_greenness_index",
    "vari", "veg", "vegetation_index_2", "strength_of_red", "strength_of_green", "strength_of_blue",
    "skewness_r", "skewness_g", "skewness_b", "skewness_y",
    "kurtosis_r", "kurtosis_g", "kurtosis_b", "kurtosis_y",
    "colour_distribution_modes", "spectral_distribution_modes", "num_unique_colours", "pixel_entropy",
    "glcm_asm", "glcm_autocorrelation", "glcm_cluster_prominence", "glcm_cluster_shade",
    "glcm_contrast", "glcm_correlation", "glcm_difference_entropy", "glcm_difference_variance",
    "glcm_dissimilarity", "glcm_entropy", "glcm_idm", "glcm_idmn", "glcm_idn", "glcm_imc1",
    "glcm_imc2", "glcm_inverse_difference", "glcm_max_probability", "glcm_mcc", "glcm_ssv",
    "glcm_sum_average", "glcm_sum_entropy", "glcm_sum_variance",
    "hog_mean", "hog_std", "log_mean", "log_std",
]

# ---- COLUMN_MAP (extractor output name -> database column), the single mapping ----
# Of the extractor's output keys only boundary_method has no database column and is dropped.
# Database trait columns not produced directly by the extractor fall into three groups:
COMPUTED_COLS = {"leaf_count"}           # number of retained leaves, computed here
ALIAS_COLS = {"leaf_area": "area_pixels"}  # the extractor has no leaf_area; leaf_area holds the
                                           # same value as area_pixels
NULL_COLS: set = set()                   # database columns the extractor does not produce (none at present)
# Add a column here if the table ever gains one the extractor does not produce.
# Every other trait column takes the extractor value of the same name.


def load_overrides(key: str) -> dict:
    """leaf_override rows of qc.sqlite as {tid: state (1 keep / 0 reject)};
    key = batch_cultivar_treatment_rep, the plant_id used in qc.sqlite."""
    c = sqlite3.connect(QC_DB)
    try:
        return {tid: state for tid, state in
                c.execute("SELECT tid,state FROM leaf_override WHERE plant_id=?", (key,))}
    except sqlite3.OperationalError:
        return {}       # no review yet: qc.sqlite has no leaf_override table
    finally:
        c.close()


def is_reviewed(key: str) -> bool:
    """Whether the plant has been marked reviewed (sets qc_status). False if not, or if the lookup fails."""
    try:
        c = sqlite3.connect(QC_DB)
        try:
            r = c.execute("SELECT 1 FROM reviewed WHERE plant_id=? LIMIT 1", (key,)).fetchone()
            return r is not None
        finally:
            c.close()
    except Exception:
        return False


def effective_keep(leaf: dict, ov: dict) -> bool:
    tid = leaf.get("tid")
    if tid in ov:
        return ov[tid] == 1
    return bool(leaf.get("keep"))


def build_mask(leaves) -> np.ndarray:
    m = np.zeros((CANVAS, CANVAS), np.uint8)
    for lv in leaves:
        p = np.asarray(lv["points"], np.int32)
        if len(p) >= 3:
            cv2.fillPoly(m, [p], 1)
    return m


def extract_raw_traits(img: np.ndarray, mask: np.ndarray) -> dict:
    """Run the three extractor groups and return {trait_name: float}; {} for an empty mask."""
    if mask.sum() == 0:
        return {}
    cnts, _ = cv2.findContours((mask > 0).astype(np.uint8),
                               cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = [c for c in cnts if cv2.contourArea(c) >= MIN_AREA]
    t = {}
    if cnts:
        t.update(E.extract_morphological(img, mask, cnts))
    t.update(E.extract_color(img, mask))
    t.update(E.extract_texture(img, mask))
    return {k: float(v) for k, v in t.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)}


def to_db_row(raw: dict, n_leaves: int) -> dict:
    """Extractor output plus the computed leaf_count -> DB_TRAIT_COLS (via COLUMN_MAP).
    Missing values and NULL_COLS -> '' (an empty CSV cell loads as SQL NULL)."""
    out = {}
    for col in DB_TRAIT_COLS:
        if col in COMPUTED_COLS:          # leaf_count
            out[col] = n_leaves
            continue
        if col in NULL_COLS:
            out[col] = ""
            continue
        src = ALIAS_COLS.get(col, col)    # leaf_area -> area_pixels, otherwise the same name
        v = raw.get(src, "")
        out[col] = "" if v == "" or (isinstance(v, float) and not np.isfinite(v)) else v
    return out


def parse_rel(rel: str):
    """rel = '2025B08/s0128/Control/rep-1' -> (batch, cultivar, treatment, rep).
    Layout: <batch>/<cultivar>/<treatment>/rep-<n>."""
    parts = rel.split("/")
    if len(parts) < 4:
        return "", "", "", ""
    m = re.search(r"rep-(\d+)", parts[3])
    return parts[0], parts[1], parts[2], (m.group(1) if m else "")


def business_key(rel: str) -> str:
    """Plant key batch_cultivar_treatment_rep, the plant_id used in qc.sqlite."""
    b, c, t, rep = parse_rel(rel)
    return f"{b}_{c}_{t}_{rep}"


def parse_business_key(rel: str) -> dict:
    """rel -> staging key columns. Treatment is in the path but not written: the loader resolves it
    from the database. sensor_code and old_plant_id stay empty; the loader finds the camera from
    the plant's position record."""
    b, c, _t, rep = parse_rel(rel)
    return {
        "batch_code": b,
        "cultivar_code": c,
        "replicate_code": rep,
        "plant_type": "observation_individual",
        "sensor_code": "",
        "old_plant_id": "",
    }


def ts_to_timestamp(stem: str):
    m = TS_RE.search(stem)
    if not m:
        return ""
    s = m.group(1)  # YYYYMMDDHHMM
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}:00"


def process_plant(rel: str, limit_frames=None) -> list[dict]:
    fj = json.load(open(f"{QC_DATA}/{rel}/frames.json"))
    bkey = business_key(rel)                    # lookup key in qc.sqlite
    ov = load_overrides(bkey)
    key = parse_business_key(rel)
    # qc_status has three values; this step writes only verified or auto.
    # `no` marks older rows that were not produced by this step.
    qc_status = "verified" if is_reviewed(bkey) else "auto"
    run_at = datetime.now().isoformat(timespec="seconds")

    frames = [f for f in fj.get("frames", []) if f.get("leaves")]
    if limit_frames:
        frames = frames[:limit_frames]

    rows = []
    for fr in frames:
        stem = fr["stem"]
        png = RASPI / rel / f"{stem}.png"
        if not png.exists():
            continue
        img = cv2.imread(str(png))
        if img is None:
            continue
        eff = [lv for lv in fr["leaves"] if effective_keep(lv, ov)]
        n_leaves = len(eff)
        raw = extract_raw_traits(img, build_mask(eff))   # empty mask (n_leaves=0) -> {}
        row = dict(key)
        row["observation_timestamp"] = ts_to_timestamp(stem)
        # daf = days since the plant's first image (used by the curves), not days after sowing;
        # this is a placeholder, and ingest/load.py computes day_after_sewing from the sowing date.
        row["day_after_sewing"] = fr.get("daf", "")
        row["qc_status"] = qc_status
        row["pipeline_version"] = PIPELINE_VERSION
        row["run_at"] = run_at
        row["frame_stem"] = stem
        row.update(to_db_row(raw, n_leaves))
        rows.append(row)
    return rows


def find_plants(batch: str) -> list[str]:
    """rel paths (relative to QC_DATA) of all plants in a batch; batch must be a full code (2025B08)."""
    root = Path(QC_DATA)
    bdir = root / require_batch_code(batch)
    if not bdir.is_dir():
        return []
    rels = []
    for fj in sorted(bdir.glob("*/*/rep-*/frames.json")):   # <cultivar>/<treatment>/rep-<n>/
        rels.append(str(fj.parent.relative_to(root)))
    return rels


def run(batch: str, limit_plants=None, limit_frames=None):
    batch = require_batch_code(batch)      # the staging file name is keyed on it, as in the loader
    plants = find_plants(batch)
    if limit_plants:
        plants = plants[:limit_plants]
    if not plants:
        print(f"[traits] no plants found for batch '{batch}' under {QC_DATA}")
        return
    print(f"[traits] batch {batch}: {len(plants)} plants")

    fields = KEY_COLS + PROV_COLS + DB_TRAIT_COLS

    Path(OUT).mkdir(parents=True, exist_ok=True)
    outp = Path(OUT) / f"staging_traits_{batch}.csv"
    n_rows = 0
    with open(outp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, restval="")
        w.writeheader()
        for i, rel in enumerate(plants, 1):
            try:
                rows = process_plant(rel, limit_frames)
            except Exception as e:
                print(f"  [warn] plant {rel} failed: {e}")
                continue
            w.writerows(rows)
            n_rows += len(rows)
            if i % 10 == 0 or i == len(plants):
                print(f"  {i}/{len(plants)} plants  {n_rows} rows")
    print(f"[traits] wrote {n_rows} rows x {len(fields)} cols -> {outp}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True, help="full batch code, e.g. 2025B08 (not B08)")
    ap.add_argument("--limit-plants", type=int)
    ap.add_argument("--limit-frames", type=int)
    a = ap.parse_args()
    try:
        batch = require_batch_code(a.batch)
    except ValueError as e:
        ap.error(str(e))
    run(batch, a.limit_plants, a.limit_frames)
