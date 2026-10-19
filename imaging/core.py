"""core.py — leaf-canopy-qc 自包含核心 (vendor-copy 自已驗證的 production 邏輯)。

不 runtime import 任何 whose_leaves_pipe / conf_pilot 腳本。只引用：
  - vendor/ 內複製的 keypoint model toolchain (stage8_*)
  - 外部訓練好的權重檔 (放在 WEIGHTS_DIR，見 *_W 常數)

涵蓋：3 模型 adaptive routing、conf 派生、v8 keypoint ownership、13-hr 軌跡投票、union area。
邏輯與 inference_adaptive.py / run_v8_all_hours.py 等價 (逐函式複製)。
"""
from __future__ import annotations

import math
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import torch

# ---- 路徑：唯一定義在 config.py（環境變數優先，否則取 repo 相對位置）----
from config import CODE_ROOT, QC_ROOT, QC_DATA as DATA_ROOT, QC_DB as SQLITE_PATH, \
    RASPI_ROOT, WEIGHTS_DIR as WEIGHTS  # noqa: E402

# 四個權重放同一個目錄
USER_W = WEIGHTS / "run_v11m_640_s1_v3_best.pt"
BASE_W = WEIGHTS / "genyolo_leaf_yolov11m.pt"
TRAIN31_W = WEIGHTS / "yolov8mseg_train31.pt"
KP_W = WEIGHTS / "stage8_keypoint_v8.pth"

# vendor toolchain on path (modules import each other by bare name)
sys.path.insert(0, str(CODE_ROOT / "vendor"))

# ---- 常數 (= production) ----
CX, CY, R = 300, 300, 150          # adaptive routing circle
NMS_IOU = 0.5
IMGSZ = 640
SPECIAL_CULTIVARS = {"s0074", "s0100", "s0180"}
REF_CIRCLE = (300, 300, 100.0)     # ownership ray-circle
ABSTAIN_THRESH = 0.1               # heatmap_peak_min < this → abstain
MATCH_RADIUS = 30.0                # daily trajectory matching
CANVAS = 600

TS_RE = re.compile(r"(\d{12})")


# ───────── geometry ─────────
def parse_ts(stem: str):
    m = TS_RE.search(stem)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d%H%M")
    except Exception:
        return None


def poly_centroid(p: np.ndarray):
    M = cv2.moments(p.astype(np.float32))
    if M["m00"] == 0:
        return float(p[:, 0].mean()), float(p[:, 1].mean())
    return M["m10"] / M["m00"], M["m01"] / M["m00"]


def in_circle(c) -> bool:
    return (c[0] - CX) ** 2 + (c[1] - CY) ** 2 <= R * R


def poly_mask_iou(p1, p2, sz=CANVAS) -> float:
    m1 = np.zeros((sz, sz), np.uint8); m2 = np.zeros((sz, sz), np.uint8)
    cv2.fillPoly(m1, [p1.astype(np.int32)], 1)
    cv2.fillPoly(m2, [p2.astype(np.int32)], 1)
    inter = int((m1 & m2).sum()); union = int((m1 | m2).sum())
    return inter / union if union else 0.0


def nms_polygons(polys, labels, iou_thr=NMS_IOU, sz=CANVAS):
    if not polys:
        return [], []
    areas = np.array([cv2.contourArea(p.astype(np.float32)) for p in polys])
    order = np.argsort(areas)[::-1]
    keep_p, keep_l, supp = [], [], set()
    for i in order:
        if i in supp:
            continue
        keep_p.append(polys[i]); keep_l.append(labels[i])
        for j in order:
            if j == i or j in supp:
                continue
            if poly_mask_iou(polys[i], polys[j], sz) > iou_thr:
                supp.add(j)
    return keep_p, keep_l


def union_area(polys, sz=CANVAS) -> int:
    if not polys:
        return 0
    m = np.zeros((sz, sz), np.uint8)
    for p in polys:
        cv2.fillPoly(m, [np.asarray(p, np.int32)], 1)
    return int(m.sum())


