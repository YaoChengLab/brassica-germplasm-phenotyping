"""
Unit tests for the lean admin batch-creation pure layer:
schemas/admin_batch_validation.py + services/admin_batch_service.py (expand).

No DB. Covers: expand structural invariants (1 nursery + N individuals, parent
linkage, walk-in NULL coord/time, one G120 row per individual), date derivation,
and the validation rules of the batch schemas.
"""

import sys
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

# Make `app` importable when running pytest from the backend dir.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.admin_batch_validation import (  # noqa: E402
    CreateBatchRequest,
    Observation,
    ObservationIndividual,
    PlantGroup,
    WalkinVisit,
)
from app.services.admin_batch_service import (  # noqa: E402
    NURSERY,
    OBSERVATION,
    build_preview,
    expand_batch,
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _individuals(n, rack="A1_1", x0=1000, y0=600):
    # unique coords within a rack by spreading x
    return [
        ObservationIndividual(
            replicate_code=i + 1,
            rack_code=rack,
            coordinate_x=x0 + i * 100,
            coordinate_y=y0,
        )
        for i in range(n)
    ]


def _group(cultivar="s0001", treatment="Control", n=3, chamber="R141", rack="A1_1"):
    return PlantGroup(
        cultivar_code=cultivar,
        treatment_code=treatment,
        replicate_count=n,
        walkin_visits=[
            WalkinVisit(
                chamber_code=chamber,
                entry_date=date(2025, 1, 1),
                exit_date=date(2025, 1, 20),
                growth_condition_id=2,
            )
        ],
        observation=Observation(
            growth_condition_id=6,
            entry_date=date(2025, 1, 21),
            entry_time="10:00:00",
            exit_date=date(2025, 3, 1),
            exit_time="11:00:00",
            individuals=_individuals(n, rack=rack),
        ),
    )


def _request(groups=None, code="2025B15"):
    return CreateBatchRequest(
        batch_code=code,
        notes="unit test batch",
        plant_groups=groups or [_group()],
    )


# ---------------------------------------------------------------------------
# expand structural invariants
# ---------------------------------------------------------------------------

def test_expand_one_nursery_plus_n_individuals():
    exp = expand_batch(_request())
    assert len(exp.plants) == 1 + 3  # nursery + 3 individuals
    nurseries = [p for p in exp.plants if p.plant_type == NURSERY]
    individuals = [p for p in exp.plants if p.plant_type == OBSERVATION]
    assert len(nurseries) == 1
    assert len(individuals) == 3


def test_individuals_parent_points_to_nursery():
    exp = expand_batch(_request())
    nursery = next(p for p in exp.plants if p.plant_type == NURSERY)
    assert nursery.parent_local_id is None
    assert nursery.replicate_code is None
    for ind in (p for p in exp.plants if p.plant_type == OBSERVATION):
        assert ind.parent_local_id == nursery.local_id
    assert sorted(p.replicate_code for p in exp.plants if p.plant_type == OBSERVATION) == [1, 2, 3]


def test_local_ids_unique_and_sequential():
    exp = expand_batch(_request(groups=[_group(n=2), _group(cultivar="s0002", n=2, rack="B1_1")]))
    ids = [p.local_id for p in exp.plants]
    assert ids == list(range(1, len(ids) + 1))


def test_walkin_rows_have_null_coord_and_time():
    exp = expand_batch(_request())
    walkin = [c for c in exp.chamber_history if c.role == "walkin"]
    assert len(walkin) == 1
    w = walkin[0]
    assert w.chamber_code == "R141"
    assert w.coordinate_x is None and w.coordinate_y is None
    assert w.entry_time is None and w.exit_time is None
    assert w.rack_code is None  # no rack specified


def test_each_individual_gets_exactly_one_g120_row():
    exp = expand_batch(_request())
    obs_rows = [c for c in exp.chamber_history if c.role == "observation"]
    individuals = [p for p in exp.plants if p.plant_type == OBSERVATION]
    assert len(obs_rows) == len(individuals) == 3
    for c in obs_rows:
        assert c.chamber_code == "G120"
        assert c.coordinate_x is not None and c.coordinate_y is not None
        assert c.entry_time == "10:00:00"


def test_chamber_history_count_matches():
    exp = expand_batch(_request())
    # 1 walk-in (nursery) + 3 observation
    assert len(exp.chamber_history) == 1 + 3


def test_named_walkin_rack_preserved():
    g = _group()
    g.walkin_visits[0].rack_code = "A1"
    exp = expand_batch(_request(groups=[g]))
    w = next(c for c in exp.chamber_history if c.role == "walkin")
    assert w.rack_code == "A1"


# ---------------------------------------------------------------------------
# date derivation
# ---------------------------------------------------------------------------

def test_derive_start_and_end_dates():
    exp = expand_batch(_request())
    assert exp.start_date == date(2025, 1, 1)   # earliest walk-in entry
    assert exp.end_date == date(2025, 3, 1)     # latest observation exit


def test_end_date_none_when_no_exit():
    g = _group()
    g.observation.exit_date = None
    # walk-in still has an exit_date, so end_date = walk-in exit
    exp = expand_batch(_request(groups=[g]))
    assert exp.end_date == date(2025, 1, 20)


# ---------------------------------------------------------------------------
# validation rules
# ---------------------------------------------------------------------------

def test_batch_code_format_rejected():
    with pytest.raises(ValidationError):
        _request(code="B15")
    with pytest.raises(ValidationError):
        _request(code="2025X15")


def test_batch_code_format_accepted():
    assert _request(code="2025B15").batch_code == "2025B15"


def test_walkin_chamber_must_be_walkin():
    with pytest.raises(ValidationError):
        WalkinVisit(
            chamber_code="G120",
            entry_date=date(2025, 1, 1),
            exit_date=date(2025, 1, 2),
            growth_condition_id=2,
        )


def test_walkin_entry_after_exit_rejected():
    with pytest.raises(ValidationError):
        WalkinVisit(
            chamber_code="R141",
            entry_date=date(2025, 1, 10),
            exit_date=date(2025, 1, 1),
            growth_condition_id=2,
        )


def test_individuals_count_must_match_replicate_count():
    with pytest.raises(ValidationError):
        PlantGroup(
            cultivar_code="s0001",
            treatment_code="Control",
            replicate_count=5,
            walkin_visits=[
                WalkinVisit(
                    chamber_code="R141",
                    entry_date=date(2025, 1, 1),
                    exit_date=date(2025, 1, 20),
                    growth_condition_id=2,
                )
            ],
            observation=Observation(
                growth_condition_id=6,
                entry_date=date(2025, 1, 21),
                individuals=_individuals(3),  # only 3, not 5
            ),
        )


def test_replicate_codes_must_be_one_to_n():
    inds = _individuals(3)
    inds[2].replicate_code = 9  # breaks the {1,2,3} set
    with pytest.raises(ValidationError):
        PlantGroup(
            cultivar_code="s0001",
            treatment_code="Control",
            replicate_count=3,
            walkin_visits=[
                WalkinVisit(
                    chamber_code="R141",
                    entry_date=date(2025, 1, 1),
                    exit_date=date(2025, 1, 20),
                    growth_condition_id=2,
                )
            ],
            observation=Observation(
                growth_condition_id=6,
                entry_date=date(2025, 1, 21),
                individuals=inds,
            ),
        )


def test_duplicate_coord_within_batch_rejected():
    g1 = _group(cultivar="s0001", n=2)
    g2 = _group(cultivar="s0002", n=2)
    # force a collision: same rack + coord across groups
    g2.observation.individuals[0].rack_code = g1.observation.individuals[0].rack_code
    g2.observation.individuals[0].coordinate_x = g1.observation.individuals[0].coordinate_x
    g2.observation.individuals[0].coordinate_y = g1.observation.individuals[0].coordinate_y
    with pytest.raises(ValidationError):
        _request(groups=[g1, g2])


def test_same_coord_different_rack_allowed():
    g1 = _group(cultivar="s0001", n=2)
    g2 = _group(cultivar="s0002", n=2)
    for ind in g2.observation.individuals:
        ind.rack_code = "B1_1"  # different rack, same coords as g1 are fine
    req = _request(groups=[g1, g2])
    assert len(req.plant_groups) == 2


def test_coordinate_must_be_positive():
    with pytest.raises(ValidationError):
        ObservationIndividual(replicate_code=1, rack_code="A1_1", coordinate_x=0, coordinate_y=600)


def test_coords_optional_at_create():
    # A plant may be created unplaced (coords filled later via the coordinate page).
    ind = ObservationIndividual(replicate_code=1, rack_code="A1_1")
    assert ind.coordinate_x is None and ind.coordinate_y is None


def test_coords_both_or_neither():
    with pytest.raises(ValidationError):
        ObservationIndividual(replicate_code=1, rack_code="A1_1", coordinate_x=1000)


def test_unplaced_individuals_not_flagged_duplicate():
    # Two groups whose individuals are all unplaced must not collide on (rack, None, None).
    g1 = _group(cultivar="s0001", n=2)
    g2 = _group(cultivar="s0002", n=2)
    for g in (g1, g2):
        for ind in g.observation.individuals:
            ind.coordinate_x = None
            ind.coordinate_y = None
    req = _request(groups=[g1, g2])
    assert len(req.plant_groups) == 2


def test_at_least_one_walkin_visit_required():
    with pytest.raises(ValidationError):
        PlantGroup(
            cultivar_code="s0001",
            treatment_code="Control",
            replicate_count=1,
            walkin_visits=[],
            observation=Observation(
                growth_condition_id=6,
                entry_date=date(2025, 1, 21),
                individuals=_individuals(1),
            ),
        )


# ---------------------------------------------------------------------------
# preview projection
# ---------------------------------------------------------------------------

def test_build_preview_counts_and_shape():
    preview = build_preview(_request(groups=[_group(n=3), _group(cultivar="s0002", n=2, rack="B1_1")]))
    # (1 nursery + 3) + (1 nursery + 2) = 5 plants and 2 nursery groups
    assert preview.plant_count == 5
    assert preview.nursery_group_count == 2
    assert len(preview.plants) == 7
    # walk-in: 2 (one per group) + observation: 5 = 7 chamber_history
    assert preview.chamber_history_count == 7
    assert preview.start_date == date(2025, 1, 1)
    assert preview.end_date == date(2025, 3, 1)
