"""Stage 8 v5 — polygon-aware keypoint model.

Three changes from stage8_keypoint_poc.py:
  1. Dynamic interpolation: INTER_CUBIC when upscaling, INTER_AREA when downscaling
  2. pad_ratio jitter [0.05, 0.30] as scale augmentation (only with augment=True)
  3. Polygon mask as a 4th input channel (input shape (4, 256, 256))

Shared helpers (direction_loss, spread_loss, load_gt_samples, ...) are reused from
stage8_keypoint_poc; the model and dataset classes here are parallel versions.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset
from torchvision.models import ResNet18_Weights, resnet18

# Reuse constants from v3/v4
from stage8_keypoint_poc import (
    CROP_SIZE,
    IMAGENET_MEAN,
    IMAGENET_STD,
)

PAD_RANGE_AUG = (0.05, 0.30)   # train-time jitter
PAD_FIXED = 0.15                # eval/inference default (as in stage8_keypoint_poc)


def compute_crop_bbox_v5(img_hw: tuple[int, int], polygon: np.ndarray,
                          pad_ratio: float) -> tuple[int, int, int, int]:
    """Same as v3 compute_crop_bbox but pad_ratio is explicit (no global default)."""
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


def dynamic_resize(img: np.ndarray, target: int = CROP_SIZE) -> np.ndarray:
    """Patch 1: INTER_CUBIC when upscaling, INTER_AREA when downscaling."""
    h, w = img.shape[:2]
    if max(h, w) > target:
        interp = cv2.INTER_AREA
    else:
        interp = cv2.INTER_CUBIC
    return cv2.resize(img, (target, target), interpolation=interp)


def render_polygon_mask(polygon_crop_coords: np.ndarray,
                          crop_hw: tuple[int, int],
                          target: int = CROP_SIZE) -> np.ndarray:
    """Patch 3: draw a binary mask from the polygon (crop coordinates) and resize it to target.
    Nearest-neighbour resizing keeps the 0/1 edges."""
    h, w = crop_hw
    mask = np.zeros((h, w), dtype=np.uint8)
    poly = polygon_crop_coords.astype(np.int32)
    cv2.fillPoly(mask, [poly], 255)
    mask_resized = cv2.resize(mask, (target, target), interpolation=cv2.INTER_NEAREST)
    return (mask_resized > 127).astype(np.float32)


class LeafDatasetV5(Dataset):
    """Dataset changes from stage8_keypoint_poc:
    - crop and mask are computed on the fly in __getitem__ (no one-off cache at init)
    - with augment=True, pad_ratio ~ U[0.05, 0.30]
    - returns (tensor_4ch, labels_4): tensor RGB(3) + mask(1)
    """
    def __init__(self, samples: list[dict], augment: bool = False,
                  img_cache: dict | None = None):
        self.samples = samples
        self.augment = augment
        self._img_cache = img_cache if img_cache is not None else {}
        # Pre-warm image cache (several leaves share one plant image)
        for s in samples:
            if s["image_path"] not in self._img_cache:
                img = cv2.imread(s["image_path"])
                if img is None:
                    raise RuntimeError(f"cannot read {s['image_path']}")
                self._img_cache[s["image_path"]] = img

    def __len__(self) -> int:
        return len(self.samples)

    def _make_sample(self, s: dict, pad_ratio: float
                     ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (rgb_256 BGR, mask_256 [0,1], labels [bx,by,tx,ty] in [0,1])."""
        img = self._img_cache[s["image_path"]]
        polygon = s["polygon"]  # source coords
        bbox = compute_crop_bbox_v5(img.shape[:2], polygon, pad_ratio)
        x0, y0, x1, y1 = bbox
        crop = img[y0:y1, x0:x1]
        crop_hw = crop.shape[:2]
        rgb_256 = dynamic_resize(crop, CROP_SIZE)
        # polygon to crop coords + render mask at native crop resolution then resize
        poly_crop = polygon - np.array([x0, y0])
        mask_256 = render_polygon_mask(poly_crop, crop_hw, CROP_SIZE)
        base_norm = coords_full_to_crop(s["base_full"], bbox)
        tip_norm = coords_full_to_crop(s["tip_full"], bbox)
        labels = np.array([base_norm[0], base_norm[1],
                           tip_norm[0], tip_norm[1]], dtype=np.float32)
        return rgb_256, mask_256, labels

    def _augment_geo(self, rgb: np.ndarray, mask: np.ndarray,
                     labels: np.ndarray
                     ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        bx, by, tx, ty = labels.tolist()
        # H-flip: mirror x
        if random.random() < 0.5:
            rgb = cv2.flip(rgb, 1)
            mask = cv2.flip(mask, 1)
            bx, tx = 1.0 - bx, 1.0 - tx
        # Rotation ±15°
        if random.random() < 0.7:
            angle = random.uniform(-15.0, 15.0)
            M = cv2.getRotationMatrix2D((CROP_SIZE / 2, CROP_SIZE / 2), angle, 1.0)
            rgb = cv2.warpAffine(rgb, M, (CROP_SIZE, CROP_SIZE),
                                  borderValue=(0, 0, 0))
            mask = cv2.warpAffine(mask, M, (CROP_SIZE, CROP_SIZE),
                                   flags=cv2.INTER_NEAREST, borderValue=0)
            def rot_pt(px, py):
                ux = M[0, 0] * px + M[0, 1] * py + M[0, 2]
                uy = M[1, 0] * px + M[1, 1] * py + M[1, 2]
                return ux, uy
            bx_px, by_px = rot_pt(bx * CROP_SIZE, by * CROP_SIZE)
            tx_px, ty_px = rot_pt(tx * CROP_SIZE, ty * CROP_SIZE)
            bx, by = bx_px / CROP_SIZE, by_px / CROP_SIZE
            tx, ty = tx_px / CROP_SIZE, ty_px / CROP_SIZE
        # Mild colour jitter (only on RGB)
        if random.random() < 0.5:
            hsv = cv2.cvtColor(rgb, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[..., 1] *= random.uniform(0.85, 1.15)
            hsv[..., 2] *= random.uniform(0.85, 1.15)
            hsv = np.clip(hsv, 0.0, 255.0).astype(np.uint8)
            rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        labels = np.clip(np.array([bx, by, tx, ty], dtype=np.float32), 0.0, 1.0)
        return rgb, mask, labels

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        s = self.samples[idx]
        if self.augment:
            pad_ratio = random.uniform(*PAD_RANGE_AUG)
        else:
            pad_ratio = PAD_FIXED
        rgb, mask, labels = self._make_sample(s, pad_ratio)
        if self.augment:
            rgb, mask, labels = self._augment_geo(rgb, mask, labels)
        # RGB normalize
        rgb_f = cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        rgb_f = (rgb_f - IMAGENET_MEAN) / IMAGENET_STD
        # mask is already in [0, 1]
        # Stack: (4, H, W) — first 3 RGB, last is mask
        tensor = torch.from_numpy(
            np.concatenate([rgb_f.transpose(2, 0, 1),
                            mask[None, :, :]], axis=0).astype(np.float32))
        return tensor, torch.from_numpy(labels)


class KeypointModelV5(nn.Module):
    """ResNet-18 + 4-channel conv1 + the head of stage8_keypoint_poc."""
    def __init__(self, freeze_stages: int = 2) -> None:
        super().__init__()
        backbone = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
        # Patch 3: replace conv1 with 4-input-channel conv
        old_conv1 = backbone.conv1
        new_conv1 = nn.Conv2d(
            in_channels=4,
            out_channels=old_conv1.out_channels,
            kernel_size=old_conv1.kernel_size,
            stride=old_conv1.stride,
            padding=old_conv1.padding,
            bias=(old_conv1.bias is not None),
        )
        with torch.no_grad():
            new_conv1.weight[:, :3] = old_conv1.weight.clone()
            new_conv1.weight[:, 3:].zero_()
            if old_conv1.bias is not None and new_conv1.bias is not None:
                new_conv1.bias.copy_(old_conv1.bias)
        backbone.conv1 = new_conv1
        backbone.fc = nn.Identity()
        if freeze_stages >= 1:
            for p in backbone.bn1.parameters():
                p.requires_grad = False
            for p in backbone.layer1.parameters():
                p.requires_grad = False
            # NOTE: conv1 stays trainable so the zero-initialised 4th channel can learn
        if freeze_stages >= 2:
            for p in backbone.layer2.parameters():
                p.requires_grad = False
        self.backbone = backbone
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
