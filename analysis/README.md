# analysis

Downstream analysis of the platform's trait export. The platform stores per-image traits; growth-curve traits are fitted here from the daily series.

## Growth-curve traits

`growth_params.py` computes ten traits per plant: emergence rate, leaf count and area at the batch reference day, slopes of area and ln(area) against days after sowing, the plateau ratio, and the Gompertz parameters A, t_inf, maximum absolute growth rate and relative growth rate at 50%. Formulas are in the script's header.

1. Export a daily series for the batch, either from **Export Data** in the web interface (*Which days* `all`, *Image within a day* `all`, *Merge to* `day`, traits `leaf_area` and `leaf_count`) or directly:

   ```
   curl -o daily_2025B08.csv "http://127.0.0.1:3000/api/v1/export/traits.csv?batch_codes=2025B08&level=day&day_mode=all&frame_pick=all&traits=leaf_area,leaf_count"
   ```

2. Run the script in the imaging environment (numpy and scipy only):

   ```
   python analysis/growth_params.py daily_2025B08.csv growth_2025B08.csv
   ```

The Gompertz fit needs at least five days and the plateau ratio at least six. The batch reference day is the last day on which every exported plant still has data, so it depends on which plants are exported. The demo plant has six imaging days, so its values differ from values computed over its full imaging period.
