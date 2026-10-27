"""Structured trait export — the platform's hand-off point to downstream analysis.

Three things every export carries, because none of them can be recovered from the
numbers afterwards: the business key of each plant, the sampling recipe that
produced the value, and the DAS/frame counts the recipe actually hit. The CSV
holds the first and third; the recipe lives in the companion manifest, whose URL
is returned in the `X-Export-Manifest` header.

Analysis is deliberately out of scope: growth-model parameters (Gompertz
asymptote, emergence rate, solidity dynamics …) are not stored per frame and are
fitted downstream from the `level=day` series.
"""
from __future__ import annotations

import csv
import io
import logging
from dataclasses import replace
from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from ....core.dependencies import get_current_user, get_db
from ....services.trait_export import (
    DEPRECATED_TRAITS,
    DOWNSTREAM_ONLY_TRAITS,
    MAX_ROWS,
    MAX_SCOPES,
    PRESET_NOTES,
    PRESETS,
    SIGNATURE_TRAITS,
    TRAIT_ALIASES,
    TRAIT_COLUMNS,
    Recipe,
    Scope,
    Selection,
    build_sql,
    categories,
    count_rows,
    coverage,
    fetch,
    scope_hits,
)
from ....services.trait_export import environment as env_export
from ....services.trait_export import gdd as gdd_export
from ....services.trait_export.recipe import DAY_MODES, FRAME_PICKS, LEVELS

router = APIRouter()
logger = logging.getLogger(__name__)

PREVIEW_ROWS = 20
COVERAGE_LIMIT = 400  # plants listed individually in the manifest


def _csv_list(value: Optional[str]) -> List[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _int_list(value: Optional[str]) -> List[int]:
    out = []
    for v in _csv_list(value):
        try:
            out.append(int(v))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"not an integer: {v!r}")
    return out


