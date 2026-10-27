"""
Admin batch-creation service (lean scope: create new batch only).

This module has two layers:

1. Pure expand layer (this file, no DB): turns a validated CreateBatchRequest into
   a flat ExpandedBatch of plants + chamber_history rows, with codes (not FK ids)
   and structural parent links by local_id. Fully unit-testable without a database.

2. Commit layer: resolves codes -> FK ids, derives sensor_id from rack, assigns ids
   from the table sequences, and writes in FK order batch -> plants -> chamber_history.

Field rules: each G120 individual gets exactly ONE chamber_history row
on a raspi sub-rack (not arduino+raspi); walk-in rows have NULL coord/time.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.phenotype import (
    Batch,
    BatchMilestone,
    Cultivar,
    GrowthChamber,
    GrowthCondition,
    PhysicalObservation,
    Plant,
    PlantChamberHistory,
    Rack,
    RaspiObservation,
    Sensor,
    ThermalObservation,
    Treatment,
)
from app.schemas.admin_batch_validation import (
    BatchPreviewResponse,
    CreateBatchRequest,
    ExpandedChamberHistoryOut,
    ExpandedPlantOut,
)

NURSERY = "nursery_group"
OBSERVATION = "observation_individual"

# Event-backed data stage with no observation table (tracked in batch_milestones).
DIGITAL_CAMERA = "digital_camera"

# Sensor type used per chamber_history role.
ROLE_SENSOR_TYPE = {"walkin": "arduino", "observation": "raspi"}

# A raspi frame is named pic<camera>-<yyyymmddHHMM>.jpg, where <camera> is the
# raspi sensor_code (e.g. A1-102). The camera thus resolves to a sensor and its
# rack — this is how a coordinate-page placement fixes rack + sensor at once.
_CAMERA_RE = re.compile(r"^pic(.+)-\d{12}\.\w+$", re.IGNORECASE)


def _camera_code_from_ref(ref: str) -> str:
    """'picA1-102-202606041100.jpg' -> 'A1-102' (a raspi sensor_code)."""
    m = _CAMERA_RE.match(ref)
    if not m:
        raise DimensionResolutionError(
            f"cannot parse camera code from reference_image {ref!r}"
        )
    return m.group(1)


class DimensionResolutionError(Exception):
    """A code/id in the request could not be resolved to an existing row.
    Router translates this to HTTP 422."""


class BatchCodeConflict(Exception):
    """batch_code already exists. Router translates this to HTTP 409."""


class BatchNotFound(Exception):
    """Target batch_code does not exist (append). Router -> HTTP 404."""


class CoordinateConflict(Exception):
    """An appended G120 coordinate collides with one already in the batch.
    Router translates this to HTTP 409."""


# ---------------------------------------------------------------------------
# Expanded intermediate structures (codes, not FK ids; links by local_id)
# ---------------------------------------------------------------------------

@dataclass
class ExpandedPlant:
    local_id: int
    plant_type: str
    cultivar_code: str
    treatment_code: str
    replicate_code: Optional[int] = None
    parent_local_id: Optional[int] = None


@dataclass
class ExpandedChamberHistory:
    plant_local_id: int
    role: str  # 'walkin' | 'observation'
    chamber_code: str
    growth_condition_id: int
    entry_date: date
    rack_code: Optional[str] = None
    entry_time: Optional[str] = None
    exit_date: Optional[date] = None
    exit_time: Optional[str] = None
    coordinate_x: Optional[int] = None
    coordinate_y: Optional[int] = None


@dataclass
class ExpandedBatch:
    batch_code: str
    start_date: date
    end_date: Optional[date]
    notes: Optional[str]
    plants: List[ExpandedPlant] = field(default_factory=list)
    chamber_history: List[ExpandedChamberHistory] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure expand
# ---------------------------------------------------------------------------

def _expand_groups(plant_groups) -> Tuple[List["ExpandedPlant"], List["ExpandedChamberHistory"]]:
    """Expand plant_groups into flat plants + chamber_history rows (pure, no DB).
    local_id is a 1-based running counter in creation order (nursery before its
    individuals); the commit layer maps it to real ids and wires parent_plant_id.
    Shared by create (expand_batch) and append (commit_append)."""
    plants: List[ExpandedPlant] = []
    chamber_history: List[ExpandedChamberHistory] = []
    next_local = 1

    for group in plant_groups:
        # 1 nursery_group: replicate_code=None, parent=None
        nursery = ExpandedPlant(
            local_id=next_local,
            plant_type=NURSERY,
            cultivar_code=group.cultivar_code,
            treatment_code=group.treatment_code,
            replicate_code=None,
            parent_local_id=None,
        )
        next_local += 1
        plants.append(nursery)

        # Nursery walk-in chamber_history: one row per visit, NULL coord/time.
        for visit in group.walkin_visits:
            chamber_history.append(
                ExpandedChamberHistory(
                    plant_local_id=nursery.local_id,
                    role="walkin",
                    chamber_code=visit.chamber_code,
                    rack_code=visit.rack_code,  # None => no rack specified (service maps to blank rack)
                    growth_condition_id=visit.growth_condition_id,
                    entry_date=visit.entry_date,
                    entry_time=None,
                    exit_date=visit.exit_date,
                    exit_time=None,
                    coordinate_x=None,
                    coordinate_y=None,
                )
            )

        # N observation_individual + their single G120 chamber_history row each.
        obs = group.observation
        for ind in obs.individuals:
            individual = ExpandedPlant(
                local_id=next_local,
                plant_type=OBSERVATION,
                cultivar_code=group.cultivar_code,
                treatment_code=group.treatment_code,
                replicate_code=ind.replicate_code,
                parent_local_id=nursery.local_id,
            )
            next_local += 1
            plants.append(individual)

            chamber_history.append(
                ExpandedChamberHistory(
                    plant_local_id=individual.local_id,
                    role="observation",
                    chamber_code="G120",
                    rack_code=ind.rack_code,
                    growth_condition_id=obs.growth_condition_id,
                    entry_date=obs.entry_date,
                    entry_time=obs.entry_time,
                    exit_date=obs.exit_date,
                    exit_time=obs.exit_time,
                    coordinate_x=ind.coordinate_x,
                    coordinate_y=ind.coordinate_y,
                )
            )

    return plants, chamber_history


def expand_batch(req: CreateBatchRequest) -> ExpandedBatch:
    """Expand a validated create request into an ExpandedBatch (plants +
    chamber_history + derived batch dates)."""
    plants, chamber_history = _expand_groups(req.plant_groups)
    start_date, end_date = _derive_batch_dates(chamber_history)
    return ExpandedBatch(
        batch_code=req.batch_code,
        start_date=start_date,
        end_date=end_date,
        notes=req.notes,
        plants=plants,
        chamber_history=chamber_history,
    )


def _derive_batch_dates(rows: List[ExpandedChamberHistory]):
    """start = earliest entry_date across all rows; end = latest exit_date present
    (None if no row has an exit_date)."""
    start_date = min(r.entry_date for r in rows)
    exits = [r.exit_date for r in rows if r.exit_date is not None]
    end_date = max(exits) if exits else None
    return start_date, end_date


# ---------------------------------------------------------------------------
# Preview projection (request -> what-will-be-written, codes not yet ids)
# ---------------------------------------------------------------------------

def _project_preview(batch_code, start_date, end_date, notes, plants, chamber_history) -> BatchPreviewResponse:
    return BatchPreviewResponse(
        batch_code=batch_code,
        start_date=start_date,
        end_date=end_date,
        notes=notes,
        plant_count=sum(p.plant_type == OBSERVATION for p in plants),
        nursery_group_count=sum(p.plant_type == NURSERY for p in plants),
        chamber_history_count=len(chamber_history),
        plants=[
            ExpandedPlantOut(
                local_id=p.local_id,
                plant_type=p.plant_type,
                cultivar_code=p.cultivar_code,
                treatment_code=p.treatment_code,
                replicate_code=p.replicate_code,
                parent_local_id=p.parent_local_id,
            )
            for p in plants
        ],
        chamber_history=[
            ExpandedChamberHistoryOut(
                plant_local_id=c.plant_local_id,
                role=c.role,
                chamber_code=c.chamber_code,
                rack_code=c.rack_code,
                growth_condition_id=c.growth_condition_id,
                entry_date=c.entry_date,
                entry_time=c.entry_time,
                exit_date=c.exit_date,
                exit_time=c.exit_time,
                coordinate_x=c.coordinate_x,
                coordinate_y=c.coordinate_y,
            )
            for c in chamber_history
        ],
    )


def build_preview(req: CreateBatchRequest) -> BatchPreviewResponse:
    expanded = expand_batch(req)
    return _project_preview(
        expanded.batch_code, expanded.start_date, expanded.end_date,
        expanded.notes, expanded.plants, expanded.chamber_history,
    )


def build_append_preview(batch_code: str, plant_groups) -> BatchPreviewResponse:
    """Dry-run of an append: shows the plants + chamber_history that WOULD be added.
    start/end reflect the appended rows only (the real batch dates are recomputed
    over all rows at commit)."""
    plants, chamber_history = _expand_groups(plant_groups)
    start_date, end_date = _derive_batch_dates(chamber_history)
    return _project_preview(batch_code, start_date, end_date, None, plants, chamber_history)


# ---------------------------------------------------------------------------
# Commit layer (DB): resolve codes -> FK ids, derive sensor, write in FK order
# ---------------------------------------------------------------------------

@dataclass
class _Dimensions:
    """Lookup tables resolved once from the DB for a single commit."""
    cultivar_id: Dict[str, int]
    treatment_id: Dict[str, int]
    chamber_id: Dict[str, int]
    growth_condition_ids: set
    # (chamber_id, rack_code) -> rack_id; rack_code "" is the chamber blank rack.
    rack_id: Dict[Tuple[int, str], int]
    # chamber_id -> blank rack_id (for walk-in with no rack)
    blank_rack_id: Dict[int, int]
    # (rack_id, sensor_type) -> sensor_id
    sensor_id: Dict[Tuple[int, str], int]
    # raspi sensor_code (= camera code in frame filenames) -> (sensor_id, rack_id)
    raspi_sensor: Dict[str, Tuple[int, int]]


def _load_dimensions(db: Session) -> _Dimensions:
    cultivar_id = {c.cultivar_code: c.id for c in db.query(Cultivar).all()}
    treatment_id = {t.treatment_code: t.id for t in db.query(Treatment).all()}
    chamber_id = {c.chamber_code: c.id for c in db.query(GrowthChamber).all()}
    growth_condition_ids = {gc.id for gc in db.query(GrowthCondition.id).all()}

    rack_id: Dict[Tuple[int, str], int] = {}
    blank_rack_id: Dict[int, int] = {}
    for r in db.query(Rack).all():
        code = (r.rack_code or "").strip()
        rack_id[(r.chamber_id, code)] = r.id
        if code == "" and r.chamber_id is not None:
            blank_rack_id[r.chamber_id] = r.id

    sensor_id: Dict[Tuple[int, str], int] = {}
    raspi_sensor: Dict[str, Tuple[int, int]] = {}
    for s in db.query(Sensor).all():
        if s.rack_id is not None and s.sensor_type:
            sensor_id[(s.rack_id, s.sensor_type)] = s.id
            if s.sensor_type == "raspi" and s.sensor_code:
                raspi_sensor[s.sensor_code] = (s.id, s.rack_id)

    return _Dimensions(
        cultivar_id=cultivar_id,
        treatment_id=treatment_id,
        chamber_id=chamber_id,
        growth_condition_ids=growth_condition_ids,
        rack_id=rack_id,
        blank_rack_id=blank_rack_id,
        sensor_id=sensor_id,
        raspi_sensor=raspi_sensor,
    )


def _resolve_rack(dims: _Dimensions, chamber_id: int, rack_code: Optional[str]) -> int:
    """rack_code None/blank => chamber blank rack (no rack specified); else (chamber, code)."""
    code = (rack_code or "").strip()
    if code == "":
        rid = dims.blank_rack_id.get(chamber_id)
        if rid is None:
            raise DimensionResolutionError(
                f"no blank rack for chamber_id={chamber_id} (cannot place a walk-in stay without a rack)"
            )
        return rid
    rid = dims.rack_id.get((chamber_id, code))
    if rid is None:
        raise DimensionResolutionError(
            f"rack_code {code!r} not found in chamber_id={chamber_id}"
        )
    return rid


def _resolve_sensor(dims: _Dimensions, rack_id: int, role: str) -> int:
    sensor_type = ROLE_SENSOR_TYPE[role]
    sid = dims.sensor_id.get((rack_id, sensor_type))
    if sid is None:
        raise DimensionResolutionError(
            f"no {sensor_type} sensor on rack_id={rack_id} (role={role})"
        )
    return sid


def _resolve_placement(dims: _Dimensions, chamber_id: int, role: str,
                       rack_code: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """(rack_id, sensor_id) for a chamber_history row. Observation plants may defer
    placement: a blank rack_code yields (None, None) — rack + sensor are assigned
    later on the coordinate page, derived from the frame's camera code. Walk-in
    always resolves (blank rack + its arduino sensor)."""
    if role == "observation" and not (rack_code or "").strip():
        return None, None
    rid = _resolve_rack(dims, chamber_id, rack_code)
    sid = _resolve_sensor(dims, rid, role)
    return rid, sid


def commit_batch(db: Session, req: CreateBatchRequest) -> dict:
    """Resolve codes -> FK ids and write batch + plants + chamber_history in a
    single transaction. Returns a small summary. Raises BatchCodeConflict (409)
    or DimensionResolutionError (422); the caller owns the HTTP translation.

    Relies on migration 005 having advanced the id sequences so ORM inserts do
    not collide with existing PKs.
    """
    expanded = expand_batch(req)
    dims = _load_dimensions(db)

    if db.query(Batch).filter(Batch.batch_code == req.batch_code).first():
        raise BatchCodeConflict(f"batch_code {req.batch_code!r} already exists")

    # Pre-resolve every code so we fail before writing anything.
    for g in req.plant_groups:
        if g.cultivar_code not in dims.cultivar_id:
            raise DimensionResolutionError(f"cultivar_code {g.cultivar_code!r} not found")
        if g.treatment_code not in dims.treatment_id:
            raise DimensionResolutionError(f"treatment_code {g.treatment_code!r} not found")
    for c in expanded.chamber_history:
        if c.chamber_code not in dims.chamber_id:
            raise DimensionResolutionError(f"chamber_code {c.chamber_code!r} not found")
        if c.growth_condition_id not in dims.growth_condition_ids:
            raise DimensionResolutionError(
                f"growth_condition_id {c.growth_condition_id} not found"
            )
        chamber_id = dims.chamber_id[c.chamber_code]
        _resolve_placement(dims, chamber_id, c.role, c.rack_code)  # validate now

    # Write inside one transaction.
    batch = Batch(
        batch_code=expanded.batch_code,
        start_date=expanded.start_date,
        end_date=expanded.end_date,
        notes=expanded.notes,
    )
    db.add(batch)
    db.flush()  # get batch.id

    local_to_real: Dict[int, int] = {}
    for p in expanded.plants:
        plant = Plant(
            batch_id=batch.id,
            cultivar_id=dims.cultivar_id[p.cultivar_code],
            treatment_id=dims.treatment_id[p.treatment_code],
            replicate_code=p.replicate_code,
            plant_type=p.plant_type,
            parent_plant_id=(
                local_to_real[p.parent_local_id]
                if p.parent_local_id is not None
                else None
            ),
        )
        db.add(plant)
        db.flush()  # get plant.id (nursery flushed before its individuals)
        local_to_real[p.local_id] = plant.id

    for c in expanded.chamber_history:
        chamber_id = dims.chamber_id[c.chamber_code]
        rack_id, sensor_id = _resolve_placement(dims, chamber_id, c.role, c.rack_code)
        db.add(
            PlantChamberHistory(
                plant_id=local_to_real[c.plant_local_id],
                batch_id=batch.id,
                chamber_id=chamber_id,
                rack_id=rack_id,
                growth_condition_id=c.growth_condition_id,
                sensor_id=sensor_id,
                entry_date=c.entry_date,
                entry_time=c.entry_time,
                exit_date=c.exit_date,
                exit_time=c.exit_time,
                coordinate_x=c.coordinate_x,
                coordinate_y=c.coordinate_y,
            )
        )

    db.commit()

    return {
        "batch_id": batch.id,
        "batch_code": batch.batch_code,
        "plant_count": sum(p.plant_type == OBSERVATION for p in expanded.plants),
        "nursery_group_count": sum(p.plant_type == NURSERY for p in expanded.plants),
        "chamber_history_count": len(expanded.chamber_history),
    }


def commit_append(db: Session, batch_code: str, plant_groups) -> dict:
    """Append plant_groups to an existing batch in one transaction. Reuses the same
    expand + resolve + write logic as create, but attaches to the existing batch_id,
    rejects coords colliding with already-persisted plants, and recomputes the
    batch's start/end dates over all rows.

    Raises BatchNotFound (404), CoordinateConflict (409), or
    DimensionResolutionError (422); the caller owns the HTTP translation.
    """
    batch = db.query(Batch).filter(Batch.batch_code == batch_code).first()
    if not batch:
        raise BatchNotFound(f"batch_code {batch_code!r} not found")

    plants, chamber_history = _expand_groups(plant_groups)
    dims = _load_dimensions(db)

    # Pre-resolve every code so we fail before writing anything.
    for g in plant_groups:
        if g.cultivar_code not in dims.cultivar_id:
            raise DimensionResolutionError(f"cultivar_code {g.cultivar_code!r} not found")
        if g.treatment_code not in dims.treatment_id:
            raise DimensionResolutionError(f"treatment_code {g.treatment_code!r} not found")
    for c in chamber_history:
        if c.chamber_code not in dims.chamber_id:
            raise DimensionResolutionError(f"chamber_code {c.chamber_code!r} not found")
        if c.growth_condition_id not in dims.growth_condition_ids:
            raise DimensionResolutionError(f"growth_condition_id {c.growth_condition_id} not found")
        chamber_id = dims.chamber_id[c.chamber_code]
        _resolve_placement(dims, chamber_id, c.role, c.rack_code)

    # New G120 coords must not collide with coords already in this batch.
    existing = (
        db.query(PlantChamberHistory.rack_id,
                 PlantChamberHistory.coordinate_x,
                 PlantChamberHistory.coordinate_y)
        .filter(PlantChamberHistory.batch_id == batch.id,
                PlantChamberHistory.coordinate_x.isnot(None))
        .all()
    )
    existing_coords = {(rid, x, y) for rid, x, y in existing}
    for c in chamber_history:
        if c.coordinate_x is None:
            continue
        chamber_id = dims.chamber_id[c.chamber_code]
        rid = _resolve_rack(dims, chamber_id, c.rack_code)
        if (rid, c.coordinate_x, c.coordinate_y) in existing_coords:
            raise CoordinateConflict(
                f"coordinate already used in batch {batch_code}: rack={c.rack_code} "
                f"({c.coordinate_x},{c.coordinate_y})"
            )

    local_to_real: Dict[int, int] = {}
    for p in plants:
        plant = Plant(
            batch_id=batch.id,
            cultivar_id=dims.cultivar_id[p.cultivar_code],
            treatment_id=dims.treatment_id[p.treatment_code],
            replicate_code=p.replicate_code,
            plant_type=p.plant_type,
            parent_plant_id=(
                local_to_real[p.parent_local_id] if p.parent_local_id is not None else None
            ),
        )
        db.add(plant)
        db.flush()
        local_to_real[p.local_id] = plant.id

    for c in chamber_history:
        chamber_id = dims.chamber_id[c.chamber_code]
        rack_id, sensor_id = _resolve_placement(dims, chamber_id, c.role, c.rack_code)
        db.add(
            PlantChamberHistory(
                plant_id=local_to_real[c.plant_local_id],
                batch_id=batch.id,
                chamber_id=chamber_id,
                rack_id=rack_id,
                growth_condition_id=c.growth_condition_id,
                sensor_id=sensor_id,
                entry_date=c.entry_date,
                entry_time=c.entry_time,
                exit_date=c.exit_date,
                exit_time=c.exit_time,
                coordinate_x=c.coordinate_x,
                coordinate_y=c.coordinate_y,
            )
        )

    db.flush()
    # Recompute batch start/end across ALL rows (existing + appended).
    bounds = (
        db.query(func.min(PlantChamberHistory.entry_date),
                 func.max(PlantChamberHistory.exit_date))
        .filter(PlantChamberHistory.batch_id == batch.id)
        .one()
    )
    batch.start_date = bounds[0]
    batch.end_date = bounds[1]

    totals = dict(
        db.query(Plant.plant_type, func.count(Plant.id))
        .filter(Plant.batch_id == batch.id)
        .group_by(Plant.plant_type)
        .all()
    )
    db.commit()

    return {
        "batch_id": batch.id,
        "batch_code": batch.batch_code,
        "added_plant_count": sum(p.plant_type == OBSERVATION for p in plants),
        "added_nursery_group_count": sum(p.plant_type == NURSERY for p in plants),
        "added_chamber_history_count": len(chamber_history),
        "plant_count_total": totals.get(OBSERVATION, 0),
        "nursery_group_count_total": totals.get(NURSERY, 0),
    }


def list_observation_plants(db: Session, batch_code: str) -> List[dict]:
    """Existing observation_individual plants of a batch with their G120 placement,
    ordered by cultivar then replicate (so the edit table shows where entry left off).
    Raises BatchNotFound (404)."""
    batch = db.query(Batch).filter(Batch.batch_code == batch_code).first()
    if not batch:
        raise BatchNotFound(f"batch_code {batch_code!r} not found")

    g120 = db.query(GrowthChamber.id).filter(GrowthChamber.chamber_code == "G120").scalar()

    q = (
        db.query(Plant, PlantChamberHistory, Cultivar.cultivar_code,
                 Treatment.treatment_code, Rack.rack_code)
        .join(Cultivar, Cultivar.id == Plant.cultivar_id)
        .outerjoin(Treatment, Treatment.id == Plant.treatment_id)
        .join(PlantChamberHistory,
              (PlantChamberHistory.plant_id == Plant.id)
              & (PlantChamberHistory.chamber_id == g120))
        .outerjoin(Rack, Rack.id == PlantChamberHistory.rack_id)
        .filter(Plant.batch_id == batch.id, Plant.plant_type == OBSERVATION)
        .order_by(Cultivar.cultivar_code, Plant.replicate_code)
    )

    out = []
    for plant, ch, cultivar_code, treatment_code, rack_code in q.all():
        out.append({
            "plant_id": plant.id,
            "cultivar_code": cultivar_code,
            "treatment_code": treatment_code,
            "replicate_code": plant.replicate_code,
            "rack_code": rack_code,
            "coordinate_x": ch.coordinate_x,
            "coordinate_y": ch.coordinate_y,
            "coord_ref_image": ch.coord_ref_image,
            # G120 observation window: helps locate the reference frame (frames are
            # named by timestamp; the entry date+time points at the first frame).
            "entry_date": ch.entry_date,
            "entry_time": ch.entry_time,
            "exit_date": ch.exit_date,
            "exit_time": ch.exit_time,
        })
    return out


def batch_defaults(db: Session, batch_code: str) -> dict:
    """The batch's existing shared parameters (treatment + nursery/observation
    chamber, dates, times, growth conditions), so the edit/append page can pre-fill
    'Batch defaults' from the record instead of starting blank. Derived from an
    existing plant's chamber_history. Raises BatchNotFound (404)."""
    batch = db.query(Batch).filter(Batch.batch_code == batch_code).first()
    if not batch:
        raise BatchNotFound(f"batch_code {batch_code!r} not found")

    g120 = db.query(GrowthChamber.id).filter(GrowthChamber.chamber_code == "G120").scalar()

    # Most common treatment among observation plants.
    trow = (
        db.query(Treatment.treatment_code, func.count(Plant.id))
        .join(Plant, Plant.treatment_id == Treatment.id)
        .filter(Plant.batch_id == batch.id, Plant.plant_type == OBSERVATION)
        .group_by(Treatment.treatment_code)
        .order_by(func.count(Plant.id).desc())
        .first()
    )

    # Observation (G120) shared params from any observation plant.
    obs = (
        db.query(PlantChamberHistory)
        .join(Plant, Plant.id == PlantChamberHistory.plant_id)
        .filter(Plant.batch_id == batch.id, Plant.plant_type == OBSERVATION,
                PlantChamberHistory.chamber_id == g120)
        .first()
    )

    # Nursery walk-in shared params from any nursery plant's non-G120 row (earliest).
    walk = (
        db.query(PlantChamberHistory, GrowthChamber.chamber_code)
        .join(Plant, Plant.id == PlantChamberHistory.plant_id)
        .join(GrowthChamber, GrowthChamber.id == PlantChamberHistory.chamber_id)
        .filter(Plant.batch_id == batch.id, Plant.plant_type == NURSERY,
                PlantChamberHistory.chamber_id != g120)
        .order_by(PlantChamberHistory.entry_date)
        .first()
    )

    return {
        "treatment_code": trow[0] if trow else None,
        "walkin_chamber_code": walk[1] if walk else None,
        "walkin_entry_date": walk[0].entry_date if walk else None,
        "walkin_exit_date": walk[0].exit_date if walk else None,
        "walkin_gc_id": walk[0].growth_condition_id if walk else None,
        "obs_gc_id": obs.growth_condition_id if obs else None,
        "obs_entry_date": obs.entry_date if obs else None,
        "obs_entry_time": obs.entry_time if obs else None,
        "obs_exit_date": obs.exit_date if obs else None,
        "obs_exit_time": obs.exit_time if obs else None,
    }