def get_cultivar_id(path: Path) -> str:
    for part in Path(path).parts:
        if part.startswith("s") and part[1:].isdigit() and len(part) == 5:
            return part
    return ""


# ───────── plant enumeration ─────────
def all_plants(batch: str | None = None):
    """RASPI_ROOT 下的植株目錄 <batch>/<cultivar>/<treatment>/rep-<n> → [(tag, rel)]。"""
    pattern = f"{batch}/s*/*/rep-*" if batch else "20[0-9][0-9]B*/s*/*/rep-*"
    out = []
    for pdir in sorted(RASPI_ROOT.glob(pattern)):
        if pdir.is_dir():
            rel = pdir.relative_to(RASPI_ROOT).as_posix()
            out.append((rel.replace("/", "_"), rel))
    return out


def cultivar_plants(cultivar: str):
    return [(t, r) for t, r in all_plants() if f"/{cultivar}/" in f"/{r}"]


# ───────── YOLO adaptive routing ─────────
def load_yolo_models():
    from ultralytics import YOLO
    for w in (USER_W, BASE_W, TRAIN31_W):
        assert w.exists(), f"missing weight {w}"
    return {"user": YOLO(str(USER_W)), "base": YOLO(str(BASE_W)),
            "train31": YOLO(str(TRAIN31_W))}


def dets_from_result(r, model_name):
    if r.masks is None or r.boxes is None:
        return []
    confs = r.boxes.conf.cpu().numpy()
    out = []
    for i, m in enumerate(r.masks.xy):
        p = np.asarray(m, np.float32)
        if p.shape[0] < 3:
            continue
        out.append({"points": [[round(float(x), 2), round(float(y), 2)] for x, y in p],
                    "conf": round(float(confs[i]), 4), "model": model_name})
    return out


def infer_frame(img, cultivar, models, conf):
    """3 模型 adaptive 的 raw dets (pre-routing；含 model 標記與 conf)。"""
    if cultivar in SPECIAL_CULTIVARS:
        r = models["train31"](img, conf=conf, imgsz=IMGSZ, verbose=False)[0]
        return dets_from_result(r, "TRAIN31")
    ru = models["user"](img, conf=conf, imgsz=IMGSZ, verbose=False)[0]
    rb = models["base"](img, conf=conf, imgsz=IMGSZ, verbose=False)[0]
    return dets_from_result(ru, "USER") + dets_from_result(rb, "BASE")


def derive_version(dets, conf_thr, cultivar):
    """忠實重現 adaptive_route：conf 過濾各模型 → in/out-circle routing → NMS。"""
    arrs = [(np.asarray(d["points"], np.float32), d["conf"], d["model"]) for d in dets]
    if cultivar in SPECIAL_CULTIVARS:
        return [(p, "TRAIN31") for p, c, m in arrs if m == "TRAIN31" and c >= conf_thr]
    sel_p, sel_l = [], []
    for p, c, m in arrs:
        if c < conf_thr:
            continue
        cen = poly_centroid(p)
        if m == "USER" and in_circle(cen):
            sel_p.append(p); sel_l.append("USER")
        elif m == "BASE" and not in_circle(cen):
            sel_p.append(p); sel_l.append("BASE")
    kp, kl = nms_polygons(sel_p, sel_l)
    return list(zip(kp, kl))


# ───────── v8 keypoint ownership ─────────
from stage8_keypoint_v5 import (          # noqa: E402  (vendored)
    PAD_FIXED, coords_crop_to_full, compute_crop_bbox_v5, dynamic_resize,
)
from stage8_keypoint_poc import CROP_SIZE, IMAGENET_MEAN, IMAGENET_STD   # noqa: E402
from stage8_keypoint_v6_heatmap import KeypointHeatmapModel, soft_argmax  # noqa: E402
from stage8_keypoint_v7_dt import render_polygon_distance_transform       # noqa: E402


