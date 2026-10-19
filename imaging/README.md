# imaging

Command-line image processing for single-plant images: leaf segmentation and ownership (`build.py`, `core.py`, `vendor/`), 2D traits (`traits_2d/`) and overlays (`overlays/`). The leaf-level review UI that sits between ownership and traits is in `../qc/`.

```
demo/crops/<batch>/<accession>/<treatment>/rep-<n>/*.png
  -> build.py              segmentation + ownership -> qc/data/<same 4 levels>/frames.json
  -> qc/server.py          optional review in the browser -> qc/qc.sqlite
  -> traits_2d/traits.py   2D traits per image -> imaging/out/staging_traits_<batch>.csv
  -> overlays/render_overlays.py   overlay images for the platform plant viewer
```

## Setup

```
conda env create -f imaging/environment.yml
conda activate bgp-imaging
python imaging/download_weights.py
```

`download_weights.py` puts four weights in `imaging/weights/` and checks each file's SHA-256. Three are ours and come from this repository's GitHub Release. The fourth, GenYOLO-Leaf (`genyolo_leaf_yolov11m.pt`), is downloaded from its authors' release at <https://github.com/aaslihanyildirim/GenYOLO-Leaf>; it is not redistributed here.

The first run of `build.py` also downloads the ImageNet weights for ResNet-18 through torchvision, so the machine needs internet access once.

## Run the demo

Run from the repository root. The demo is one plant (accession s0123, plant 3) photographed over six days; see `../demo/README.md`.

```
export RASPI_ROOT=$PWD/demo/crops
python imaging/build.py --batch 2025B08
python qc/server.py --host 127.0.0.1 --port 8090
python imaging/traits_2d/traits.py --batch 2025B08
python imaging/overlays/render_overlays.py --batch 2025B08 --effective
```

1. `build.py` writes `qc/data/2025B08/s0123/Control/rep-3/frames.json`: every leaf polygon in the 69 images with its automatic keep or reject decision.
2. `qc/server.py` is optional. Open <http://127.0.0.1:8090>, review leaves and mark the plant as reviewed; the decisions go to `qc/qc.sqlite`. Stop the server with Ctrl+C.
3. `traits.py` writes `imaging/out/staging_traits_2025B08.csv` with one row per image. Leaves you rejected in the review are left out, and the rows are marked `verified` once the plant is marked reviewed, otherwise `auto`. Images in which no leaf was detected produce no row; on a GPU every demo image has leaves, so the demo gives 69 rows.
4. `render_overlays.py` writes one transparent overlay per image to `demo/raspi_RGB_overlay/`: retained leaves in green, rejected leaves in red. `--effective` applies your review decisions. The platform shows these overlays in the plant viewer, so run this step before starting the platform (`../platform/README.md`).

`build.py` skips a plant whose `frames.json` already exists; add `--force` to run it again.

## Paths

Every path can be changed with an environment variable. The defaults are inside the repository.

| Variable | Default | Content |
|---|---|---|
| `RASPI_ROOT` | `raspi_RGB/` at the repository root | Single-plant images, `<batch>/<accession>/<treatment>/rep-<n>/*.png` |
| `QC_ROOT` | `qc/` | `data/` for `frames.json`, and `qc.sqlite` for review decisions |
| `WEIGHTS_DIR` | `imaging/weights/` | The four model weights |
| `OUT_DIR` | `imaging/out/` | Trait CSV files |
| `OVERLAY_ROOT` | `raspi_RGB_overlay/` next to `RASPI_ROOT` | Overlay images from `overlays/render_overlays.py` |

## GPU or CPU

We recommend running inference on a GPU. On a machine without one, `build.py` falls back to the CPU automatically, but the results will float slightly.

- The GPU reproduces the published `frames.json` exactly for the demo plant: detections, keep decisions, track IDs and polygons.
- On the CPU, leaf masks differ at their edges (median IoU 0.96 against the GPU masks), a few frames gain or lose one leaf, and the daily mean kept leaf area differs by up to about 7%, most on the first demo day, when the leaves are smallest.
- The cause is floating-point differences between the two devices, not the confidence threshold. Confidence scores agree to within 0.002.
- Track IDs can change on the CPU, so QC overrides recorded on one device's output do not carry over to the other device's output.

For the 69 demo images, inference takes about 23 s on an NVIDIA RTX A2000 and about 84 s on a 12-core Intel Xeon w3-2423.
