# Supplemental Data S3: six-trait survey of 258 accessions

These tables support Figure 6 and the collection-wide survey in Sections 2.6 and 3.5.
Methods are in Supplementary Methods S9.

| File | Rows | Content |
|---|---|---|
| `fig6_plant_traits.csv` | 1,114 | One row per plant: batch, accession, crop group, genome, plant ID, the batch summary date and the six traits |
| `fig6_accession_traits.csv` | 258 | One row per accession, one point in Figure 6: the mean of the accession's plants in `fig6_plant_traits.csv` |

## Columns

| Column | Meaning | Unit |
|---|---|---|
| `batch` | Batch identifier (plant table only) | code |
| `accession` | Accession identifier | code |
| `crop_type`, `crop_code` | Crop group and its two-letter code in Figure 6 (`crop_code` in the accession table only) | category |
| `genome` | Genome label recorded on the platform; `nd`, not recorded | category |
| `plant_id` | Plant identifier within the batch and accession (plant table only) | code |
| `das_ref` | Batch summary date (plant table only) | days after sowing |
| `n_plants` | Plants averaged into the accession row | count |
| `n_batches`, `batches` | Number and identifiers of the batches contributing plants | count, code |
| `area_ref` | Projected leaf area: daily means interpolated to the summary date | px² |
| `count_ref` | Visible leaf count: daily means interpolated to the summary date | count |
| `solidity` | Mask area divided by convex-hull area, averaged over the images of the summary date and the two preceding days | dimensionless |
| `ellipse_aspect_ratio` | Major-to-minor axis ratio of the fitted ellipse, averaged over the same three days | dimensionless |
| `excess_green_index` | ExG = 2G − R − B from the 8-bit channel values, averaged over the same three days; colour is uncorrected | digital number |
| `rgr_slope` | Relative growth rate: slope of ln(daily mean projected leaf area) against days after sowing over the plant's imaging window | day⁻¹ |

An accession grown in more than one batch pools the plants of all its batches, so
batches with more plants carry more weight. Projected leaf area is in pixels and is not
calibrated to physical area.
