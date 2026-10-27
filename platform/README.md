# platform

PostgreSQL database, Redis cache, FastAPI backend and React web interface behind Nginx, run with Docker Compose, plus the loader (`ingest/`) that writes trait records into the database.

## Start

Requires Docker with Compose v2. Run the imaging steps first (`../imaging/README.md`), then:

```
cd platform
cp .env.template .env
docker compose up -d --build database redis api-service frontend
```

`.env` holds the database password (`DB_PASSWORD`, `change-me` in the template). It is fixed when the database volume is first created; to change it later, remove the volume with `docker compose down -v`, which deletes the data.

- Web interface: <http://127.0.0.1:3000>
- API documentation: <http://127.0.0.1:3000/api/v1/docs>

On the first start, the database is created from `database/init/`: `01-schema.sql` holds the schema and `02-seed.sql` the reference rows the demo plant needs (growth chambers, rack, camera, growth condition, treatment and accession s0123).

## Register the demo batch

`../demo/batch_2025B08.json` registers the batch of the demo plant: accession s0123, treatment Control, four plants, nursery in chamber R141 and imaging in G120 under camera A2-104. Only plant 3 has demo images. Either:

- open the API documentation, choose **POST /api/v1/admin/batches**, paste the file and execute; `/api/v1/admin/batches/preview` shows what would be written without writing; or
- open **Batch Registration → New batch** in the web interface and enter the same values.

The camera of each plant is derived from its rack, so the file gives rack `A1_2` and no camera.

## Load traits

Run from `platform/` in the imaging environment, on the same machine as the containers (the loader talks to the `bpp-database` container through `docker exec`):

```
conda activate bgp-imaging
python -m ingest.load --batch 2025B08           # dry run: writes, reports, then rolls back
python -m ingest.load --batch 2025B08 --apply   # writes
```

The loader reads `../imaging/out/staging_traits_2025B08.csv`. It finds each plant by batch, accession and replicate, takes the camera from the plant's position record, and computes days after sowing from the plant's nursery entry date. It stops without writing if any row cannot be matched to exactly one plant and one camera. Each run is recorded with its pipeline version.

A rerun overwrites the records of the same plant, camera and capture time. If traits are recomputed from an empty `qc/qc.sqlite`, reviewed records go back to `auto`, so keep the same `qc.sqlite` when loading again.

## Browse and export

- **Cultivar Search** lists the accession.
- **Plant Viewer**: choose batch 2025B08, cultivar s0123, treatment Control, replicate 3. The images, trait curves and the segmentation overlay toggle are on this page.
- **Export Data** writes a CSV with a provenance JSON recording the sampling recipe, contributing plants and days, quality-control filter and pipeline version. `../analysis/README.md` shows the daily export used for growth-curve traits.

## Settings

| Variable (`.env`) | Default | Effect |
|---|---|---|
| `BPP_OPERATOR` | `admin` | Name recorded as the operator in batch milestones, export provenance and logs |
| `CROPS_DIR` | `../demo/crops` | Single-plant images shown in the plant viewer |
| `OVERLAY_DIR` | `../demo/raspi_RGB_overlay` | Overlay images from `imaging/overlays/render_overlays.py` |
| `ENVIRONMENT` | `development` | `production` turns batch registration off |

The web interface listens on 127.0.0.1:3000 and the API on 127.0.0.1:8000. There is no login, so keep both on the local machine or a trusted network. The database and Redis are reachable only from the other containers, not from the host; to query the database, run `docker exec -it bpp-database psql -U phenouser plant_phenotyping`.
