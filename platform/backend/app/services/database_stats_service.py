from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.phenotype import Batch, Cultivar, Plant, RaspiObservation, Sensor

# ==============================================================================
# HOME-PAGE BREAKDOWNS
# ==============================================================================
# A column earns a place here only if it is a closed vocabulary: a small set of
# category labels. A low distinct count is necessary but not sufficient —
# `leaf_count` has 28 distinct values and is still a measurement, `rack_code`
# has 22 and is an identifier, `notes` columns are free text, and
# `eppendorf_in_50cc` is an inventory quantity. Sparse columns are excluded too:
# `edible_part` has 5 values but only 31 of 336 rows filled, so its chart would
# be a statement about what is missing rather than about the collection.
CULTIVAR_BREAKDOWN_COLUMNS = ("genome_type", "common_name", "manufacturer_name")

# Missing value key. The frontend renders the empty string as "Unassigned".
UNASSIGNED = ""


def _group_counts(db: Session, column) -> dict:
    """Value -> row count for one column; NULLs collapse into UNASSIGNED."""
    rows = db.query(column, func.count()).group_by(column).all()
    return {
        (value if value is not None else UNASSIGNED): count
        for value, count in rows
    }


def get_database_stats(db: Session):
    """
    Home-page statistics: four headline counts plus per-column breakdowns.

    RGB-derived observations only. The 3D scan and FLIR tables are retained in
    the database but are not part of what the platform reports.
    """
    total_cultivars_with_data = db.query(func.count(func.distinct(Plant.cultivar_id))).scalar()
    # Plants and batches count only those holding observations, so the headline
    # numbers match what the platform reports on: nursery-group records and
    # batches registered before their images are processed carry no traits.
    # The per-batch list below still shows every registered batch.
    total_plants = db.query(func.count(func.distinct(RaspiObservation.plant_id))).scalar()
    total_batches = (
        db.query(func.count(func.distinct(Plant.batch_id)))
        .join(RaspiObservation, RaspiObservation.plant_id == Plant.id)
        .scalar()
    )
    total_observations = db.query(RaspiObservation).count()

    cultivar_breakdowns = {
        name: _group_counts(db, getattr(Cultivar, name))
        for name in CULTIVAR_BREAKDOWN_COLUMNS
    }

    # Plants and observations per batch. The pair is the point: a batch can be
    # registered with plants and still hold zero observations because the
    # pipeline has not run for it yet, which neither number shows on its own.
    per_batch = (
        db.query(
            Batch.batch_code,
            func.count(func.distinct(Plant.id)).label("plants"),
            func.count(RaspiObservation.id).label("observations"),
        )
        .outerjoin(Plant, Plant.batch_id == Batch.id)
        .outerjoin(RaspiObservation, RaspiObservation.plant_id == Plant.id)
        .group_by(Batch.batch_code)
        .order_by(Batch.batch_code)
        .all()
    )

    return {
        "total_cultivars": total_cultivars_with_data,
        "total_plants": total_plants,
        "total_batches": total_batches,
        "total_observations": total_observations,
        "observations_by_qc_status": _group_counts(db, RaspiObservation.qc_status),
        "cultivar_breakdowns": cultivar_breakdowns,
        "sensors_by_type": _group_counts(db, Sensor.sensor_type),
        "batches": [
            {"batch_code": code, "plants": plants, "observations": observations}
            for code, plants, observations in per_batch
        ],
    }
