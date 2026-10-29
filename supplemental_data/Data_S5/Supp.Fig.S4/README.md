# Figure S4

Re-draw (Python 3 with NumPy and Matplotlib), from this folder:

```
python figures/plot_dead_plant.py --data data --out output
```

| File | Rows | Content |
|---|---|---|
| `data/dead_plant_s0124_noon.csv` | 104 | Accession s0124, batch 2025B08: one row per plant (four plants) and day, for the 12:00 image of each day (days 13-38 after sowing): date, day after sowing, leaf count, projected leaf area and quality-control state; these are the values of the images in Figure S4(c) on the days shown there |
| `data/dead_plant_s0124_tiles.json` | 20 | Accession s0124, batch 2025B08: for each of the 20 images (four plants, five days, 12:00) the image file, the number of detections, of leaves kept automatically and after manual review, and the polygons of the leaves kept after manual review |

The 20 source images named in `dead_plant_s0124_tiles.json` are not included, so the script
draws panels a and b and skips the image tiles of panel c. Placing the images in
`data/dead_plant_images/` restores panel c.

The commands above create an `output/` folder. Figure scripts write PNG, PDF and SVG. Table scripts write Markdown and JSON. Panel letters and labels added during figure assembly are not regenerated.
Prepared inputs are bundled in `data/`. Raw extraction scripts and databases are not included. See the [package README](../README.md) for scope.
