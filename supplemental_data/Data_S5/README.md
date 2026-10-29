# Supplemental Data S5: analysis code for the manuscript results

This package reruns the analyses behind the manuscript figures and tables from bundled
prepared data. The platform source code and model weights are on
[GitHub](https://github.com/YaoChengLab/brassica-germplasm-phenotyping).

Python 3.12. From this directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python make_all.py
```

On Windows use `.venv\Scripts\python.exe`. Package installation needs internet;
the analysis needs no network, database, model weights or GPU. Figure 7 runs 50 repeats
of 10-fold accession-grouped cross-validation and can take several minutes.

```sh
.venv/bin/python make_all.py Fig.5 Fig.6
.venv/bin/python make_all.py --output /path/to/new/results
```

The runner uses paths relative to this package and writes to `results/` by default.
It verifies the input checksums in `input_checksums.json` first and stops on failure.
The Figure 7 analysis also checks its results against the archived reference tables
in `Fig.7/reference/` (see `Fig.7/README.md`).

## Scope

| Folder | Manuscript item |
|---|---|
| `Fig.5` | Figure 5 panels |
| `Fig.6` | Figure 6 and the Section 2.6 survey statistics |
| `Fig.7` | Figure 7, Table S7 and the fresh-weight model details |
| `Supp.Fig.S2` | Figure S2 panels |
| `Supp.Fig.S3` | Figure S3 panels |
| `Supp.Fig.S4` | Figure S4 panels a and b |
| `Table.1` | Table S6, of which Table 1 reports a subset of rows |
| `Supp.Table.S5` | Table S5 |

The package does not rerun image segmentation, leaf assignment, model training,
test-image evaluation, manual review, raw-weight exclusions or raw database extraction.
Detection metrics and Figure 5 timing constants are prepared results. Raw images are
not included, so the image tiles of Figure S4c are not regenerated. Panel letters and
labels added during figure assembly are not regenerated.

Prepared inputs are kept in each analysis folder so each analysis can be used alone.
Shared small tables may therefore occur twice; their checksums are identical.

## Definitions and limits

Accession and batch identifiers are unchanged. Pixel measurements stay in pixels.
Projected area is not full leaf surface area. Manual-review agreement is not an
independent biological validation. Trait definitions are in Table S4.

Figure 7 starts from archived means at six significant digits. Raw weighing data
are not included. Small rank-statistic differences caused by rounding are described in
`Fig.7/README.md`. Image and weight means were computed separately; plant-level
pairing is not assumed.

Each analysis README documents fields, units and run commands.
