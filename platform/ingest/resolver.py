"""ingest/resolver.py — maps the plant key of staging rows to plant_id and sensor_id in the database.

Files outside the database store only the plant key; it is resolved to the current `plants.id`
at load time, so the records do not depend on database ids.

- plant_id: `(batch_code, cultivar_code, replicate_code, plant_type='observation_individual')` -> plants.id.
  This is unique when a batch has one treatment. Batches with several treatments would need
  treatment_code in the staging rows, which is not implemented.
- sensor_id: taken from the plant's `plant_positions`, not from a sensor code in the path.
  Each plant must have exactly one camera; with more than one (camera changed during the batch)
  the plant is reported as ambiguous and not written.
"""
import os
import sys

from . import db

# config (batch-code check) lives in the imaging module.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "imaging"))
from config import require_batch_code  # noqa: E402


class BatchResolver:
    def __init__(self, batch_code: str):
        self.batch_code = require_batch_code(batch_code)

        rows = db.query_rows(f"""
            SELECT c.cultivar_code, p.replicate_code, p.plant_type, p.id, p.treatment_id,
                   (SELECT count(DISTINCT ch.sensor_id) FROM plant_positions ch WHERE ch.plant_id=p.id),
                   (SELECT min(ch.sensor_id)            FROM plant_positions ch WHERE ch.plant_id=p.id)
            FROM plants p
            JOIN cultivars c ON c.id=p.cultivar_id
            JOIN batches   b ON b.id=p.batch_id
            WHERE b.batch_code='{batch_code}' AND p.plant_type='observation_individual'
        """, ["cultivar_code", "replicate_code", "plant_type",
              "plant_id", "treatment_id", "n_sensors", "sensor_id"])

        # (cultivar_code, replicate_code, plant_type) → plant row
        self.plants = {(r["cultivar_code"], r["replicate_code"], r["plant_type"]): r
                       for r in rows}
        # sensor_id -> sensor_code (for a provenance cross-check)
        self.sensor_code = {r["id"]: r["sensor_code"] for r in db.query_rows(
            "SELECT id, sensor_code FROM sensors", ["id", "sensor_code"])}

    def resolve(self, row: dict):
        """Return (result, reason): on success result=(plant_id, sensor_id, sensor_code_db) and
        reason=None; on failure result=None and reason is a string."""
        key = (row.get("cultivar_code"), row.get("replicate_code"),
               row.get("plant_type", "observation_individual"))
        p = self.plants.get(key)
        if p is None:
            return None, "no_plant_match"
        if int(p["n_sensors"]) != 1:
            return None, f"ambiguous_sensor(n={p['n_sensors']})"
        sid = int(p["sensor_id"])
        return (int(p["plant_id"]), sid, self.sensor_code.get(str(sid))), None
