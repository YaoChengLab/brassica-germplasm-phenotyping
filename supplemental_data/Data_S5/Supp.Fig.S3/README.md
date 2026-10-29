# Figure S3

Re-draw (Python 3 with NumPy and Matplotlib), from this folder:

```
python figures/plot_s0232_trajectories.py --data data --out output --only s3
```

| File | Rows | Content |
|---|---|---|
| `data/s0232_daily_by_plant.csv` | 336 | Accession s0232, batch 2025B08: daily mean of 12 per-image traits (leaf count, projected leaf area, solidity and the nine traits of Figure S3) per plant, day after sowing and leaf selection |
| `data/s0232_timeseries_features.csv` | 12 | Accession s0232, batch 2025B08: four time-series features per plant and leaf selection |

The commands above create an `output/` folder. Figure scripts write PNG, PDF and SVG. Table scripts write Markdown and JSON. Panel letters and labels added during figure assembly are not regenerated.

Prepared inputs are bundled in `data/`. Raw extraction scripts and databases are not included. See the [package README](../README.md) for scope.
