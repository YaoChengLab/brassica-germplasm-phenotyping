"""Thermal time (GDD) attached to exported rows.

GDD is not a stored column and cannot be joined in SQL: it is walked per plant
through `plant_positions`, summing each day's contribution from whichever
chamber the plant was in, so it is computed in Python and merged onto the rows
afterwards.

Two properties of this GDD that a downstream script must not have to guess, and
that therefore go into the manifest and the column name:

* **Aligned, not absolute.** The anchor chamber's entry day is GDD = 0, so days
  before the plant entered it are *negative*. This is thermal time relative to a
  biologically meaningful event, not degree-days since sowing.
* **Gaps stay empty.** A day whose chamber has no environment records yields
  None, and None is exported as an empty cell — never 0. Where the environment
  record of a chamber has a gap, every GDD cell of a batch imaged in that window
  is empty. That is the data, not a failure of this code.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from .recipe import Recipe
from .query import Selection, build_sql

logger = logging.getLogger(__name__)

# Emitted per level. Cultivar level gets none: a mean of thermal time across
# replicates would need per-plant values the grouped query no longer carries, and
# a half-defined aggregate is worse than none — export level=plant for GDD.
GDD_COLUMNS = {
    "frame": ["gdd_aligned"],
    "day": ["gdd_aligned"],
    "plant": ["gdd_aligned_first", "gdd_aligned_last"],
    "cultivar": [],
}


def columns_for(rec: Recipe) -> List[str]:
    return GDD_COLUMNS.get(rec.level, []) if rec.include_gdd else []


def build_lookup(db: Session, rec: Recipe, sel: Selection) -> Tuple[Dict[int, Dict[int, Optional[float]]], Dict[str, Any]]:
    """Return ({plant_id: {das: gdd}}, metadata). Never raises — a GDD failure
    must not take the export down with it; the metadata says what happened.

    Runs on its own session on purpose. `GDDService` swallows per-plant failures
    internally, and a swallowed DB error still leaves the *transaction* aborted —
    which would then fail every later query of the export in the caller's session.
    A separate read-only session keeps that blast radius at zero.
    """
    if not columns_for(rec):
        return {}, {"included": False, "reason": "not requested" if not rec.include_gdd
                    else "not emitted at cultivar level (export level=plant for GDD)"}

    from ...config.database import SessionLocal
    from ..gdd_service import DEFAULT_ANCHOR_CHAMBER, GDDService, T_BASE, T_OPT, T_UPPER

    sql, params, _ = build_sql(rec, sel)
    own = SessionLocal()
    try:
        return _build(own, rec, sel, sql, params, GDDService, T_BASE, T_OPT, T_UPPER)
    finally:
        own.close()


def _build(db, rec, sel, sql, params, GDDService, T_BASE, T_OPT, T_UPPER):
    try:
        plant_ids = [
            int(r[0]) for r in db.execute(
                text(f"SELECT DISTINCT plant_id FROM ({sql}) q ORDER BY plant_id"), params
            ).all()
        ]
    except Exception as e:
        logger.warning(f"GDD scope query failed: {e}")
        db.rollback()
        return {}, {"included": False, "reason": f"scope query failed: {e}"}

    # An anchor code that does not exist must not fall through: GDDService looks the
    # chamber up with .get(), so an unknown code yields *unaligned* cumulative GDD
    # instead of an error — numbers that look fine and mean something else.
    known = [r[0] for r in db.execute(text("SELECT chamber_code FROM growth_chambers ORDER BY chamber_code")).all()]
    if rec.gdd_anchor not in known:
        return {}, {
            "included": False,
            "invalid_anchor": True,
            "reason": f"unknown anchor chamber {rec.gdd_anchor!r}; known chambers: {known}",
        }

    meta: Dict[str, Any] = {
        "included": True,
        "column_names": columns_for(rec),
        "anchor_chamber": rec.gdd_anchor,
        "definition": (
            f"Cumulative bilinear GDD, aligned so that the day the plant entered "
            f"{rec.gdd_anchor} is 0; earlier days are negative."
        ),
        "bilinear_params": {"t_base": T_BASE, "t_opt": T_OPT, "t_upper": T_UPPER, "unit": "degree-day"},
        "chamber_resolution": "per chamber (not per rack/zone) from env_observations",
        "null_policy": "empty cell = no environment record for that chamber-day; never 0",
        "plants_in_scope": len(plant_ids),
    }
    if not plant_ids:
        return {}, {**meta, "included": False, "reason": "no plants in scope"}

    try:
        lookup, gap_days = GDDService(db).compute_plants_gdd_by_das(plant_ids, rec.gdd_anchor)
    except Exception as e:
        logger.warning(f"GDD computation failed: {e}")
        db.rollback()
        return {}, {**meta, "included": False, "reason": f"computation failed: {e}"}

    filled = sum(1 for d in lookup.values() for v in d.values() if v is not None)
    total = sum(len(d) for d in lookup.values())
    plants_all_empty = [pid for pid, d in lookup.items() if d and not any(v is not None for v in d.values())]
    meta.update({
        "plant_days_with_value": filled,
        "plant_days_total": total,
        "env_gap_days": len(gap_days),
        "plants_with_no_gdd_at_all": len(plants_all_empty),
        "warning": (
            "Every GDD cell for {} of {} plants is empty (no environment records for their "
            "chamber-days). Do not read empty as 0.".format(len(plants_all_empty), len(lookup))
            if plants_all_empty else None
        ),
    })
    return lookup, meta


def lookup_at_timestamps(
    plant_id: int, timestamps: List[Any], anchor: Optional[str] = None,
) -> Tuple[Dict[Any, Optional[float]], Dict[str, Any]]:
    """Aligned GDD at each observation timestamp (per-frame resolution).

    The hourly accumulation is the model's own unit, so thermal time is defined
    between days too; the plant-view time series uses this so its points stay
    per-frame on the GDD axis. Same session and failure policy as `build_lookup`.
    """
    from ...config.database import SessionLocal
    from ..gdd_service import DEFAULT_ANCHOR_CHAMBER, GDDService, T_BASE, T_OPT, T_UPPER

    anchor = anchor or DEFAULT_ANCHOR_CHAMBER
    if not timestamps:
        return {}, {"included": False, "reason": "no observations"}
    db = SessionLocal()
    try:
        known = [r[0] for r in db.execute(text("SELECT chamber_code FROM growth_chambers ORDER BY chamber_code")).all()]
        if anchor not in known:
            return {}, {"included": False, "invalid_anchor": True,
                        "reason": f"unknown anchor chamber {anchor!r}; known chambers: {known}"}
        try:
            values = GDDService(db).compute_plant_gdd_at_timestamps(plant_id, timestamps, anchor)
        except Exception as e:
            logger.warning(f"GDD at timestamps failed for plant {plant_id}: {e}")
            db.rollback()
            return {}, {"included": False, "reason": f"computation failed: {e}"}
    finally:
        db.close()
    filled = sum(1 for v in values.values() if v is not None)
    return values, {
        "included": True,
        "anchor_chamber": anchor,
        "resolution": "per observation timestamp (hourly accumulation, pro rata within the hour)",
        "definition": (f"Cumulative bilinear GDD, aligned so that the day the plant entered "
                       f"{anchor} is 0; earlier days are negative."),
        "method": ("hourly: mean chamber temperature per hour -> bilinear(T)/24, summed; "
                   "a day with no environment record is null for that day and after it"),
        "bilinear_params": {"t_base": T_BASE, "t_opt": T_OPT, "t_upper": T_UPPER, "unit": "degree-day"},
        "chamber_resolution": "per chamber (not per rack/zone) from env_observations",
        "null_policy": "null = no environment record for that chamber-day; never 0",
        "observations_with_value": filled,
        "observations_total": len(values),
    }


def enrich(row: Dict[str, Any], rec: Recipe, lookup: Dict[int, Dict[int, Optional[float]]]) -> Dict[str, Any]:
    """Add this level's GDD column(s) to one row dict (in place)."""
    cols = columns_for(rec)
    if not cols:
        return row
    per_das = lookup.get(int(row["plant_id"])) if row.get("plant_id") is not None else None
    if rec.level in ("frame", "day"):
        row["gdd_aligned"] = (per_das or {}).get(int(row["das"])) if row.get("das") is not None else None
    else:  # plant
        row["gdd_aligned_first"] = (per_das or {}).get(int(row["das_first"])) if row.get("das_first") is not None else None
        row["gdd_aligned_last"] = (per_das or {}).get(int(row["das_last"])) if row.get("das_last") is not None else None
    return row
