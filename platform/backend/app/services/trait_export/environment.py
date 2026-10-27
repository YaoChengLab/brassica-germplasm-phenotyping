"""Environment export, keyed to plants.

Environment records belong to a *chamber*, not to a plant: a sensor sits in a
chamber and logs every ~hour. A plant is tied to them only through
`plant_positions` — which chamber it was in, between which dates. This module
does that join so the exported rows carry the same business key as the trait
export (batch / cultivar / treatment / replicate) and can be matched up 1:1.

Aggregation deliberately mirrors the GDD method (`gdd_service`) so the two files
never disagree:

* An **hourly mean across all the chamber's sensors** is the atom. G120 has 32
  sensors; their mean is the chamber's temperature for that hour.
* Daily statistics are computed **over those hourly means**, not over raw
  readings, so a sensor logging twice as often cannot pull the day's mean.
* `n_hours_observed` is exported per day. It matters: the daily GDD contribution
  is the sum of `bilinear(T_hour)/24`, so a day with only 6 observed hours yields
  roughly a quarter of its true contribution rather than an error. In this
  dataset that is rare (G120 330/337 days have all 24 hours, 2 have < 12), but a
  downstream script should filter on it rather than assume.

**Chamber-level resolution is a real limitation, not a rounding detail**: plants
in the same chamber share one temperature series, so within-chamber position
gradients are invisible here.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from .query import Selection, selection_where
from .recipe import Recipe

logger = logging.getLogger(__name__)

ENV_LEVELS = ("day", "hour")

# Why an environment export can come back with nothing. Stated in one place because
# both the CSV (which refuses) and the preview (which would otherwise show an empty
# table) have to say it: no rows here means "no records for these chamber-days",
# never "the chamber was at 0".
NO_ROWS_EXPLANATION = (
    "No environment records for these plants in this window. Seedling-stage conditions "
    "are not included either: they belong to the nursery group, not the individual plant."
)

# Rows are materialised (the GDD attach needs them in hand), so the ceiling is
# lower than the trait export's and is checked with a COUNT before fetching —
# otherwise an hour-level export of every plant would blow up memory before any
# limit could reject it.
ENV_MAX_ROWS = {"day": 500_000, "hour": 200_000}

KEY_COLUMNS = ["batch_code", "cultivar_code", "treatment_code", "replicate_code", "plant_id"]

DAY_COLUMNS = KEY_COLUMNS + [
    "date", "das", "chamber_code", "n_sensors", "n_hours_observed",
    "t_mean", "t_min", "t_max", "rh_mean", "rh_min", "rh_max",
    "gdd_day", "gdd_aligned",
]
HOUR_COLUMNS = KEY_COLUMNS + [
    "observed_hour", "date", "das", "chamber_code", "n_sensors", "t_mean", "rh_mean",
]


def columns_for(level: str) -> List[str]:
    return DAY_COLUMNS if level == "day" else HOUR_COLUMNS


def _scope_cte(sel: Selection, params: Dict[str, Any]) -> str:
    """Selected plants joined to the chambers they lived in, and when."""
    where = ["p.plant_type = 'observation_individual'"] + selection_where(sel, params)
    return f"""
        SELECT p.id AS plant_id, b.batch_code, c.cultivar_code,
               COALESCE(t.treatment_code, '') AS treatment_code,
               p.replicate_code, h.chamber_id, g.chamber_code,
               h.entry_date, COALESCE(h.exit_date, CURRENT_DATE) AS exit_date
        FROM plants p
        JOIN batches b ON b.id = p.batch_id
        JOIN cultivars c ON c.id = p.cultivar_id
        LEFT JOIN treatments t ON t.id = p.treatment_id
        JOIN plant_positions h ON h.plant_id = p.id
        JOIN growth_chambers g ON g.id = h.chamber_id
        WHERE {' AND '.join(where)}
    """


# Sowing date inferred the same way gdd_service infers it — from any imaging row
# that carries both a timestamp and a DAS — so DAS here means the same thing as
# DAS in the trait export.
_SOW_CTE = """
    SELECT plant_id, MIN(observation_timestamp::date - day_after_sewing) AS sowing
    FROM trait_observations
    WHERE day_after_sewing IS NOT NULL
    GROUP BY plant_id
"""

_HOURLY_CTE = """
    SELECT s.chamber_id,
           date_trunc('hour', e.observation_timestamp) AS hh,
           AVG(e.temperature_celsius) AS t_mean,
           AVG(e.humidity_percent) AS rh_mean,
           COUNT(DISTINCT e.sensor_id) AS n_sensors
    FROM env_observations e
    JOIN sensors s ON s.id = e.sensor_id
    WHERE e.temperature_celsius IS NOT NULL
    GROUP BY s.chamber_id, date_trunc('hour', e.observation_timestamp)