def parse_request(
    preset: str = Query("default", description="Named recipe to start from; other params override it"),
    batch_codes: Optional[str] = Query(None, description="Comma-separated, e.g. 2025B08"),
    cultivar_codes: Optional[str] = Query(None),
    treatment_codes: Optional[str] = Query(None),
    replicate_codes: Optional[str] = Query(None),
    plant_ids: Optional[str] = Query(None, description="Comma-separated internal plant ids"),
    scopes: Optional[str] = Query(
        None,
        description="Semicolon-separated business keys, OR-ed: "
                    "batch/cultivar/treatment/replicate, empty component = any "
                    "(e.g. 2025B08/s0117/Control/1;2025B09/s0232//). Use this rather than the "
                    "flat lists when the picks are specific pairs — the flat lists cross-multiply.",
    ),
    traits: Optional[str] = Query(None, description="Comma-separated trait columns; default = signature set"),
    level: Optional[str] = Query(None, description=f"One of {LEVELS}"),
    day_mode: Optional[str] = Query(None, description=f"One of {DAY_MODES}"),
    n_days: Optional[int] = Query(None, ge=1, le=400, description="day_mode=tail: imaging days counted back"),
    das_list: Optional[str] = Query(None, description="day_mode=list: comma-separated DAS values"),
    das_from: Optional[int] = Query(None),
    das_to: Optional[int] = Query(None),
    date_from: Optional[date] = Query(None, description="day_mode=dates: first imaging date (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="day_mode=dates: last imaging date, inclusive"),
    frame_pick: Optional[str] = Query(None, description=f"One of {FRAME_PICKS}"),
    pick_hour: Optional[float] = Query(None, ge=0, le=24, description="frame_pick=nearest_hour target hour"),
    require_leaves: Optional[bool] = Query(None),
    qc_status: Optional[str] = Query(None, description="Comma-separated: auto,verified[,no]"),
    include_gdd: Optional[bool] = Query(None, description="Attach thermal time (aligned on the anchor chamber's entry day)"),
    gdd_anchor: Optional[str] = Query(None, description="Chamber code whose entry day is GDD = 0"),
):
    """Resolve query parameters into (Recipe, Selection). A preset supplies the
    defaults; anything given explicitly wins, so `preset=default&level=day`
    is a legitimate way to ask for that window's daily series."""
    if preset not in PRESETS:
        raise HTTPException(status_code=400, detail=f"unknown preset {preset!r}; have {list(PRESETS)}")
    base = PRESETS[preset]
    rec = Recipe(
        day_mode=day_mode or base.day_mode,
        n_days=n_days if n_days is not None else base.n_days,
        das_list=_int_list(das_list) if das_list else base.das_list,
        das_from=das_from if das_from is not None else base.das_from,
        das_to=das_to if das_to is not None else base.das_to,
        date_from=date_from if date_from is not None else base.date_from,
        date_to=date_to if date_to is not None else base.date_to,
        frame_pick=frame_pick or base.frame_pick,
        pick_hour=pick_hour if pick_hour is not None else base.pick_hour,
        require_leaves=require_leaves if require_leaves is not None else base.require_leaves,
        qc_status=tuple(_csv_list(qc_status)) if qc_status else tuple(base.qc_status),
        level=level or base.level,
        traits=_csv_list(traits) or list(base.traits),
        include_gdd=include_gdd if include_gdd is not None else base.include_gdd,
        gdd_anchor=gdd_anchor or base.gdd_anchor,
    )
    try:
        rec.validate()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    specs = [s.strip() for s in (scopes or "").split(";") if s.strip()]
    if len(specs) > MAX_SCOPES:
        raise HTTPException(status_code=400, detail=f"at most {MAX_SCOPES} scopes per export")
    try:
        parsed_scopes = [Scope.parse(s) for s in specs]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    sel = Selection(
        batch_codes=_csv_list(batch_codes),
        cultivar_codes=_csv_list(cultivar_codes),
        treatment_codes=_csv_list(treatment_codes),
        replicate_codes=_csv_list(replicate_codes),
        plant_ids=_int_list(plant_ids),
        scopes=parsed_scopes,
    )
    return rec, sel, preset


@router.get("/traits/options", operation_id="export_trait_options")
async def trait_options(current_user=Depends(get_current_user)):
    """Everything the export UI needs to build its form."""
    return {
        "traits": TRAIT_COLUMNS,
        "trait_categories": categories(),
        "signature_traits": SIGNATURE_TRAITS,
        "deprecated_traits": DEPRECATED_TRAITS,
        "trait_aliases": TRAIT_ALIASES,
        "downstream_only_traits": DOWNSTREAM_ONLY_TRAITS,
        "downstream_only_note": (
            "Fitted over a whole trajectory by the downstream analysis scripts (growth "
            "parameters, shape dynamics). Not stored per single-plant image, so the platform cannot "
            "export them — export level=day and fit them there."
        ),
        "levels": list(LEVELS),
        "day_modes": list(DAY_MODES),
        "frame_picks": list(FRAME_PICKS),
        "qc_values": ["auto", "verified", "no"],
        "gdd": {
            "column_names_by_level": gdd_export.GDD_COLUMNS,
            "note": (
                "Thermal time is aligned on the anchor chamber's entry day (that day is 0, "
                "earlier days negative), computed per chamber-day; a day with no environment "
                "record exports as an empty cell, never 0."
            ),
        },
        "presets": {
            name: {**rec.as_dict(), "note": PRESET_NOTES.get(name, "")}
            for name, rec in PRESETS.items()
        },
        "max_rows": MAX_ROWS,
        "max_scopes": MAX_SCOPES,
        "environment": {
            "resolutions": list(env_export.ENV_LEVELS),
            "columns_by_resolution": {lv: env_export.columns_for(lv) for lv in env_export.ENV_LEVELS},
            "max_rows_by_resolution": env_export.ENV_MAX_ROWS,
            "note": (
                "Separate file, same business key. Chamber-level: hourly mean across the "
                "chamber's sensors; daily statistics are computed over those hourly means."
            ),
        },
    }


def _pipeline_provenance(db: Session, rec: Recipe, sel: Selection) -> dict:
    """Which pipeline versions / analysis runs the exported rows came from."""
    sql, params, _ = build_sql(replace(rec, level="frame"), sel)
    q = f"""
        SELECT DISTINCT r.pipeline_version
        FROM trait_observations r
        WHERE r.plant_id IN (SELECT DISTINCT plant_id FROM ({sql}) s)
    """
    try:
        versions = [v[0] for v in db.execute(text(q), params).all()]
    except Exception as e:  # provenance is a nice-to-have, never fail the export
        logger.warning(f"pipeline provenance query failed: {e}")
        versions = []
    return {"pipeline_versions": sorted(v for v in versions if v)}


def _reject_invalid_anchor(meta: dict) -> None:
    if meta.get("invalid_anchor"):
        raise HTTPException(status_code=400, detail=meta["reason"])


def _ascii_header(value: str) -> str:
    """Response headers are latin-1; anything else raises at response construction
    time and turns a working export into a 500."""
    return value.encode("ascii", "replace").decode("ascii")


def _gdd_header(meta: dict) -> str:
    """One line that does not let an all-empty GDD column pass as "included" —
    a batch imaged during the G120 environment gap gets every cell empty, and a
    header saying merely "included" would invite reading empty as zero."""
    if not meta.get("included"):
        return f"absent: {meta.get('reason', 'n/a')}"
    filled, total = meta.get("plant_days_with_value"), meta.get("plant_days_total")
    if not filled:
        return "all empty: no environment records for these chamber-days (do not read as 0)"
    return f"{filled}/{total} plant-days have a value"


def _scopes_header(hits: list) -> str:
    """One line about the selection rows, for a download that was never previewed.
    A row that matched nothing has to be said out loud: the file is then smaller
    than what was picked, and no number in it shows that."""
    if not hits:
        return "no selection rows (flat filters or plant ids)"
    empty = [h["scope"] for h in hits if not h["plants"]]
    head = f"{len(hits)} selection row(s), {sum(h['plants'] for h in hits)} plant hits"
    if empty:
        return f"{head}; MATCHED NOTHING: {', '.join(empty)}"
    return head


def _manifest(db: Session, rec: Recipe, sel: Selection, preset: str, user, gdd_meta=None) -> dict:
    cols = build_sql(rec, sel)[2] + gdd_export.columns_for(rec)
    n = count_rows(db, rec, sel)
    cov = coverage(db, rec, sel)
    hits = scope_hits(db, sel, cov)
    das_seen = sorted({int(d) for row in cov for d in (row["das_used"] or "").split(";") if d})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": getattr(user, "username", None),
        "source": "Plant Phenotyping Platform trait_observations (Raspberry Pi top-view RGB)",
        "preset": preset,
        "recipe": rec.as_dict(),
        "selection": sel.as_dict(),
        "columns": cols,
        "row_count": n,
        "plant_count": len(cov),
        "das_values_used": das_seen,
        "frames_used_total": sum(r["n_frames_used"] for r in cov),
        "coverage": cov[:COVERAGE_LIMIT],
        "coverage_truncated": len(cov) > COVERAGE_LIMIT,
        # Per selection row, so a row that contributed nothing is visible. The
        # counts can sum to more than plant_count when rows overlap (a cultivar
        # row and one of its replicates), which is why both are reported.
        "scope_hits": hits,
        "scopes_matching_nothing": [h["scope"] for h in hits if not h["plants"]],
        "scope_hits_overlap": sum(h["plants"] for h in hits) > len(cov),
        "provenance": _pipeline_provenance(db, rec, sel),
        "gdd": gdd_meta if gdd_meta is not None else gdd_export.build_lookup(db, rec, sel)[1],
        "notes": [
            "Values are pixel-based; no conversion to physical units (single top-view "
            "camera, no in-plane scale reference at leaf height).",
            "Growth parameters and shape dynamics are not included: they are fitted over "
            "a whole trajectory by the downstream analysis scripts, not stored per frame.",
            "qc_status 'auto' = model leaf ownership, 'verified' = human-reviewed; 'no' "
            "rows are pre-QC and excluded unless explicitly requested.",
            "das_used lists the imaging days that actually contributed per plant — a "
            "plant with a gap can hit different days than its replicates.",
            "scope_hits gives each selection row's contribution; a row with plants = 0 "
            "put nothing in this file, so the export covers less than was picked.",
            "GDD columns are aligned thermal time (anchor entry day = 0, earlier days "
            "negative), not degree-days since sowing; empty means no environment record "
            "for that chamber-day and must not be read as 0.",
        ],
    }


