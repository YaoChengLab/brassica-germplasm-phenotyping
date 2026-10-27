"""
v2 Query Service — fixes N+1, adds fields support, new lightweight endpoints.
"""

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import List, Dict, Any, Optional, Set
from datetime import timedelta
import logging

from ..models.phenotype import (
    Batch, Cultivar, Plant, Treatment, Rack,
    PhysicalObservation, RaspiObservation, ThermalObservation,
    EnvironmentObservation, Sensor, PlantChamberHistory,
)
from ..core.exceptions import DatabaseError
from ..services.query_service import QueryService

logger = logging.getLogger(__name__)


class QueryServiceV2(QueryService):
    """
    v2 query service extending v1 with:
    - N+1 fix for observations-with-environment
    - Sparse field selection
    - New lightweight cultivar list endpoint
    - Bulk cultivar details
    """

    ALWAYS_INCLUDE = {'id', 'plant_id', 'observation_timestamp'}

    # ------------------------------------------------------------------
    # Field selection helper
    # ------------------------------------------------------------------

    def _select_fields(self, model, fields: Optional[List[str]]):
        """
        Return a list of SQLAlchemy column attributes for *model* limited to
        *fields* (plus mandatory columns).  If *fields* is None, return [model]
        to select all columns.
        """
        if not fields:
            return [model]

        valid = {c.name for c in model.__table__.columns}
        requested = (set(fields) | self.ALWAYS_INCLUDE) & valid
        return [getattr(model, f) for f in requested]

    # ------------------------------------------------------------------
    # New: lightweight cultivar list
    # ------------------------------------------------------------------

    def get_all_cultivars_summary(self) -> Dict[str, Any]:
        """
        Return a minimal cultivar list: id, cultivar_code, product_name.
        No observation counts, no joins — as fast as possible.
        """
        try:
            rows = (
                self.db.query(Cultivar.id, Cultivar.cultivar_code, Cultivar.product_name)
                .order_by(Cultivar.cultivar_code)
                .all()
            )
            data = [
                {"id": r.id, "cultivar_code": r.cultivar_code, "product_name": r.product_name}
                for r in rows
            ]
            return {"total_count": len(data), "data": data}
        except Exception as e:
            logger.error(f"get_all_cultivars_summary failed: {e}")
            raise DatabaseError(f"Failed to retrieve cultivar summary: {e}")

    # ------------------------------------------------------------------
    # New: bulk cultivar details
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # N+1 fix: observations with environment
    # ------------------------------------------------------------------

    def _resolve_zone_arduino_sensors(self, plant_id: int) -> Dict[str, Any]:
        """
        Resolve the zone-specific arduino sensor(s) for a plant.

        Mapping chain:
            plant → PlantChamberHistory.sensor_id (raspi)
            → Sensor.rack_id → Rack.rack_code (e.g. "B1_2")
            → zone = rack_code split '_' first part (e.g. "B1")
            → arduino sensors with same sensor_code in same chamber

        Returns dict with:
            chamber_id, zone, raspi_sensor_id, arduino_sensor_ids,
            raspi_sensor_code, rack_code
        """
        row = (
            self.db.query(
                PlantChamberHistory.chamber_id,
                PlantChamberHistory.sensor_id,
                Sensor.sensor_code.label('raspi_code'),
                Rack.rack_code,
            )
            .join(Sensor, PlantChamberHistory.sensor_id == Sensor.id)
            .join(Rack, Sensor.rack_id == Rack.id)
            .filter(PlantChamberHistory.plant_id == plant_id)
            .first()
        )

        if not row:
            return {"chamber_id": None, "zone": None, "arduino_sensor_ids": []}

        # Zone = rack_code prefix before '_' (e.g. "B1_2" → "B1")
        zone = row.rack_code.split('_')[0] if row.rack_code else None

        arduino_sensor_ids = []
        if zone and row.chamber_id:
            arduino_sensor_ids = [
                sid for (sid,) in
                self.db.query(Sensor.id)
                .filter(
                    Sensor.chamber_id == row.chamber_id,
                    Sensor.sensor_type == 'arduino',
                    Sensor.sensor_code == zone,
                )
                .all()
            ]

        return {
            "chamber_id": row.chamber_id,
            "zone": zone,
            "raspi_sensor_id": row.sensor_id,
            "raspi_sensor_code": row.raspi_code,
            "rack_code": row.rack_code,
            "arduino_sensor_ids": arduino_sensor_ids,
        }

    def get_observations_with_environment_v2(
        self,
        plant_id: int,
        fields: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get all observations for a plant enriched with **zone-specific**
        environment data.

        Key differences from v1:
        - Uses only the arduino sensor(s) in the plant's zone, not all
          sensors in the chamber. This preserves the 2-4°C spatial gradient
          across G120 zones (A/B/C/D).
        - Missing values are returned as null — no interpolation at API level.
        - Returns zone metadata so the caller knows which sensor was used.
        """
        try:
            # Get plant info
            plant_info = (
                self.db.query(
                    Cultivar.cultivar_code,
                    Cultivar.product_name,
                    Plant.replicate_code,
                )
                .select_from(Plant)
                .join(Cultivar)
                .filter(Plant.id == plant_id)
                .first()
            )

            if not plant_info:
                return None

            # Resolve zone-specific arduino sensor(s)
            zone_info = self._resolve_zone_arduino_sensors(plant_id)
            arduino_sensor_ids = zone_info["arduino_sensor_ids"]

            # ---- Collect observations ----
            observations = []

            # RGB-derived traits only; 3D scan and FLIR are not served.
            for model, obs_type in [
                (RaspiObservation, "raspi"),
            ]:
                exclude = {'id', 'plant_id', 'sensor_id', 'observation_timestamp'}
                rows = (
                    self.db.query(model)
                    .filter(model.plant_id == plant_id)
                    .order_by(model.observation_timestamp)
                    .all()
                )
                for row in rows:
                    all_cols = {c.name for c in model.__table__.columns} - exclude
                    selected_cols = (all_cols & set(fields)) if fields else all_cols

                    traits = {c: getattr(row, c) for c in selected_cols}
                    observations.append({
                        "observation_timestamp": row.observation_timestamp,
                        "day_after_sewing": getattr(row, 'day_after_sewing', None),
                        "type": obs_type,
                        "traits": traits,
                    })

            observations.sort(key=lambda x: x["observation_timestamp"])

            # ---- Batch-fetch zone env data (single query) ----
            if arduino_sensor_ids and observations:
                timestamps = [o["observation_timestamp"] for o in observations]
                min_ts = min(timestamps) - timedelta(hours=1)
                max_ts = max(timestamps)

                env_rows = (
                    self.db.query(
                        EnvironmentObservation.observation_timestamp,
                        EnvironmentObservation.temperature_celsius,
                        EnvironmentObservation.humidity_percent,
                    )
                    .filter(
                        EnvironmentObservation.sensor_id.in_(arduino_sensor_ids),
                        EnvironmentObservation.observation_timestamp >= min_ts,
                        EnvironmentObservation.observation_timestamp <= max_ts,
                    )
                    .order_by(EnvironmentObservation.observation_timestamp)
                    .all()
                )

                # Window aggregation — zone-specific, no cross-zone mixing
                for obs in observations:
                    obs_ts = obs["observation_timestamp"]
                    window_start = obs_ts - timedelta(hours=1)

                    temps = []
                    hums = []
                    for env in env_rows:
                        if window_start <= env.observation_timestamp <= obs_ts:
                            if env.temperature_celsius is not None:
                                temps.append(float(env.temperature_celsius))
                            if env.humidity_percent is not None:
                                hums.append(float(env.humidity_percent))

                    # Return raw averages; null if no data — no interpolation
                    obs["env_temperature"] = round(sum(temps) / len(temps), 2) if temps else None
                    obs["env_humidity"] = round(sum(hums) / len(hums), 2) if hums else None
                    obs["env_records"] = max(len(temps), len(hums))
            else:
                for obs in observations:
                    obs["env_temperature"] = None
                    obs["env_humidity"] = None
                    obs["env_records"] = 0

            return {
                "cultivar_info": {
                    "cultivar_code": plant_info.cultivar_code,
                    "product_name": plant_info.product_name,
                    "replicate_code": plant_info.replicate_code,
                },
                "zone_info": {
                    "zone": zone_info.get("zone"),
                    "raspi_sensor_code": zone_info.get("raspi_sensor_code"),
                    "rack_code": zone_info.get("rack_code"),
                    "arduino_sensor_ids": zone_info.get("arduino_sensor_ids", []),
                },
                "observations": observations,
            }

        except Exception as e:
            logger.error(f"get_observations_with_environment_v2 failed for plant {plant_id}: {e}")
            raise DatabaseError(
                f"Failed to retrieve observations with environment for plant {plant_id}: {e}"
            )

    # ------------------------------------------------------------------
    # Fields-aware plant observations
    # ------------------------------------------------------------------

    def get_plant_observations_v2(
        self,
        plant_id: int,
        observation_type: Optional[str] = None,
        fields: Optional[List[str]] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Get observations for a plant with optional field filtering and pagination.
        """
        try:
            plant_info = (
                self.db.query(
                    Cultivar.cultivar_code,
                    Cultivar.product_name,
                    Plant.replicate_code,
                )
                .select_from(Plant)
                .join(Cultivar)
                .filter(Plant.id == plant_id)
                .first()
            )

            cultivar_info = {
                "cultivar_code": plant_info.cultivar_code if plant_info else None,
                "product_name": plant_info.product_name if plant_info else None,
                "replicate_code": plant_info.replicate_code if plant_info else None,
            }

            response = {"cultivar_info": cultivar_info, "raspi": []}

            def _query_obs(model, key):
                cols = self._select_fields(model, fields)
                q = self.db.query(*cols).filter(model.plant_id == plant_id)
                q = q.order_by(model.observation_timestamp)
                q = q.offset(offset).limit(limit)
                rows = q.all()
                if len(cols) == 1 and cols[0] is model:
                    # Full model selected
                    exclude = {'id', 'plant_id', 'sensor_id'}
                    response[key] = [
                        {c.name: getattr(row, c.name) for c in model.__table__.columns if c.name not in exclude}
                        for row in rows
                    ]
                else:
                    response[key] = [dict(row._mapping) for row in rows]

            if not observation_type or observation_type == "raspi":
                _query_obs(RaspiObservation, "raspi")

            return response

        except Exception as e:
            logger.error(f"get_plant_observations_v2 failed: {e}")
            raise DatabaseError(f"Failed to retrieve observations for plant {plant_id}: {e}")

    # ------------------------------------------------------------------
    # Batch plant-zone mapping
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Signature traits (cultivar profile table)
    # ------------------------------------------------------------------

    # The "signature" traits shown on the cultivar page. Defined once, in
    # services.trait_export, because the CSV export offers the same set as its
    # default and the two must not drift apart. All come from the Raspberry Pi
    # top-view RGB series (same source as the growth curves), so every batch has
    # them and they carry replicates — the DSLR colour/texture table is a single
    # shot per plant in one batch only and is deliberately NOT mixed in.
    from .trait_export import SIGNATURE_TRAITS  # noqa: F401  (re-exported as a class attr)

    def get_cultivar_signature_traits(self, cultivar_code: str) -> Optional[Dict[str, Any]]:
        """
        Per-batch snapshot of the signature traits for one cultivar.

        The sampling recipe is NOT defined here: it is the platform default from
        `services.trait_export` (last 4 imaging days, the frame nearest 14:00,
        averaged per plant-day then across days, QC-correct rows only), the very
        same recipe the CSV export resolves. A number on this table is therefore
        the number in the exported file — previously this endpoint had its own
        one-reference-day rule and silently disagreed with the export.

        Value = mean ± sample SD across the replicates of that batch. Batches whose
        observations are still the pre-QC legacy rows are returned with
        status='not_processed' rather than silently dropped.
        """
        from sqlalchemy import text
        from dataclasses import replace as _replace
        from .trait_export import PRESETS, Selection, build_sql

        try:
            cultivar = (
                self.db.query(Cultivar)
                .filter(Cultivar.cultivar_code == cultivar_code)
                .first()
            )
            if not cultivar:
                return None

            # All batches this cultivar was grown in (so we can mark the ones
            # without QC-correct data instead of omitting them).
            batch_rows = (
                self.db.query(Batch.batch_code, func.count(Plant.id))
                .join(Plant, Plant.batch_id == Batch.id)
                .filter(
                    Plant.cultivar_id == cultivar.id,
                    Plant.plant_type == 'observation_individual',
                )
                .group_by(Batch.batch_code)
                .order_by(Batch.batch_code)
                .all()
            )

            trait_cols = self.SIGNATURE_TRAITS  # fixed whitelist, not user input
            recipe = _replace(PRESETS["default"], level="cultivar", traits=list(trait_cols))
            sql, params, _ = build_sql(recipe, Selection(cultivar_codes=[cultivar_code]))
            rows = self.db.execute(text(sql), params).mappings().all()
            by_batch = {r['batch_code']: r for r in rows}

            batches = []
            for batch_code, plant_count in batch_rows:
                row = by_batch.get(batch_code)
                if row is None:
                    batches.append({
                        "batch_code": batch_code,
                        "plant_count": plant_count,
                        "status": "not_processed",
                        "das_used": None,
                        "n_days_used": None,
                        "n_replicates": 0,
                        "n_verified": 0,
                        "values": {},
                    })
                    continue
                batches.append({
                    "batch_code": batch_code,
                    "plant_count": plant_count,
                    "status": "ok",
                    "das_used": row['das_used'],
                    "n_days_used": int(row['n_days_used']) if row['n_days_used'] is not None else None,
                    "n_replicates": int(row['n_replicates']),
                    "n_verified": int(row['n_verified']),
                    "values": {
                        c: {
                            "mean": float(row[f'{c}_mean']) if row[f'{c}_mean'] is not None else None,
                            "sd": float(row[f'{c}_sd']) if row[f'{c}_sd'] is not None else None,
                        }
                        for c in trait_cols
                    },
                })

            return {
                "cultivar_code": cultivar_code,
                "source": "raspi_rgb_topview",
                "trait_keys": list(trait_cols),
                "recipe": recipe.as_dict(),
                "batches": batches,
            }
        except Exception as e:
            logger.error(f"get_cultivar_signature_traits failed for {cultivar_code}: {e}")
            raise DatabaseError(f"Failed to retrieve signature traits for {cultivar_code}: {e}")

    # ------------------------------------------------------------------
    # Chamber timeline + environment
    # ------------------------------------------------------------------

    # What kind of space each chamber is. Explicit per chamber code rather than
    # parsed from the R*/G* prefix — an unknown chamber gets no label instead of a
    # guessed one (the old hardcoded G121–G125 legend is the cautionary tale).
    # Long-term home for this is a column on growth_chambers.
    CHAMBER_FACILITIES = {
        'R141': {"key": "walk_in", "label": "Walk-in", "description": "walk-in growth chamber"},
        'R142': {"key": "walk_in", "label": "Walk-in", "description": "walk-in growth chamber"},
        'G120': {"key": "greenhouse", "label": "Greenhouse", "description": "observation greenhouse"},
        'G111': {"key": "greenhouse", "label": "Greenhouse", "description": "observation greenhouse"},
    }

    def get_cultivar_chamber_timeline(self, cultivar_code: str) -> Optional[Dict[str, Any]]:
        """
        Where this cultivar's plants stayed and for how long, per batch, with the
        environment (temperature / humidity) recorded in that chamber during each
        stay.

        One entry per (batch, chamber, entry_date, exit_date). Environment is
        chamber-level: all arduino sensors mounted in that chamber, restricted to
        the stay window. Stays without environment readings are returned with
        environment=None (the arduino series has real gaps) instead of being
        dropped.
        """
        from sqlalchemy import text

        try:
            cultivar = (
                self.db.query(Cultivar)
                .filter(Cultivar.cultivar_code == cultivar_code)
                .first()
            )
            if not cultivar:
                return None

            stay_rows = self.db.execute(text("""
                SELECT b.batch_code,
                       b.start_date AS batch_start_date,
                       b.end_date   AS batch_end_date,
                       g.id         AS chamber_id,
                       g.chamber_code,
                       h.entry_date, h.exit_date,
                       COUNT(DISTINCT h.plant_id) AS plant_count,
                       string_agg(DISTINCT p.plant_type, ',') AS plant_types
                FROM plant_positions h
                JOIN plants p ON p.id = h.plant_id
                JOIN batches b ON b.id = p.batch_id
                JOIN growth_chambers g ON g.id = h.chamber_id
                WHERE p.cultivar_id = :cultivar_id
                GROUP BY b.batch_code, b.start_date, b.end_date,
                         g.id, g.chamber_code, h.entry_date, h.exit_date
                ORDER BY b.batch_code, h.entry_date
            """), {"cultivar_id": cultivar.id}).mappings().all()

            if not stay_rows:
                return {"cultivar_code": cultivar_code, "batches": []}

            # Environment per stay: summary + daily series, in two grouped queries
            # over the union of the stay windows (chamber-level, arduino only).
            windows = [
                {
                    "chamber_id": r['chamber_id'],
                    "entry": r['entry_date'],
                    "exit": r['exit_date'] or r['entry_date'],
                }
                for r in stay_rows
            ]
            # CAST(... AS date) rather than ::date — the double colon collides
            # with SQLAlchemy's bind-parameter syntax.
            values_sql = ", ".join(
                f"(:c{i}, CAST(:s{i} AS date), CAST(:e{i} AS date))"
                for i in range(len(windows))
            )
            params: Dict[str, Any] = {}
            for i, w in enumerate(windows):
                params[f"c{i}"] = w['chamber_id']
                params[f"s{i}"] = w['entry']
                params[f"e{i}"] = w['exit']

            env_sql = f"""
            WITH win(chamber_id, entry_date, exit_date) AS (VALUES {values_sql}),
            readings AS (
                SELECT w.chamber_id, w.entry_date, w.exit_date,
                       (e.observation_timestamp AT TIME ZONE 'UTC')::date AS day,
                       e.temperature_celsius AS t,
                       e.humidity_percent AS rh,
                       sn.id AS sensor_id
                FROM win w
                JOIN sensors sn ON sn.chamber_id = w.chamber_id
                                AND sn.sensor_type = 'arduino'
                JOIN env_observations e
                     ON e.sensor_id = sn.id
                    AND e.observation_timestamp >= w.entry_date::timestamptz
                    AND e.observation_timestamp < (w.exit_date + 1)::timestamptz
            )
            SELECT chamber_id, entry_date, exit_date, day,
                   COUNT(*) AS n,
                   COUNT(DISTINCT sensor_id) AS n_sensors,
                   AVG(t) AS t_mean, MIN(t) AS t_min, MAX(t) AS t_max,
                   AVG(rh) AS rh_mean, MIN(rh) AS rh_min, MAX(rh) AS rh_max
            FROM readings
            GROUP BY chamber_id, entry_date, exit_date, day
            ORDER BY chamber_id, entry_date, day
            """
            daily_rows = self.db.execute(text(env_sql), params).mappings().all()

            daily_by_stay: Dict[Any, List[Dict[str, Any]]] = {}
            for r in daily_rows:
                key = (r['chamber_id'], r['entry_date'], r['exit_date'])
                daily_by_stay.setdefault(key, []).append(r)

            def _num(v):
                return float(v) if v is not None else None

            def _summarize(rows):
                """Day-weighted summary of one stay from its daily rows."""
                if not rows:
                    return None
                total_n = sum(int(r['n']) for r in rows)
                if total_n == 0:
                    return None
                t_vals = [(float(r['t_mean']), int(r['n'])) for r in rows if r['t_mean'] is not None]
                rh_vals = [(float(r['rh_mean']), int(r['n'])) for r in rows if r['rh_mean'] is not None]
                t_mean = sum(v * n for v, n in t_vals) / sum(n for _, n in t_vals) if t_vals else None
                rh_mean = sum(v * n for v, n in rh_vals) / sum(n for _, n in rh_vals) if rh_vals else None
                t_mins = [_num(r['t_min']) for r in rows if r['t_min'] is not None]
                t_maxs = [_num(r['t_max']) for r in rows if r['t_max'] is not None]
                rh_mins = [_num(r['rh_min']) for r in rows if r['rh_min'] is not None]
                rh_maxs = [_num(r['rh_max']) for r in rows if r['rh_max'] is not None]
                return {
                    "n_readings": total_n,
                    "n_sensors": max(int(r['n_sensors']) for r in rows),
                    "days_covered": len(rows),
                    "temperature": {
                        "mean": t_mean,
                        "min": min(t_mins) if t_mins else None,
                        "max": max(t_maxs) if t_maxs else None,
                    },
                    "humidity": {
                        "mean": rh_mean,
                        "min": min(rh_mins) if rh_mins else None,
                        "max": max(rh_maxs) if rh_maxs else None,
                    },
                    "daily": [
                        {
                            "date": r['day'].isoformat(),
                            "t_mean": _num(r['t_mean']),
                            "t_min": _num(r['t_min']),
                            "t_max": _num(r['t_max']),
                            "rh_mean": _num(r['rh_mean']),
                        }
                        for r in rows
                    ],
                }

            batches: Dict[str, Dict[str, Any]] = {}
            for r in stay_rows:
                batch = batches.setdefault(r['batch_code'], {
                    "batch_code": r['batch_code'],
                    "batch_start_date": r['batch_start_date'].isoformat() if r['batch_start_date'] else None,
                    "batch_end_date": r['batch_end_date'].isoformat() if r['batch_end_date'] else None,
                    "stays": [],
                })
                exit_date = r['exit_date']
                types = (r['plant_types'] or '').split(',')
                # Phase comes from what kind of plant record was in the chamber;
                # facility comes from the chamber itself. They are independent —
                # do not derive one from the other.
                phase = 'seedling' if types and all(t == 'nursery_group' for t in types) else 'observation'
                facility = self.CHAMBER_FACILITIES.get(r['chamber_code'])
                key = (r['chamber_id'], r['entry_date'], exit_date or r['entry_date'])
                batch['stays'].append({
                    "chamber_code": r['chamber_code'],
                    "facility": facility['label'] if facility else None,
                    "facility_key": facility['key'] if facility else None,
                    "facility_description": facility['description'] if facility else None,
                    "phase": phase,
                    "entry_date": r['entry_date'].isoformat(),
                    "exit_date": exit_date.isoformat() if exit_date else None,
                    "days": (exit_date - r['entry_date']).days if exit_date else None,
                    "plant_count": int(r['plant_count']),
                    "environment": _summarize(daily_by_stay.get(key)),
                })

            return {
                "cultivar_code": cultivar_code,
                "batches": sorted(batches.values(), key=lambda b: b['batch_code']),
            }
        except Exception as e:
            logger.error(f"get_cultivar_chamber_timeline failed for {cultivar_code}: {e}")
            raise DatabaseError(f"Failed to retrieve chamber timeline for {cultivar_code}: {e}")

    # ------------------------------------------------------------------
    # Filter options with safety cap
    # ------------------------------------------------------------------

    def get_cultivar_filter_options_v2(self, max_items: int = 500) -> Dict[str, List[str]]:
        """Get filter options with a safety upper bound."""
        try:
            product_names = (
                self.db.query(Cultivar.product_name)
                .distinct()
                .order_by(Cultivar.product_name)
                .limit(max_items)
                .all()
            )
            # Genome type is a small closed vocabulary (5 values), so the
            # advanced search renders it as a picker rather than free text.
            genome_types = (
                self.db.query(Cultivar.genome_type)
                .distinct()
                .order_by(Cultivar.genome_type)
                .limit(max_items)
                .all()
            )
            return {
                "product_names": [name[0] for name in product_names if name[0]],
                "genome_types": [g[0] for g in genome_types if g[0]],
            }
        except Exception as e:
            logger.error(f"get_cultivar_filter_options_v2 failed: {e}")
            raise DatabaseError(f"Failed to retrieve cultivar filter options: {e}")