"""


def _day_filter(rec: Recipe, params: Dict[str, Any], das_expr: str, date_expr: str) -> str:
    """Restrict which plant-days are exported.

    `range`/`dates` map straight onto DAS or calendar bounds. `tail`/`list` are
    imaging-frame notions, so they are honoured by intersecting with the DAS values
    the trait recipe would actually export — that way an environment file can be
    lined up exactly with the trait file it accompanies. `all` gives the plant's
    whole chamber residence, including days with no imaging.
    """
    if rec.day_mode == "range":
        params["das_from"] = int(rec.das_from)
        params["das_to"] = int(rec.das_to)
        return f"AND {das_expr} BETWEEN :das_from AND :das_to"
    if rec.day_mode == "dates":
        params["date_from"] = rec.date_from
        params["date_to"] = rec.date_to
        return f"AND {date_expr} BETWEEN :date_from AND :date_to"
    return ""


def build_sql(rec: Recipe, sel: Selection, level: str) -> Tuple[str, Dict[str, Any], List[str]]:
    if level not in ENV_LEVELS:
        raise ValueError(f"level must be one of {ENV_LEVELS}")
    params: Dict[str, Any] = {}
    head = f"""
        WITH scope AS ({_scope_cte(sel, params)}),
        sow AS ({_SOW_CTE}),
        hourly AS ({_HOURLY_CTE})
    """

    if level == "hour":
        sql = f"""{head}
        SELECT sc.batch_code, sc.cultivar_code, sc.treatment_code, sc.replicate_code, sc.plant_id,
               h.hh AS observed_hour, h.hh::date AS date,
               (h.hh::date - sw.sowing) AS das,
               sc.chamber_code, h.n_sensors,
               ROUND(h.t_mean::numeric, 3) AS t_mean,
               ROUND(h.rh_mean::numeric, 3) AS rh_mean
        FROM scope sc
        JOIN hourly h ON h.chamber_id = sc.chamber_id
                     AND h.hh::date BETWEEN sc.entry_date AND sc.exit_date
        LEFT JOIN sow sw ON sw.plant_id = sc.plant_id
        WHERE TRUE {_day_filter(rec, params, "(h.hh::date - sw.sowing)", "h.hh::date")}
        ORDER BY sc.batch_code, sc.cultivar_code, sc.treatment_code, sc.replicate_code, h.hh
        """
        return sql, params, HOUR_COLUMNS

    sql = f"""{head},
        env_day AS (
            SELECT chamber_id, hh::date AS day,
                   COUNT(*) AS n_hours_observed,
                   MAX(n_sensors) AS n_sensors,
                   AVG(t_mean) AS t_mean, MIN(t_mean) AS t_min, MAX(t_mean) AS t_max,
                   AVG(rh_mean) AS rh_mean, MIN(rh_mean) AS rh_min, MAX(rh_mean) AS rh_max
            FROM hourly GROUP BY chamber_id, hh::date
        ),
        joined AS (
            SELECT sc.batch_code, sc.cultivar_code, sc.treatment_code, sc.replicate_code,
                   sc.plant_id, sc.chamber_code, e.day, (e.day - sw.sowing) AS das,
                   e.n_sensors, e.n_hours_observed,
                   ROUND(e.t_mean::numeric, 3) AS t_mean,
                   ROUND(e.t_min::numeric, 3) AS t_min,
                   ROUND(e.t_max::numeric, 3) AS t_max,
                   ROUND(e.rh_mean::numeric, 3) AS rh_mean,
                   ROUND(e.rh_min::numeric, 3) AS rh_min,
                   ROUND(e.rh_max::numeric, 3) AS rh_max
            FROM scope sc
            JOIN env_day e ON e.chamber_id = sc.chamber_id
                          AND e.day BETWEEN sc.entry_date AND sc.exit_date
            LEFT JOIN sow sw ON sw.plant_id = sc.plant_id
        )
        SELECT batch_code, cultivar_code, treatment_code, replicate_code, plant_id,
               day AS date, das, chamber_code, n_sensors, n_hours_observed,
               t_mean, t_min, t_max, rh_mean, rh_min, rh_max
        FROM joined
        WHERE TRUE {_day_filter(rec, params, "das", "day")}
        ORDER BY batch_code, cultivar_code, treatment_code, replicate_code, day
    """
    return sql, params, DAY_COLUMNS


def restrict_to_trait_days(rec: Recipe) -> bool:
    """tail/list windows are frame notions; the SQL above cannot express them."""
    return rec.day_mode in ("tail", "list")


def trait_day_keys(db: Session, rec: Recipe, sel: Selection) -> Optional[set]:
    """The (plant_id, das) pairs the trait export would emit for this recipe."""
    from dataclasses import replace
    from .query import build_sql as trait_sql
    sql, params, _ = trait_sql(replace(rec, level="day", traits=["leaf_count"]), sel)
    try:
        rows = db.execute(text(f"SELECT plant_id, das FROM ({sql}) q"), params).all()
    except Exception as e:
        logger.warning(f"trait-day intersection failed: {e}")
        return None
    return {(int(r[0]), int(r[1])) for r in rows}


def count(db: Session, rec: Recipe, sel: Selection, level: str) -> int:
    """Row count before materialising. Note this counts *before* the tail/list
    intersection, so it is an upper bound for those modes."""
    sql, params, _ = build_sql(rec, sel, level)
    return int(db.execute(text(f"SELECT COUNT(*) FROM ({sql}) q"), params).scalar() or 0)


def fetch(db: Session, rec: Recipe, sel: Selection, level: str, limit: Optional[int] = None):
    """Yield (columns, list of row dicts). GDD columns are attached from the same
    service the trait export uses, so there is one definition of thermal time."""
    sql, params, cols = build_sql(rec, sel, level)
    keep = trait_day_keys(db, rec, sel) if restrict_to_trait_days(rec) else None

    rows: List[Dict[str, Any]] = []
    result = db.execute(text(sql), params)
    for raw in result.mappings():
        row = dict(raw)
        if keep is not None:
            if row["das"] is None or (int(row["plant_id"]), int(row["das"])) not in keep:
                continue
        rows.append(row)
        if limit and len(rows) >= limit:
            break

    if level == "day":
        _attach_gdd(db, rec, rows)
    return cols, rows


def _attach_gdd(db: Session, rec: Recipe, rows: List[Dict[str, Any]]) -> None:
    """Add `gdd_day` (that chamber-day's contribution) and `gdd_aligned` (the
    plant's cumulative, anchor-aligned value). Both come from `gdd_service` —
    re-deriving the bilinear formula in SQL would create a second definition of
    the same quantity."""
    for row in rows:
        row.setdefault("gdd_day", None)
        row.setdefault("gdd_aligned", None)
    if not rows or not rec.include_gdd:
        return
    from ...config.database import SessionLocal
    from ..gdd_service import GDDService

    own = SessionLocal()
    try:
        svc = GDDService(own)
        chamber_ids = {
            code: cid for code, cid in
            own.execute(text("SELECT chamber_code, id FROM growth_chambers")).all()
        }
        daily_by_chamber: Dict[int, Dict[Any, float]] = {}
        plant_ids = sorted({int(r["plant_id"]) for r in rows})
        aligned, _gaps = svc.compute_plants_gdd_by_das(plant_ids, rec.gdd_anchor)
        for row in rows:
            cid = chamber_ids.get(row["chamber_code"])
            if cid is not None:
                if cid not in daily_by_chamber:
                    daily_by_chamber[cid] = svc.get_chamber_daily_gdd(cid)
                row["gdd_day"] = daily_by_chamber[cid].get(row["date"])
            das = row.get("das")
            if das is not None:
                row["gdd_aligned"] = (aligned.get(int(row["plant_id"])) or {}).get(int(das))
    except Exception as e:
        logger.warning(f"environment GDD attach failed: {e}")
        own.rollback()
    finally:
        own.close()


def method_notes(rec: Recipe) -> Dict[str, Any]:
    from ..gdd_service import T_BASE, T_OPT, T_UPPER
    return {
        "atom": "hourly mean across every sensor in the chamber",
        "daily_statistics": "computed over hourly means, not raw readings",
        "resolution": (
            "per chamber — plants in the same chamber share one series, so "
            "within-chamber position gradients are not represented"
        ),
        "n_hours_observed": (
            "hours actually observed that day; the daily GDD contribution is the sum of "
            "bilinear(T_hour)/24, so a partially covered day is under-counted rather than "
            "flagged. Filter on this column."
        ),
        "gdd_day": "that chamber-day's bilinear contribution (degree-days)",
        "gdd_aligned": f"the plant's cumulative GDD, 0 on the day it entered {rec.gdd_anchor}",
        "bilinear_params": {"t_base": T_BASE, "t_opt": T_OPT, "t_upper": T_UPPER},
        "join_key": "batch_code + cultivar_code + treatment_code + replicate_code (+ date/das)",
        "sowing_date": "inferred from imaging rows carrying both timestamp and DAS",
    }
