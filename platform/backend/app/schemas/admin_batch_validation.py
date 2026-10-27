"""
Admin batch-creation request/response schemas (lean scope: create new batch only).

This module is pure validation:
no DB access. FK resolution (codes -> ids, sensor derived from rack) happens in
admin_batch_service at commit time.
"""

import re
from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# Walk-in (nursery) chambers. Observation individuals live in G120.
WALKIN_CHAMBER_CODES = {"R141", "R142"}
BATCH_CODE_RE = re.compile(r"^\d{4}B\d{2}$")


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class WalkinVisit(BaseModel):
    """One nursery walk-in stay. rack omitted => no rack specified (chamber blank rack);
    sensor is always derived from the rack by the service, never sent here."""
    chamber_code: str
    entry_date: date
    exit_date: date
    growth_condition_id: int
    rack_code: Optional[str] = None  # default: no rack specified

    @field_validator("chamber_code")
    @classmethod
    def _chamber_must_be_walkin(cls, v: str) -> str:
        if v not in WALKIN_CHAMBER_CODES:
            raise ValueError(
                f"walk-in chamber_code must be one of {sorted(WALKIN_CHAMBER_CODES)}, got {v!r}"
            )
        return v

    @model_validator(mode="after")
    def _entry_before_exit(self) -> "WalkinVisit":
        if self.entry_date > self.exit_date:
            raise ValueError(
                f"entry_date {self.entry_date} must be <= exit_date {self.exit_date}"
            )
        return self


class ObservationIndividual(BaseModel):
    """One G120 observation plant. Rack + pixel coordinate are both deferred to the
    coordinate page: a plant is created with only cultivar/replicate, then placed
    later by clicking the camera frame (which fixes rack + sensor + coord in one
    step, derived from the frame's camera code). rack_code/coords are still
    accepted here for the append page's inline typo-fix flow. When a coord is
    given, x and y must both be present and positive."""
    replicate_code: int = Field(..., ge=1)
    rack_code: Optional[str] = None  # G120 raspi sub-rack (e.g. A1_1); None => placed later
    coordinate_x: Optional[int] = Field(None, gt=0)
    coordinate_y: Optional[int] = Field(None, gt=0)

    @model_validator(mode="after")
    def _coords_both_or_neither(self) -> "ObservationIndividual":
        if (self.coordinate_x is None) != (self.coordinate_y is None):
            raise ValueError(
                "coordinate_x and coordinate_y must both be set or both omitted"
            )
        return self


class Observation(BaseModel):
    """Shared G120 stay parameters for a PlantGroup's individuals."""
    growth_condition_id: int
    entry_date: date
    entry_time: Optional[str] = None
    exit_date: Optional[date] = None
    exit_time: Optional[str] = None
    individuals: List[ObservationIndividual] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _entry_before_exit(self) -> "Observation":
        if self.exit_date is not None and self.entry_date > self.exit_date:
            raise ValueError(
                f"observation entry_date {self.entry_date} must be <= exit_date {self.exit_date}"
            )
        return self


class PlantGroup(BaseModel):
    """One cultivar x treatment group: 1 nursery_group + N observation_individual."""
    cultivar_code: str
    treatment_code: str
    replicate_count: int = Field(..., ge=1)
    walkin_visits: List[WalkinVisit] = Field(..., min_length=1)
    observation: Observation

    @model_validator(mode="after")
    def _individuals_match_replicates(self) -> "PlantGroup":
        inds = self.observation.individuals
        if len(inds) != self.replicate_count:
            raise ValueError(
                f"observation.individuals length {len(inds)} != replicate_count "
                f"{self.replicate_count}"
            )
        codes = sorted(i.replicate_code for i in inds)
        expected = list(range(1, self.replicate_count + 1))
        if codes != expected:
            raise ValueError(
                f"replicate_code set {codes} must be exactly {expected}"
            )
        return self


def _assert_coords_unique(plant_groups: List[PlantGroup]) -> None:
    """G120 coords must be unique within a batch (across all groups). rack_code
    disambiguates: (rack_code, x, y) is the spatial key. Shared by create + append.
    Unplaced individuals (null coords) are skipped — many plants may await
    placement, so their (rack, None, None) keys must not collide."""
    seen = set()
    for g in plant_groups:
        for ind in g.observation.individuals:
            if ind.coordinate_x is None or ind.coordinate_y is None:
                continue
            key = (ind.rack_code, ind.coordinate_x, ind.coordinate_y)
            if key in seen:
                raise ValueError(
                    f"duplicate G120 coordinate within batch: rack={ind.rack_code} "
                    f"({ind.coordinate_x},{ind.coordinate_y})"
                )
            seen.add(key)


