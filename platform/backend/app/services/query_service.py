from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text, func, or_, and_
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime, timezone
import traceback # Added for detailed error logging
import sqlparse

from ..models.phenotype import (
    Batch, Cultivar, Plant, Rack, Treatment, RaspiObservation, ThermalObservation,
    PhysicalObservation, GrowthChamber, GrowthCondition, PlantChamberHistory,
    Sensor, EnvironmentObservation
)
from ..core.exceptions import DatabaseError

logger = logging.getLogger(__name__)

_MEDIA_IMG_ROOT = "/app/static/media/uploads/img"

# Preferred order when a cultivar is missing some views: Top first (clearest
# overhead shot), then Side, then Close-up, with Bottom last (root/medium shots
# are least representative). Used for both the card thumbnail pick and the
# detail-page gallery ordering.
VIEW_PRIORITY = {"TopView": 0, "SideView": 1, "CloseUpView": 2, "BottomView": 3}


def view_rank_from_filename(filename: str) -> int:
    """Rank an image filename by its embedded view token (lower = higher priority)."""
    for view, rank in VIEW_PRIORITY.items():
        if f"_{view}_" in filename:
            return rank
    return 99


def get_cultivar_thumbnail(cultivar_code: str) -> Optional[str]:
    """Return '/media/uploads/img/<code>/<webp>' for the cultivar's representative thumbnail.

    Reads the cultivar image folder live and picks the highest-priority view
    (Top > Side > Close-up > Bottom) among the .webp files, so renaming a file's
    view token is reflected immediately with no manifest to keep in sync. Returns
    None when the folder is missing or has no webp images.
    """
    import os

    folder = f"{_MEDIA_IMG_ROOT}/{cultivar_code}"
    try:
        webps = [f for f in os.listdir(folder) if f.lower().endswith(".webp")]
    except OSError:
        return None
    if not webps:
        return None
    chosen = min(webps, key=lambda f: (view_rank_from_filename(f), f))
    return f"/media/uploads/img/{cultivar_code}/{chosen}"


