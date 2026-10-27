"""ingest/db.py — read-only database queries for the loader.

Connects through `docker exec bpp-database psql` (local to the host, no password needed).
Writes go through the same route in load.py, which pipes one transaction into psql.
"""
import subprocess

CONTAINER = "bpp-database"
USER = "phenouser"
DBNAME = "plant_phenotyping"
SEP = "|"


def query(sql: str, timeout: int = 120) -> str:
    """Run read-only SQL and return the raw psql -tA text (columns separated by |). Raises on failure."""
    out = subprocess.run(
        ["docker", "exec", CONTAINER, "psql", "-U", USER, "-d", DBNAME,
         "-tA", "-F", SEP, "-c", sql],
        capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr.strip()[:300]}")
    return out.stdout


def query_rows(sql: str, cols: list[str]) -> list[dict]:
    """Return [{col: val}]; column names come from the caller (in SELECT order). NULL -> ''."""
    rows = []
    for ln in query(sql).splitlines():
        if ln == "":
            continue
        vals = ln.split(SEP)
        rows.append(dict(zip(cols, vals)))
    return rows
