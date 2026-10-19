"""traits.py — 批次 QC-aware 2D 性狀提取引擎 (管線整合 S2, 路 B)。

角色：把 qc_delta_prototype 的單株原型升級為「可吃 batch_code 的批跑 production 引擎」，
產出對齊 DB trait_observations 的 staging CSV（只算 QC ownership、不寫 DB）。

設計要點（見 vault [[表型影像管線整合重構規劃]] 2026-07-13 節）：
  - 純 CPU：柵格化既有 frames.json polygon，不跑 YOLO、不重裁（適用「既有已 QC 批次重灌」）。
  - ownership = effective_keep（qc.sqlite override 有則用，否則 frames.json keep = M2 fallback）。
  - leaf_count = len(effective 選中葉)（修正原型 union-mask connected-component 的葉數 bug）。
  - 輸出 = per-frame 列：business key（partial，treatment 留 S3 由 DB 解析）+ provenance
           + DB trait_observations 的全 trait 欄（COLUMN_MAP 對齊，單一真相源）。
  - 只產 staging CSV 落 out/（gitignore）；per-batch upsert 進 DB 是 S3。

用法：
  conda run -n pheno python -m traits_2d.traits --batch 2025B08 [--limit-plants N] [--limit-frames N]
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

# ---- 常數 ----
RASPI = Path(RASPI_ROOT)           # 乾淨 crop 正本（core.py 同源）
CANVAS = 600
MIN_AREA = 3                       # 與 qc_delta_prototype / b08_full_trait_extract 一致的 contour 門檻
PIPELINE_VERSION = "traits_2d@2026-07-13"
TS_RE = re.compile(r"(\d{12})")

# ---- business key / provenance 欄（staging 前綴）----
KEY_COLS = [
    "batch_code", "cultivar_code", "replicate_code", "plant_type",   # business key（缺 treatment_code）
    "sensor_code", "observation_timestamp", "day_after_sewing",       # 定位 / 對應
]
PROV_COLS = ["qc_status", "pipeline_version", "run_at", "old_plant_id", "frame_stem"]

# ---- DB trait_observations 的 trait 欄（扣掉 id/plant_id/sensor_id/
#      observation_timestamp/day_after_sewing/image_file 這 6 個 key 欄與 4 個
#      provenance 欄；順序即 DB 順序）----
#      mer_angle（原 Morph #23，方向角旋轉相依=非穩定性狀）已於 2026-07-27 移除，
#      對齊抽取器與 registry；DB 欄位本身尚未 DROP，drift-guard 會列為
#      「DB 有、worker 未填」的 deprecated 欄，不影響 upsert。
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

# ---- COLUMN_MAP（extractor 輸出名 → DB 欄）D4 對照，單一真相源 ----
# 由實跑 extractor dump 校準（2026-07-13）：extractor 實際輸出 104 key，其中僅
# boundary_method 非 DB 欄被丟；DB 107 trait 欄有 5 欄非 extractor 直出，分三類處理：
COMPUTED_COLS = {"leaf_count"}           # 本引擎算 effective 選中葉數，extractor 不產
ALIAS_COLS = {"leaf_area": "area_pixels"}  # extractor 不產 leaf_area；舊 DB leaf_area==area_pixels，
                                           # 且消費端 batch_correction_service 讀 leaf_area → 以 area_pixels 填
NULL_COLS: set = set()                   # 目前沒有「DB 有欄但 extractor 不產」的欄位
# 2026-08-17 兩支 migration 把這一類欄位清乾淨了，故本集合為空：
#   012  compactness／roundness／gap_fraction_canopy_porosity（343,809 列全 NULL）
#   013  max_／mean_／median_radius_from_centroid（抽取器 2026-07-07 起不產；
#        僅 20 列有值且全在 qc_status='no' 的 legacy 髒列）
# 若日後又出現「DB 有欄、extractor 不產」的欄位，加回這裡即可。
# 其餘 DB trait 欄一律以「同名」向 extractor 取值（1:1）。


def load_overrides(key: str) -> dict:
    """qc.sqlite leaf_override：{tid: state(1 keep / 0 reject)}，key = underscore business key
    （Phase 2 re-key 後 qc.sqlite 的 plant_id，見 rekey/apply_rekey.py）。"""
    c = sqlite3.connect(QC_DB)
    try:
        return {tid: state for tid, state in
                c.execute("SELECT tid,state FROM leaf_override WHERE plant_id=?", (key,))}
    except sqlite3.OperationalError:
        return {}       # no review yet: qc.sqlite has no leaf_override table
    finally:
        c.close()


def is_reviewed(key: str) -> bool:
    """plant-level 人工審查證據 → qc_status。key = underscore business key。無證據 / 查詢失敗回 False。"""
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
    """呼叫 vendored extractor 三 group，回傳 {trait_name: float}。空 mask 回 {}。"""
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
    """把 extractor 原始輸出 + 算得的 leaf_count → 對齊 DB_TRAIT_COLS（COLUMN_MAP）。
    缺值 / NULL_COLS → ''（CSV 空 = SQL NULL）。"""
    out = {}
    for col in DB_TRAIT_COLS:
        if col in COMPUTED_COLS:          # leaf_count
            out[col] = n_leaves
            continue
        if col in NULL_COLS:
            out[col] = ""
            continue
        src = ALIAS_COLS.get(col, col)    # leaf_area → area_pixels，其餘同名
        v = raw.get(src, "")
        out[col] = "" if v == "" or (isinstance(v, float) and not np.isfinite(v)) else v
    return out


def parse_rel(rel: str):
    """rel = '2025B08/s0128/Control/rep-1' → (batch, cultivar, treatment, rep)。
    Phase 3 rename 後結構 = <batch>/<cultivar>/<treatment>/rep-<n>。"""
    parts = rel.split("/")
    if len(parts) < 4:
        return "", "", "", ""
    m = re.search(r"rep-(\d+)", parts[3])
    return parts[0], parts[1], parts[2], (m.group(1) if m else "")


def business_key(rel: str) -> str:
    """underscore business key ＝ qc.sqlite re-key 後的 plant_id（見 rekey/apply_rekey.py）。"""
    b, c, t, rep = parse_rel(rel)
    return f"{b}_{c}_{t}_{rep}"


def parse_business_key(rel: str) -> dict:
    """rel → staging key 欄。treatment 已在路徑但不進 staging（S3 由 DB join 補，單 treatment 唯一）；
    sensor_code / old_plant_id 已不在路徑 → 留空（純 provenance，sensor 由 resolver 查 DB chamberhistory）。"""
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
    bkey = business_key(rel)                    # qc.sqlite 查找鍵（re-key 後 = underscore business key）
    ov = load_overrides(bkey)
    key = parse_business_key(rel)
    # 3 態 qc_status（見 vault §2026-07-13(g)）：本引擎只產 verified/auto；
    # `no` 保留給未經本引擎的舊 pre-QC 列（遷移時標記）。
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
        raw = extract_raw_traits(img, build_mask(eff))   # 空 mask (n_leaves=0) → {}
        row = dict(key)
        row["observation_timestamp"] = ts_to_timestamp(stem)
        # daf = 首圖後天數（curves 內部用），≠ DAS；此欄僅佔位，
        # 真正的 day_after_sewing 由 ingest/load.py 以 DB 播種日覆蓋計算。
        row["day_after_sewing"] = fr.get("daf", "")
        row["qc_status"] = qc_status
        row["pipeline_version"] = PIPELINE_VERSION
        row["run_at"] = run_at
        row["frame_stem"] = stem
        row.update(to_db_row(raw, n_leaves))
        rows.append(row)
    return rows


def find_plants(batch: str) -> list[str]:
    """回傳 batch 下所有 plant 的 rel（相對 QC_DATA）。batch 須為 canonical 批號（2025B08）。"""
    root = Path(QC_DATA)
    bdir = root / require_batch_code(batch)
    if not bdir.is_dir():
        return []
    rels = []
    for fj in sorted(bdir.glob("*/*/rep-*/frames.json")):   # <cultivar>/<treatment>/rep-<n>/
        rels.append(str(fj.parent.relative_to(root)))
    return rels


def run(batch: str, limit_plants=None, limit_frames=None):
    batch = require_batch_code(batch)      # staging 檔名以此為 key，須與 ingest 端同形
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
    ap.add_argument("--batch", required=True, help="完整批號，如 2025B08（不接受短名 B08）")
    ap.add_argument("--limit-plants", type=int)
    ap.add_argument("--limit-frames", type=int)
    a = ap.parse_args()
    try:
        batch = require_batch_code(a.batch)
    except ValueError as e:
        ap.error(str(e))
    run(batch, a.limit_plants, a.limit_frames)
