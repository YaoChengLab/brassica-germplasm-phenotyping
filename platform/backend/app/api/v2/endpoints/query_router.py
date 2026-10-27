"""
v2 Query Router — improved endpoints with fields, pagination, caching, and new endpoints.
Deprecated endpoints (GET cultivars/search, POST faceted-search, POST advanced-search) removed.
"""

from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam
from sqlalchemy.orm import Session
from typing import List, Optional, Any
import logging
import traceback

from ....core.dependencies import get_db
from ....services.query_service_v2 import QueryServiceV2
from ....services.query_service import view_rank_from_filename
from ....services.database_stats_service import get_database_stats
from ....services.cache_service import CacheService
from ....services.decimation import lttb_downsample_dicts
from ....schemas.query_validation import (
    PaginatedPlantResponse,
    PlantObservationsResponse,
    PaginatedCultivarSearchResponse,
    FacetedFilterOptions,
    CultivarDetailsResponse,
    UnifiedCultivarSearchRequest,
    SensorResponse,
    PaginatedEnvironmentObservationResponse,
)
from ....schemas.query_validation_v2 import (
    CultivarSummaryResponse,
    BatchesWithCultivarsResponse,
)
from ....core.exceptions import DatabaseError
from ...v2.deps import parse_fields, PaginationParams

router = APIRouter()
logger = logging.getLogger(__name__)

_cache = CacheService()


# ========================================
# NEW v2 endpoints
# ========================================

@router.get("/cultivars/all", response_model=CultivarSummaryResponse, operation_id="v2_get_all_cultivars")
async def get_all_cultivars(db: Session = Depends(get_db)):
    """
    Lightweight cultivar list (id, cultivar_code, product_name only).
    Cached for 5 minutes.
    """
    query_service = QueryServiceV2(db)
    try:
        result = _cache.get_or_set(
            "cache:cultivars_all",
            lambda: query_service.get_all_cultivars_summary(),
            ttl=300,
        )
        return result
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# Improved v2 endpoints (from v1)
# ========================================

