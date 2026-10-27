"""
Batch registration router, mounted at /api/v1/admin when management is enabled
(see api/v1/api.py): form options, accession create, batch preview and create, batch
list and detail, plant coordinates, and appending plants to a batch.

Every endpoint takes Depends(get_admin_user) and logs the operator. The release has no
login: get_admin_user returns the fixed operator (BPP_OPERATOR).
"""

import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ....core.dependencies import get_db, get_admin_user
from ....models.phenotype import Cultivar, GrowthCondition, Rack, Sensor, Treatment
from ....schemas.admin_batch_validation import (
    _validate_reference_image,
    AppendPlantsRequest,
    AppendPlantsResponse,
    BatchDataStatusResponse,
    BatchDefaultsResponse,
    BatchPreviewResponse,
    CreateBatchRequest,
    CreateBatchResponse,
    CreateCultivarRequest,
    CultivarOut,
    FormOptionsResponse,
    GrowthConditionOption,
    ObservationPlantOut,
    RackOption,
    SetMilestoneRequest,
    SetMilestoneResponse,
    TreatmentOption,
    UpdatePlacementsRequest,
    UpdatePlacementsResponse,
    WALKIN_CHAMBER_CODES,
)
from ....services.admin_batch_service import (
    BatchCodeConflict,
    BatchNotFound,
    CoordinateConflict,
    DimensionResolutionError,
    batch_data_status,
    batch_defaults,
    build_append_preview,
    build_preview,
    commit_append,
    commit_batch,
    list_observation_plants,
    set_milestone,
    update_placements,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Chamber id of G120 (observation chamber) — its raspi sub-racks feed the coord picker.
G120_CHAMBER_ID = 3
# Per-chamber default growth_condition (the most common one in existing data).
DEFAULT_WALKIN_GC_ID = 2
DEFAULT_OBSERVATION_GC_ID = 6

# Local raw-frame archive root (mounted read-only via docker-compose.override.yml on
# the dev machine only). Layout: <root>/<rack>-<camera>/pic<rack>-<camera>-<ts>.jpg.
G120_PIC_ROOT = os.getenv("G120_PIC_ROOT", "/app/g120_pic")


@router.get(
    "/frames/{filename}",
    operation_id="admin_get_reference_frame",
    summary="Serve a recorded reference frame from the local 8T1 archive (admin, dev only)",
)
async def get_reference_frame(filename: str, admin_user=Depends(get_admin_user)):
    """Return the full-frame image a coordinate was digitized from, so the coordinate
    page can auto-display an already-recorded reference. Only usable where the 8T1
    archive is mounted (the dev machine); on production the whole admin router is not
    even mounted. Filename is validated (no path traversal) and the resolved path is
    confined to the archive root."""
    try:
        name = _validate_reference_image(filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not name:
        raise HTTPException(status_code=404, detail="no frame")
    m = re.match(r"^pic(.+)-\d{12}\.\w+$", name)  # picA1-102-<ts>.jpg -> subdir A1-102
    if not m:
        raise HTTPException(status_code=422, detail="unrecognized frame name")
    root = Path(G120_PIC_ROOT).resolve()
    fpath = (root / m.group(1) / name).resolve()
    if os.path.commonpath([str(root), str(fpath)]) != str(root):
        raise HTTPException(status_code=400, detail="invalid path")
    if not fpath.is_file():
        raise HTTPException(status_code=404, detail="frame not found on this machine")
    media = "image/png" if name.lower().endswith(".png") else "image/jpeg"
    return FileResponse(str(fpath), media_type=media)


def _gc_label(gc: GrowthCondition) -> str:
    """Human label for a growth_condition dropdown entry."""
    if gc.notes and gc.notes.strip():
        return f"{gc.id}: {gc.notes.strip()}"
    parts = [p for p in (gc.light_intensity, gc.light_photoperiod) if p and p.strip()]
    suffix = f" ({', '.join(parts)})" if parts else ""
    return f"gc {gc.id}{suffix}"


@router.get(
    "/batches/form-options",
    response_model=FormOptionsResponse,
    operation_id="admin_batch_form_options",
    summary="Dropdown sources for the create-batch form (admin only)",
)
async def get_form_options(
    db: Session = Depends(get_db),
    admin_user=Depends(get_admin_user),
):
    """Return the dimension lists the create form needs: walk-in chambers,
    treatments, growth_conditions, and the 16 G120 raspi sub-racks. New batches
    always use the chamber blank rack for walk-in (no rack specified), so named walk-in
    racks are intentionally not exposed here."""
    treatments = db.query(Treatment).order_by(Treatment.id).all()
    gcs = db.query(GrowthCondition).order_by(GrowthCondition.id).all()
    g120_racks = (
        db.query(Rack)
        .filter(Rack.chamber_id == G120_CHAMBER_ID)
        .order_by(Rack.rack_code)
        .all()
    )

    logger.info(f"Admin {admin_user.username} fetched batch form-options")

    return FormOptionsResponse(
        walkin_chamber_codes=sorted(WALKIN_CHAMBER_CODES),
        treatments=[TreatmentOption.model_validate(t) for t in treatments],
        growth_conditions=[
            GrowthConditionOption(id=gc.id, label=_gc_label(gc)) for gc in gcs
        ],
        g120_racks=[
            RackOption(id=r.id, rack_code=r.rack_code)
            for r in g120_racks
            if r.rack_code and r.rack_code.strip()
        ],
        default_walkin_growth_condition_id=DEFAULT_WALKIN_GC_ID,
        default_observation_growth_condition_id=DEFAULT_OBSERVATION_GC_ID,
    )


@router.post(
    "/batches/preview",
    response_model=BatchPreviewResponse,
    operation_id="admin_batch_preview",
    summary="Dry-run expand of a create-batch request (admin only)",
)
async def preview_batch(
    request: CreateBatchRequest,
    admin_user=Depends(get_admin_user),
):
    """Expand the request into the plants + chamber_history that would be written,
    without touching the DB. Structural validation runs in the request schema;
    FK existence is only checked on the real POST."""
    logger.info(f"Admin {admin_user.username} previewed batch '{request.batch_code}'")
    return build_preview(request)


@router.post(
    "/batches",
    response_model=CreateBatchResponse,
    status_code=201,
    operation_id="admin_create_batch",
    summary="Create a new batch with its plants and chamber history (admin only)",
)
async def create_batch(
    request: CreateBatchRequest,
    db: Session = Depends(get_db),
    admin_user=Depends(get_admin_user),
):
    """Resolve dimension codes to FK ids and write batch -> plants ->
    chamber_history in one transaction. 409 if batch_code exists, 422 if any
    code/id cannot be resolved."""
    try:
        result = commit_batch(db, request)
    except BatchCodeConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except DimensionResolutionError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    logger.info(
        f"Admin {admin_user.username} created batch '{result['batch_code']}' "
        f"(id={result['batch_id']}, {result['plant_count']} plants, "
        f"{result['chamber_history_count']} chamber_history)"
    )
    return CreateBatchResponse(**result)


@router.get(
    "/batches/{batch_code}/observation-plants",
    response_model=list[ObservationPlantOut],
    operation_id="admin_batch_observation_plants",
    summary="Existing observation plants of a batch with placement (admin only)",
)
async def get_observation_plants(
    batch_code: str,
    db: Session = Depends(get_db),
    admin_user=Depends(get_admin_user),
):
    """List existing observation_individual plants + their G120 placement so the
    edit page can show what's already entered (cultivar locked, placement editable).
    404 if the batch doesn't exist."""
    try:
        rows = list_observation_plants(db, batch_code)
    except BatchNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    return [ObservationPlantOut(**r) for r in rows]


@router.get(
    "/batches/{batch_code}/defaults",
    response_model=BatchDefaultsResponse,
    operation_id="admin_batch_defaults",
    summary="A batch's existing shared defaults, to pre-fill the edit form (admin only)",
)
async def get_batch_defaults(
    batch_code: str,
    db: Session = Depends(get_db),
    admin_user=Depends(get_admin_user),
):
    """Return the batch's existing treatment / chamber / date / growth-condition
    defaults so the edit/append page starts from the record, not blank. 404 if the
    batch doesn't exist."""
    try:
        return BatchDefaultsResponse(**batch_defaults(db, batch_code))
    except BatchNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/racks/camera-map",
    operation_id="admin_camera_rack_map",
    summary="raspi camera code -> rack_code map (admin only)",
)
async def get_camera_rack_map(
    db: Session = Depends(get_db),
    admin_user=Depends(get_admin_user),
):
    """Map each raspi camera code (= sensor_code, e.g. A1-102) to its rack_code
    (e.g. A1_1). The coordinate page uses it to show which rack a loaded frame
    resolves to — the same camera->sensor->rack link the backend writes on save."""
    rows = (
        db.query(Sensor.sensor_code, Rack.rack_code)
        .join(Rack, Rack.id == Sensor.rack_id)
        .filter(Sensor.sensor_type == "raspi")
        .all()
    )
    return {code: rack for code, rack in rows if code and rack}


@router.get(
    "/batches/{batch_code}/data-status",
    response_model=BatchDataStatusResponse,
    operation_id="admin_batch_data_status",
    summary="Per-cultivar data completeness for a batch (admin only)",
)
async def get_data_status(
    batch_code: str,
    db: Session = Depends(get_db),
    admin_user=Depends(get_admin_user),
):
    """Per-cultivar counts of observation plants having raspi / physical(3D) /
    thermal data, plus lifecycle gates (entered/exited observation) so the UI can
    distinguish a real gap from 'not due yet'. 404 if the batch doesn't exist."""
    try:
        return batch_data_status(db, batch_code)
    except BatchNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/batches/{batch_code}/milestone",
    response_model=SetMilestoneResponse,
    operation_id="admin_batch_set_milestone",
    summary="Toggle an event-backed data milestone for a cultivar (admin only)",
)
async def post_milestone(
    batch_code: str,
    request: SetMilestoneRequest,
    db: Session = Depends(get_db),
    admin_user=Depends(get_admin_user),
):
    """Mark/unmark an event-backed stage (e.g. digital_camera) for a cultivar in a
    batch. 404 unknown batch, 422 if the cultivar isn't in the batch."""
    try:
        result = set_milestone(
            db, batch_code, request.cultivar_code, request.stage, request.shot,
            marked_by=admin_user.username,
        )
    except BatchNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DimensionResolutionError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    logger.info(
        f"Admin {admin_user.username} set milestone {request.stage}={request.shot} "
        f"for {request.cultivar_code} in batch '{batch_code}'"
    )
    return SetMilestoneResponse(**result)