class CreateBatchRequest(BaseModel):
    batch_code: str
    notes: Optional[str] = None
    plant_groups: List[PlantGroup] = Field(..., min_length=1)

    @field_validator("batch_code")
    @classmethod
    def _batch_code_format(cls, v: str) -> str:
        if not BATCH_CODE_RE.match(v):
            raise ValueError(f"batch_code must match ^\\d{{4}}B\\d{{2}}$, got {v!r}")
        return v

    @model_validator(mode="after")
    def _coords_unique_within_batch(self) -> "CreateBatchRequest":
        _assert_coords_unique(self.plant_groups)
        return self


class AppendPlantsRequest(BaseModel):
    """Append plant groups to an EXISTING batch (batch_code comes from the URL).
    Same per-group structure as create; coord uniqueness within the request is
    checked here, and against already-persisted batch coords in the service."""
    plant_groups: List[PlantGroup] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _coords_unique_within_request(self) -> "AppendPlantsRequest":
        _assert_coords_unique(self.plant_groups)
        return self


class AppendPlantsResponse(BaseModel):
    batch_id: int
    batch_code: str
    added_plant_count: int  # tracked plants; nursery groups are counted separately
    added_nursery_group_count: int = 0
    added_chamber_history_count: int
    plant_count_total: int
    nursery_group_count_total: int = 0


# Full-frame reference image the coords were digitized from, e.g.
# "picA1-102-202412040600.jpg" (pic<rack>-<camera>-<yyyymmddHHMM>.ext). Only the
# filename is stored (the image itself is never uploaded), so it is untrusted text
# going into the DB: reject anything that is not a bare image basename of the
# expected shape. rack cross-check is intentionally NOT enforced here — the DB
# rack_code scheme (A1_1) differs from the frame rack token (A1-102) and the
# mapping is unresolved, so enforcing it would wrongly reject valid filenames.
REF_IMAGE_RE = re.compile(r"^pic[A-Za-z]+\d*-\d+-\d{12}\.(jpg|jpeg|png)$", re.IGNORECASE)
REF_IMAGE_MAX_LEN = 128