@router.post("/cultivars/search", response_model=PaginatedCultivarSearchResponse, operation_id="v2_search_cultivars")
async def unified_search_cultivars(
    request: UnifiedCultivarSearchRequest,
    db: Session = Depends(get_db),
):
    """
    Unified cultivar search (same as v1, single entry point for all search modes).
    """
    query_service = QueryServiceV2(db)
    try:
        if request.filters:
            result = query_service.search_cultivars_dynamic(
                filters=[f.dict() for f in request.filters],
                logic=request.logic,
                limit=request.limit,
                offset=request.offset,
            )
        elif request.product_name_filters or request.cultivar_code_filters:
            result = query_service.search_cultivars_faceted(
                product_name_filters=request.product_name_filters or [],
                cultivar_code_filters=request.cultivar_code_filters or [],
                search_term=request.search_term,
                limit=request.limit,
                offset=request.offset,
            )
        else:
            result = query_service.search_cultivars_faceted(
                product_name_filters=[],
                cultivar_code_filters=[],
                search_term=request.search_term,
                limit=request.limit,
                offset=request.offset,
            )
        return result
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/cultivars/{cultivar_code}/details", response_model=CultivarDetailsResponse, operation_id="v2_get_cultivar_details")
async def get_cultivar_details(
    cultivar_code: str,
    db: Session = Depends(get_db),
):
    """
    Get cultivar details with Redis cache (TTL 5m).
    """
    query_service = QueryServiceV2(db)
    try:
        result = _cache.get_or_set(
            f"cache:cultivar:{cultivar_code}:details",
            lambda: query_service.get_cultivar_details(cultivar_code),
            ttl=300,
        )
        if not result:
            raise HTTPException(status_code=404, detail=f"Cultivar with code {cultivar_code} not found")
        return result
    except HTTPException:
        raise
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cultivars/{cultivar_code}/time-series", operation_id="v2_get_cultivar_time_series")
async def get_cultivar_time_series(
    cultivar_code: str,
    max_points: Optional[int] = QueryParam(None, ge=10, le=10000, description="Max data points per series (LTTB)"),
    fields: Optional[List[str]] = Depends(parse_fields),
    db: Session = Depends(get_db),
):
    """
    Get time-series data with optional LTTB downsampling and field selection.
    """
    query_service = QueryServiceV2(db)
    try:
        time_series_data = query_service.get_cultivar_time_series_data(cultivar_code)
        if not time_series_data:
            cultivar = query_service.get_cultivar_details(cultivar_code)
            if not cultivar:
                raise HTTPException(status_code=404, detail=f"Cultivar with code {cultivar_code} not found")

        # Apply LTTB downsampling per series if requested
        if max_points:
            for key, series_data in time_series_data.items():
                for trait_key in ['leaf_count', 'leaf_area']:
                    points = series_data.get(trait_key, [])
                    if len(points) > max_points:
                        series_data[trait_key] = lttb_downsample_dicts(
                            points, max_points,
                            x_key='days_after_planting',
                            y_key='value',
                        )

        return time_series_data
    except HTTPException:
        raise
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cultivars/{cultivar_code}/signature-traits", operation_id="v2_get_cultivar_signature_traits")
async def get_cultivar_signature_traits(
    cultivar_code: str,
    db: Session = Depends(get_db),
):
    """
    Signature trait snapshot per batch (Raspberry Pi top-view RGB, QC-correct
    observations only): mean ± SD across replicates on the reference day.
    """
    query_service = QueryServiceV2(db)
    try:
        result = _cache.get_or_set(
            f"cache:cultivar:{cultivar_code}:signature-traits",
            lambda: query_service.get_cultivar_signature_traits(cultivar_code),
            ttl=300,
        )
        if result is None:
            raise HTTPException(status_code=404, detail=f"Cultivar with code {cultivar_code} not found")
        return result
    except HTTPException:
        raise
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cultivars/{cultivar_code}/chamber-timeline", operation_id="v2_get_cultivar_chamber_timeline")
async def get_cultivar_chamber_timeline(
    cultivar_code: str,
    db: Session = Depends(get_db),
):
    """
    Chamber stays per batch (where the plants were and for how long) with the
    temperature/humidity recorded in that chamber during each stay.
    """
    query_service = QueryServiceV2(db)
    try:
        result = _cache.get_or_set(
            f"cache:cultivar:{cultivar_code}:chamber-timeline",
            lambda: query_service.get_cultivar_chamber_timeline(cultivar_code),
            ttl=300,
        )
        if result is None:
            raise HTTPException(status_code=404, detail=f"Cultivar with code {cultivar_code} not found")
        return result
    except HTTPException:
        raise
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cultivars/{cultivar_code}/images", operation_id="v2_get_cultivar_images")
async def get_cultivar_images(
    cultivar_code: str,
    db: Session = Depends(get_db),
):
    """Get cultivar images (unchanged from v1)."""
    import os
    try:
        query_service = QueryServiceV2(db)
        cultivar = query_service.get_cultivar_details(cultivar_code)
        if not cultivar:
            raise HTTPException(status_code=404, detail=f"Cultivar with code {cultivar_code} not found")

        media_path = f"/app/static/media/uploads/img/{cultivar_code}"
        if not os.path.exists(media_path):
            return {"images": []}

        # Only webp is served/displayed; jpg sources are not deployed.
        image_files = [
            f for f in os.listdir(media_path)
            if f.lower().endswith('.webp')
        ]
        # Order by view priority (Top > Side > Close-up > Bottom), filename as tiebreak.
        image_files.sort(key=lambda f: (view_rank_from_filename(f), f))
        return {"images": image_files}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_cultivar_images: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/cultivars/filter-options", response_model=FacetedFilterOptions, operation_id="v2_get_filter_options")
async def get_cultivar_filter_options(
    max_items: int = QueryParam(default=500, ge=1, le=2000, description="Max filter items to return"),
    db: Session = Depends(get_db),
):
    """Get filter options with safety cap. Cached 10 minutes."""
    query_service = QueryServiceV2(db)
    try:
        result = _cache.get_or_set(
            f"cache:filter_options:{max_items}",
            lambda: query_service.get_cultivar_filter_options_v2(max_items),
            ttl=600,
        )
        return result
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# Batch / Plant endpoints
# ========================================