@router.patch(
    "/batches/{batch_code}/plants",
    response_model=UpdatePlacementsResponse,
    operation_id="admin_batch_update_placements",
    summary="Update placement/replicate of existing plants in a batch (admin only)",
)
async def patch_placements(
    batch_code: str,
    request: UpdatePlacementsRequest,
    db: Session = Depends(get_db),
    admin_user=Depends(get_admin_user),
):
    """Update rack/coordinate/replicate of existing observation plants (typo fixes).
    Cultivar/treatment are not editable here. 404 unknown batch, 409 coordinate
    collision, 422 if a plant_id is not an observation plant in the batch."""
    try:
        result = update_placements(db, batch_code, request.updates)
    except BatchNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CoordinateConflict as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except DimensionResolutionError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    logger.info(
        f"Admin {admin_user.username} updated {result['updated_count']} plant "
        f"placements in batch '{result['batch_code']}'"
    )
    return UpdatePlacementsResponse(**result)


@router.post(
    "/batches/{batch_code}/plants/preview",
    response_model=BatchPreviewResponse,
    operation_id="admin_batch_append_preview",
    summary="Dry-run expand of plants to append to an existing batch (admin only)",
)
async def preview_append_plants(
    batch_code: str,
    request: AppendPlantsRequest,
    admin_user=Depends(get_admin_user),
):
    """Expand the plant_groups that would be added to an existing batch, without
    touching the DB. start/end in the response reflect the appended rows only."""
    logger.info(f"Admin {admin_user.username} previewed append to batch '{batch_code}'")
    return build_append_preview(batch_code, request.plant_groups)