def _validate_reference_image(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = v.strip()
    if v == "":
        return None
    if len(v) > REF_IMAGE_MAX_LEN:
        raise ValueError(f"reference_image too long (>{REF_IMAGE_MAX_LEN} chars)")
    if "/" in v or "\\" in v or ".." in v or "\x00" in v:
        raise ValueError("reference_image must be a bare filename (no path separators)")
    if not REF_IMAGE_RE.match(v):
        raise ValueError(
            "reference_image must look like 'pic<rack>-<camera>-<yyyymmddHHMM>.jpg' "
            "(.jpg/.jpeg/.png)"
        )
    return v


class ObservationPlantOut(BaseModel):
    """An existing observation_individual plant with its G120 placement, for the
    edit table (cultivar/treatment locked; placement editable)."""
    plant_id: int
    cultivar_code: str
    treatment_code: Optional[str] = None
    replicate_code: Optional[int] = None
    rack_code: Optional[str] = None
    coordinate_x: Optional[int] = None
    coordinate_y: Optional[int] = None
    coord_ref_image: Optional[str] = None
    entry_date: Optional[date] = None   # G120 observation window (frame lookup aid)
    entry_time: Optional[str] = None    # HH:MM:SS — the entry frame's timestamp
    exit_date: Optional[date] = None
    exit_time: Optional[str] = None


class BatchDefaultsResponse(BaseModel):
    """A batch's existing shared parameters, to pre-fill the edit/append form."""
    treatment_code: Optional[str] = None
    walkin_chamber_code: Optional[str] = None
    walkin_entry_date: Optional[date] = None
    walkin_exit_date: Optional[date] = None
    walkin_gc_id: Optional[int] = None
    obs_gc_id: Optional[int] = None
    obs_entry_date: Optional[date] = None
    obs_entry_time: Optional[str] = None
    obs_exit_date: Optional[date] = None
    obs_exit_time: Optional[str] = None


class PlantPlacementUpdate(BaseModel):
    plant_id: int
    replicate_code: int = Field(..., ge=1)
    # Rack is resolved from ONE of two sources: reference_image (coordinate page —
    # the frame's camera code maps to the raspi sensor and thus its rack) or an
    # explicit rack_code (append page's inline edit). At least one is required.
    rack_code: Optional[str] = None
    coordinate_x: int = Field(..., gt=0)
    coordinate_y: int = Field(..., gt=0)
    # The reference frame these coords were read from; also the rack/sensor source.
    reference_image: Optional[str] = None

    @field_validator("reference_image")
    @classmethod
    def _check_reference_image(cls, v: Optional[str]) -> Optional[str]:
        return _validate_reference_image(v)

    @model_validator(mode="after")
    def _rack_source_present(self) -> "PlantPlacementUpdate":
        if not (self.rack_code or self.reference_image):
            raise ValueError(
                "placement needs a rack source: give reference_image (coordinate "
                "page) or rack_code (inline edit)"
            )
        return self


class UpdatePlacementsRequest(BaseModel):
    """Update placement (rack/coord) + replicate of EXISTING observation plants.
    Cultivar/treatment are not editable here (changing them is a structural move
    between nursery groups — out of scope)."""
    updates: List[PlantPlacementUpdate] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _coords_unique_within_request(self) -> "UpdatePlacementsRequest":
        seen = set()
        for u in self.updates:
            # The tray key is whichever rack source the update carries: the frame
            # (reference_image) for the coordinate page, or rack_code inline. Two
            # points from the same frame can't share a pixel; same pixel on
            # different frames (different racks) is fine.
            tray = u.reference_image or u.rack_code
            key = (tray, u.coordinate_x, u.coordinate_y)
            if key in seen:
                raise ValueError(
                    f"duplicate coordinate in update set: {tray} "
                    f"({u.coordinate_x},{u.coordinate_y})"
                )
            seen.add(key)
        return self


class UpdatePlacementsResponse(BaseModel):
    batch_code: str
    updated_count: int


class CultivarDataStatus(BaseModel):
    cultivar_code: str
    observation_plant_count: int          # N: observation plants of this cultivar
    raspi_plant_count: int                # plants with >=1 trait_observations row
    physical_plant_count: int             # plants with >=1 physical_observations (3D)
    thermal_plant_count: int              # plants with >=1 thermal_observations (FLIR)
    digital_camera_shot: bool = False     # event-backed milestone (no data table yet)


class BatchDataStatusResponse(BaseModel):
    batch_code: str
    observation_entered: bool             # gate: raspi expected once true
    observation_exited: bool              # gate: gantry (3D/thermal) expected once true
    cultivars: List[CultivarDataStatus]


class SetMilestoneRequest(BaseModel):
    cultivar_code: str
    stage: str = "digital_camera"
    shot: bool


class SetMilestoneResponse(BaseModel):
    batch_code: str
    cultivar_code: str
    stage: str
    shot: bool


# ---------------------------------------------------------------------------
# Expanded (preview) output schemas — what will be written, codes not yet FK ids
# ---------------------------------------------------------------------------

class ExpandedPlantOut(BaseModel):
    local_id: int
    plant_type: str
    cultivar_code: str
    treatment_code: str
    replicate_code: Optional[int] = None
    parent_local_id: Optional[int] = None


class ExpandedChamberHistoryOut(BaseModel):
    plant_local_id: int
    role: str  # 'walkin' | 'observation'
    chamber_code: str
    rack_code: Optional[str] = None
    growth_condition_id: int
    entry_date: date
    entry_time: Optional[str] = None
    exit_date: Optional[date] = None
    exit_time: Optional[str] = None
    coordinate_x: Optional[int] = None
    coordinate_y: Optional[int] = None


class BatchPreviewResponse(BaseModel):
    batch_code: str
    start_date: date
    end_date: Optional[date] = None
    notes: Optional[str] = None
    plant_count: int  # tracked plants; nursery groups are counted separately
    nursery_group_count: int = 0
    chamber_history_count: int
    plants: List[ExpandedPlantOut]
    chamber_history: List[ExpandedChamberHistoryOut]


class CreateBatchResponse(BaseModel):
    batch_id: int
    batch_code: str
    plant_count: int  # tracked plants; nursery groups are counted separately
    nursery_group_count: int = 0
    chamber_history_count: int


# ---------------------------------------------------------------------------
# Form-options (dropdown sources for the create form)
# ---------------------------------------------------------------------------

class TreatmentOption(BaseModel):
    id: int
    treatment_code: str

    class Config:
        from_attributes = True


class GrowthConditionOption(BaseModel):
    id: int
    label: str


class RackOption(BaseModel):
    id: int
    rack_code: str


class FormOptionsResponse(BaseModel):
    walkin_chamber_codes: List[str]
    treatments: List[TreatmentOption]
    growth_conditions: List[GrowthConditionOption]
    g120_racks: List[RackOption]
    default_walkin_growth_condition_id: Optional[int] = None
    default_observation_growth_condition_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Minimal cultivar create (rich metadata deferred to a dedicated channel)
# ---------------------------------------------------------------------------

class CreateCultivarRequest(BaseModel):
    cultivar_code: str = Field(..., min_length=1)
    product_name: Optional[str] = None
    notes: Optional[str] = None


class CultivarOut(BaseModel):
    id: int
    cultivar_code: str
    product_name: Optional[str] = None

    class Config:
        from_attributes = True