class QueryService:
    """
    Simplified QueryService focusing on core functionality.
    Removed complex query building methods in favor of simple SQL execution.
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.table_models = {
            "batches": Batch,
            "cultivars": Cultivar,
            "plants": Plant,
            "racks": Rack,
            "treatments": Treatment,
            "trait_observations": RaspiObservation,
            "thermal_observations": ThermalObservation,
            "physical_observations": PhysicalObservation,
            "growth_chambers": GrowthChamber,
            "growth_conditions": GrowthCondition,
            "plant_positions": PlantChamberHistory,
            "sensors": Sensor,
            "env_observations": EnvironmentObservation,
        }

    def get_cultivar_details(self, cultivar_code: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information for a specific cultivar by cultivar_code.
        """
        try:
            cultivar = self.db.query(Cultivar).filter(Cultivar.cultivar_code == cultivar_code).first()
            if not cultivar:
                return None

            # All plant counts below are observation individuals only. A batch also
            # holds one `nursery_group` record per cultivar — an aggregate for the
            # seedling tray, not a replicate — so counting it inflated every count
            # by one (an accession with four replicates read 5).
            OBSERVED = Plant.plant_type == 'observation_individual'

            # Get total plant replicates
            total_replicates = self.db.query(func.count(Plant.id)).filter(
                Plant.cultivar_id == cultivar.id, OBSERVED
            ).scalar()

            # Get associated batches with dates and plant counts
            batches_info = self.db.query(
                Batch.batch_code,
                Batch.start_date,
                Batch.end_date,
                func.count(Plant.id).label('plant_count')
            ).join(Plant).filter(
                Plant.cultivar_id == cultivar.id, OBSERVED
            ).group_by(Batch.id, Batch.batch_code, Batch.start_date, Batch.end_date).all()

            # Get associated treatments and their plant counts
            treatments_info = self.db.query(
                Treatment.treatment_code,
                func.count(Plant.id).label('plant_count')
            ).join(Plant).filter(
                Plant.cultivar_id == cultivar.id, OBSERVED
            ).group_by(Treatment.treatment_code).all()

            return {
                "id": cultivar.id,
                "cultivar_code": cultivar.cultivar_code,
                "permanent_code": cultivar.permanent_code,
                "manufacturer_name": cultivar.manufacturer_name,
                "product_code": cultivar.product_code,
                "common_name": cultivar.common_name,
                "product_name": cultivar.product_name,
                "genome_type": cultivar.genome_type,
                "planting_description": cultivar.planting_description,
                "planting_time": cultivar.planting_time,
                "flowering_time": cultivar.flowering_time,
                "edible_part": cultivar.edible_part,
                "germination_rate": cultivar.germination_rate,
                "seed_stock": cultivar.seed_stock,
                "eppendorf_in_50cc": cultivar.eppendorf_in_50cc,
                "seed_coating": cultivar.seed_coating,
                "number_aluminum_bag": cultivar.number_aluminum_bag,
                "notes": cultivar.notes,
                "total_plant_replicates": total_replicates,
                "batches": [{"batch_code": b.batch_code, "start_date": b.start_date.isoformat() if b.start_date else None, "end_date": b.end_date.isoformat() if b.end_date else None, "plant_count": b.plant_count} for b in batches_info],
                "treatments": [{"treatment_code": t.treatment_code, "plant_count": t.plant_count} for t in treatments_info]
            }
        except Exception as e:
            logger.error(f"Failed to get cultivar details for code {cultivar_code}: {e}")
            raise DatabaseError(f"Failed to retrieve details for cultivar code {cultivar_code}: {e}")

    def get_cultivar_filter_options(self) -> Dict[str, List[str]]:
        """
        Get unique product names from the database for faceted search filters.
        """
        try:
            product_names = self.db.query(Cultivar.product_name).distinct().order_by(Cultivar.product_name).all()

            return {
                "product_names": [name[0] for name in product_names if name[0]],
            }
        except Exception as e:
            logger.error(f"Failed to get cultivar filter options: {e}")
            raise DatabaseError(f"Failed to retrieve cultivar filter options: {e}")

    def search_cultivars_faceted(
        self,
        product_name_filters: List[str] = None,
        cultivar_code_filters: List[str] = None,
        search_term: str = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Perform a faceted search for cultivars based on product names, cultivar codes, and/or free-text search.
        Supports searching by cultivar_code or product_name (or both).
        """
        try:
            query = self.db.query(Cultivar)
            conditions = []

            # Handle free-text search on both fields (like DataAnalysisPage)
            if search_term and search_term.strip():
                search_lower = f"%{search_term.strip().lower()}%"
                conditions.append(or_(
                    Cultivar.cultivar_code.ilike(search_lower),
                    Cultivar.product_name.ilike(search_lower)
                ))

            # Conditions for product_name_filters (OR logic)
            # Note: product_name_filters can contain EITHER product names OR cultivar codes
            # We need to check both fields
            product_name_conditions = []
            if product_name_filters and len(product_name_filters) > 0:
                for name in product_name_filters:
                    if name:  # Only add non-empty names
                        # Check BOTH product_name AND cultivar_code
                        # This allows the same filter field to work with both types of values
                        product_name_conditions.append(
                            or_(
                                Cultivar.product_name.ilike(f"%{name}%"),
                                Cultivar.cultivar_code.ilike(f"%{name}%")
                            )
                        )

                if product_name_conditions:  # Only add condition if we have actual filters
                    conditions.append(or_(*product_name_conditions))

            # Conditions for cultivar_code_filters (OR logic) - NEW
            cultivar_code_conditions = []
            if cultivar_code_filters and len(cultivar_code_filters) > 0:
                for code in cultivar_code_filters:
                    if code:  # Only add non-empty codes
                        cultivar_code_conditions.append(Cultivar.cultivar_code.ilike(f"%{code}%"))

                if cultivar_code_conditions:  # Only add condition if we have actual filters
                    conditions.append(or_(*cultivar_code_conditions))

            # Combine all conditions with OR logic
            if conditions:
                query = query.filter(or_(*conditions))
            # If no filters applied, query remains unfiltered (browse all)

            total_count = query.count()

            # Subquery for RaspiObservation counts
            raspi_count_sq = self.db.query(
                Plant.cultivar_id,
                func.count(RaspiObservation.id).label('raspi_count')
            ).join(RaspiObservation).group_by(Plant.cultivar_id).subquery()

            # Join with observation counts and apply main query filters
            results_with_counts = query.add_columns(
                func.coalesce(raspi_count_sq.c.raspi_count, 0).label('raspi_observation_count'),
            ).outerjoin(raspi_count_sq, Cultivar.id == raspi_count_sq.c.cultivar_id).order_by(Cultivar.id).offset(offset).limit(limit).all()

            data = []
            for cultivar, raspi_count in results_with_counts:
                cultivar_dict = cultivar.__dict__.copy()
                cultivar_dict.pop('_sa_instance_state', None)
                cultivar_dict.pop('plants', None)
                cultivar_dict["raspi_observation_count"] = raspi_count
                cultivar_dict["thumbnail_url"] = get_cultivar_thumbnail(cultivar.cultivar_code)
                data.append(cultivar_dict)

            return {
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
                "data": data
            }

        except Exception as e:
            logger.error(f"Faceted cultivar search failed: {e}")
            raise DatabaseError(f"Failed to perform faceted cultivar search: {e}")

    # ========================================
    # CORE BATCH METHODS (KEPT)
    # ========================================

    def get_filtered_plants(
        self,
        batch_code: Optional[str],
        cultivar_code: Optional[str],
        product_name: Optional[str],
        treatment_code: Optional[str],
        replicate_code: Optional[int],
        limit: int,
        offset: int,
    ):
        """Get plants with dynamic filters and pagination."""
        try:
            query = self.db.query(Plant).options(
                joinedload(Plant.batch),
                joinedload(Plant.cultivar),
                joinedload(Plant.treatment),
            )

            if batch_code:
                query = query.join(Batch).filter(Batch.batch_code == batch_code)
            
            if cultivar_code or product_name:
                query = query.join(Cultivar)
                if cultivar_code:
                    query = query.filter(Cultivar.cultivar_code == cultivar_code)
                if product_name:
                    query = query.filter(Cultivar.product_name.ilike(f"%{product_name}%"))

            if treatment_code:
                query = query.join(Treatment).filter(Treatment.treatment_code == treatment_code)
            if replicate_code is not None:
                query = query.filter(Plant.replicate_code == replicate_code)

            total_count = query.count()

            # Subquery for observation counts per plant
            raspi_count_sq = self.db.query(
                RaspiObservation.plant_id,
                func.count(RaspiObservation.id).label('raspi_count')
            ).group_by(RaspiObservation.plant_id).subquery()

            plants_with_counts = query.add_columns(
                func.coalesce(raspi_count_sq.c.raspi_count, 0).label('raspi_count'),
            ).outerjoin(
                raspi_count_sq, Plant.id == raspi_count_sq.c.plant_id
            ).offset(offset).limit(limit).all()

            result_data = []
            for plant, raspi_count in plants_with_counts:
                result_data.append({
                    "plant_id": plant.id,
                    "batch_code": plant.batch.batch_code if plant.batch else "",
                    "cultivar_code": plant.cultivar.cultivar_code if plant.cultivar else "",
                    "product_name": plant.cultivar.product_name if plant.cultivar else None,
                    "treatment_code": plant.treatment.treatment_code if plant.treatment else None,
                    "replicate_code": plant.replicate_code,
                    "plant_type": plant.plant_type,
                    "parent_plant_id": plant.parent_plant_id,
                    "total_raspi": raspi_count,
                })

            return {
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
                "data": result_data,
            }
        except Exception as e:
            logger.error(f"Get filtered plants failed: {e}")
            raise DatabaseError(f"Failed to retrieve filtered plants: {e}")

    # ========================================
    # PLANT OBSERVATION METHODS (KEPT)
    # ========================================
        
    def get_plant_observations(self, plant_id: int, observation_type: Optional[str] = None):
        """Get all observations for a specific plant, separated by type, with cultivar info."""
        try:
            # Get cultivar information and replicate code
            plant_info = self.db.query(
                Cultivar.cultivar_code,
                Cultivar.product_name,
                Plant.replicate_code
            ).select_from(Plant).join(Cultivar).filter(Plant.id == plant_id).first()
            
            cultivar_info = {
                "cultivar_code": plant_info.cultivar_code if plant_info else None,
                "product_name": plant_info.product_name if plant_info else None,
                "replicate_code": plant_info.replicate_code if plant_info else None
            }
            
            # 3D scan and FLIR rows stay in the database but are not served:
            # the platform presents RGB-derived traits only.
            response = {
                "cultivar_info": cultivar_info,
                "raspi": []
            }

            # Raspi observations
            if not observation_type or observation_type == "raspi":
                raspi_data = self.db.query(RaspiObservation).filter(
                    RaspiObservation.plant_id == plant_id
                ).order_by(RaspiObservation.observation_timestamp).all()
                response["raspi"] = [
                    {c.name: getattr(row, c.name) for c in RaspiObservation.__table__.columns if c.name not in ('id', 'plant_id', 'sensor_id')}
                    for row in raspi_data
                ]
            
            return response
            
        except Exception as e:
            logger.error(f"Get plant observations failed: {e}")
            raise DatabaseError(f"Failed to retrieve observations for plant {plant_id}: {e}")

    def get_observations_with_environment(self, plant_id: int) -> Optional[Dict[str, Any]]:
        """
        Get all observations for a plant, each enriched with environment data
        (avg temperature/humidity from same chamber's arduino sensors within 1 hour before observation).
        """
        try:
            # Get plant info
            plant_info = self.db.query(
                Cultivar.cultivar_code,
                Cultivar.product_name,
                Plant.replicate_code
            ).select_from(Plant).join(Cultivar).filter(Plant.id == plant_id).first()

            if not plant_info:
                return None

            # Get the chamber_id for this plant
            chamber_row = self.db.query(PlantChamberHistory.chamber_id).filter(
                PlantChamberHistory.plant_id == plant_id
            ).first()
            chamber_id = chamber_row.chamber_id if chamber_row else None

            # Get arduino sensor IDs in this chamber (for env matching)
            arduino_sensor_ids = []
            if chamber_id:
                arduino_sensor_ids = [
                    sid for (sid,) in self.db.query(Sensor.id).filter(
                        Sensor.chamber_id == chamber_id,
                        Sensor.sensor_type == 'arduino'
                    ).all()
                ]

            # Collect all observations with their type
            observations = []

            # Raspi
            for row in self.db.query(RaspiObservation).filter(
                RaspiObservation.plant_id == plant_id
            ).order_by(RaspiObservation.observation_timestamp).all():
                traits = {
                    c.name: getattr(row, c.name)
                    for c in RaspiObservation.__table__.columns
                    if c.name not in ('id', 'plant_id', 'sensor_id', 'observation_timestamp', 'day_after_sewing')
                }
                observations.append({
                    "observation_timestamp": row.observation_timestamp,
                    "day_after_sewing": row.day_after_sewing,
                    "type": "raspi",
                    "traits": traits,
                })

            # Sort all observations by timestamp
            observations.sort(key=lambda x: x["observation_timestamp"])

            # Batch-fetch env data: collect unique timestamps, query once
            if arduino_sensor_ids and observations:
                unique_timestamps = sorted(set(o["observation_timestamp"] for o in observations))

                # Build env lookup: for each unique timestamp, avg of 1-hour window
                env_cache = {}
                for ts in unique_timestamps:
                    from datetime import timedelta
                    window_start = ts - timedelta(hours=1)
                    result = self.db.query(
                        func.avg(EnvironmentObservation.temperature_celsius).label('avg_temp'),
                        func.avg(EnvironmentObservation.humidity_percent).label('avg_hum'),
                        func.count(EnvironmentObservation.id).label('record_count'),
                    ).filter(
                        EnvironmentObservation.sensor_id.in_(arduino_sensor_ids),
                        EnvironmentObservation.observation_timestamp >= window_start,
                        EnvironmentObservation.observation_timestamp <= ts,
                    ).first()

                    env_cache[ts] = {
                        "env_temperature": round(float(result.avg_temp), 2) if result.avg_temp is not None else None,
                        "env_humidity": round(float(result.avg_hum), 2) if result.avg_hum is not None else None,
                        "env_records": result.record_count or 0,
                    }

                # Attach env data to each observation
                for obs in observations:
                    env = env_cache.get(obs["observation_timestamp"], {})
                    obs["env_temperature"] = env.get("env_temperature")
                    obs["env_humidity"] = env.get("env_humidity")
                    obs["env_records"] = env.get("env_records", 0)
            else:
                for obs in observations:
                    obs["env_temperature"] = None
                    obs["env_humidity"] = None
                    obs["env_records"] = 0

            return {
                "cultivar_info": {
                    "cultivar_code": plant_info.cultivar_code,
                    "product_name": plant_info.product_name,
                    "replicate_code": plant_info.replicate_code,
                },
                "observations": observations,
            }

        except Exception as e:
            logger.error(f"Get observations with environment failed for plant {plant_id}: {e}")
            raise DatabaseError(f"Failed to retrieve observations with environment for plant {plant_id}: {e}")

    # ========================================
    # SCHEMA AND STATISTICS METHODS (KEPT)
    # ========================================

    def get_database_summary(self) -> Dict[str, Any]:
        """Get simple database statistics"""
        try:
            stats = {
                "total_plants": self.db.query(func.count(Plant.id)).scalar() or 0,
                "total_batches": self.db.query(func.count(Batch.id)).scalar() or 0,
                "total_cultivars": self.db.query(func.count(Cultivar.id)).scalar() or 0,
                "total_treatments": self.db.query(func.count(Treatment.id)).scalar() or 0,
                "observation_counts": {
                    "physical": self.db.query(func.count(PhysicalObservation.id)).scalar() or 0,
                    "raspi": self.db.query(func.count(RaspiObservation.id)).scalar() or 0,
                    "thermal": self.db.query(func.count(ThermalObservation.id)).scalar() or 0
                },
                "last_updated": datetime.now()
            }
            return stats
        except Exception as e:
            logger.error(f"Failed to get simple database stats: {str(e)}")
            return {
                "total_plants": 0,
                "total_batches": 0,
                "total_cultivars": 0,
                "total_treatments": 0,
                "observation_counts": {"physical": 0, "raspi": 0, "thermal": 0},
                "last_updated": datetime.now()
            }

    def search_cultivars_dynamic(
        self,
        filters: List[Dict[str, Any]],
        logic: str,
        limit: int,
        offset: int
    ) -> Dict[str, Any]:
        """Search cultivars dynamically based on filters and logic, supporting both cultivar and observation fields."""
        try:
            # Define field mappings for observation tables. 3D scan and FLIR
            # traits are deliberately not searchable: the platform does not
            # present them, so accepting them here would offer a dimension the
            # rest of the interface cannot show.
            observation_fields = {
                # RaspiObservation fields
                'leaf_count': ('raspi', RaspiObservation.leaf_count),
                'leaf_area': ('raspi', RaspiObservation.leaf_area),
            }
            cultivar_columns = {c.name for c in Cultivar.__table__.columns}

            # Separate cultivar and observation filters
            cultivar_filters = []
            observation_filters = []

            for f in filters:
                field_name = f["field"]
                operator = f["operator"].lower()
                value = f["value"]

                if field_name in observation_fields:
                    observation_filters.append((field_name, operator, value))
                elif field_name in cultivar_columns:
                    cultivar_filters.append((field_name, operator, value))
                else:
                    # Silently dropping the condition would turn a stale saved
                    # query into an unfiltered browse-all that still looks like
                    # a search result. Reject it and name the field instead.
                    allowed = sorted(cultivar_columns | set(observation_fields))
                    raise ValueError(
                        f"Unknown search field '{field_name}'. "
                        f"Searchable fields: {', '.join(allowed)}"
                    )

            # Start with base query
            query = self.db.query(Cultivar)

            # Apply cultivar filters
            cultivar_conditions = []
            for field_name, operator, value in cultivar_filters:
                field = getattr(Cultivar, field_name)
                condition = self._build_condition(field, operator, value)
                if condition is not None:
                    cultivar_conditions.append(condition)

            if cultivar_conditions:
                if logic == "AND":
                    query = query.filter(and_(*cultivar_conditions))
                else:
                    query = query.filter(or_(*cultivar_conditions))

            # Apply observation filters with joins
            if observation_filters:
                # Group filters by observation type to minimize joins
                raspi_filters = [(f, o, v) for f, o, v in observation_filters if observation_fields[f][0] == 'raspi']

                observation_conditions = []

                # Handle raspi filters
                if raspi_filters:
                    raspi_subquery = self._build_observation_subquery(raspi_filters, observation_fields, RaspiObservation, logic)
                    observation_conditions.append(Cultivar.id.in_(raspi_subquery))

                # Combine observation conditions
                if observation_conditions:
                    if logic == "AND" and len(observation_conditions) > 1:
                        query = query.filter(and_(*observation_conditions))
                    else:
                        query = query.filter(or_(*observation_conditions))

            total_count = query.count()

            # Subquery for RaspiObservation counts
            raspi_count_sq = self.db.query(
                Plant.cultivar_id,
                func.count(RaspiObservation.id).label('raspi_count')
            ).join(RaspiObservation).group_by(Plant.cultivar_id).subquery()

            # Join with observation counts and apply main query filters
            results_with_counts = query.add_columns(
                func.coalesce(raspi_count_sq.c.raspi_count, 0).label('raspi_observation_count'),
            ).outerjoin(raspi_count_sq, Cultivar.id == raspi_count_sq.c.cultivar_id).order_by(Cultivar.id).offset(offset).limit(limit).all()

            data = []
            for cultivar, raspi_count in results_with_counts:
                cultivar_dict = cultivar.__dict__.copy()
                cultivar_dict.pop('_sa_instance_state', None)
                cultivar_dict.pop('plants', None)
                cultivar_dict["raspi_observation_count"] = raspi_count
                cultivar_dict["thumbnail_url"] = get_cultivar_thumbnail(cultivar.cultivar_code)
                data.append(cultivar_dict)

            return {
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
                "data": data
            }

        except ValueError:
            # Bad request (unknown field), not a database failure — let the
            # router turn it into a 400 instead of masking it as a 500.
            raise
        except Exception as e:
            logger.error(f"Dynamic cultivar search failed: {e}")
            raise DatabaseError(f"Failed to perform dynamic cultivar search: {e}")

    def _build_condition(self, field, operator: str, value):
        """Build SQLAlchemy condition based on operator."""
        try:
            if operator == "eq":
                return field == value
            elif operator == "ne":
                return field != value
            elif operator == "like":
                return field.ilike(f"%{value}%")
            elif operator == "not_like":
                return ~field.ilike(f"%{value}%")
            elif operator == "gt":
                return field > float(value)
            elif operator == "lt":
                return field < float(value)
            elif operator == "gte":
                return field >= float(value)
            elif operator == "lte":
                return field <= float(value)
            elif operator == "in":
                if not isinstance(value, list):
                    raise ValueError(f"Value for 'in' operator must be a list, got {type(value)}")
                return field.in_(value)
            elif operator == "not_in":
                if not isinstance(value, list):
                    raise ValueError(f"Value for 'not_in' operator must be a list, got {type(value)}")
                return ~field.in_(value)
            else:
                logger.warning(f"Unsupported operator: {operator}")
                return None
        except (ValueError, TypeError) as e:
            logger.warning(f"Error building condition for {field} {operator} {value}: {e}")
            return None

    def _build_observation_subquery(self, filters, observation_fields, observation_model, logic):
        """Build subquery for observation table filtering."""
        conditions = []

        for field_name, operator, value in filters:
            _, field = observation_fields[field_name]
            condition = self._build_condition(field, operator, value)
            if condition is not None:
                conditions.append(condition)

        if not conditions:
            return []

        # Build subquery to get cultivar IDs that match observation conditions
        subquery = (
            self.db.query(Plant.cultivar_id)
            .join(observation_model, Plant.id == observation_model.plant_id)
        )

        if logic == "AND":
            subquery = subquery.filter(and_(*conditions))
        else:
            subquery = subquery.filter(or_(*conditions))

        return subquery.distinct()

    def get_cultivar_time_series_data(self, cultivar_code: str) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """
        Get time-series data for a specific cultivar by cultivar_code, aggregated by batch and replicate.
        """
        try:
            # First get the cultivar ID from the code
            cultivar = self.db.query(Cultivar).filter(Cultivar.cultivar_code == cultivar_code).first()
            if not cultivar:
                return {}
            
            # Query to get all raspi observations for a given cultivar
            observations = (
            self.db.query(
                RaspiObservation.leaf_count,
                RaspiObservation.leaf_area,
                RaspiObservation.observation_timestamp,
                Batch.batch_code,
                Batch.start_date, # Need start_date to calculate days_after_planting
                Plant.replicate_code,
            )
            .join(Plant, RaspiObservation.plant_id == Plant.id)
            .join(Batch, Plant.batch_id == Batch.id)
            .filter(Plant.cultivar_id == cultivar.id)
            .order_by(
                Batch.batch_code,
                Plant.replicate_code,
                RaspiObservation.observation_timestamp,
            )
            .all()
)

            # Structure the data for plotting
            plot_data = {}
            for obs in observations:
                # Calculate days_after_planting
                if obs.start_date and obs.observation_timestamp:
                    # SIMPLE FIX: Treat database timestamps as naive local time
                    # Remove timezone info to prevent browser conversion issues
                    observation_timestamp_dt = obs.observation_timestamp
                    
                    # Strip timezone to treat as naive local time
                    if observation_timestamp_dt.tzinfo is not None:
                        observation_timestamp_dt = observation_timestamp_dt.replace(tzinfo=None)
                    
                    # Also make start_date naive for consistent calculation
                    start_date_dt = datetime.combine(obs.start_date, datetime.min.time())

                    # Calculate precise days with decimal precision for time
                    time_delta = observation_timestamp_dt - start_date_dt
                    days_after_planting = time_delta.total_seconds() / (24 * 3600)  # Decimal days
                    days_after_planting_int = time_delta.days  # Integer days for compatibility
                else:
                    days_after_planting = None # Or handle as an error/skip
                    days_after_planting_int = None

                if days_after_planting is None:
                    continue # Skip if days_after_planting cannot be calculated

                batch_key = f"{cultivar_code}-{obs.replicate_code}-{obs.batch_code}"
                if batch_key not in plot_data:
                    plot_data[batch_key] = {
                        "leaf_count": [],
                        "leaf_area": []
                    }
                
                plot_data[batch_key]["leaf_count"].append({
                    "days_after_planting": days_after_planting,
                    "days_after_planting_int": days_after_planting_int,
                    "observation_timestamp": observation_timestamp_dt.isoformat(),
                    "value": obs.leaf_count
                })
                plot_data[batch_key]["leaf_area"].append({
                    "days_after_planting": days_after_planting,
                    "days_after_planting_int": days_after_planting_int,
                    "observation_timestamp": observation_timestamp_dt.isoformat(),
                    "value": obs.leaf_area
                })

            return plot_data
        except Exception as e:
            import traceback
            logger.error(f"Failed to get time-series data for cultivar {cultivar_id}: {e}\n{traceback.format_exc()}")
            raise DatabaseError(f"Failed to retrieve time-series data for cultivar {cultivar_id}: {e}")

    def get_batches_with_cultivars(self) -> List[Dict[str, Any]]:
        """
        Get all available batches with their associated cultivars.
        Returns list of batches with cultivar information.
        """
        try:
            from collections import OrderedDict

            imaged = self.db.query(RaspiObservation.plant_id).distinct().subquery()
            rows = self.db.query(
                Batch.batch_code,
                Batch.start_date,
                Batch.end_date,
                Cultivar.id.label('cultivar_id'),
                Cultivar.cultivar_code,
                Cultivar.product_name,
                func.count(Plant.id).label('plant_count'),
                func.count(imaged.c.plant_id).label('imaged_plant_count')
            ).select_from(Batch).join(
                Plant, Plant.batch_id == Batch.id
            ).join(
                Cultivar, Plant.cultivar_id == Cultivar.id
            ).outerjoin(
                imaged, imaged.c.plant_id == Plant.id
            ).filter(
                # Tracked plants only, not the nursery-group row each cultivar also has.
                Plant.plant_type == 'observation_individual'
            ).group_by(
                Batch.batch_code, Batch.start_date, Batch.end_date,
                Cultivar.id, Cultivar.cultivar_code, Cultivar.product_name
            ).order_by(Batch.batch_code, Cultivar.cultivar_code).all()

            grouped = OrderedDict()
            for row in rows:
                if row.batch_code not in grouped:
                    start_iso = row.start_date.isoformat() if row.start_date else None
                    end_iso = row.end_date.isoformat() if row.end_date else None
                    grouped[row.batch_code] = {
                        'batch_code': row.batch_code,
                        # batch_start_date retained for backward compatibility
                        'batch_start_date': start_iso,
                        'start_date': start_iso,
                        'end_date': end_iso,
                        'plant_count': 0,
                        'imaged_plant_count': 0,
                        'cultivars': []
                    }
                grouped[row.batch_code]['cultivars'].append({
                    'id': row.cultivar_id,
                    'cultivar_code': row.cultivar_code,
                    'product_name': row.product_name,
                    'plant_count': row.plant_count,
                    'imaged_plant_count': row.imaged_plant_count
                })
                grouped[row.batch_code]['plant_count'] += row.plant_count
                grouped[row.batch_code]['imaged_plant_count'] += row.imaged_plant_count

            result = list(grouped.values())
            for batch in result:
                batch['cultivar_count'] = len(batch['cultivars'])
            return result

        except Exception as e:
            import traceback
            logger.error(f"Failed to get batches with cultivars: {e}\n{traceback.format_exc()}")
            raise DatabaseError(f"Failed to get batches with cultivars: {e}")

    # ========================================
    # ENVIRONMENT OBSERVATION METHODS
    # ========================================

    def get_environment_sensors(self) -> list:
        """Get all sensors with rack/chamber info."""
        try:
            results = self.db.query(
                Sensor,
                Rack.rack_code,
                GrowthChamber.chamber_code,
            ).outerjoin(Rack, Sensor.rack_id == Rack.id
            ).outerjoin(GrowthChamber, Sensor.chamber_id == GrowthChamber.id
            ).order_by(Sensor.id).all()

            return [
                {
                    "id": sensor.id,
                    "sensor_code": sensor.sensor_code,
                    "sensor_type": sensor.sensor_type,
                    "rack_id": sensor.rack_id,
                    "rack_code": rack_code,
                    "chamber_id": sensor.chamber_id,
                    "chamber_code": chamber_code,
                    "notes": sensor.notes,
                }
                for sensor, rack_code, chamber_code in results
            ]
        except Exception as e:
            logger.error(f"Failed to get environment sensors: {e}")
            raise DatabaseError(f"Failed to retrieve sensors: {e}")

    def get_environment_observations(
        self,
        sensor_ids: list = None,
        chamber_code: str = None,
        start_date: str = None,
        end_date: str = None,
        interval: str = "raw",
        limit: int = 1000,
        offset: int = 0,
    ) -> dict:
        """Query environment observations with optional aggregation."""
        try:
            from datetime import datetime as dt

            if interval == "raw":
                query = self.db.query(
                    EnvironmentObservation.id,
                    EnvironmentObservation.sensor_id,
                    Sensor.sensor_code,
                    EnvironmentObservation.observation_timestamp,
                    EnvironmentObservation.temperature_celsius,
                    EnvironmentObservation.humidity_percent,
                    EnvironmentObservation.pressure_hpa,
                ).join(Sensor, EnvironmentObservation.sensor_id == Sensor.id)

                if sensor_ids:
                    query = query.filter(EnvironmentObservation.sensor_id.in_(sensor_ids))
                if chamber_code:
                    query = query.filter(Sensor.chamber_id == self.db.query(GrowthChamber.id).filter(func.upper(GrowthChamber.chamber_code) == func.upper(chamber_code)).scalar_subquery())
                if start_date:
                    query = query.filter(EnvironmentObservation.observation_timestamp >= dt.strptime(start_date, '%Y-%m-%d'))
                if end_date:
                    query = query.filter(EnvironmentObservation.observation_timestamp <= dt.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59))

                total_count = query.count()
                rows = query.order_by(EnvironmentObservation.observation_timestamp).offset(offset).limit(limit).all()

                data = [
                    {
                        "id": r.id,
                        "sensor_id": r.sensor_id,
                        "sensor_code": r.sensor_code,
                        "observation_timestamp": r.observation_timestamp,
                        "temperature_celsius": float(r.temperature_celsius) if r.temperature_celsius is not None else None,
                        "humidity_percent": float(r.humidity_percent) if r.humidity_percent is not None else None,
                        "pressure_hpa": float(r.pressure_hpa) if r.pressure_hpa is not None else None,
                    }
                    for r in rows
                ]
            else:
                # Aggregated query (hourly or daily)
                if interval == "hourly":
                    time_bucket = func.date_trunc('hour', EnvironmentObservation.observation_timestamp)
                else:
                    time_bucket = func.date_trunc('day', EnvironmentObservation.observation_timestamp)

                query = self.db.query(
                    EnvironmentObservation.sensor_id,
                    Sensor.sensor_code,
                    time_bucket.label('observation_timestamp'),
                    func.avg(EnvironmentObservation.temperature_celsius).label('temperature_celsius'),
                    func.avg(EnvironmentObservation.humidity_percent).label('humidity_percent'),
                    func.avg(EnvironmentObservation.pressure_hpa).label('pressure_hpa'),
                ).join(Sensor, EnvironmentObservation.sensor_id == Sensor.id)

                if sensor_ids:
                    query = query.filter(EnvironmentObservation.sensor_id.in_(sensor_ids))
                if chamber_code:
                    query = query.filter(Sensor.chamber_id == self.db.query(GrowthChamber.id).filter(func.upper(GrowthChamber.chamber_code) == func.upper(chamber_code)).scalar_subquery())
                if start_date:
                    query = query.filter(EnvironmentObservation.observation_timestamp >= dt.strptime(start_date, '%Y-%m-%d'))
                if end_date:
                    query = query.filter(EnvironmentObservation.observation_timestamp <= dt.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59))

                query = query.group_by(
                    EnvironmentObservation.sensor_id,
                    Sensor.sensor_code,
                    time_bucket,
                )

                # Count total groups
                count_query = query.subquery()
                total_count = self.db.query(func.count()).select_from(count_query).scalar()

                rows = query.order_by(time_bucket).offset(offset).limit(limit).all()

                data = [
                    {
                        "id": 0,  # aggregated rows don't have a single id
                        "sensor_id": r.sensor_id,
                        "sensor_code": r.sensor_code,
                        "observation_timestamp": r.observation_timestamp,
                        "temperature_celsius": float(r.temperature_celsius) if r.temperature_celsius is not None else None,
                        "humidity_percent": float(r.humidity_percent) if r.humidity_percent is not None else None,
                        "pressure_hpa": float(r.pressure_hpa) if r.pressure_hpa is not None else None,
                    }
                    for r in rows
                ]

            return {
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
                "data": data,
            }

        except Exception as e:
            logger.error(f"Failed to get environment observations: {e}")
            raise DatabaseError(f"Failed to retrieve environment observations: {e}")

    # ========================================
    # MAIN QUERY EXECUTION METHOD (CORE)
    # ========================================
        
    def execute_simple_query(self, query_request) -> Dict[str, Any]:
        """Execute simple query (custom SQL only) - MAIN QUERY METHOD"""
        import time
        
        start_time = time.time()
        
        try:
            # Get SQL query (custom SQL only)
            sql = query_request.sql

            # Whitelist validation: only allow SELECT statements
            parsed = sqlparse.parse(sql)
            if not parsed:
                return {"success": False, "error_message": "Invalid SQL query"}
            for statement in parsed:
                if statement.get_type() != 'SELECT':
                    return {"success": False, "error_message": "Only SELECT queries are allowed"}
            # Prevent stacked queries (multiple statements separated by semicolons)
            if ';' in sql.strip().rstrip(';'):
                return {"success": False, "error_message": "Multiple statements are not allowed"}
            
            # Handle parameterized queries
            parameters = query_request.parameters or {}
            
            # Execute query with parameters
            if parameters:
                result = self.db.execute(text(sql), parameters)
            else:
                result = self.db.execute(text(sql))
                
            columns = list(result.keys())
            rows = result.fetchall()
            
            # Convert to list of dicts
            data = []
            for row in rows:
                row_dict = {}
                for i, col_name in enumerate(columns):
                    value = row[i]
                    # Handle datetime serialization
                    if hasattr(value, 'isoformat'):
                        value = value.isoformat()
                    elif hasattr(value, '__float__'):
                        value = float(value)
                    row_dict[col_name] = value
                data.append(row_dict)
            
            # Apply limit
            total_rows = len(data)
            data = data[:query_request.limit]
            
            execution_time = (time.time() - start_time) * 1000  # milliseconds
            
            return {
                "success": True,
                "data": data,
                "total_rows": total_rows,
                "execution_time_ms": execution_time
            }
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Simple query execution failed: {str(e)}")
            return {
                "success": False,
                "error_message": str(e),
                "execution_time_ms": execution_time
            }
