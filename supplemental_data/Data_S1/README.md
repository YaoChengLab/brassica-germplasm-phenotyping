# Supplemental Data S1: example export for 64 plants in 2025B08

`Supp.Data.S1.csv` and `Supp.Data.S1_manifest.json` are one CSV export from the
platform and its JSON record, as described in Section 3.1 and Supplementary Methods S7.

## Export settings

- Batch 2025B08, all 64 plants of 16 accessions.
- Seven imaging days: 16, 18, 20, 22, 24, 26 and 28 days after sowing (DAS).
- One image per plant and day, nearest to 12:00; 448 images in total.
- Values are averaged per plant over the seven days, giving one row per plant.
- Quality-control states `auto` and `verified`; all records in this batch were manually
  verified (`all_verified`).
- Pipeline version `traits_2d@2026-07-13`.

## Files

| File | Content |
|---|---|
| `Supp.Data.S1.csv` | 64 rows, one per plant: plant key (batch, accession, treatment, replicate, plant ID), contributing days and images, and the per-image traits |
| `Supp.Data.S1_manifest.json` | The export record: sampling settings (`recipe`), plant selection, columns, days and images used per plant (`coverage`), pipeline version and notes |

Column names are the platform's trait identifiers. Trait definitions, formulas and
units are in Table S4. Values are in pixels or pixel-derived units; they are not
converted to physical units.

In the manifest, `recipe.day_mode` is `list`, so the days are taken from `das_list`.
The field `n_days: 4` is a default that applies only to other day modes and was not
used for this export.
