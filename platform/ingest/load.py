"""ingest/load.py — idempotent per-batch load of the staging trait CSV into trait_observations.

Steps: the resolver maps each row's plant key to plant_id and sensor_id in Python and builds a
resolved CSV, then one transaction is sent through `docker exec -i psql`: create a temporary
staging table -> COPY the rows in -> create the analysis_run in a CTE ->
`INSERT ... SELECT ... ON CONFLICT (plant_id, sensor_id, observation_timestamp) DO UPDATE`.

By default this is a dry run: the same transaction, including the idempotent DDL
(ADD COLUMN IF NOT EXISTS, analysis_runs, the natural-key UNIQUE constraint), the upsert and the
before/after counts, ends with ROLLBACK and leaves nothing behind (PostgreSQL DDL is
transactional). `--apply` commits.

Usage (from platform/, env bgp-imaging):
  python -m ingest.load --batch 2025B08           # dry run (ROLLBACK)
  python -m ingest.load --batch 2025B08 --apply   # write
"""
import argparse
import csv
import io
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# config (paths, batch-code check) and traits_2d live in the imaging module.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "imaging"))
from config import OUT, require_batch_code  # noqa: E402
from ingest import db  # noqa: E402
from ingest.resolver import BatchResolver  # noqa: E402
from traits_2d.traits import DB_TRAIT_COLS  # noqa: E402

# Provenance columns and the natural-key constraint that _ddl_idempotent() ensures.
# database/init/01-schema.sql already has them, so on a fresh deployment the DDL is a no-op.
NEW_COLUMNS = {
    "qc_status": "varchar(16)",
    "analysis_run_id": "integer",
    "pipeline_version": "varchar(64)",
}
UNIQUE_NAME = "uq_trait_observations_natural"

# Columns written to trait_observations (analysis_run_id is added by the CTE)
INSERT_COLS = (["plant_id", "sensor_id", "observation_timestamp", "day_after_sewing"]
               + DB_TRAIT_COLS + ["qc_status", "pipeline_version", "image_file"])
CONFLICT_KEY = ["plant_id", "sensor_id", "observation_timestamp"]
# Integer columns (the extractor returns floats, which COPY into an integer column rejects):
# the integer trait/meta columns of trait_observations are leaf_count, sift_keypoint_count, day_after_sewing
INT_COLS = {"leaf_count", "sift_keypoint_count", "day_after_sewing"}


def _iv(v):
    """Integer column value: '7.0' -> '7'; empty stays empty (NULL)."""
    if v in ("", None):
        return ""
    return str(int(float(v)))


def _resolved_csv(rows, resolver) -> tuple[str, int, int, set]:
    """Resolve staging rows into CSV text of INSERT_COLS. Returns (csv_text, ok, unresolved, plant_ids)."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    ok = bad = 0
    pids = set()
    for r in rows:
        res, reason = resolver.resolve(r)
        if res is None:
            bad += 1
            continue
        plant_id, sensor_id, _ = res
        pids.add(plant_id)
        rec = [plant_id, sensor_id, r["observation_timestamp"], _iv(r.get("day_after_sewing", ""))]
        rec += [_iv(r.get(c, "")) if c in INT_COLS else r.get(c, "") for c in DB_TRAIT_COLS]
        # image_file links the record to its crop: <frame_stem>.png
        stem = r.get("frame_stem", "")
        rec += [r.get("qc_status", ""), r.get("pipeline_version", ""), f"{stem}.png" if stem else ""]
        w.writerow(rec)
        ok += 1
    return buf.getvalue(), ok, bad, pids


def _batch_matches(rows, batch, path) -> bool:
    """Every staging row's batch_code must equal --batch; otherwise stop.

    Why: `resolver.resolve()` looks up (cultivar_code, replicate_code, plant_type) only among the
    plants of --batch and ignores the row's batch_code. If rows of another batch slipped in (a
    stale file, a wrong `--staging`, the same number in another year such as 2025B08 vs 2026B08),
    most of those keys would also match an accession and replicate of this batch, be written to
    the wrong plant_id without warning, and still be reported as all resolved.
    """
    other = Counter(r.get("batch_code") or "(empty)" for r in rows
                    if (r.get("batch_code") or "") != batch)
    if not other:
        return True
    print(f"[load] staging batch codes do not match --batch; stopping without writing\n"
          f"       staging: {path}\n"
          f"       expected {batch}, found: " +
          ", ".join(f"{b} x{n}" for b, n in sorted(other.items())))
    return False


def _ddl_idempotent() -> str:
    """Idempotent schema DDL (safe whether or not the columns and constraint already exist)."""
    add = ",\n  ".join(f"ADD COLUMN IF NOT EXISTS {c} {t}" for c, t in NEW_COLUMNS.items())
    return f"""ALTER TABLE trait_observations
  {add};
