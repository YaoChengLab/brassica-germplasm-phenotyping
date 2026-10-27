from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, date

# ========================================
# CORE RESPONSE MODELS (KEPT)
# ========================================

class BatchResponse(BaseModel):
    id: int
    batch_code: str
    start_date: Optional[date]
    end_date: Optional[date]
    plant_count: int

    class Config:
        from_attributes = True

class PlantDetailResponse(BaseModel):
    plant_id: int
    batch_code: str
    cultivar_code: str
    treatment_code: Optional[str]
    replicate_number: Optional[int]
    plant_type: Optional[str] = None
    parent_plant_id: Optional[int] = None
    total_observations: int

    class Config:
        from_attributes = True


class FilteredPlantResponse(BaseModel):
    plant_id: int
    batch_code: str
    cultivar_code: str
    product_name: Optional[str]
    treatment_code: Optional[str]
    replicate_code: Optional[int]
    plant_type: Optional[str] = None
    parent_plant_id: Optional[int] = None
    total_raspi: int

    class Config:
        from_attributes = True

class PaginatedPlantResponse(BaseModel):
    total_count: int
    limit: int
    offset: int
    data: List[FilteredPlantResponse]

class ObservationSummary(BaseModel):
    observation_type: str
    count: int
    date_range: Dict[str, Optional[datetime]]
    measurements: Dict[str, Any]
    latest_values: Optional[Dict[str, Any]] = None

class RaspiObservationData(BaseModel):
    observation_timestamp: datetime
    day_after_sewing: Optional[int]

    # Basic leaf measurements
    leaf_count: Optional[int]
    leaf_area: Optional[float]

    # Area and size measurements
    area_pixels: Optional[float]
    bounding_box_area: Optional[float]
    perimeter_pixels: Optional[float]
    convex_hull_area_pixels: Optional[float]
    convex_hull_perimeter: Optional[float]
    extent: Optional[float]

    # Plant dimensions
    plant_height: Optional[float]
    plant_width: Optional[float]
    equivalent_diameter: Optional[float]

    # Shape analysis
    compactness: Optional[float]
    roundness: Optional[float]
    eccentricity: Optional[float]
    radial_symmetry: Optional[float]

    # Ellipse fitting parameters
    major_axis_length: Optional[float]
    minor_axis_length: Optional[float]
    ellipse_aspect_ratio: Optional[float]
    ellipse_center_x: Optional[float]
    ellipse_center_y: Optional[float]
    ellipse_angle_degrees: Optional[float]

    # Radius measurements (from centroid)
    max_radius_from_centroid: Optional[float]
    mean_radius_from_centroid: Optional[float]
    median_radius_from_centroid: Optional[float]
    min_radius_from_centroid: Optional[float]
    std_radius_from_centroid: Optional[float]

    # Color channel measurements
    red_channel: Optional[float]
    green_channel: Optional[float]
    blue_channel: Optional[float]

    # Color ratios
    red_green_ratio: Optional[float]
    blue_green_ratio: Optional[float]
    blue_red_ratio: Optional[float]

    # Color indices
    excess_green_index: Optional[float]
    excess_green_minus_red: Optional[float]
    excess_red_index: Optional[float]
    green_index: Optional[float]
    green_leaf_index: Optional[float]
    green_difference: Optional[float]
    green_difference_variant: Optional[float]
    greenness: Optional[float]
    gap_fraction_canopy_porosity: Optional[float]

    # HSL color space
    hue: Optional[float]
    saturation: Optional[float]
    lightness: Optional[float]

    # Chroma and brightness
    chroma: Optional[float]
    chroma_prime: Optional[float]
    anthocyanin_chroma_basic: Optional[float]
    anthocyanin_chroma_difference: Optional[float]
    anthocyanin_chroma_ratio: Optional[float]
    brightness: Optional[float]

    # Vegetation indices
    cive: Optional[float]
    dgci: Optional[float]
    mgrvi: Optional[float]
    ndyi: Optional[float]
    ngrdi: Optional[float]
    rgbvi: Optional[float]
    triangular_greenness_index: Optional[float]
    vari: Optional[float]
    veg: Optional[float]
    vegetation_index_2: Optional[float]

    # Color strength
    strength_of_red: Optional[float]
    strength_of_green: Optional[float]
    strength_of_blue: Optional[float]

    # Distribution and entropy
    colour_distribution_modes: Optional[float]
    spectral_distribution_modes: Optional[float]
    num_unique_colours: Optional[float]
    pixel_entropy: Optional[float]

    # GLCM texture features
    glcm_asm: Optional[float]
    glcm_autocorrelation: Optional[float]
    glcm_cluster_prominence: Optional[float]
    glcm_cluster_shade: Optional[float]
    glcm_contrast: Optional[float]
    glcm_correlation: Optional[float]
    glcm_difference_entropy: Optional[float]
    glcm_difference_variance: Optional[float]
    glcm_dissimilarity: Optional[float]
    glcm_entropy: Optional[float]
    glcm_idm: Optional[float]
    glcm_idmn: Optional[float]
    glcm_idn: Optional[float]
    glcm_imc1: Optional[float]
    glcm_imc2: Optional[float]
    glcm_inverse_difference: Optional[float]
    glcm_max_probability: Optional[float]
    glcm_mcc: Optional[float]
    glcm_ssv: Optional[float]
    glcm_sum_average: Optional[float]
    glcm_sum_entropy: Optional[float]
    glcm_sum_variance: Optional[float]

    # HOG features
    hog_mean: Optional[float]
    hog_std: Optional[float]

    # Log features
    log_mean: Optional[float]
    log_std: Optional[float]

    # Image reference
    image_file: Optional[str]

    class Config:
        from_attributes = True

