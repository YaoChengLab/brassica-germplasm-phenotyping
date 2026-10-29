# Figure 7 and fresh-weight models

Rebuild Figure 7, the concise Table S7, and the full model checks from the bundled data.
This folder can be copied and run on its own.

## Run

Use Python 3.12. The verified run used Python 3.12.14 on macOS ARM64.
From this folder:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run_all.py
```

On Windows, use `.venv\Scripts\python.exe` in place of `.venv/bin/python`.
Installing the packages requires an internet connection. The analysis itself runs offline.
The default run uses seeds 0–49 and performs 50 repetitions of 10-fold cross-validation for four models in each of two analyses. It can take several minutes.

An optional output location is supported:

```sh
.venv/bin/python run_all.py --output rerun_outputs
```

The script resolves data paths relative to its own location, not the current working directory.
It writes generated results to the selected output folder. It does not change the bundled data.

## Main outputs

| File | Contents |
|---|---|
| `outputs/Fig7.png`, `.pdf`, `.svg` | Two-panel Figure 7, with `(a)` / `(b)` labels and lowercase *p* |
| `outputs/Table_S7.xlsx` | Seven-row table with definitions and footnotes |
| `outputs/Table_S7.csv` | The same seven rows in plain text |
| `outputs/Table_S7_notes.txt` | Table title and notes |
| `outputs/Table_S7_preview.png` | Readable table preview |
| `outputs/Model_details.xlsx` | Full model statistics, tests, coefficients and batch fits |
| `outputs/Detailed_model_statistics.csv` | All 20 statistics from the original S7, recalculated |
| `outputs/verification.json` | Comparison with the archived results and input/CV checks |
| `outputs/environment.json` | Python and package versions used in the run |

Each analysis has its own folder: `outputs/all_batches/` and `outputs/without_B12_B13/`.
These contain:

- `summary.json`: exact model comparisons, correlation interval, and sensitivity results.
- `Model_checks.png` / `.pdf`: residuals versus fitted values, normal Q–Q plot, residuals versus leverage, and Cook's distance.
- `Model_checks.csv`: nested F, clustered Wald, slope-interaction, Shapiro–Wilk and Breusch–Pagan tests.
- `Residuals_and_influence.csv`: fitted values, residuals, leverage and Cook's distance for each analysis unit.
- `Figure7_plot_data.csv`: batch-adjusted coordinates and mean cross-validation predictions.
- `CV_folds.csv`: the fold for each accession–batch unit in each repetition.
- `CV_repeat_metrics.csv`: R² and root mean squared error for each model and repetition.
- Full-precision association, coefficient, model and batch-statistic CSV files, plus original-format rounded exports.
- `fw_model_v2_log.txt` and `execution.log`: model output and execution messages.

## Data and scope

`data/Table_units_269.csv` is the archived model input: **269 accession–batch means, 257 accessions, 12 batches**. It was saved at six significant digits. It contains 1,074 image records and 1,056 weighed plants in the included units; these counts describe separate sets of plants.

`data/fig6_plant_traits.csv` contains the supplied per-plant image summaries. The script checks their accession–batch averages against the model input. It also uses these records for the original plant-level batch diagnostics. It does not extract traits from images.

**The package starts from accession–batch means.** The raw fresh-weight records
are not included. The original dead/missing/zero-weight
exclusions and fresh-weight averaging therefore cannot be rerun from this package.
The scripts reproduce the statistical analysis from the prepared data.

Image and fresh-weight values were averaged separately by accession within batch because plant replicate identifiers could not be confirmed between sources. No plant-level pairing is inferred. Harvest timing is retained in the data and is not corrected.

`data/data_dictionary.csv` defines the fields. `data/provenance.json` records SHA-256 checksums of the inputs and references, and the 2025B13 harvest-date correction. The original filenames, accession codes, batch codes and crop labels are preserved. The prepared data do not contain treatment, QC-state or pipeline-version columns; these are not inferred.

## Analysis

The response is natural-log fresh weight. Projected leaf area is also natural-log transformed. All models include a batch fixed effect:

- **M0:** batch only.
- **M1 (area model):** M0 + ln(projected leaf area).
- **M2 (extended model):** M1 + standardized leaf count + standardized solidity.
- **M2_aspect:** M1 + standardized leaf count + standardized aspect ratio.

The second analysis excludes 2025B12 and 2025B13 and contains 221 units, 211 accessions and 10 batches. Both analyses retain the original 50 repetitions and seeds 0–49. All records from an accession stay in the same fold. Training/test accession separation and representation of test batches in training data are checked.

R² and RMSE are calculated on the ln(fresh weight) scale. Their means and SDs are calculated across repetitions; SD uses `ddof=0`, as in the original script. Panel (b) exponentiates the **mean predicted log weight** across repetitions. It does not average predictions after exponentiation or apply a retransformation bias correction. Cross-validation tests held-out accessions within represented batches; it does not test new batches.

The nested F test compares the fitted area and extended models. The Wald test uses accession-clustered standard errors and a chi-square statistic with 2 degrees of freedom. Slope and coefficient confidence intervals also use clustered standard errors. The partial-correlation interval is the original approximate Fisher z interval with standard error `1/sqrt(n - number_of_batches - 2)`; it is **not** a clustered interval. The simpler S7 footnote makes this distinction explicit.

The original residual-Pearson p-values and Bonferroni adjustment for six traits are retained. The diagnostic Spearman statistic is the pooled correlation of within-batch ranks, as in the original script. These calculations are reproduced without changing the analysis design.

Full details retain the original prediction-error statistic under `CV_median_abs_pct_err`: `100 * median(abs(observed / predicted - 1))`. Its denominator is predicted weight, not observed weight. The batch diagnostic threshold `371² px²` is inherited from the original code and is descriptive; it is not a validated physical calibration.

Additional checks include a batch-by-area interaction, variance inflation factors, a model with crop group, and a sensitivity analysis without 2025B11. No records are removed on the basis of these diagnostics.

## Reproduction checks

`run_all.py` checks input/reference hashes before starting. At the end, it checks the seven S7 rows against the archived table at the displayed precision, compares model/association/coefficient/batch outputs with their rounded references, checks fold grouping, and checks Excel/CSV agreement. Failure returns a nonzero exit status and is recorded in `verification.json`.

Six-significant-digit archived means can cause small numeric differences from calculations made with the original unrounded means. The comparison therefore checks reported precision, not bit-for-bit equality with the original numerical analysis or figure image. Fonts and image metadata can also differ by operating system. Figure colors, panels, scales and plotted quantities follow the current v03 script.

Unused historical script copies have been omitted. `reference/` retains only expected statistical tables used for verification. `reference/Table_S7_original.csv` is used only for verification, never as the source of new model results. The full historical S7 formatter remains in `scripts/make_details.py` to retain the detailed reporting convention.

### Observed precision differences

The first rerun matched all seven displayed S7 rows and the reported Figure 7 statistics. Rank-based checks are more sensitive to rounding: for example, the RGR rank correlation was −0.001403 in the original analysis and −0.001774 from archived means. Its p-value changed from 0.9817 to 0.9769. All changed rank statistics are listed in `verification.json`. Pearson correlations, regression comparisons and cross-validation results match at their reported precision. The verifier checks rank statistics separately, with limits of 0.001 for rho and 0.01 for p, rather than presenting these differences as exact matches.

The recorded checks above describe the source analysis.
