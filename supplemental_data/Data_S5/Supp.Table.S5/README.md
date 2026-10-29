# Table S5

Re-build (Python 3), from this folder:

```
python tables/make_table_s5.py --data data --out output
```

| File | Rows | Content |
|---|---|---|
| `data/detection_test.json` | — | Detection model: test-set metrics |
| `data/keypoint_v8_eval_per_leaf.csv` | 1058 | Keypoint model: per-leaf errors; rows with role == holdout form the test set |

The commands above create an `output/` folder. Figure scripts write PNG, PDF and SVG. Table scripts write Markdown and JSON. Panel letters and labels added during figure assembly are not regenerated.

Prepared inputs are bundled in `data/`. Raw extraction scripts and databases are not included. See the [package README](../README.md) for scope.
