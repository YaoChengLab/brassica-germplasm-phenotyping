# Supplemental Data S2: fresh weight and image traits

`Table_units_269.csv` contains 269 accession–batch means from 257 accessions
in 12 batches. Each row represents one accession in one batch. These data
support the fresh-weight analysis in Figure 7.

The table includes plant counts, image and harvest times, mean fresh weight
and its standard deviation, and image traits. Fresh weight is in grams,
projected leaf area is in square pixels, and observation times are in days
after sowing. The field definitions and units are listed below.

Image traits and fresh weights were averaged separately within each
accession–batch group. They are not paired measurements from individual plants.
All rows are included in the main analysis (`in_model = True`), so
`exclusion_reason` is blank.

Harvest times for 2025B13 were corrected to 2025-12-18 (37 days after sowing)
after the original preparation. This changed `harvest_das` and `harvest_gap_d`
in 11 rows; the fresh-weight and image-trait values used in the models are
unchanged.

## Field definitions

| Field | Definition | Unit |
|---|---|---|
| `batch` | Batch identifier | code |
| `accession` | Accession identifier; the same accession can occur in more than one batch | code |
| `crop_type` | Crop-group label | category |
| `genome` | Genome label (AA, AABB, AACC, BBCC, CC or nd) | category |
| `n_plants_img` | Number of plant image-trait records used to calculate the accession–batch means | count |
| `n_plants_fw` | Number of valid fresh-weight records used to calculate the accession–batch mean | count |
| `das_ref` | Batch image summary time | days after sowing |
| `harvest_das` | Mean harvest time for fresh-weight records | days after sowing |
| `harvest_gap_d` | Mean harvest time minus image summary time (harvest_das minus das_ref) | days |
| `fw_mean_g` | Mean fresh weight within the accession–batch group | g |
| `fw_sd_g` | Standard deviation of fresh weight within the accession–batch group | g |
| `area_ref` | Mean projected leaf area across plants at the batch summary date | px² |
| `count_ref` | Mean visible leaf count across plants at the batch summary date | count |
| `solidity` | Mask-area to convex-hull-area ratio, averaged over the summary window and across plants | dimensionless |
| `ellipse_aspect_ratio` | Fitted-ellipse aspect ratio, averaged over the summary window and across plants | dimensionless |
| `excess_green_index` | Excess green index, averaged over the summary window and across plants; image color is uncorrected | digital-number index |
| `rgr_slope` | Slope of ln(daily mean projected leaf area) against days after sowing over the imaging window, averaged across plants | day⁻¹ |
| `in_model` | Main-analysis inclusion flag; True for all rows in this table | boolean |
| `exclusion_reason` | Reason for exclusion from the main analysis; blank for all rows in this table | text |
