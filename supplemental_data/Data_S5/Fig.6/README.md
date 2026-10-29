# Figure 6

Re-draw (Python 3 with NumPy and Matplotlib; pandas and SciPy), from this folder:

```
python figures/plot_trait_splom.py --data data --out output
python tables/stats_fig6.py --data data --out output
```

| File | Rows | Content |
|---|---|---|
| `data/fig6_accession_traits.csv` | 258 | One row per accession (one point of Fig. 6, 258 accessions of seven crop types): crop type and code, genome, number of plants and batches, and the six plotted traits in original units, taken at each batch's reference day; see README for columns, units and the rule |
| `data/fig6_plant_traits.csv` | 1114 | One row per plant of the 258 accessions: batch, accession, crop type, genome, plant ID, the batch's reference day (das_ref) and the six traits; the accession values of fig6_accession_traits.csv are the means of these rows |

The commands above create an `output/` folder. Figure scripts write PNG, PDF and SVG. Table scripts write Markdown and JSON. Panel letters and labels added during figure assembly are not regenerated.

Prepared inputs are bundled in `data/`. Raw extraction scripts and databases are not included. See the [package README](../README.md) for scope.

`tables/stats_fig6.py` writes the statistics quoted in Section 2.6 to `output/fig6_stats_*.csv` (definitions in Supplementary Methods S9).

## Fig. 6 tables: columns and units

`fig6_accession_traits.csv`, one row per accession (one point in Fig. 6):

| Column | Meaning | Unit |
|---|---|---|
| `accession` | accession code | — |
| `crop_type`, `crop_code` | crop type (common name) and its two-letter code in the figure | — |
| `genome` | genome type as recorded on the platform (`nd` = not recorded) | — |
| `n_plants` | plants averaged into this row | plants |
| `n_batches`, `batches` | number and codes of the batches the accession was grown in | — |
| `area_ref` | projected leaf area (PLA): daily means interpolated to the batch's reference day | px² (not calibrated to physical area) |
| `count_ref` | leaf count: daily means interpolated to the batch's reference day | leaves |
| `solidity` | plant area divided by convex hull area: mean over the images of the reference day and the two days before | dimensionless |
| `ellipse_aspect_ratio` | major to minor axis of the fitted ellipse: mean over the same three days | dimensionless |
| `excess_green_index` | ExG = 2G − R − B from the mean 8-bit channel values: mean over the same three days | DN (8-bit digital number) |
| `rgr_slope` | relative growth rate (RGR): slope of ln(daily PLA) against days after sowing over the plant's whole imaging window | day⁻¹ |

Only images with at least one kept leaf carry trait values, so a plant's last day is its
last day with trait values, not its last imaging day. The reference day of a batch is the
last day with trait values for at least 90% of its plants (the 10th percentile of the
plants' last days). All 13 hourly images of a day (06:00–18:00) are used. Plants whose
trait values end before the reference day, start after it, or are missing from the
three-day window are left out; for Fig. 6 these are 9 plants: B03 s0031 (1) and s0060 (2),
B06 s0091 (1) and s0092 (3), B12 s0329 (2). Their images continue to the end of the batch,
but those of the last days contain no kept leaf.

| Batch | Reference day (DAS) |
|---|---|
| 2025B03 | 28 |
| 2025B04 | 32 |
| 2025B05 | 29 |
| 2025B06 | 21 |
| 2025B07 | 27 |
| 2025B08 | 39 |
| 2025B09 | 38 |
| 2025B10 | 29 |
| 2025B11 | 39 |
| 2025B12 | 48 |
| 2025B13 | 37 |
| 2025B14 | 41 |

`fig6_plant_traits.csv` has the same six traits for each plant, with `batch`,
`accession`, `crop_type`, `genome`, `plant_id` and `das_ref` (the batch's reference
day). Each accession value is the mean of its plants' rows. For an accession grown in
more than one batch the plants of all its batches are pooled, so batches with more
plants weigh more; this differs from a mean of batch means only for s0031, s0060,
s0091, s0092, s0145 and s0232. Trait definitions are given in Supplementary Table S4.