class CultivarInfo(BaseModel):
    cultivar_code: Optional[str]
    product_name: Optional[str]
    replicate_code: Optional[int]

class PlantObservationsResponse(BaseModel):
    cultivar_info: CultivarInfo
    raspi: List[RaspiObservationData]

class TableInfo(BaseModel):
    name: str
    columns: List[Dict[str, Any]]
    row_count: int
    relationships: List[str] = []

# ========================================
# SIMPLE QUERY INTERFACE (MAIN API)
# ========================================

class SimpleQueryRequest(BaseModel):
    """Simple query interface for custom SQL queries"""
    query_type: Literal["custom_sql"] 
    sql: str = Field(..., description="SQL query to execute")
    parameters: Optional[Dict[str, Any]] = {}
    limit: int = Field(default=1000, le=10000, ge=1)

class SimpleQueryResult(BaseModel):
    """Simple query result format"""
    success: bool
    data: Optional[List[Dict[str, Any]]] = None
    total_rows: Optional[int] = None
    execution_time_ms: Optional[float] = None
    error_message: Optional[str] = None

class CultivarSearchResponse(BaseModel):
    common_name: Optional[str]
    product_name: Optional[str]
    cultivar_code: str
    raspi_observation_count: int

    class Config:
        from_attributes = True

class FilterCondition(BaseModel):
    field: str
    operator: Literal["eq", "ne", "like", "not_like", "in", "not_in", "gt", "lt", "gte", "lte"]
    value: Any

class FacetedSearchRequest(BaseModel):
    product_name_filters: List[str] = Field(default_factory=list, description="List of product names to filter by (OR logic)")
    cultivar_code_filters: Optional[List[str]] = Field(default_factory=list, description="List of cultivar codes to filter by (OR logic)")
    search_term: Optional[str] = Field(default=None, description="Free-text search on both cultivar code and product name")

class CultivarSearchRequest(BaseModel):
    filters: List[FilterCondition] = Field(..., description="List of filter conditions")
    logic: Literal["AND", "OR"] = Field("AND", description="Logic to combine filters: 'AND' or 'OR'")
    limit: int = Field(default=50, le=200, ge=1, description="Number of results to return")
    offset: int = Field(default=0, ge=0, description="Number of results to skip")

