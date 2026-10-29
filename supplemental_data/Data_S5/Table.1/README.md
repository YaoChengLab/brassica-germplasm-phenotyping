# Table 1 and Table S6

Re-build (Python 3), from this folder:

```
python tables/make_table1_s6.py --data data --out output
```

The output is the full Table S6; Table 1 in the main text reports a subset of its rows.

| File | Rows | Content |
|---|---|---|
| `data/ownership_twobatch_summary.csv` | 2 | Per batch: the four counts (TP, FP, FN, TN), agreement, false-reject rate and false-keep rate of automatic ownership against manual review; share of trajectories changed in review; per-image detection counts |
| `data/ownership_twobatch_cotyledon.csv` | 84 | Per batch and accession, and pooled: false-reject rate of cotyledons and true leaves on the same plant-days |
| `data/ownership_twobatch_by_accession.csv` | 40 | Per batch and accession: the four counts, agreement, false-reject rate and false-keep rate of automatic ownership |

The commands above create an `output/` folder. Figure scripts write PNG, PDF and SVG. Table scripts write Markdown and JSON. Panel letters and labels added during figure assembly are not regenerated.

Prepared inputs are bundled in `data/`. Raw extraction scripts and databases are not included. See the [package README](../README.md) for scope.
