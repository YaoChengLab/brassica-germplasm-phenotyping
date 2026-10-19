# Leaf ownership review

`server.py` is a browser-based tool for reviewing the leaf-to-plant assignment produced by `imaging/build.py`. For each plant it shows every detected leaf with its automatic keep or reject decision; the reviewer can overturn a decision, and the plant's daily leaf count and leaf area are recomputed immediately. The tool does not import torch and needs no GPU.

To run it on the demo, follow `../imaging/README.md`.

## Run

```
python qc/server.py --host 127.0.0.1 --port 8090
```

Then open <http://127.0.0.1:8090>. Anyone who can reach the port can write review decisions, so keep the server on localhost or a trusted network.

| Variable | Default | Content |
|---|---|---|
| `QC_ROOT` | `qc/` | Holds `data/` (the `frames.json` files written by `build.py`) and `qc.sqlite` |
| `RASPI_ROOT` | `QC_ROOT/raspi_RGB`, else `../raspi_RGB` next to `QC_ROOT` | Single-plant images, `<batch>/<accession>/<treatment>/rep-<n>/*.png` |

## What is stored

Review decisions are written to `QC_ROOT/qc.sqlite`. `frames.json` is never modified, so the automatic result stays available.

| Table | Content |
|---|---|
| `leaf_override(plant_id, tid, state)` | Manual keep (1) or reject (0) for one leaf track; `tid` is `<date>#<track index>` |
| `leaf_class(plant_id, tid, klass)` | Leaf class, currently `cotyledon` |
| `reviewed(plant_id, ts)` | Plant marked as reviewed |
| `cotyledon_done(plant_id, ts)` | Cotyledon marking finished for the plant |
| `note(plant_id, text, ts)` | Free-text note on the plant |

`imaging/traits_2d/traits.py` reads these tables when it computes traits: rejected leaves are left out, and rows of a reviewed plant are marked `verified`.

A track ID depends on the order in which `build.py` writes its output. Overrides therefore belong to the `frames.json` they were made on; after `frames.json` is rebuilt, for example on a different device, start the review again from an empty `qc.sqlite`.
