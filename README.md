# Brassica Germplasm Phenotyping

An image-based platform that links Brassica germplasm records, plant images, and trait data.

This repository contains the code for the manuscript:

> **An image-based phenotyping platform for *Brassicaceae* germplasm characterization**
>
> Chen-Feng Yen, Ruei-Shiuan Wang, Te-Chang Hsu, Po-Xing Zheng, Hsuan-Wei Kao, Jheng-Yan Ou, Yu-Lin Wu, Yao-Cheng Lin

We developed a system that links crop accessions to repeated plant images, measured traits and growing conditions. Software detects leaves and assigns them to individual plants, with assignments checked and corrected by an operator. The system measures traits from individual images and tracks changes over time. We tested it with diverse *Brassicaceae* accessions and compared traits across seven crop groups. Users can inspect the images behind each measurement and export the linked records for further study.

Developed by the [Bioinformatics & Computational Genomics Group](https://www.southerngenomics.org/home).

> **Status:** under preparation. The imaging workflow (`imaging/`, `qc/`, `demo/`) is available; the platform and the model weights will be added in upcoming commits.

## Planned contents

| Directory | Contents |
|---|---|
| `platform/` | Database schema, backend API, web interface, validated data ingestion, Docker Compose deployment |
| `imaging/` | Leaf segmentation, leaf-to-plant assignment and 2D trait extraction (command line; GPU recommended, CPU supported) |
| `qc/` | Browser-based review tool for leaf-to-plant assignment |
| `demo/` | Single-plant example images for testing the imaging workflow |

## License

GNU Affero General Public License v3.0 (AGPL-3.0). See [LICENSE](LICENSE).