def load_keypoint_model(device):
    assert KP_W.exists(), f"missing keypoint weight {KP_W}"
    ckpt = torch.load(str(KP_W), map_location=device, weights_only=False)
    model = KeypointHeatmapModel(num_keypoints=2, in_channels=4, freeze_stages=2).to(device)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model


def _preprocess(crop_bgr, dt_256):
    rgb = dynamic_resize(crop_bgr, CROP_SIZE)
    rgb_f = cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    rgb_f = (rgb_f - IMAGENET_MEAN) / IMAGENET_STD
    t = np.concatenate([rgb_f.transpose(2, 0, 1), dt_256[None, :, :]], axis=0).astype(np.float32)
    return torch.from_numpy(t).unsqueeze(0)


def run_keypoint(model, device, img_bgr, poly):
    bbox = compute_crop_bbox_v5(img_bgr.shape[:2], poly, pad_ratio=PAD_FIXED)
    x0, y0, x1, y1 = bbox
    if x1 - x0 < 10 or y1 - y0 < 10:
        return None
    crop = img_bgr[y0:y1, x0:x1]
    poly_local = poly - np.array([x0, y0])
    dt_256 = render_polygon_distance_transform(poly_local, crop.shape[:2], CROP_SIZE)
    tensor = _preprocess(crop, dt_256).to(device)
    with torch.no_grad():
        pred_hm = model(tensor)
        peak = pred_hm.amax(dim=(2, 3))[0].cpu().numpy()
        coord = soft_argmax(pred_hm)[0].cpu().numpy()
    base_full = coords_crop_to_full(coord[0], bbox)
    tip_full = coords_crop_to_full(coord[1], bbox)
    return {"tip": tuple(map(float, tip_full)), "base": tuple(map(float, base_full)),
            "heatmap_peak_min": float(min(peak))}


def ray_through_circle(tip, base, circle=REF_CIRCLE) -> bool:
    cx, cy, r = circle
    x1, y1 = float(tip[0]), float(tip[1]); x2, y2 = float(base[0]), float(base[1])
    dx, dy = x2 - x1, y2 - y1
    n2 = dx * dx + dy * dy
    if n2 < 1e-6:
        return False
    t = ((cx - x1) * dx + (cy - y1) * dy) / n2
    return (math.hypot(x1 + t * dx - cx, y1 + t * dy - cy) <= r) and (t > 0)


def build_trajectories(recs, match_radius=MATCH_RADIUS):
    """Greedy nearest-centroid matching across hours within one day (= production)."""
    by_hour = defaultdict(list)
    for i, r in enumerate(recs):
        by_hour[r["hour"]].append(i)
    hours = sorted(by_hour)
    if not hours:
        return []
    trajs = [[i] for i in by_hour[hours[0]]]
    last = {tid: (recs[ids[0]]["cx"], recs[ids[0]]["cy"]) for tid, ids in enumerate(trajs)}
    for h in hours[1:]:
        cand = by_hour[h][:]; used = set()
        for tid, traj in enumerate(trajs):
            lcx, lcy = last[tid]; best_i, best_d = -1, match_radius
            for ci in cand:
                if ci in used:
                    continue
                d = math.hypot(recs[ci]["cx"] - lcx, recs[ci]["cy"] - lcy)
                if d < best_d:
                    best_d, best_i = d, ci
            if best_i >= 0:
                traj.append(best_i); used.add(best_i)
                last[tid] = (recs[best_i]["cx"], recs[best_i]["cy"])
        for ci in cand:
            if ci not in used:
                trajs.append([ci]); last[len(trajs) - 1] = (recs[ci]["cx"], recs[ci]["cy"])
    return trajs


def vote_daily_decision(traj_recs):
    """(decision True/False/None, n_pass, n_total). 非 abstain 幀多數決。"""
    voting = [r for r in traj_recs if not r["abstain"]]
    n = len(voting)
    if n == 0:
        return None, 0, 0
    n_pass = sum(1 for r in voting if r["passes"])
    return (n_pass > n / 2), n_pass, n