@router.post(
    "/batches/{batch_code}/plants",
    response_model=AppendPlantsResponse,
    status_code=201,
    operation_id="admin_batch_append_plants",
    summary="Append plants to an existing batch (admin only)",
)
async def append_plants(
    batch_code: str,
    request: AppendPlantsRequest,
    db: Session = Depends(get_db),
    admin_user=Depends(get_admin_user),
):
    """Append plant groups to an existing batch (incremental entry). 404 if the
    batch doesn't exist, 409 if a coordinate collides with one already in the
    batch, 422 if any code/id cannot be resolved."""
    try:
        result = commit_append(db, batch_code, request.plant_groups)
    except BatchNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CoordinateConflict as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except DimensionResolutionError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    logger.info(
        f"Admin {admin_user.username} appended {result['added_plant_count']} plants "
        f"to batch '{result['batch_code']}' (total now {result['plant_count_total']})"
    )
    return AppendPlantsResponse(**result)


@router.post(
    "/cultivars",
    response_model=CultivarOut,
    status_code=201,
    operation_id="admin_create_cultivar",
    summary="Create a minimal cultivar (admin only)",
)
async def create_cultivar(
    request: CreateCultivarRequest,
    db: Session = Depends(get_db),
    admin_user=Depends(get_admin_user),
):
    """Create a cultivar with only cultivar_code required (plus optional
    product_name/notes). Rich metadata (genome_type, seed stock, …) is deferred
    to a dedicated channel because its authoritative source is uncertain.

    New batches almost always carry a new cultivar (274/293 appear in one batch),
    so this lets the form add one inline. Returns 409 if the code already exists."""
    code = request.cultivar_code.strip()
    if not code:
        raise HTTPException(status_code=422, detail="cultivar_code must not be blank")

    existing = db.query(Cultivar).filter(Cultivar.cultivar_code == code).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"cultivar_code {code!r} already exists (id={existing.id})",
        )

    cultivar = Cultivar(
        cultivar_code=code,
        product_name=request.product_name,
        notes=request.notes,
    )
    db.add(cultivar)
    db.commit()
    db.refresh(cultivar)

    logger.info(f"Admin {admin_user.username} created cultivar '{code}' (id={cultivar.id})")

    return CultivarOut.model_validate(cultivar)
