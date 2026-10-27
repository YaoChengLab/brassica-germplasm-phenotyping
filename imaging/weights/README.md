# Model weights

`build.py` needs four model files in this directory. `python imaging/download_weights.py`, run from the repository root, downloads them and checks each file's SHA-256 (the expected sizes and checksums are in `download_weights.py`). The weight files themselves are not tracked by git.

| File | Model | Role in `build.py` | Source |
|---|---|---|---|
| `brassicaceae_leaf_seg.pt` | YOLO11m-seg, one class (`leaf`) | Leaves inside the routing circle at the centre of each single-plant image | This repository, release `yolo-weight`; fine-tuned from GenYOLO-Leaf (see below) |
| `brassicaceae_lobed_leaf_seg.pt` | YOLOv8m-seg, two classes (`normal-leaf`, `lobe-leaf`) | All leaves of the accessions with deeply lobed leaves (s0074, s0100, s0180) | This repository, release `yolo-weight`; trained from an earlier in-house checkpoint |
| `brassicaceae_leaf_keypoint.pth` | ResNet-18 with a 4-channel input (RGB + distance transform of the leaf polygon) and a heatmap head for leaf base and tip | Leaf-to-plant assignment (`vendor/` holds the model code) | This repository, release `keypoint-weight` |
| `genyolo_leaf_yolov11m.pt` | GenYOLO-Leaf YOLO11m-seg | Leaves outside the routing circle | Not redistributed here: downloaded from the authors' release <https://github.com/aaslihanyildirim/GenYOLO-Leaf/releases/tag/shared_best_models> |

The three in-house models were trained with Ultralytics 8.3.228 (segmentation) and PyTorch (keypoint model). The release files hold the trained parameters unchanged; stored training paths and run names were removed.

## License

The three in-house weights are released under the GNU Affero General Public License v3.0 (AGPL-3.0), the license of this repository and the license that Ultralytics records in its model files. `brassicaceae_leaf_seg.pt` is in addition a derivative of the GenYOLO-Leaf weights, whose BSD 3-Clause notice is reproduced below.

## Training records inside the files

Each file keeps its training settings and per-epoch curves. They can be read in the `bgp-imaging` environment:

```
python -c "import torch; ck = torch.load('imaging/weights/brassicaceae_leaf_seg.pt', weights_only=False); print(ck['train_args']); print(ck['train_metrics'])"
python -c "import torch; ck = torch.load('imaging/weights/brassicaceae_leaf_keypoint.pth', weights_only=False); print({k: v for k, v in ck['metadata'].items() if k != 'history'})"
```

- Segmentation models: `train_args` (settings), `train_metrics` (final metrics), `train_results` (per-epoch curves).
- Keypoint model: `metadata`, with the per-epoch curves in `metadata['history']`.

The metrics stored in the files are computed on the validation split used during training. The manuscript reports the segmentation performance on a separate test split, so the numbers differ.

## GenYOLO-Leaf

`genyolo_leaf_yolov11m.pt` and the starting point of `brassicaceae_leaf_seg.pt` are from GenYOLO-Leaf:

Yıldırım, A., & Terzi, R. (2026). GenYOLO-leaf: a data-centric and open source framework for generalizable leaf instance segmentation across diverse datasets. *The Visual Computer*, 42(2), 145. <https://doi.org/10.1007/s00371-025-04351-4>

`brassicaceae_leaf_seg.pt` is a derivative of the GenYOLO-Leaf weights and is distributed with their copyright notice and license:

```
BSD 3-Clause License

Copyright (c) 2025, aaslihanyildirim

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```
