"""Plant viewer router: plant key -> one plant -> its observations and images.

- The plant key `<batch>_<cultivar>_<treatment>_<replicate>` is the external identifier;
  plants.id is only an internal surrogate key.
- Images come from the single-plant image directory mounted at /app/crops (CROPS_DIR in
  Compose); the path follows from the plant key (`<batch>/<cultivar>/<treatment>/rep-<n>/`).
  Without that mount the image endpoints return 503.
"""
import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import List, Optional

from ....core.dependencies import get_db
from ....models.phenotype import Plant, RaspiObservation, Cultivar, Treatment, Batch
from ....core.exceptions import DatabaseError
from ....services.trait_export import gdd as gdd_export

router = APIRouter()

CROPS_ROOT = os.getenv("CROPS_ROOT", "/app/crops")
# Transparent segmentation and assignment overlays (PNG, rendered offline by imaging/overlays),
# in a read-only tree that mirrors the crops; without that mount the overlay endpoint returns 503.
OVERLAY_ROOT = os.getenv("OVERLAY_ROOT", "/app/crops_overlay")
_TS_RE = re.compile(r"(\d{12})")   # YYYYMMDDHHMM in the file name
# Default trait columns for the growth curves and QC (override with ?fields=)
_DEFAULT_TRAITS = ["leaf_count", "leaf_area", "solidity", "plant_height", "plant_width", "canopy_porosity"]

_SEWING_SQL = text("""
    SELECT MIN(pch.entry_date)
    FROM plants p
    JOIN plant_positions pch ON pch.plant_id = p.parent_plant_id
    JOIN growth_chambers gc       ON gc.id = pch.chamber_id
    WHERE p.id = :pid AND gc.chamber_code LIKE 'R%'
""")


def _business_key(batch, cultivar, treatment, replicate) -> str:
    return f"{batch}_{cultivar}_{treatment}_{replicate}"


def _plant_dir(batch, cultivar, treatment, replicate) -> Path:
    return Path(CROPS_ROOT) / str(batch) / str(cultivar) / str(treatment) / f"rep-{replicate}"


def _overlay_dir(batch, cultivar, treatment, replicate) -> Path:
    return Path(OVERLAY_ROOT) / str(batch) / str(cultivar) / str(treatment) / f"rep-{replicate}"


def _plant_codes(db: Session, plant_id: int):
    """Return (batch_code, cultivar_code, treatment_code, replicate_code, plant_type, parent_plant_id) or None."""
    row = (db.query(Batch.batch_code, Cultivar.cultivar_code, Treatment.treatment_code,
                    Plant.replicate_code, Plant.plant_type, Plant.parent_plant_id)
           .join(Batch, Batch.id == Plant.batch_id)
           .join(Cultivar, Cultivar.id == Plant.cultivar_id)
           .join(Treatment, Treatment.id == Plant.treatment_id)
           .filter(Plant.id == plant_id).first())
    return row


@router.get("/resolve", operation_id="plant_view_resolve")
def resolve_plant(
    batch_code: str = QueryParam(...),
    cultivar_code: str = QueryParam(...),
    treatment_code: str = QueryParam("Control"),
    replicate_code: int = QueryParam(...),
    db: Session = Depends(get_db),
):
    """Plant key (batch, accession, treatment, replicate) -> the one matching plant; 404 if none."""
    plant = (db.query(Plant)
             .join(Batch, Batch.id == Plant.batch_id)
             .join(Cultivar, Cultivar.id == Plant.cultivar_id)
             .join(Treatment, Treatment.id == Plant.treatment_id)
             .filter(Batch.batch_code == batch_code,
                     Cultivar.cultivar_code == cultivar_code,
                     Treatment.treatment_code == treatment_code,
                     Plant.replicate_code == replicate_code,
                     Plant.plant_type == "observation_individual")
             .first())
    if plant is None:
        raise HTTPException(status_code=404, detail="No matching plant for this business key")

    sewing = db.execute(_SEWING_SQL, {"pid": plant.id}).scalar()
    das_row = db.execute(text(
        "SELECT min(day_after_sewing), max(day_after_sewing), count(*) "
        "FROM trait_observations WHERE plant_id = :pid"), {"pid": plant.id}).first()

    return {
        "business_key": _business_key(batch_code, cultivar_code, treatment_code, replicate_code),
        "plant_id": plant.id,
        "batch_code": batch_code,
        "cultivar_code": cultivar_code,
        "treatment_code": treatment_code,
        "replicate_code": replicate_code,
        "plant_type": plant.plant_type,
        "parent_plant_id": plant.parent_plant_id,
        "sewing_date": sewing.isoformat() if sewing else None,
        "das_min": das_row[0], "das_max": das_row[1],
        "n_raspi_observations": das_row[2],
    }


