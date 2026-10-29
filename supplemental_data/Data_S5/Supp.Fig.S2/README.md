# Figure S2

Re-draw (Python 3 with NumPy and Matplotlib), from this folder:

```
python figures/plot_ownership_twobatch.py --data data --out output
```

| File | Rows | Content |
|---|---|---|
| `data/ownership_twobatch_summary.csv` | 2 | Per batch: the four counts (TP, FP, FN, TN), agreement, false-reject rate and false-keep rate of automatic ownership against manual review; share of trajectories changed in review; per-image detection counts |
| `data/ownership_twobatch_by_das.csv` | 51 | Per batch and day after sowing: the four counts, agreement, false-reject rate and false-keep rate of automatic ownership |
| `data/ownership_twobatch_cotyledon.csv` | 84 | Per batch and accession, and pooled: false-reject rate of cotyledons and true leaves on the same plant-days |

The commands above create an `output/` folder. Figure scripts write PNG, PDF and SVG. Table scripts write Markdown and JSON. Panel letters and labels added during figure assembly are not regenerated.

Prepared inputs are bundled in `data/`. Raw extraction scripts and databases are not included. See the [package README](../README.md) for scope.