CREATE TABLE IF NOT EXISTS analysis_runs (
  id serial PRIMARY KEY, modality varchar(32) NOT NULL, batch_code varchar(16) NOT NULL,
  pipeline_version varchar(64) NOT NULL, qc_snapshot_hash varchar(64), extractor_sha varchar(32),
  status varchar(16) NOT NULL, started_at timestamptz, finished_at timestamptz, n_rows integer);
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='{UNIQUE_NAME}') THEN
    ALTER TABLE trait_observations ADD CONSTRAINT {UNIQUE_NAME}
      UNIQUE (plant_id, sensor_id, observation_timestamp);
  END IF;
END $$;"""


def _upsert_sql(batch: str, n_rows: int) -> str:
    cols = ", ".join(INSERT_COLS)
    # day_after_sewing is computed from the sowing date in the database, not from the daf of
    # frames.json (days since the first image, not days after sowing). Sowing date = the earliest
    # entry_date of the parent nursery group in a nursery chamber (chamber code R%).
    sel = ", ".join(
        "(stg.observation_timestamp::date - sew.sewing_date)"
        if c == "day_after_sewing" else f"stg.{c}"
        for c in INSERT_COLS)
    set_cols = ", ".join(f"{c}=EXCLUDED.{c}" for c in INSERT_COLS if c not in CONFLICT_KEY)
    return f"""WITH run AS (
  INSERT INTO analysis_runs(modality,batch_code,pipeline_version,status,started_at,finished_at,n_rows)
  VALUES ('traits_2d','{batch}',(SELECT pipeline_version FROM stg LIMIT 1),'done',now(),now(),{n_rows})
  RETURNING id),
sew AS (
  SELECT p.id AS plant_id, MIN(pch.entry_date) AS sewing_date
  FROM plants p
  JOIN plant_positions pch ON pch.plant_id = p.parent_plant_id
  JOIN growth_chambers gc      ON gc.id = pch.chamber_id
  WHERE gc.chamber_code LIKE 'R%'
  GROUP BY p.id)
INSERT INTO trait_observations ({cols}, analysis_run_id)
SELECT {sel}, (SELECT id FROM run)
FROM stg LEFT JOIN sew ON sew.plant_id = stg.plant_id
ON CONFLICT ({', '.join(CONFLICT_KEY)}) DO UPDATE SET {set_cols},
  analysis_run_id=EXCLUDED.analysis_run_id;"""


def build_script(batch, csv_text, n_rows, pids, apply: bool) -> str:
    stg_cols = ", ".join(INSERT_COLS)
    pid_list = ",".join(str(p) for p in sorted(pids))
    cnt = (f"SELECT qc_status, count(*) FROM trait_observations "
           f"WHERE plant_id IN ({pid_list}) GROUP BY qc_status ORDER BY qc_status;")
    end = "COMMIT;" if apply else "ROLLBACK;"
    return f"""\\set ON_ERROR_STOP on
BEGIN;
{_ddl_idempotent()}
CREATE TEMP TABLE stg ON COMMIT DROP AS
  SELECT {stg_cols} FROM trait_observations WITH NO DATA;
COPY stg ({stg_cols}) FROM STDIN WITH (FORMAT csv, NULL '');
{csv_text}\\.
\\echo === BEFORE ({batch} staging plants) ===
{cnt}
{_upsert_sql(batch, n_rows)}
\\echo === AFTER ({batch} staging plants) ===
{cnt}
\\echo === analysis_runs (this txn) ===
SELECT id, modality, batch_code, status, n_rows FROM analysis_runs ORDER BY id DESC LIMIT 1;
{end}
"""


def run(batch, staging, apply):
    batch = require_batch_code(batch)      # check before building the file name: a short code would point to a missing or wrong staging file
    path = Path(staging) if staging else Path(OUT) / f"staging_traits_{batch}.csv"
    if not path.exists():
        print(f"[load] staging file not found: {path}"); return
    rows = list(csv.DictReader(open(path)))
    if not _batch_matches(rows, batch, path):
        return
    resolver = BatchResolver(batch)
    csv_text, ok, bad, pids = _resolved_csv(rows, resolver)
    print(f"[load] {batch}: staging {len(rows)} rows -> {ok} resolved / {bad} unresolved; {len(pids)} plants")
    if bad:
        print(f"[load] {bad} rows could not be resolved; stopping without writing"); return

    script = build_script(batch, csv_text, ok, pids, apply)
    mode = "APPLY(COMMIT)" if apply else "DRY-RUN(ROLLBACK)"
    print(f"[load] sending to psql ({mode}) ...\n")
    out = subprocess.run(
        ["docker", "exec", "-i", db.CONTAINER, "psql", "-U", db.USER, "-d", db.DBNAME],
        input=script, capture_output=True, text=True)
    print(out.stdout)
    if out.returncode != 0:
        print("STDERR:", out.stderr[:800]); sys.exit(1)
    if not apply:
        print("[load] dry run finished; the transaction was rolled back (database unchanged).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True, help="full batch code, e.g. 2025B08 (not B08)")
    ap.add_argument("--staging")
    ap.add_argument("--apply", action="store_true", help="commit the load (otherwise a dry run that rolls back)")
    a = ap.parse_args()
    try:
        batch = require_batch_code(a.batch)
    except ValueError as e:
        ap.error(str(e))
    run(batch, a.staging, a.apply)