@router.get("/traits/manifest", operation_id="export_trait_manifest")
async def trait_manifest(
    parsed=Depends(parse_request),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    rec, sel, preset = parsed
    lookup, gdd_meta = gdd_export.build_lookup(db, rec, sel)
    _reject_invalid_anchor(gdd_meta)
    return _manifest(db, rec, sel, preset, current_user, gdd_meta)


@router.get("/traits/preview", operation_id="export_trait_preview")
async def trait_preview(
    parsed=Depends(parse_request),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """First rows plus the manifest, so the form can be checked before download."""
    rec, sel, preset = parsed
    lookup, gdd_meta = gdd_export.build_lookup(db, rec, sel)
    _reject_invalid_anchor(gdd_meta)
    cols, result = fetch(db, rec, sel, limit=PREVIEW_ROWS)
    rows = [gdd_export.enrich(dict(r), rec, lookup) for r in result.mappings()]
    cols = cols + gdd_export.columns_for(rec)
    manifest = _manifest(db, rec, sel, preset, current_user, gdd_meta)
    return {
        "columns": cols,
        "rows": rows,
        "preview_rows": len(rows),
        "manifest": manifest,
        "too_large": manifest["row_count"] > MAX_ROWS,
    }


# ---------------------------------------------------------------- environment
# A separate file rather than extra columns on the trait rows: environment is a
# chamber-day series, so folding it in would repeat the same values on every
# frame of a day. Same business key, so the two files join cleanly.


def _env_manifest(db: Session, rec: Recipe, sel: Selection, preset: str, user, level: str, n_rows: int) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": getattr(user, "username", None),
        "source": "Plant Phenotyping Platform env_observations via sensors -> growth_chambers, joined to plants through plant_positions",
        "preset": preset,
        "level": level,
        "window": {
            "day_mode": rec.day_mode,
            "note": (
                "tail/list windows are defined on single-plant images; environment rows are "
                "intersected with the DAS values the matching trait export would emit"
                if env_export.restrict_to_trait_days(rec)
                else "range/dates apply directly; all = the plant's whole chamber residence"
            ),
            "das_from": rec.das_from, "das_to": rec.das_to,
            "date_from": rec.date_from.isoformat() if rec.date_from else None,
            "date_to": rec.date_to.isoformat() if rec.date_to else None,
            "n_days": rec.n_days if rec.day_mode == "tail" else None,
            "das_list": rec.das_list if rec.day_mode == "list" else None,
        },
        "selection": sel.as_dict(),
        "columns": env_export.columns_for(level),
        "row_count": n_rows,
        "method": env_export.method_notes(rec),
        "notes": [
            "Join to the trait export on batch_code + cultivar_code + treatment_code + "
            "replicate_code (+ date or das).",
            "Temperature and humidity are chamber-level: every plant in a chamber shares "
            "one series, so within-chamber position effects are not represented.",
            "n_hours_observed < 24 means the day is partially covered; gdd_day is then "
            "under-counted, not flagged.",
        ],
    }


@router.get("/environment/preview", operation_id="export_environment_preview")
async def environment_preview(
    parsed=Depends(parse_request),
    # Named `resolution`, not `level`: FastAPI binds one query param to every
    # declaration of that name, so a `level` here would also land in the trait
    # recipe and be rejected by its own validator before reaching this endpoint.
    resolution: str = Query("day", description=f"One of {env_export.ENV_LEVELS}"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    rec, sel, preset = parsed
    level = resolution
    if level not in env_export.ENV_LEVELS:
        raise HTTPException(status_code=400, detail=f"resolution must be one of {env_export.ENV_LEVELS}")
    cols, rows = env_export.fetch(db, rec, sel, level, limit=PREVIEW_ROWS)
    return {
        "columns": cols,
        "rows": rows,
        "preview_rows": len(rows),
        # An empty result is an answer, not a blank table: the same explanation the
        # CSV endpoint refuses with, so the UI never shows "no data" without saying
        # why (and nobody reads the absence as zeros).
        "empty_reason": None if rows else env_export.NO_ROWS_EXPLANATION,
        "manifest": _env_manifest(db, rec, sel, preset, current_user, level, len(rows)),
        "manifest_row_count_is_preview_only": True,
    }


@router.get("/environment.csv", operation_id="export_environment_csv")
async def export_environment_csv(
    parsed=Depends(parse_request),
    resolution: str = Query("day", description=f"One of {env_export.ENV_LEVELS}"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    rec, sel, preset = parsed
    level = resolution
    if level not in env_export.ENV_LEVELS:
        raise HTTPException(status_code=400, detail=f"resolution must be one of {env_export.ENV_LEVELS}")
    ceiling = env_export.ENV_MAX_ROWS[level]
    upper_bound = env_export.count(db, rec, sel, level)
    if upper_bound > ceiling:
        raise HTTPException(
            status_code=400,
            detail=f"{upper_bound} rows exceeds the {ceiling} limit for level={level}. "
                   "Narrow the selection or the window, or use level=day.",
        )
    cols, rows = env_export.fetch(db, rec, sel, level)
    if not rows:
        raise HTTPException(status_code=404, detail=env_export.NO_ROWS_EXPLANATION)
    def stream():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(cols)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        for row in rows:
            writer.writerow(["" if row.get(c) is None else row[c] for c in cols])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    logger.info(f"user={getattr(current_user, 'username', '?')} exporting {len(rows)} environment rows level={level}")
    return StreamingResponse(
        stream(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=bpp_environment_{level}_{stamp}.csv",
            "X-Export-Rows": str(len(rows)),
            "X-Export-Resolution": "chamber-level; hourly mean across the chamber's sensors",
        },
    )


@router.get("/traits.csv", operation_id="export_traits_csv")
async def export_traits_csv(
    parsed=Depends(parse_request),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    rec, sel, preset = parsed
    total = count_rows(db, rec, sel)
    if total == 0:
        raise HTTPException(status_code=404, detail="No observations that pass the QC filter match this selection and window.")
    if total > MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"{total} rows exceeds the {MAX_ROWS} limit. Narrow the selection, or use level=day/plant.",
        )
    lookup, gdd_meta = gdd_export.build_lookup(db, rec, sel)
    _reject_invalid_anchor(gdd_meta)
    # Computed before streaming starts: a download can be pressed without ever
    # opening the preview, and a selection row that matched nothing would then
    # leave no trace at all.
    hits = scope_hits(db, sel, coverage(db, rec, sel))
    cols, result = fetch(db, rec, sel)
    cols = cols + gdd_export.columns_for(rec)

    def stream():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(cols)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        for raw in result.mappings():
            row = gdd_export.enrich(dict(raw), rec, lookup)
            writer.writerow(["" if row.get(c) is None else row[c] for c in cols])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    name = f"bpp_traits_{rec.level}_{preset}_{stamp}.csv"
    logger.info(
        f"user={getattr(current_user, 'username', '?')} exporting {total} rows "
        f"level={rec.level} preset={preset} recipe={rec.describe()}"
    )
    return StreamingResponse(
        stream(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={name}",
            "X-Export-Rows": str(total),
            "X-Export-Recipe": _ascii_header(rec.describe()),
            "X-Export-Gdd": _ascii_header(_gdd_header(gdd_meta)),
            "X-Export-Scopes": _ascii_header(_scopes_header(hits)),
        },
    )
