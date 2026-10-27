"""Stage 8 v6 — heatmap regression baseline.

Three differences from the coordinate regression in stage8_keypoint_v5:
  1. Output: a (2, 64, 64) heatmap instead of a (4,) tuple of scalars
  2. Loss: a single MSE on the heatmap, without direction/spread/collapse penalties
     (those failure modes do not arise with heatmaps)
  3. Inference: soft-argmax gives sub-pixel coordinates

The input pipeline is the same as stage8_keypoint_v5 (LeafDatasetV5): 4-channel RGB + polygon mask.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision.models import ResNet18_Weights, resnet18

# Reuse v5 dataset for input processing (returns (tensor_4ch, labels_4))
sys.path.insert(0, str(Path(__file__).parent))
from stage8_keypoint_v5 import LeafDatasetV5  # noqa: F401

HEATMAP_HW = 64           # output spatial size (256/4 downsample from ResNet)
GAUSSIAN_SIGMA = 2.0      # target peak std (px in heatmap space)
NUM_KEYPOINTS = 2         # base + tip


def labels_to_heatmap(labels: torch.Tensor,
                       H: int = HEATMAP_HW,
                       W: int = HEATMAP_HW,
                       sigma: float = GAUSSIAN_SIGMA) -> torch.Tensor:
    """Convert (B, 4) labels in [0,1] → (B, 2, H, W) Gaussian heatmap target.

    Channel 0 = base, channel 1 = tip.
    """
    B = labels.shape[0]
    device = labels.device
    yy = torch.arange(H, device=device, dtype=torch.float32).view(1, 1, H, 1)
    xx = torch.arange(W, device=device, dtype=torch.float32).view(1, 1, 1, W)
    # GT pixel positions in heatmap space (shape: B, 2, 1, 1)
    bx = labels[:, 0].view(B, 1, 1, 1) * (W - 1)
    by = labels[:, 1].view(B, 1, 1, 1) * (H - 1)
    tx = labels[:, 2].view(B, 1, 1, 1) * (W - 1)
    ty = labels[:, 3].view(B, 1, 1, 1) * (H - 1)
    base_hm = torch.exp(-((xx - bx) ** 2 + (yy - by) ** 2) / (2 * sigma * sigma))
    tip_hm = torch.exp(-((xx - tx) ** 2 + (yy - ty) ** 2) / (2 * sigma * sigma))
    return torch.cat([base_hm, tip_hm], dim=1)  # (B, 2, H, W)


def soft_argmax(heatmap: torch.Tensor, beta: float = 50.0) -> torch.Tensor:
    """(B, K, H, W) → (B, K, 2) coords in normalized [0,1].

    Sub-pixel by softmax-weighted average over spatial positions.
    beta = sharpness; high → close to hard argmax; low → blurry mean.
    """
    B, K, H, W = heatmap.shape
    flat = heatmap.view(B, K, -1) * beta
    weights = F.softmax(flat, dim=-1)  # (B, K, H*W)
    yy = torch.arange(H, device=heatmap.device, dtype=torch.float32) / max(H - 1, 1)
    xx = torch.arange(W, device=heatmap.device, dtype=torch.float32) / max(W - 1, 1)
    grid_y, grid_x = torch.meshgrid(yy, xx, indexing="ij")
    grid = torch.stack([grid_x.reshape(-1), grid_y.reshape(-1)], dim=-1)  # (H*W, 2) order (x, y)
    coords = torch.einsum("bkn,nd->bkd", weights, grid)  # (B, K, 2)
    return coords


def hard_argmax(heatmap: torch.Tensor) -> torch.Tensor:
    """Hard argmax — integer pixel precision. Useful for sanity check."""
    B, K, H, W = heatmap.shape
    flat = heatmap.view(B, K, -1)
    idx = flat.argmax(dim=-1)
    y = (idx // W).float() / max(H - 1, 1)
    x = (idx % W).float() / max(W - 1, 1)
    return torch.stack([x, y], dim=-1)  # (B, K, 2)


class KeypointHeatmapModel(nn.Module):
    """ResNet-18 (4-channel) backbone + deconv head → (K, 64, 64) heatmap."""

    def __init__(self, num_keypoints: int = NUM_KEYPOINTS,
                  in_channels: int = 4, freeze_stages: int = 2) -> None:
        super().__init__()
        backbone = resnet18(weights=ResNet18_Weights.IMAGENET1K_V1)
        old_conv1 = backbone.conv1
        new_conv1 = nn.Conv2d(
            in_channels=in_channels,
            out_channels=old_conv1.out_channels,
            kernel_size=old_conv1.kernel_size,
            stride=old_conv1.stride,
            padding=old_conv1.padding,
            bias=(old_conv1.bias is not None),
        )
        with torch.no_grad():
            n_copy = min(3, in_channels)
            new_conv1.weight[:, :n_copy] = old_conv1.weight[:, :n_copy].clone()
            if in_channels > 3:
                new_conv1.weight[:, 3:].zero_()
            if old_conv1.bias is not None and new_conv1.bias is not None:
                new_conv1.bias.copy_(old_conv1.bias)
        backbone.conv1 = new_conv1
        # Strip avgpool + fc → output feature map (B, 512, 8, 8) for 256×256 input
        # Children indexing: 0=conv1 1=bn1 2=relu 3=maxpool 4=layer1 5=layer2 6=layer3 7=layer4 8=avgpool 9=fc
        # We freeze layers conservatively like v5.
        if freeze_stages >= 1:
            for p in backbone.bn1.parameters(): p.requires_grad = False
            for p in backbone.layer1.parameters(): p.requires_grad = False
        if freeze_stages >= 2:
            for p in backbone.layer2.parameters(): p.requires_grad = False
        self.backbone = nn.Sequential(*list(backbone.children())[:8])

        # Deconv head: 8 → 16 → 32 → 64
        self.head = nn.Sequential(
            nn.ConvTranspose2d(512, 256, 4, stride=2, padding=1),
            nn.BatchNorm2d(256), nn.ReLU(inplace=True),
            nn.ConvTranspose2d(256, 128, 4, stride=2, padding=1),
            nn.BatchNorm2d(128), nn.ReLU(inplace=True),
            nn.ConvTranspose2d(128, 64, 4, stride=2, padding=1),
            nn.BatchNorm2d(64), nn.ReLU(inplace=True),
            nn.Conv2d(64, num_keypoints, kernel_size=1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        feat = self.backbone(x)
        hm = self.head(feat)
        return hm  # (B, K, 64, 64)