def update_placements(db: Session, batch_code: str, updates) -> dict:
    """Update placement (rack/coord) + replicate of existing observation plants in
    one transaction. Cultivar/treatment are NOT touched. Rejects coords that would
    collide within the batch. Raises BatchNotFound (404), CoordinateConflict (409),
    or DimensionResolutionError (422)."""
    batch = db.query(Batch).filter(Batch.batch_code == batch_code).first()
    if not batch:
        raise BatchNotFound(f"batch_code {batch_code!r} not found")

    dims = _load_dimensions(db)
    g120 = dims.chamber_id.get("G120")
    if g120 is None:
        raise DimensionResolutionError("G120 chamber not found")

    update_map = {u.plant_id: u for u in updates}
    plants = {p.id: p for p in db.query(Plant).filter(Plant.id.in_(update_map.keys())).all()}
    for pid in update_map:
        p = plants.get(pid)
        if not p or p.batch_id != batch.id or p.plant_type != OBSERVATION:
            raise DimensionResolutionError(
                f"plant_id {pid} is not an observation plant in batch {batch_code}"
            )

    # Resolve each update's rack/sensor up front (fail before writing). Rack comes
    # from ONE of two sources: the reference frame's camera code (coordinate page,
    # authoritative) or an explicit rack_code (append page inline edit).
    resolved = {}
    for pid, u in update_map.items():
        ref = getattr(u, "reference_image", None)
        if ref:
            cam = _camera_code_from_ref(ref)
            got = dims.raspi_sensor.get(cam)
            if got is None:
                raise DimensionResolutionError(
                    f"no raspi sensor for camera {cam!r} (from reference_image {ref!r})"
                )
            sid, rid = got
        else:
            rid = _resolve_rack(dims, g120, u.rack_code)
            sid = _resolve_sensor(dims, rid, "observation")
        resolved[pid] = (rid, sid, u.coordinate_x, u.coordinate_y, u.replicate_code, ref)

    # Coord uniqueness across ALL observation plants after applying the updates.
    rows = (
        db.query(PlantChamberHistory)
        .filter(PlantChamberHistory.batch_id == batch.id,
                PlantChamberHistory.chamber_id == g120)
        .all()
    )
    ch_by_plant = {ch.plant_id: ch for ch in rows}
    final = {}
    for ch in rows:
        if ch.plant_id in resolved:
            rid, _sid, x, y, _rep, _ref = resolved[ch.plant_id]
            final[ch.plant_id] = (rid, x, y)
        elif ch.coordinate_x is not None:
            final[ch.plant_id] = (ch.rack_id, ch.coordinate_x, ch.coordinate_y)
    seen = {}
    for pid, key in final.items():
        if key in seen:
            raise CoordinateConflict(
                f"coordinate collision after update: rack_id={key[0]} "
                f"({key[1]},{key[2]}) on plants {seen[key]} and {pid}"
            )
        seen[key] = pid

    updated = 0
    for pid, (rid, sid, x, y, rep, ref) in resolved.items():
        ch = ch_by_plant.get(pid)
        if ch is None:
            raise DimensionResolutionError(f"plant_id {pid} has no G120 chamber_history row")
        ch.rack_id = rid
        ch.sensor_id = sid
        ch.coordinate_x = x
        ch.coordinate_y = y
        # Only overwrite provenance when the caller supplied one; a PATCH without
        # reference_image (e.g. the append page) leaves any existing value intact.
        if ref is not None:
            ch.coord_ref_image = ref
        plants[pid].replicate_code = rep
        updated += 1

    db.commit()
    return {"batch_code": batch.batch_code, "updated_count": updated}


