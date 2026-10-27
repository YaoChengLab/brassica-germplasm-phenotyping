"""v7-dt: distance transform polygon channel.

The only difference from stage8_keypoint_v6_heatmap: the 4th input channel is a distance
transform (normalised to [0,1]) instead of the binary polygon mask. Architecture, loss,
decoding and augmentation are inherited unchanged.

Why: a binary mask is sensitive to noise on the polygon boundary (occluded leaves, leaves cut
at the image edge, fragmented masks). A distance transform is strong in the core of the polygon
and weak at its edge, so it is robust to boundary noise, and its ridge approximates the midrib,
which is what a person reads to place base and tip.
"""
from __future__ import annotations

import random

import cv2
import numpy as np
import torch

from stage8_keypoint_v5 import (
    LeafDatasetV5,
    PAD_RANGE_AUG,
    PAD_FIXED,
    compute_crop_bbox_v5,
    coords_full_to_crop,
    dynamic_resize,
)
from stage8_keypoint_poc import CROP_SIZE, IMAGENET_MEAN, IMAGENET_STD


def render_polygon_distance_transform(polygon_crop_coords: np.ndarray,
                                        crop_hw: tuple[int, int],
                                        target: int = CROP_SIZE) -> np.ndarray:
    """Replacement for v5/v6's render_polygon_mask.

    Returns normalized distance transform ∈ [0, 1]:
      - on the polygon boundary: 0
      - inside the polygon: distance to the nearest boundary / max(distance)
      - outside the polygon: 0
    Resized to target with INTER_LINEAR (the values are floats).
    """
    h, w = crop_hw
    mask = np.zeros((h, w), dtype=np.uint8)
    poly = polygon_crop_coords.astype(np.int32)
    cv2.fillPoly(mask, [poly], 255)
    dt = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    if dt.max() > 0:
        dt = dt / dt.max()
    dt_resized = cv2.resize(dt, (target, target), interpolation=cv2.INTER_LINEAR)
    return dt_resized.astype(np.float32)


class LeafDatasetV7DT(LeafDatasetV5):
    """LeafDatasetV5 with a distance transform instead of the binary mask as the 4th channel."""

    def _make_sample(self, s: dict, pad_ratio: float
                      ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        img = self._img_cache[s["image_path"]]
        polygon = s["polygon"]
        bbox = compute_crop_bbox_v5(img.shape[:2], polygon, pad_ratio)
        x0, y0, x1, y1 = bbox
        crop = img[y0:y1, x0:x1]
        crop_hw = crop.shape[:2]
        rgb_256 = dynamic_resize(crop, CROP_SIZE)
        poly_crop = polygon - np.array([x0, y0])
        # ★ Only difference: distance transform instead of binary mask
        dt_256 = render_polygon_distance_transform(poly_crop, crop_hw, CROP_SIZE)
        base_norm = coords_full_to_crop(s["base_full"], bbox)
        tip_norm = coords_full_to_crop(s["tip_full"], bbox)
        labels = np.array([base_norm[0], base_norm[1],
                           tip_norm[0], tip_norm[1]], dtype=np.float32)
        return rgb_256, dt_256, labels
