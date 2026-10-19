"""
Stage 8 keypoint regression POC — direct base/tip prediction.

Small CNN head on ImageNet-ResNet18 features predicts
(base_x, base_y, tip_x, tip_y) relative to each polygon's bbox crop.

Trained on 65 human-annotated leaves (2 plants, 2 cultivars) with heavy
augmentation; evaluated via leave-one-plant-out CV (2 folds).

Metrics:
  |Δθ_line|          orientation error ∈ [0°, 90°] (lower = better)
  direction_ok       % where tip/base predicted on correct sides
  base_dist_px       L2 distance between predicted and GT base (pixels)
  tip_dist_px        same for tip

Outputs:
  {out}/summary.csv        per-leaf metrics
  {out}/method_stats.csv   aggregates per fold + vs classical methods
  {out}/overlays/          per-frame overlay PNGs (GT + pred arrows)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from torchvision.models import ResNet18_Weights, resnet18


CROP_SIZE = 256
PAD_RATIO = 0.15
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


# ─── data loading ─────────────────────────────────────────────────────────

def load_gt_samples(gt_root: Path) -> list[dict]:
    samples: list[dict] = []
    for gt_file in sorted(gt_root.rglob("*_midrib_gt.json")):
        with open(gt_file, encoding="utf-8") as f:
            gt = json.load(f)
        src_json = Path(gt["source_json"])
        src_img = src_json.with_suffix(".png")
        if not src_img.is_file() or not src_json.is_file():
            continue
        with open(src_json, encoding="utf-8") as f:
            src_data = json.load(f)
        polys = [sh["points"] for sh in src_data.get("shapes", [])
                 if sh.get("shape_type") == "polygon"]
        plant = gt_file.parent.name
        frame_stem = gt_file.stem.replace("_midrib_gt", "")
        for ann in gt.get("annotations", []):
            if ann.get("status") != "done":
                continue
            idx = ann["original_polygon_index"]
            if idx >= len(polys) or len(polys[idx]) < 3:
                continue
            samples.append({
                "plant": plant,
                "frame": frame_stem,
                "image_path": str(src_img),
                "polygon": np.array(polys[idx], dtype=np.float64),
                "base_full": np.array(ann["base"], dtype=np.float64),
                "tip_full": np.array(ann["tip"], dtype=np.float64),
                "polygon_index": idx,
                "area_px": float(ann.get("area_px", 0.0)),
            })
    return samples


def compute_crop_bbox(img_hw: tuple[int, int], polygon: np.ndarray,
                      pad_ratio: float = PAD_RATIO
                      ) -> tuple[int, int, int, int]:
    H, W = img_hw
    x_min, x_max = float(polygon[:, 0].min()), float(polygon[:, 0].max())
    y_min, y_max = float(polygon[:, 1].min()), float(polygon[:, 1].max())
    pad = int(max(x_max - x_min, y_max - y_min) * pad_ratio)
    x0 = max(0, int(x_min) - pad)
    y0 = max(0, int(y_min) - pad)
    x1 = min(W, int(x_max) + pad)
    y1 = min(H, int(y_max) + pad)
    return x0, y0, x1, y1


def coords_full_to_crop(pt_full: np.ndarray,
                        bbox: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, x1, y1 = bbox
    return np.array([(pt_full[0] - x0) / max(1, x1 - x0),
                     (pt_full[1] - y0) / max(1, y1 - y0)],
                    dtype=np.float32)


def coords_crop_to_full(pt_norm: np.ndarray,
                        bbox: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, x1, y1 = bbox
    return np.array([pt_norm[0] * (x1 - x0) + x0,
                     pt_norm[1] * (y1 - y0) + y0],
                    dtype=np.float32)


# ─── dataset with cache ───────────────────────────────────────────────────

class LeafDataset(Dataset):
    def __init__(self, samples: list[dict], augment: bool = False,
                 img_cache: dict | None = None):
        self.samples = samples
        self.augment = augment
        self._cache: list[tuple[np.ndarray, np.ndarray,
                                tuple[int, int, int, int]]] = []
        self._img_cache = img_cache if img_cache is not None else {}
        for s in samples:
            if s["image_path"] not in self._img_cache:
                img = cv2.imread(s["image_path"])
                if img is None:
                    raise RuntimeError(f"cannot read {s['image_path']}")
                self._img_cache[s["image_path"]] = img
            img = self._img_cache[s["image_path"]]
            bbox = compute_crop_bbox(img.shape[:2], s["polygon"])
            x0, y0, x1, y1 = bbox
            crop = img[y0:y1, x0:x1].copy()
            crop_resized = cv2.resize(crop, (CROP_SIZE, CROP_SIZE),
                                      interpolation=cv2.INTER_AREA)
            base_norm = coords_full_to_crop(s["base_full"], bbox)
            tip_norm = coords_full_to_crop(s["tip_full"], bbox)
            labels = np.array([base_norm[0], base_norm[1],
                               tip_norm[0], tip_norm[1]], dtype=np.float32)
            self._cache.append((crop_resized, labels, bbox))

    def __len__(self) -> int:
        return len(self.samples)

    def _augment(self, crop: np.ndarray, labels: np.ndarray
                 ) -> tuple[np.ndarray, np.ndarray]:
        bx, by, tx, ty = labels.tolist()
        # H-flip: mirror x
        if random.random() < 0.5:
            crop = cv2.flip(crop, 1)
            bx, tx = 1.0 - bx, 1.0 - tx
        # Rotation (±15°, milder so orientation is still recognizable)
        if random.random() < 0.7:
            angle = random.uniform(-15.0, 15.0)
            M = cv2.getRotationMatrix2D((CROP_SIZE / 2, CROP_SIZE / 2),
                                        angle, 1.0)
            crop = cv2.warpAffine(crop, M, (CROP_SIZE, CROP_SIZE),
                                  borderValue=(0, 0, 0))
            def rot_pt(px: float, py: float) -> tuple[float, float]:
                ux = M[0, 0] * px + M[0, 1] * py + M[0, 2]
                uy = M[1, 0] * px + M[1, 1] * py + M[1, 2]
                return ux, uy
            bx_px, by_px = rot_pt(bx * CROP_SIZE, by * CROP_SIZE)
            tx_px, ty_px = rot_pt(tx * CROP_SIZE, ty * CROP_SIZE)
            bx, by = bx_px / CROP_SIZE, by_px / CROP_SIZE
            tx, ty = tx_px / CROP_SIZE, ty_px / CROP_SIZE
        # Mild colour jitter
        if random.random() < 0.5:
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[..., 1] *= random.uniform(0.85, 1.15)
            hsv[..., 2] *= random.uniform(0.85, 1.15)
            hsv = np.clip(hsv, 0.0, 255.0).astype(np.uint8)
            crop = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        labels = np.array([bx, by, tx, ty], dtype=np.float32)
        labels = np.clip(labels, 0.0, 1.0)
        return crop, labels

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        crop, labels, _ = self._cache[idx]
        crop = crop.copy()
        labels = labels.copy()
        if self.augment:
            crop, labels = self._augment(crop, labels)
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        rgb = (rgb - IMAGENET_MEAN) / IMAGENET_STD
        tensor = torch.from_numpy(rgb.transpose(2, 0, 1)
                                  .astype(np.float32))
        return tensor, torch.from_numpy(labels)


# ─── model ───────────────────────────────────────────────────────────────

class KeypointModel(nn.Module):
    def __init__(self, freeze_stages: int = 2) -> None:
        super().__init__()
        self.backbone = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
        self.backbone.fc = nn.Identity()
        # Freeze only the first `freeze_stages` blocks (conv1+bn1+layer1..)
        if freeze_stages >= 1:
            for p in self.backbone.conv1.parameters():
                p.requires_grad = False
            for p in self.backbone.bn1.parameters():
                p.requires_grad = False
            for p in self.backbone.layer1.parameters():
                p.requires_grad = False
        if freeze_stages >= 2:
            for p in self.backbone.layer2.parameters():
                p.requires_grad = False
        # layer3, layer4, head stay trainable
        self.head = nn.Sequential(
            nn.Linear(512, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            nn.Linear(256, 128),
            nn.ReLU(inplace=True),
            nn.Dropout(0.2),
            nn.Linear(128, 4),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        feat = self.backbone(x)
        return self.head(feat)


# ─── metrics ─────────────────────────────────────────────────────────────

def angle_of_vec(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(dy, dx)) % 180.0


def angle_diff_line(a: float, b: float) -> float:
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def direction_agreement(base_pred: np.ndarray, tip_pred: np.ndarray,
                        base_gt: np.ndarray, tip_gt: np.ndarray) -> bool:
    v_p = tip_pred - base_pred
    v_g = tip_gt - base_gt
    n_p = float(np.linalg.norm(v_p))
    n_g = float(np.linalg.norm(v_g))
    if n_p < 1e-6 or n_g < 1e-6:
        return False
    return float(np.dot(v_p, v_g) / (n_p * n_g)) > 0.0


# ─── training / eval ─────────────────────────────────────────────────────

def direction_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """1 - cosine similarity of (tip - base) vectors (helps direction)."""
    v_p = pred[:, 2:] - pred[:, :2]
    v_t = target[:, 2:] - target[:, :2]
    cos = F.cosine_similarity(v_p, v_t, dim=1, eps=1e-6)
    return (1.0 - cos).mean()


def spread_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """Penalise predictions where base and tip collapse to the same point.
    Encourages |pred base→tip| to match |gt base→tip|."""
    v_p = pred[:, 2:] - pred[:, :2]
    v_t = target[:, 2:] - target[:, :2]
    len_p = v_p.norm(dim=1)
    len_t = v_t.norm(dim=1)
    return F.l1_loss(len_p, len_t)


def train_fold(train_ds: LeafDataset, val_ds: LeafDataset,
               epochs: int, lr: float, batch_size: int,
               device: str, verbose: bool = True) -> KeypointModel:
    train_loader = DataLoader(train_ds, batch_size=batch_size,
                              shuffle=True, num_workers=0,
                              drop_last=False)
    val_loader = DataLoader(val_ds, batch_size=batch_size,
                            shuffle=False, num_workers=0)
    model = KeypointModel(freeze_stages=2).to(device)
    # Smaller lr on backbone (fine-tune), full lr on head
    backbone_params = [p for n, p in model.backbone.named_parameters()
                       if p.requires_grad]
    head_params = list(model.head.parameters())
    optim = torch.optim.AdamW(
        [{"params": backbone_params, "lr": lr * 0.1},
         {"params": head_params, "lr": lr}],
        weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(optim, T_max=epochs)
    best_val = float("inf")
    best_state = None
    for ep in range(epochs):
        model.train()
        tr_loss = 0.0
        n_tr = 0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            pred = model(x)
            l_mse = F.mse_loss(pred, y)
            l_dir = direction_loss(pred, y)
            l_spread = spread_loss(pred, y)
            loss = l_mse + 0.5 * l_dir + 0.3 * l_spread
            optim.zero_grad()
            loss.backward()
            optim.step()
            tr_loss += loss.item() * x.size(0)
            n_tr += x.size(0)
        sched.step()
        tr_loss /= max(n_tr, 1)
        model.eval()
        val_loss = 0.0
        n_val = 0
        with torch.no_grad():
            for x, y in val_loader:
                x, y = x.to(device), y.to(device)
                pred = model(x)
                val_loss += F.mse_loss(pred, y).item() * x.size(0)
                n_val += x.size(0)
        val_loss /= max(n_val, 1)
        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.detach().cpu().clone()
                          for k, v in model.state_dict().items()}
        if verbose and (ep % 10 == 0 or ep == epochs - 1):
            print(f"    ep {ep:3d}  train={tr_loss:.4f}  val={val_loss:.4f}")
    if best_state is not None:
        model.load_state_dict(best_state)
    return model


def eval_fold(model: KeypointModel, samples: list[dict],
              val_ds: LeafDataset, device: str) -> list[dict]:
    model.eval()
    results = []
    for i, s in enumerate(samples):
        crop, _, bbox = val_ds._cache[i]
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        rgb = (rgb - IMAGENET_MEAN) / IMAGENET_STD
        x_t = torch.from_numpy(rgb.transpose(2, 0, 1)
                               .astype(np.float32)).unsqueeze(0).to(device)
        with torch.no_grad():
            pred = model(x_t).cpu().numpy()[0]
        base_pred = coords_crop_to_full(np.array(pred[:2]), bbox)
        tip_pred = coords_crop_to_full(np.array(pred[2:]), bbox)
        gt_angle = angle_of_vec(s["tip_full"][0] - s["base_full"][0],
                                s["tip_full"][1] - s["base_full"][1])
        pr_angle = angle_of_vec(tip_pred[0] - base_pred[0],
                                tip_pred[1] - base_pred[1])
        d_line = angle_diff_line(gt_angle, pr_angle)
        dir_ok = direction_agreement(base_pred, tip_pred,
                                     s["base_full"], s["tip_full"])
        results.append({
            "plant": s["plant"],
            "frame": s["frame"],
            "polygon_index": s["polygon_index"],
            "area_px": round(s["area_px"], 1),
            "gt_angle": round(gt_angle, 2),
            "pred_angle": round(pr_angle, 2),
            "diff_line": round(d_line, 2),
            "direction_ok": int(dir_ok),
            "base_dist_px": round(float(np.linalg.norm(
                base_pred - s["base_full"])), 1),
            "tip_dist_px": round(float(np.linalg.norm(
                tip_pred - s["tip_full"])), 1),
            "base_pred_x": round(float(base_pred[0]), 1),
            "base_pred_y": round(float(base_pred[1]), 1),
            "tip_pred_x": round(float(tip_pred[0]), 1),
            "tip_pred_y": round(float(tip_pred[1]), 1),
        })
    return results


# ─── overlays ────────────────────────────────────────────────────────────

def write_overlays(results: list[dict], samples: list[dict],
                   img_cache: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    by_frame: defaultdict = defaultdict(list)
    sample_lut = {(s["plant"], s["frame"], s["polygon_index"]): s
                  for s in samples}
    for r in results:
        key = (r["plant"], r["frame"], r["polygon_index"])
        by_frame[(r["plant"], r["frame"])].append((r, sample_lut[key]))
    for (plant, frame), items in sorted(by_frame.items()):
        sub = out_dir / plant
        sub.mkdir(parents=True, exist_ok=True)
        s0 = items[0][1]
        img = img_cache.get(s0["image_path"])
        if img is None:
            img = cv2.imread(s0["image_path"])
        n = len(items)
        ncol = min(n, 4)
        nrow = (n + ncol - 1) // ncol
        fig, axes = plt.subplots(nrow, ncol,
                                 figsize=(4.5 * ncol, 4.8 * nrow),
                                 squeeze=False)
        axes_flat = axes.flatten()
        for i, (r, s) in enumerate(items):
            ax = axes_flat[i]
            bbox = compute_crop_bbox(img.shape[:2], s["polygon"])
            x0, y0, x1, y1 = bbox
            crop = img[y0:y1, x0:x1]
            poly_local = s["polygon"] - np.array([x0, y0])
            base_local = s["base_full"] - np.array([x0, y0])
            tip_local = s["tip_full"] - np.array([x0, y0])
            base_pred_local = np.array([r["base_pred_x"] - x0,
                                        r["base_pred_y"] - y0])
            tip_pred_local = np.array([r["tip_pred_x"] - x0,
                                       r["tip_pred_y"] - y0])
            ax.imshow(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
            closed = np.vstack([poly_local, poly_local[:1]])
            ax.plot(closed[:, 0], closed[:, 1], color="yellow",
                    lw=1.0, alpha=0.7)
            # GT: solid blue
            ax.annotate("", xy=tip_local, xytext=base_local,
                        arrowprops=dict(arrowstyle="->",
                                        color="#1a5fff", lw=2.5,
                                        mutation_scale=20), zorder=5)
            ax.scatter([base_local[0]], [base_local[1]], s=45,
                       color="#1a5fff", edgecolors="white", zorder=6)
            # Predicted: dashed magenta
            ax.annotate("", xy=tip_pred_local, xytext=base_pred_local,
                        arrowprops=dict(arrowstyle="->",
                                        color="#d02080", lw=2.2,
                                        linestyle="--",
                                        mutation_scale=18), zorder=4)
            ax.scatter([base_pred_local[0]], [base_pred_local[1]], s=35,
                       color="#d02080", edgecolors="white", zorder=5)
            ax.set_xlim(0, x1 - x0)
            ax.set_ylim(y1 - y0, 0)
            ax.axis("off")
            dir_str = "✓" if r["direction_ok"] else "✗"
            ax.set_title(
                f"leaf#{r['polygon_index']}  area={r['area_px']:.0f}px\n"
                f"|Δθ|={r['diff_line']:.0f}°  dir={dir_str}  "
                f"base_d={r['base_dist_px']:.0f}px  "
                f"tip_d={r['tip_dist_px']:.0f}px",
                fontsize=8)
        for j in range(n, len(axes_flat)):
            axes_flat[j].axis("off")
        handles = [
            plt.Line2D([0], [0], color="#1a5fff", lw=2.5, label="GT"),
            plt.Line2D([0], [0], color="#d02080", lw=2.2, linestyle="--",
                       label="predicted"),
        ]
        fig.legend(handles=handles, loc="upper center", ncol=2, fontsize=9,
                   bbox_to_anchor=(0.5, 1.01), frameon=False)
        fig.suptitle(f"{plant}  {frame}", fontsize=11, y=1.04)
        fig.tight_layout()
        fig.savefig(sub / f"{frame}.png", dpi=130, bbox_inches="tight")
        plt.close(fig)


# ─── main ────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt-root",
                    default="verification_output/stage8_poc/midrib_gt")
    ap.add_argument("--out",
                    default="verification_output/stage8_poc/keypoint_eval")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-overlay", action="store_true")
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
        torch.backends.cudnn.benchmark = True

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[INFO] device={device}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    samples = load_gt_samples(Path(args.gt_root))
    plants = sorted({s["plant"] for s in samples})
    print(f"[INFO] {len(samples)} samples across {len(plants)} plants")
    for p in plants:
        n = sum(1 for s in samples if s["plant"] == p)
        print(f"         {p}: {n}")

    shared_img_cache: dict[str, np.ndarray] = {}

    all_results: list[dict] = []
    for val_plant in plants:
        print(f"\n=== Fold: val={val_plant} ===")
        tr_samples = [s for s in samples if s["plant"] != val_plant]
        va_samples = [s for s in samples if s["plant"] == val_plant]
        print(f"  train n={len(tr_samples)}   val n={len(va_samples)}")
        tr_ds = LeafDataset(tr_samples, augment=True,
                            img_cache=shared_img_cache)
        va_ds = LeafDataset(va_samples, augment=False,
                            img_cache=shared_img_cache)
        model = train_fold(tr_ds, va_ds,
                           epochs=args.epochs, lr=args.lr,
                           batch_size=args.batch_size, device=device)
        fold_results = eval_fold(model, va_samples, va_ds, device=device)
        for r in fold_results:
            r["val_fold"] = val_plant
        all_results.extend(fold_results)

    # Write per-leaf CSV
    summary_csv = out_dir / "summary.csv"
    with open(summary_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(all_results[0].keys()))
        w.writeheader()
        w.writerows(all_results)
    print(f"\n[OK] wrote {summary_csv}  ({len(all_results)} rows)")

    # Aggregate metrics
    print()
    header = (f"{'scope':<22} {'n':>4} {'med_|Δθ|':>10} "
              f"{'≤15°':>7} {'≤30°':>7} "
              f"{'dir_ok':>8} {'base_d':>8} {'tip_d':>8}")
    print(header)
    stat_rows: list[dict] = []
    for scope in ["ALL"] + plants:
        subset = (all_results if scope == "ALL"
                  else [r for r in all_results if r["plant"] == scope])
        if not subset:
            continue
        diffs = np.array([r["diff_line"] for r in subset])
        bdist = np.array([r["base_dist_px"] for r in subset])
        tdist = np.array([r["tip_dist_px"] for r in subset])
        dir_ok = np.array([r["direction_ok"] for r in subset])
        rec = {
            "scope": scope,
            "n": len(subset),
            "median_diff_line": round(float(np.median(diffs)), 2),
            "mean_diff_line": round(float(np.mean(diffs)), 2),
            "pct_le_15": round(float((diffs <= 15.0).mean() * 100), 1),
            "pct_le_30": round(float((diffs <= 30.0).mean() * 100), 1),
            "pct_le_45": round(float((diffs <= 45.0).mean() * 100), 1),
            "direction_ok_pct": round(float(dir_ok.mean() * 100), 1),
            "median_base_dist_px": round(float(np.median(bdist)), 1),
            "median_tip_dist_px": round(float(np.median(tdist)), 1),
        }
        stat_rows.append(rec)
        print(f"{scope:<22} {rec['n']:>4} "
              f"{rec['median_diff_line']:>9.1f}° "
              f"{rec['pct_le_15']:>6.1f}% {rec['pct_le_30']:>6.1f}% "
              f"{rec['direction_ok_pct']:>7.1f}% "
              f"{rec['median_base_dist_px']:>7.1f}px "
              f"{rec['median_tip_dist_px']:>7.1f}px")

    # Also load classical method stats if present for side-by-side compare
    classical_csv = (Path(args.gt_root).parent / "midrib_eval"
                     / "method_stats.csv")
    if classical_csv.is_file():
        print("\n[Comparison vs classical methods (median |Δθ|, % ≤15°)]")
        with open(classical_csv, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            if r["scope"] == "ALL":
                print(f"  {r['method']:<15}  median={r['median']:>5}°  "
                      f"≤15°={r['pct_le_15']:>5}%")
        # our method
        all_rec = next(r for r in stat_rows if r["scope"] == "ALL")
        print(f"  {'keypoint_dl':<15}  "
              f"median={all_rec['median_diff_line']:>5.1f}°  "
              f"≤15°={all_rec['pct_le_15']:>5.1f}%")

    stats_csv = out_dir / "method_stats.csv"
    with open(stats_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(stat_rows[0].keys()))
        w.writeheader()
        w.writerows(stat_rows)
    print(f"[OK] wrote {stats_csv}")

    if not args.no_overlay:
        write_overlays(all_results, samples, shared_img_cache,
                       out_dir / "overlays")
        print(f"[OK] wrote overlays → {out_dir / 'overlays'}")


if __name__ == "__main__":
    main()