def batch_data_status(db: Session, batch_code: str) -> dict:
    """Per-cultivar data completeness for a batch: how many of each cultivar's
    observation plants have rows in raspi / physical(3D) / thermal tables, plus
    batch-level lifecycle gates (entered/exited observation) so the UI can tell a
    real gap from 'not due yet'. Raises BatchNotFound (404)."""
    batch = db.query(Batch).filter(Batch.batch_code == batch_code).first()
    if not batch:
        raise BatchNotFound(f"batch_code {batch_code!r} not found")

    # Observation plants of the batch, grouped by cultivar.
    rows = (
        db.query(Plant.id, Cultivar.cultivar_code)
        .join(Cultivar, Cultivar.id == Plant.cultivar_id)
        .filter(Plant.batch_id == batch.id, Plant.plant_type == OBSERVATION)
        .all()
    )
    by_cultivar: Dict[str, list] = {}
    for pid, cc in rows:
        by_cultivar.setdefault(cc, []).append(pid)
    all_pids = [pid for pids in by_cultivar.values() for pid in pids]

    def plants_with_rows(model) -> set:
        if not all_pids:
            return set()
        q = (
            db.query(model.plant_id)
            .filter(model.plant_id.in_(all_pids))
            .distinct()
            .all()
        )
        return {r[0] for r in q}

    raspi = plants_with_rows(RaspiObservation)
    physical = plants_with_rows(PhysicalObservation)
    thermal = plants_with_rows(ThermalObservation)

    # Event-backed digital-camera milestone (cultivar_codes marked shot for this batch).
    shot_codes = {
        r[0] for r in db.query(Cultivar.cultivar_code)
        .join(BatchMilestone, BatchMilestone.cultivar_id == Cultivar.id)
        .filter(BatchMilestone.batch_id == batch.id,
                BatchMilestone.stage == DIGITAL_CAMERA).all()
    }

    cultivars = []
    for cc in sorted(by_cultivar):
        pids = by_cultivar[cc]
        cultivars.append({
            "cultivar_code": cc,
            "observation_plant_count": len(pids),
            "raspi_plant_count": sum(1 for p in pids if p in raspi),
            "physical_plant_count": sum(1 for p in pids if p in physical),
            "thermal_plant_count": sum(1 for p in pids if p in thermal),
            "digital_camera_shot": cc in shot_codes,
        })

    # Lifecycle gates from the batch's G120 observation chamber_history.
    g120 = db.query(GrowthChamber.id).filter(GrowthChamber.chamber_code == "G120").scalar()
    obs_rows = (
        db.query(PlantChamberHistory.entry_date, PlantChamberHistory.exit_date)
        .filter(PlantChamberHistory.batch_id == batch.id,
                PlantChamberHistory.chamber_id == g120)
        .all()
    )
    today = date.today()
    entered = any(e is not None and e <= today for e, _ in obs_rows)
    exited = any(x is not None for _, x in obs_rows)

    return {
        "batch_code": batch.batch_code,
        "observation_entered": entered,
        "observation_exited": exited,
        "cultivars": cultivars,
    }