class UnifiedCultivarSearchRequest(BaseModel):
    """
    Unified search request supporting simple, faceted, and advanced search modes.

    Usage modes:
    - Simple: Provide only 'search_term' (searches product name and cultivar code)
    - Faceted: Provide 'product_name_filters' and/or 'cultivar_code_filters' plus optional 'search_term'
    - Advanced: Provide 'filters' with 'logic' operator for complex filtering
    """
    # Simple search mode
    search_term: Optional[str] = Field(
        default=None,
        description="Free-text search term (simple mode or supplement to faceted/advanced)"
    )

    # Faceted search mode
    product_name_filters: Optional[List[str]] = Field(
        default=None,
        description="Product names to filter by (OR logic)"
    )
    cultivar_code_filters: Optional[List[str]] = Field(
        default=None,
        description="Cultivar codes to filter by (OR logic)"
    )

    # Advanced search mode
    filters: Optional[List[FilterCondition]] = Field(
        default=None,
        description="List of filter conditions for advanced filtering"
    )
    logic: Literal["AND", "OR"] = Field(
        default="AND",
        description="Logic to combine advanced filters: 'AND' or 'OR'"
    )

    # Pagination
    limit: int = Field(default=50, le=200, ge=1, description="Number of results to return")
    offset: int = Field(default=0, ge=0, description="Number of results to skip")

class CultivarSearchItem(BaseModel):
    id: int
    cultivar_code: str
    permanent_code: Optional[str]
    manufacturer_name: Optional[str]
    product_code: Optional[str]
    common_name: Optional[str]
    product_name: Optional[str]
    genome_type: Optional[str]

    planting_description: Optional[str] = None
    planting_time: Optional[str] = None
    flowering_time: Optional[str] = None

    edible_part: Optional[str] = None
    germination_rate: Optional[float] = None

    seed_stock: Optional[str] = None
    eppendorf_in_50cc: Optional[int] = None
    seed_coating: Optional[str] = None
    number_aluminum_bag: Optional[int] = None

    notes: Optional[str] = None

    raspi_observation_count: int = 0

    thumbnail_url: Optional[str] = None

    class Config:
        from_attributes = True

class PaginatedCultivarSearchResponse(BaseModel):
    total_count: int
    limit: int
    offset: int
    data: List[CultivarSearchItem]

class DatabaseStatsSimple(BaseModel):
    """Simple database statistics"""
    total_plants: int
    total_batches: int
    total_cultivars: int
    total_treatments: int
    observation_counts: Dict[str, int]
    last_updated: datetime

class FacetedFilterOptions(BaseModel):
    product_names: List[str]
    genome_types: List[str] = []

class CultivarBatchInfo(BaseModel):
    batch_code: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    plant_count: int

class CultivarTreatmentInfo(BaseModel):
    treatment_code: str
    plant_count: int

class CultivarDetailsResponse(BaseModel):
    id: int
    cultivar_code: str
    permanent_code: Optional[str] = None
    manufacturer_name: Optional[str] = None
    product_code: Optional[str] = None
    common_name: Optional[str] = None
    product_name: Optional[str] = None
    genome_type: Optional[str] = None

    planting_description: Optional[str] = None
    planting_time: Optional[str] = None
    flowering_time: Optional[str] = None

    edible_part: Optional[str] = None
    germination_rate: Optional[float] = None

    seed_stock: Optional[str] = None
    eppendorf_in_50cc: Optional[int] = None
    seed_coating: Optional[str] = None
    number_aluminum_bag: Optional[int] = None

    notes: Optional[str] = None

    total_plant_replicates: int
    batches: List[CultivarBatchInfo]
    treatments: List[CultivarTreatmentInfo]

    class Config:
        from_attributes = True


# ========================================
# ENVIRONMENT OBSERVATION SCHEMAS
# ========================================

class SensorResponse(BaseModel):
    id: int
    sensor_code: Optional[str]
    sensor_type: Optional[str]
    rack_id: Optional[int]
    rack_code: Optional[str]
    chamber_id: Optional[int]
    chamber_code: Optional[str]
    notes: Optional[str]

    class Config:
        from_attributes = True

class EnvironmentObservationResponse(BaseModel):
    id: int
    sensor_id: int
    sensor_code: Optional[str]
    observation_timestamp: datetime
    temperature_celsius: Optional[float]
    humidity_percent: Optional[float]
    pressure_hpa: Optional[float]

    class Config:
        from_attributes = True

class PaginatedEnvironmentObservationResponse(BaseModel):
    total_count: int
    limit: int
    offset: int
    data: List[EnvironmentObservationResponse]