@router.get("/batches/with-cultivars", response_model=BatchesWithCultivarsResponse, operation_id="v2_get_batches_with_cultivars")
async def get_batches_with_cultivars(db: Session = Depends(get_db)):
    """Get batches with associated cultivars, start/end dates, and plant/cultivar counts."""
    query_service = QueryServiceV2(db)
    try:
        return {"batches": query_service.get_batches_with_cultivars()}
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plants", response_model=PaginatedPlantResponse, operation_id="v2_get_filtered_plants")
async def get_filtered_plants(
    batch_code: Optional[str] = QueryParam(None),
    cultivar_code: Optional[str] = QueryParam(None),
    product_name: Optional[str] = QueryParam(None),
    treatment_code: Optional[str] = QueryParam(None),
    replicate_code: Optional[int] = QueryParam(None),
    limit: int = QueryParam(50, ge=1, le=200),
    offset: int = QueryParam(0, ge=0),
    db: Session = Depends(get_db),
):
    """Get filtered plants with pagination (unchanged from v1)."""
    query_service = QueryServiceV2(db)
    try:
        return query_service.get_filtered_plants(
            batch_code=batch_code,
            cultivar_code=cultivar_code,
            product_name=product_name,
            treatment_code=treatment_code,
            replicate_code=replicate_code,
            limit=limit,
            offset=offset,
        )
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# Observation endpoints (improved)
# ========================================

@router.get("/plants/{plant_id}/observations", operation_id="v2_get_plant_observations")
async def get_plant_observations(
    plant_id: int,
    observation_type: Optional[str] = QueryParam(None, pattern="^(raspi|thermal|physical)$"),
    fields: Optional[List[str]] = Depends(parse_fields),
    page: PaginationParams = Depends(),
    db: Session = Depends(get_db),
):
    """
    Get observations for a plant with ?fields= and mandatory pagination (default 500).
    """
    query_service = QueryServiceV2(db)
    try:
        result = query_service.get_plant_observations_v2(
            plant_id,
            observation_type=observation_type,
            fields=fields,
            limit=page.limit,
            offset=page.offset,
        )
        # Check plant exists
        if not any(result.get(k) for k in ('physical', 'thermal', 'raspi')):
            from ....models.phenotype import Plant
            plant = db.query(Plant).filter(Plant.id == plant_id).first()
            if not plant:
                raise HTTPException(status_code=404, detail=f"Plant with ID {plant_id} not found")
        return result
    except HTTPException:
        raise
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plants/{plant_id}/observations-with-environment", operation_id="v2_get_observations_with_environment")
async def get_observations_with_environment(
    plant_id: int,
    fields: Optional[List[str]] = Depends(parse_fields),
    db: Session = Depends(get_db),
):
    """
    Get observations enriched with environment data. N+1 fixed in v2.
    """
    query_service = QueryServiceV2(db)
    try:
        result = query_service.get_observations_with_environment_v2(plant_id, fields=fields)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Plant with ID {plant_id} not found")
        return result
    except HTTPException:
        raise
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# Compare time series
# ========================================

# ========================================
# Summary / Schema / Environment (largely unchanged)
# ========================================

@router.get("/plant/summary", operation_id="v2_get_database_summary")
async def get_database_summary(db: Session = Depends(get_db)):
    """Database statistics with Redis cache (TTL 10m)."""
    try:
        result = _cache.get_or_set(
            "cache:plant_summary",
            lambda: get_database_stats(db),
            ttl=600,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/environment/sensors", response_model=List[SensorResponse], operation_id="v2_get_environment_sensors")
async def get_environment_sensors(db: Session = Depends(get_db)):
    """Get sensors (unchanged from v1)."""
    query_service = QueryServiceV2(db)
    try:
        return query_service.get_environment_sensors()
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/environment/observations", response_model=PaginatedEnvironmentObservationResponse, operation_id="v2_get_environment_observations")
async def get_environment_observations(
    sensor_ids: Optional[str] = QueryParam(None),
    chamber_code: Optional[str] = QueryParam(None),
    start_date: Optional[str] = QueryParam(None),
    end_date: Optional[str] = QueryParam(None),
    interval: str = QueryParam("raw", pattern="^(raw|hourly|daily)$"),
    limit: int = QueryParam(1000, ge=1, le=10000),
    offset: int = QueryParam(0, ge=0),
    db: Session = Depends(get_db),
):
    """Get environment observations (unchanged from v1)."""
    query_service = QueryServiceV2(db)
    try:
        parsed_sensor_ids = None
        if sensor_ids:
            try:
                parsed_sensor_ids = [int(sid.strip()) for sid in sensor_ids.split(',') if sid.strip()]
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid sensor_ids format")

        return query_service.get_environment_observations(
            sensor_ids=parsed_sensor_ids,
            chamber_code=chamber_code,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            limit=limit,
            offset=offset,
        )
    except HTTPException:
        raise
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