def set_milestone(db: Session, batch_code: str, cultivar_code: str, stage: str,
                  shot: bool, marked_by: Optional[str] = None) -> dict:
    """Toggle an event-backed milestone for a (batch, cultivar, stage). shot=True
    upserts a row (event done), shot=False deletes it (not done). Raises
    BatchNotFound (404) or DimensionResolutionError (422, unknown cultivar / not in batch)."""
    batch = db.query(Batch).filter(Batch.batch_code == batch_code).first()
    if not batch:
        raise BatchNotFound(f"batch_code {batch_code!r} not found")
    cultivar = db.query(Cultivar).filter(Cultivar.cultivar_code == cultivar_code).first()
    if not cultivar:
        raise DimensionResolutionError(f"cultivar_code {cultivar_code!r} not found")
    in_batch = (
        db.query(Plant.id)
        .filter(Plant.batch_id == batch.id, Plant.cultivar_id == cultivar.id)
        .first()
    )
    if not in_batch:
        raise DimensionResolutionError(
            f"cultivar {cultivar_code!r} has no plants in batch {batch_code}"
        )

    existing = (
        db.query(BatchMilestone)
        .filter(BatchMilestone.batch_id == batch.id,
                BatchMilestone.cultivar_id == cultivar.id,
                BatchMilestone.stage == stage)
        .first()
    )
    if shot:
        if not existing:
            db.add(BatchMilestone(
                batch_id=batch.id, cultivar_id=cultivar.id, stage=stage,
                status="shot", marked_by=marked_by,
            ))
    elif existing:
        db.delete(existing)
    db.commit()

    return {"batch_code": batch_code, "cultivar_code": cultivar_code, "stage": stage, "shot": shot}
