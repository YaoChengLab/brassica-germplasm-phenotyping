"""build.py — Phase 0: 對 raspi_RGB 植株跑 adaptive(conf) + v8 ownership，匯出 GUI 資料。

每株一次 pass：
  per frame: adaptive infer @ conf → derive routed polys → 每 poly 跑 v8 keypoint
             → abstain(peak<0.1) + passes(ray-circle)
  per day:   build_trajectories → vote_daily_decision → 指派 tid=「date#idx」、標 keep
  匯出 data/{rel}/:
    frames.json  每幀 leaves[{tid, points, base, tip, keep}]  (GUI 可點 + 重算用快取)
    curves.json  每日 {raw_count, raw_area, keep_count, keep_area, daf}  (before=raw, after-auto=keep)

frames.json 已含 base/tip/keep → 之後改 voting 參數或人工 override 都不必重跑 keypoint。

輸入 RASPI_ROOT/<batch>/<cultivar>/<treatment>/rep-<n>/*.png，輸出 QC_ROOT/data/ 下同一組四層路徑；
路徑解析見 core.py。植株目錄沒有影像、或沒有任何檔名帶時間戳的影像時中止報錯。

Usage (env=yolo):
  python imaging/build.py --batch 2025B08
  python imaging/build.py --batch 2025B08 --cultivar s0123
  python imaging/build.py --all
  python imaging/build.py --cultivar s0001 --limit-plants 1 --limit-frames 30   # smoke
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2
import torch

import core as C


def process_plant(rel, models, kp_model, device, conf, limit_frames=None):
    src = C.RASPI_ROOT / rel
    cultivar = C.get_cultivar_id(src / "x.png")
    pngs = sorted(src.glob("*.png"))
    if not pngs:
        raise FileNotFoundError(f"no .png frames in plant directory {src}")
    if limit_frames:
        pngs = pngs[:limit_frames]

    # per-frame routed polys + per-poly keypoint → records grouped by day
    frame_polys = {}          # stem -> list of (poly, base, tip, abstain, passes)
    frame_meta = {}           # stem -> (date, hour)
    by_day = defaultdict(list)  # date -> list of record dicts (idx into a flat per-day list)
    for png in pngs:
        ts = C.parse_ts(png.stem)
        if ts is None:
            print(f"  [WARN] skip {png.name}: no YYYYMMDDHHMM timestamp in file name")
            continue
        img = cv2.imread(str(png))
        if img is None:
            print(f"  [WARN] skip {png.name}: unreadable image")
            continue
        dets = C.infer_frame(img, cultivar, models, conf)
        routed = [p for p, _ in C.derive_version(dets, conf, cultivar)]
        leaves = []
        for poly in routed:
            kp = C.run_keypoint(kp_model, device, img, poly.astype(float))
            if kp is None:
                continue
            cx, cy = C.poly_centroid(poly)
            abstain = kp["heatmap_peak_min"] < C.ABSTAIN_THRESH
            passes = C.ray_through_circle(kp["tip"], kp["base"])
            rec = {"poly": poly, "base": kp["base"], "tip": kp["tip"],
                   "cx": cx, "cy": cy, "hour": ts.hour, "abstain": abstain, "passes": passes}
            leaves.append(rec)
            by_day[ts.date()].append(rec)
        frame_polys[png.stem] = leaves
        frame_meta[png.stem] = (ts.date(), ts.hour)

    # per-day trajectories + vote → assign tid + keep to each leaf rec
    for day, recs in by_day.items():
        trajs = C.build_trajectories(recs)
        for idx, traj in enumerate(trajs):
            traj_recs = [recs[i] for i in traj]
            decision, _, _ = C.vote_daily_decision(traj_recs)
            tid = f"{day.isoformat()}#{idx}"
            for r in traj_recs:
                r["tid"] = tid
                r["keep"] = (decision is True)

    if not frame_meta:
        raise ValueError(f"no usable frame in plant directory {src} "
                         f"({len(pngs)} .png files, none readable with a timestamp)")
    plant_day0 = min(d for d, _ in frame_meta.values())

    # per-frame metrics (union_area 每幀算一次) + daily aggregate
    frames_out = []
    day_acc = defaultdict(lambda: {"rc": [], "ra": [], "kc": [], "ka": []})
    for stem in sorted(frame_polys):
        d, h = frame_meta[stem]
        recs = frame_polys[stem]
        routed = [r["poly"] for r in recs]
        keep = [r["poly"] for r in recs if r.get("keep")]
        rc, kc = len(routed), len(keep)
        ra, ka = C.union_area(routed), C.union_area(keep)
        leaves_out = [{
            "tid": r.get("tid", f"{d.isoformat()}#x"),
            "points": [[round(float(x), 1), round(float(y), 1)] for x, y in r["poly"]],
            "base": [round(r["base"][0], 1), round(r["base"][1], 1)],
            "tip": [round(r["tip"][0], 1), round(r["tip"][1], 1)],
            "keep": bool(r.get("keep", False)),
        } for r in recs]
        frames_out.append({"stem": stem, "date": d.isoformat(), "hour": h,
                           "daf": (d - plant_day0).days,
                           "raw_count": rc, "keep_count": kc,
                           "raw_area": ra, "keep_area": ka, "leaves": leaves_out})
        day_acc[d]["rc"].append(rc); day_acc[d]["ra"].append(ra)
        day_acc[d]["kc"].append(kc); day_acc[d]["ka"].append(ka)
    curves = []
    for d in sorted(day_acc):
        a = day_acc[d]
        curves.append({"date": d.isoformat(), "daf": (d - plant_day0).days,
                       "n_frames": len(a["rc"]),
                       "raw_count": round(sum(a["rc"]) / len(a["rc"]), 3),
                       "raw_area": round(sum(a["ra"]) / len(a["ra"]), 1),
                       "keep_count": round(sum(a["kc"]) / len(a["kc"]), 3),
                       "keep_area": round(sum(a["ka"]) / len(a["ka"]), 1)})

    return {"plant_tag": rel.replace("/", "_"), "rel": rel, "cultivar": cultivar,
            "ref_circle": list(C.REF_CIRCLE), "n_frames": len(frames_out),
            "frames": frames_out, "curves": curves}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conf", type=float, default=0.1)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--batch", default=None, help="full batch code, e.g. 2025B08")
    ap.add_argument("--cultivar", default=None)
    ap.add_argument("--limit-plants", type=int, default=None)
    ap.add_argument("--limit-frames", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if not (args.all or args.batch or args.cultivar):
        ap.error("give --batch, --cultivar or --all")
    if args.batch and not re.fullmatch(r"\d{4}B\d{2}", args.batch):
        ap.error(f"--batch needs a full batch code such as 2025B08, got {args.batch!r}")

    plants = C.all_plants(args.batch)
    if args.cultivar:
        plants = [(t, r) for t, r in plants if f"/{args.cultivar}/" in f"/{r}/"]
    if args.limit_plants:
        plants = plants[: args.limit_plants]
    if not plants:
        sys.exit(f"[ERROR] no plant directory matches batch={args.batch} cultivar={args.cultivar} "
                 f"under {C.RASPI_ROOT} (expected <batch>/<cultivar>/<treatment>/rep-<n>)")
    print(f"[INFO] {len(plants)} plants @ conf={args.conf}; input {C.RASPI_ROOT}; output {C.DATA_ROOT}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[INFO] loading models on {device} ...")
    models = C.load_yolo_models()
    kp_model = C.load_keypoint_model(device)

    done = skipped = 0
    for i, (tag, rel) in enumerate(plants):
        outdir = C.DATA_ROOT / rel
        fj = outdir / "frames.json"
        if fj.exists() and not args.force:
            skipped += 1
            continue
        t0 = time.time()
        res = process_plant(rel, models, kp_model, device, args.conf, args.limit_frames)
        outdir.mkdir(parents=True, exist_ok=True)
        json.dump({k: v for k, v in res.items() if k != "frames"},
                  open(outdir / "curves.json", "w"))   # curves + meta
        json.dump(res, open(fj, "w"))                  # full (frames + curves)
        done += 1
        kc = res["curves"][-1]["keep_count"] if res["curves"] else 0
        print(f"  [{i+1}/{len(plants)}] {tag}: {res['n_frames']} frames, "
              f"{len(res['curves'])} days, last keep_count={kc} ({time.time()-t0:.1f}s)")

    print(f"\n=== build done: {done} plants written to {C.DATA_ROOT}; "
          f"{skipped} skipped because frames.json exists (use --force) ===")


if __name__ == "__main__":
    main()