@router.get("/plants/{plant_id}/observations", operation_id="plant_view_observations")
def plant_observations(
    plant_id: int,
    date_from: Optional[str] = QueryParam(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = QueryParam(None, description="YYYY-MM-DD"),
    das_min: Optional[int] = QueryParam(None),
    das_max: Optional[int] = QueryParam(None),
    qc_status: Optional[str] = QueryParam(None, pattern="^(no|auto|verified)$"),
    fields: Optional[List[str]] = QueryParam(None),
    include_gdd: bool = QueryParam(False, description="Attach aligned thermal time per observation (hourly resolution)"),
    gdd_anchor: Optional[str] = QueryParam(None, description="Chamber whose entry day is GDD = 0"),
    limit: int = QueryParam(1000, ge=1, le=5000),
    offset: int = QueryParam(0, ge=0),
    db: Session = Depends(get_db),
):
    """Image-trait time series of one plant, filterable by date range, DAS and qc_status."""
    if _plant_codes(db, plant_id) is None:
        raise HTTPException(status_code=404, detail=f"Plant {plant_id} not found")

    traits = fields or _DEFAULT_TRAITS
    valid = {c.name for c in RaspiObservation.__table__.columns}
    bad = [f for f in traits if f not in valid]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown fields: {bad}")

    base_cols = ["observation_timestamp", "day_after_sewing", "qc_status"]
    q = db.query(RaspiObservation).filter(RaspiObservation.plant_id == plant_id)
    if date_from:
        q = q.filter(RaspiObservation.observation_timestamp >= date_from)
    if date_to:
        q = q.filter(RaspiObservation.observation_timestamp < text("(:d::date + 1)").bindparams(d=date_to))
    if das_min is not None:
        q = q.filter(RaspiObservation.day_after_sewing >= das_min)
    if das_max is not None:
        q = q.filter(RaspiObservation.day_after_sewing <= das_max)
    if qc_status:
        q = q.filter(RaspiObservation.qc_status == qc_status)
    total = q.count()
    rows = q.order_by(RaspiObservation.observation_timestamp).limit(limit).offset(offset).all()

    # Thermal time is walked through the chamber history, not stored — the same
    # definition the export uses, so an axis switch here and a `gdd_aligned` column in
    # the CSV cannot drift apart. Resolved *per observation timestamp*, because the
    # model accumulates hourly: two frames of one day differ, so the series stays
    # per-frame on a GDD axis. A batch whose chambers have no environment records gets
    # nulls (never 0) and `observations_with_value = 0`, which is what lets the caller
    # say "no thermal time here" instead of drawing an empty chart.
    gdd_at_ts: dict = {}
    gdd_meta = None
    if include_gdd:
        stamps = [o.observation_timestamp for o in rows if o.observation_timestamp is not None]
        gdd_at_ts, gdd_meta = gdd_export.lookup_at_timestamps(plant_id, stamps, gdd_anchor)
        if gdd_meta.get("invalid_anchor"):
            raise HTTPException(status_code=400, detail=gdd_meta["reason"])

    def serialize(o):
        d = {"observation_timestamp": o.observation_timestamp.isoformat() if o.observation_timestamp else None,
             "day_after_sewing": o.day_after_sewing, "qc_status": o.qc_status}
        for f in traits:
            d[f] = getattr(o, f, None)
        if include_gdd:
            d["gdd_aligned"] = gdd_at_ts.get(o.observation_timestamp)
        return d

    out = {"plant_id": plant_id, "total_count": total, "limit": limit, "offset": offset,
           "fields": base_cols + list(traits) + (["gdd_aligned"] if include_gdd else []),
           "data": [serialize(o) for o in rows]}
    if gdd_meta is not None:
        out["gdd"] = gdd_meta
    return out


def _list_frames(db: Session, plant_id: int):
    codes = _plant_codes(db, plant_id)
    if codes is None:
        raise HTTPException(status_code=404, detail=f"Plant {plant_id} not found")
    batch, cultivar, treatment, replicate = codes[0], codes[1], codes[2], codes[3]
    pdir = _plant_dir(batch, cultivar, treatment, replicate)
    if not pdir.is_dir():
        if not Path(CROPS_ROOT).is_dir():
            raise HTTPException(status_code=503,
                                detail="Single-plant images are not mounted (CROPS_DIR in platform/.env)")
        # The archive is mounted but this plant has no images (e.g. the other
        # replicates of the demo plant): an empty list, not an error.
        return pdir, []
    # timestamp -> (das, qc_status) from the database, to label each image
    meta = {}
    for o in db.query(RaspiObservation).filter(RaspiObservation.plant_id == plant_id).all():
        if o.observation_timestamp:
            meta[o.observation_timestamp.strftime("%Y%m%d%H%M")] = (o.day_after_sewing, o.qc_status)
    frames = []
    for png in sorted(pdir.glob("*.png")):
        m = _TS_RE.search(png.name)
        key = m.group(1) if m else None
        das, qc = meta.get(key, (None, None))
        frames.append({"stem": png.name, "ts": key, "day_after_sewing": das, "qc_status": qc})
    return pdir, frames


@router.get("/plants/{plant_id}/frames", operation_id="plant_view_frames")
def plant_frames(plant_id: int, db: Session = Depends(get_db)):
    """List the plant's single-plant images: file name, timestamp, DAS, qc_status.
    has_overlays tells whether overlays exist for the plant (the web interface enables the toggle from it)."""
    codes = _plant_codes(db, plant_id)
    _, frames = _list_frames(db, plant_id)
    has_overlays = bool(codes) and _overlay_dir(codes[0], codes[1], codes[2], codes[3]).is_dir()
    return {"plant_id": plant_id, "n_frames": len(frames), "frames": frames,
            "has_overlays": has_overlays}


@router.get("/plants/{plant_id}/overlay", operation_id="plant_view_overlay")
def plant_overlay(plant_id: int, stem: str = QueryParam(...), db: Session = Depends(get_db)):
    """Serve one transparent segmentation and assignment overlay PNG. stem = a file name returned
    by the frames endpoint (same as the image file name). Static files rendered offline;
    503 when the overlay tree is not mounted."""
    codes = _plant_codes(db, plant_id)
    if codes is None:
        raise HTTPException(status_code=404, detail=f"Plant {plant_id} not found")
    odir = _overlay_dir(codes[0], codes[1], codes[2], codes[3])
    if not odir.is_dir():
        raise HTTPException(status_code=503,
                            detail="Overlay images are not mounted (OVERLAY_DIR in platform/.env)")
    if "/" in stem or "\\" in stem or not stem.lower().endswith(".png"):
        raise HTTPException(status_code=400, detail="Invalid stem")
    fpath = (odir / stem).resolve()
    if not str(fpath).startswith(str(odir.resolve()) + os.sep) or not fpath.is_file():
        raise HTTPException(status_code=404, detail="Overlay not found")
    return FileResponse(str(fpath), media_type="image/png")


@router.get("/plants/{plant_id}/image", operation_id="plant_view_image")
def plant_image(plant_id: int, stem: str = QueryParam(...), db: Session = Depends(get_db)):
    """Serve one single-plant image (PNG). stem = a file name returned by the frames endpoint."""
    codes = _plant_codes(db, plant_id)
    if codes is None:
        raise HTTPException(status_code=404, detail=f"Plant {plant_id} not found")
    pdir = _plant_dir(codes[0], codes[1], codes[2], codes[3])
    # Path traversal guard: accept a bare file name that still resolves inside the plant directory
    if "/" in stem or "\\" in stem or not stem.lower().endswith(".png"):
        raise HTTPException(status_code=400, detail="Invalid stem")
    fpath = (pdir / stem).resolve()
    if not str(fpath).startswith(str(pdir.resolve()) + os.sep) or not fpath.is_file():
        raise HTTPException(status_code=404, detail="Single-plant image not found")
    return FileResponse(str(fpath), media_type="image/png")
