# Brassica Germplasm Phenotyping

An image-based platform that links Brassica germplasm records, plant images, and trait data.

This repository contains the code for the manuscript:

> **An image-based phenotyping platform for *Brassicaceae* germplasm characterization**
>
> Chen-Feng Yen, Ruei-Shiuan Wang, Te-Chang Hsu, Po-Xing Zheng, Hsuan-Wei Kao, Jheng-Yan Ou, Yu-Lin Wu, Yao-Cheng Lin

We developed a system that links crop accessions to repeated plant images, measured traits and growing conditions. Software detects leaves and assigns them to individual plants, with assignments checked and corrected by an operator. The system measures traits from individual images and tracks changes over time. We tested it with diverse *Brassicaceae* accessions and compared traits across seven crop groups. Users can inspect the images behind each measurement and export the linked records for further study.

Developed by the [Bioinformatics & Computational Genomics Group](https://www.southerngenomics.org/home).

> **Status:** under preparation. The imaging workflow, review tool, platform, analysis script and demo data are available; the model weights are attached to this repository's GitHub Releases.

## Contents

| Directory | Contents |
|---|---|
| `imaging/` | Leaf segmentation, leaf-to-plant assignment, 2D trait extraction and overlay images (command line; GPU recommended, CPU supported) |
| `qc/` | Browser tool for reviewing the leaf-to-plant assignment |
| `platform/` | Database, web interface and API (Docker Compose), and the loader that writes traits into the database |
| `analysis/` | Growth-curve traits computed from the platform's daily trait export |
| `demo/` | 69 single-plant images of one plant over six days, and the metadata to register its batch |

## Run the demo

The steps follow the data. Each module's README has the details.

```
demo/crops (single-plant images)
  |  imaging/README.md    build.py -> qc/server.py (optional review) -> traits.py -> render_overlays.py
  v
imaging/out/staging_traits_2025B08.csv, demo/raspi_RGB_overlay/
  |  platform/README.md   docker compose up -> register the batch -> ingest -> browse and export
  v
daily trait export (CSV + provenance JSON)
  |  analysis/README.md   growth_params.py
  v
growth-curve traits per plant
```

Run the imaging steps before starting the platform: the platform mounts the overlay directory, and Docker creates a missing directory as root, which the overlay script then cannot write to.

## Scope of this release

- **The demo starts from single-plant crops.** Raw camera frames and the script that matched frames to plants and cut the crops are not included. The plant positions and time windows that drive this matching are stored in the database and shown on the batch pages.
- **Environmental sensor records are not imported.** The database tables and the environment export are included, but the import script is not, and the demo batch has no environment records.
- **Time-series traits:** the ten growth-curve traits are computed by `analysis/growth_params.py`. The nine canopy-closure traits are not included in this release.
- **Statistical analyses** (validation of the automatic assignment against manual review, the collection survey) are not part of this release.
- **The demo covers six imaging days.** Time-series traits computed from it therefore differ from values computed over a plant's full imaging period.

## Names

The web interface is titled *Plant Phenotyping Platform*. `bpp` is the code name used in container, database, environment-variable and export file names.

## Security

The platform has no login: every request acts as one operator, and anyone who can reach the services can write to the database. The services bind to 127.0.0.1; to use them from another machine, forward the ports over SSH, for example `ssh -L 3000:127.0.0.1:3000 <host>`.

## License

GNU Affero General Public License v3.0 (AGPL-3.0). See [LICENSE](LICENSE).
