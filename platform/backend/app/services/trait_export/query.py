"""Builds the SQL for a `Recipe` and runs it.

Column names are interpolated into the SQL text (SQLAlchemy cannot bind an
identifier), so every one of them is checked against the model's own column list
in `Recipe.validate()` first; all *values* are bound parameters.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from .recipe import Recipe

logger = logging.getLogger(__name__)

# A single export may not stream more rows than this; the caller is told to add
# filters instead of receiving a truncated file. Per-frame exports of a whole
# batch are the realistic way to hit it (tens of thousands of images per batch).
MAX_ROWS = 2_000_000


@dataclass(frozen=True)
class Scope:
    """One row of the selection: a business key with wildcards.

    An empty component means "any", so `2025B08/s0117//` is every replicate of
    that cultivar in that batch. A scope must name at least one component —
    an entirely empty one would quietly select the whole database.
    """

    batch_code: str = ""
    cultivar_code: str = ""
    treatment_code: str = ""
    replicate_code: str = ""

    @classmethod
    def parse(cls, spec: str) -> "Scope":
        parts = [p.strip() for p in spec.split("/")]
        if len(parts) > 4:
            raise ValueError(f"scope {spec!r} has more than 4 components")
        parts += [""] * (4 - len(parts))
        sc = cls(*parts)
        if not any(parts):
            raise ValueError("a scope must name at least one of batch/cultivar/treatment/replicate")
        return sc

    def as_str(self) -> str:
        return "/".join([self.batch_code, self.cultivar_code, self.treatment_code, self.replicate_code])


MAX_SCOPES = 400


@dataclass
class Selection:
    """Which plants.

    Two ways to say it, both honoured (AND-ed together):

    * the flat lists — each is an independent filter, so `batch_codes=[A,B]` with
      `cultivar_codes=[x,y]` is the **cross product** A×x, A×y, B×x, B×y;
    * `scopes` — a list of business keys OR-ed together, which is what a UI needs
      when the user picks "accession x in batch A" and "accession y in batch B" and means exactly
      those two, not all four combinations. Most cultivars appear in several
      batches, so the cross product would over-select without saying so.

    Empty lists mean "no restriction on this field".
    """

    batch_codes: List[str] = field(default_factory=list)
    cultivar_codes: List[str] = field(default_factory=list)
    treatment_codes: List[str] = field(default_factory=list)
    replicate_codes: List[str] = field(default_factory=list)
    plant_ids: List[int] = field(default_factory=list)
    scopes: List[Scope] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "batch_codes": self.batch_codes,
            "cultivar_codes": self.cultivar_codes,
            "treatment_codes": self.treatment_codes,
            "replicate_codes": self.replicate_codes,
            "plant_ids": self.plant_ids,
            "scopes": [s.as_str() for s in self.scopes],
        }


# The join aliases every selection filter is written against. Both this module and
# the environment export build their FROM the same way, so the WHERE fragments are
# produced once here rather than kept in step by hand.
#   replicate_code is an INTEGER column but is part of the business key, which is a
#   set of codes everywhere else in the API — compare it as text.
#   treatment_code is COALESCEd because a plant with no treatment row is exported
#   as '' and the UI sends back what it was shown.
_SEL_COLUMNS = {
    "batch": "b.batch_code",
    "cultivar": "c.cultivar_code",
    "treatment": "COALESCE(t.treatment_code, '')",
    "replicate": "p.replicate_code::text",
}


def selection_where(sel: Selection, params: Dict[str, Any]) -> List[str]:
    """WHERE fragments for a `Selection`, appending its bound values to `params`."""
    where: List[str] = []
    for key, values in (
        ("batch", sel.batch_codes),
        ("cultivar", sel.cultivar_codes),
        ("treatment", sel.treatment_codes),
        ("replicate", sel.replicate_codes),
    ):
        if values:
            where.append(f"{_SEL_COLUMNS[key]} = ANY(:sel_{key})")
            params[f"sel_{key}"] = list(values)
    if sel.plant_ids:
        where.append("p.id = ANY(:sel_plant_ids)")
        params["sel_plant_ids"] = list(sel.plant_ids)
    if sel.scopes:
        ors = []
        for i, scope in enumerate(sel.scopes):
            terms = []
            for key, value in (
                ("batch", scope.batch_code),
                ("cultivar", scope.cultivar_code),
                ("treatment", scope.treatment_code),
                ("replicate", scope.replicate_code),
            ):
                if value:
                    name = f"scope{i}_{key}"
                    terms.append(f"{_SEL_COLUMNS[key]} = :{name}")
                    params[name] = value
            if not terms:  # Scope.parse rejects this; belt and braces
                raise ValueError("empty scope would select every plant")
            ors.append("(" + " AND ".join(terms) + ")")
        where.append("(" + " OR ".join(ors) + ")")
    return where


# Business key first, then the provenance of the value, then the traits. The
# business key is the exported identity (a `plant_id` alone is an internal
# surrogate and means nothing in a downstream script).
KEY_COLUMNS = ["batch_code", "cultivar_code", "treatment_code", "replicate_code", "plant_id"]


def _obs_cte(rec: Recipe, sel: Selection, params: Dict[str, Any]) -> str:
    traits = ",\n               ".join(f"r.{t}" for t in rec.traits)
    where = [
        "p.plant_type = 'observation_individual'",
        "r.qc_status = ANY(:qc_status)",
        "r.day_after_sewing IS NOT NULL",
    ]
    params["qc_status"] = list(rec.qc_status)
    if rec.require_leaves:
        where.append("COALESCE(r.leaf_count, 0) > 0")
    where += selection_where(sel, params)
    return f"""
        SELECT b.batch_code, c.cultivar_code,
               COALESCE(t.treatment_code, '') AS treatment_code,
               p.replicate_code, p.id AS plant_id,
               r.day_after_sewing AS das, r.observation_timestamp AS observed_at,
               r.qc_status, r.sensor_id,
               {traits}
        FROM trait_observations r
        JOIN plants p ON p.id = r.plant_id
        JOIN batches b ON b.id = p.batch_id
        JOIN cultivars c ON c.id = p.cultivar_id
        LEFT JOIN treatments t ON t.id = p.treatment_id
        WHERE {' AND '.join(where)}
    """


def _window_cte(rec: Recipe, params: Dict[str, Any]) -> str:
    """Restrict to the days in the window. Ranking is per plant, so a plant with
    a gap still contributes n_days days — which days it actually was is reported
    back in the coverage table rather than assumed."""
    if rec.day_mode == "tail":
        params["n_days"] = int(rec.n_days)
        return """
            SELECT * FROM (
                SELECT o.*, DENSE_RANK() OVER (PARTITION BY o.plant_id ORDER BY o.das DESC) AS day_rank
                FROM obs o
            ) ranked
            WHERE day_rank <= :n_days
        """
    if rec.day_mode == "list":
        params["das_list"] = [int(d) for d in (rec.das_list or [])]
        return "SELECT * FROM obs WHERE das = ANY(:das_list)"
    if rec.day_mode == "range":
        params["das_from"] = int(rec.das_from)
        params["das_to"] = int(rec.das_to)
        return "SELECT * FROM obs WHERE das BETWEEN :das_from AND :das_to"
    if rec.day_mode == "dates":
        # Calendar bounds, inclusive, on the imaging date. Useful when the window
        # is defined by something that happened on a date (a treatment, an
        # equipment change) rather than by the plant's own age.
        params["date_from"] = rec.date_from
        params["date_to"] = rec.date_to
        return "SELECT * FROM obs WHERE observed_at::date BETWEEN :date_from AND :date_to"
    return "SELECT * FROM obs"


def _picked_cte(rec: Recipe, params: Dict[str, Any]) -> str:
    """Choose the frame(s) within each plant-day."""
    if rec.frame_pick == "all":
        return "SELECT * FROM win"
    if rec.frame_pick == "nearest_hour":
        params["pick_minutes"] = float(rec.pick_hour) * 60.0
        order = (
            "ABS((EXTRACT(HOUR FROM observed_at) * 60 + EXTRACT(MINUTE FROM observed_at))"
            " - :pick_minutes), observed_at"
        )
    else:
        order = "observed_at" + (" DESC" if rec.frame_pick == "last" else " ASC")
    return f"""
        SELECT DISTINCT ON (plant_id, das) *
        FROM win
        ORDER BY plant_id, das, {order}
    """


def build_sql(rec: Recipe, sel: Selection) -> tuple[str, Dict[str, Any], List[str]]:
    """Return (sql, params, output column names) for the requested level."""
    rec.validate()
    params: Dict[str, Any] = {}
    head = f"""
        WITH obs AS ({_obs_cte(rec, sel, params)}),
        win AS ({_window_cte(rec, params)}),
        picked AS ({_picked_cte(rec, params)})
    """

    if rec.level == "frame":
        cols = KEY_COLUMNS + ["das", "observed_at", "qc_status", "sensor_id"] + rec.traits
        sql = f"""{head}
        SELECT {', '.join(cols)}
        FROM picked
        ORDER BY batch_code, cultivar_code, treatment_code, replicate_code, das, observed_at
        """
        return sql, params, cols

    # Frames of a day are averaged first, so a day with more frames does not
    # outweigh a day with fewer. With one frame per day the two are identical.
    day_avgs = ",\n               ".join(f"AVG({t}::numeric) AS {t}" for t in rec.traits)
    per_day = f"""
        SELECT {', '.join(KEY_COLUMNS)}, das,
               MIN(observed_at) AS observed_at,
               COUNT(*) AS n_frames,
               bool_and(qc_status = 'verified') AS all_verified,
               {day_avgs}
        FROM picked
        GROUP BY {', '.join(KEY_COLUMNS)}, das
    """

    if rec.level == "day":
        cols = KEY_COLUMNS + ["das", "observed_at", "n_frames", "all_verified"] + rec.traits
        sql = f"""{head}, per_day AS ({per_day})
        SELECT {', '.join(cols)}
        FROM per_day
        ORDER BY batch_code, cultivar_code, treatment_code, replicate_code, das
        """
        return sql, params, cols

    plant_avgs = ",\n               ".join(f"AVG({t}) AS {t}" for t in rec.traits)
    per_plant = f"""
        SELECT {', '.join(KEY_COLUMNS)},
               COUNT(*) AS n_days_used,
               SUM(n_frames) AS n_frames_used,
               MIN(das) AS das_first, MAX(das) AS das_last,
               string_agg(das::text, ';' ORDER BY das) AS das_used,
               bool_and(all_verified) AS all_verified,
               {plant_avgs}
        FROM per_day
        GROUP BY {', '.join(KEY_COLUMNS)}
    """

    if rec.level == "plant":
        cols = KEY_COLUMNS + [
            "n_days_used", "n_frames_used", "das_first", "das_last", "das_used", "all_verified",
        ] + rec.traits
        sql = f"""{head}, per_day AS ({per_day}), per_plant AS ({per_plant})
        SELECT {', '.join(cols)}
        FROM per_plant
        ORDER BY batch_code, cultivar_code, treatment_code, replicate_code, plant_id
        """
        return sql, params, cols

    # level == "cultivar": mean ± sample SD across the replicates of one
    # batch × cultivar × treatment. SD is dispersion between replicates, not a
    # significance test.
    group = ["batch_code", "cultivar_code", "treatment_code"]
    stats = ",\n               ".join(
        f"AVG({t}) AS {t}_mean, STDDEV_SAMP({t}) AS {t}_sd" for t in rec.traits
    )
    cols = group + [
        "n_replicates", "n_verified", "n_days_used", "das_used",
    ] + [f"{t}_{s}" for t in rec.traits for s in ("mean", "sd")]
    sql = f"""{head}, per_day AS ({per_day}), per_plant AS ({per_plant})
    SELECT {', '.join(group)},
           COUNT(*) AS n_replicates,
           COUNT(*) FILTER (WHERE all_verified) AS n_verified,
           MAX(n_days_used) AS n_days_used,
           MAX(das_used) AS das_used,
           {stats}
    FROM per_plant
    GROUP BY {', '.join(group)}
    ORDER BY batch_code, cultivar_code, treatment_code
    """
    return sql, params, cols


def coverage(db: Session, rec: Recipe, sel: Selection) -> List[Dict[str, Any]]:
    """Per-plant record of what the recipe actually hit: the DAS list, the frame
    count and the QC mix. This is the part that was missing from the master table
    and cannot be reconstructed from the values."""
    cov = replace(rec, level="plant", traits=["leaf_count"])
    sql, params, _ = build_sql(cov, sel)
    rows = db.execute(text(sql), params).mappings().all()
    return [
        {
            "batch_code": r["batch_code"], "cultivar_code": r["cultivar_code"],
            "treatment_code": r["treatment_code"], "replicate_code": r["replicate_code"],
            "plant_id": r["plant_id"], "das_used": r["das_used"],
            "n_days_used": r["n_days_used"], "n_frames_used": int(r["n_frames_used"]),
            "all_verified": r["all_verified"],
        }
        for r in rows
    ]


def _plant_rows(db: Session, sel: Selection) -> List[Dict[str, Any]]:
    """The plants a selection names, with no recipe filter at all.

    Deliberately ignores the window and the QC states: it answers "does this
    business key exist?", which is what separates a typo from a real gap.
    """
    params: Dict[str, Any] = {}
    where = ["p.plant_type = 'observation_individual'"] + selection_where(sel, params)
    sql = f"""
        SELECT b.batch_code, c.cultivar_code,
               COALESCE(t.treatment_code, '') AS treatment_code,
               p.replicate_code, p.id AS plant_id
        FROM plants p
        JOIN batches b ON b.id = p.batch_id
        JOIN cultivars c ON c.id = p.cultivar_id
        LEFT JOIN treatments t ON t.id = p.treatment_id
        WHERE {' AND '.join(where)}
    """
    return [dict(r) for r in db.execute(text(sql), params).mappings().all()]


def _scope_matches(scope: Scope, row: Dict[str, Any]) -> bool:
    """A scope matches a plant when every component it names is equal; an empty
    component is a wildcard. replicate_code is an INTEGER column and the scope
    carries it as text, as the rest of the API does."""
    for value, key in (
        (scope.batch_code, "batch_code"),
        (scope.cultivar_code, "cultivar_code"),
        (scope.treatment_code, "treatment_code"),
        (scope.replicate_code, "replicate_code"),
    ):
        if value and str(row.get(key) if row.get(key) is not None else "") != value:
            return False
    return True


def scope_hits(db: Session, sel: Selection, cov: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """How many plants each selection row actually contributed.

    A row that matches nothing is otherwise silent: it adds no plants, and the
    totals still look plausible, so the export quietly holds fewer plants than
    the user picked (the mirror image of the flat lists' quiet over-selection).
    Two counts are reported because the two zeroes mean different things — a
    business key that names no plant is a mistake in the picks, while a plant
    with no rows in this window is a real gap in the data.

    Attribution is done here rather than in SQL: `cov` already carries every
    exported plant's business key, so no extra per-row query is needed.
    """
    if not sel.scopes:
        return []
    existing = _plant_rows(db, sel)
    hits = []
    for scope in sel.scopes:
        mine = [r for r in cov if _scope_matches(scope, r)]
        n_existing = sum(1 for r in existing if _scope_matches(scope, r))
        hits.append({
            "scope": scope.as_str(),
            "plants": len(mine),
            "plants_existing": n_existing,
            "frames": sum(r["n_frames_used"] for r in mine),
            "reason": None if mine else (
                "no plant has this business key — check the batch / cultivar / "
                "treatment / replicate of this row"
                if n_existing == 0 else
                f"{n_existing} plant(s) exist but none has an observation that passes "
                "the QC filter in this window"
            ),
        })
    return hits


def count_rows(db: Session, rec: Recipe, sel: Selection) -> int:
    sql, params, _ = build_sql(rec, sel)
    return int(db.execute(text(f"SELECT COUNT(*) FROM ({sql}) q"), params).scalar() or 0)


def fetch(db: Session, rec: Recipe, sel: Selection, limit: Optional[int] = None):
    """Yield (columns, row-iterator). Streams; the caller must consume it inside
    the request so the session is still open."""
    sql, params, cols = build_sql(rec, sel)
    if limit:
        sql = f"{sql} LIMIT {int(limit)}"
    result = db.execute(text(sql), params)
    return cols, result
