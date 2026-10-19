# Brassica Germplasm Phenotyping

An image-based platform that links Brassica germplasm records, plant images, and trait data.

> **Status:** under preparation. The imaging workflow (`imaging/`, `qc/`, `demo/`) is available; the platform, the license file and the model weights will be added in upcoming commits.

## Planned contents

| Directory | Contents |
|---|---|
| `platform/` | Database schema, backend API, web interface, validated data ingestion, Docker Compose deployment |
| `imaging/` | Leaf segmentation, leaf-to-plant assignment and 2D trait extraction (command line; GPU recommended, CPU supported) |
| `qc/` | Browser-based review tool for leaf-to-plant assignment |
| `demo/` | Single-plant example images for testing the imaging workflow |

## License

AGPL-3.0. The license file will be added together with the source code.
