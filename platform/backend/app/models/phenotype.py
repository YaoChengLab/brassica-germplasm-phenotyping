"""
Phenotype Models v2 - Schema aligned with csv-import-v2 and Update_schema.md
"""

from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime, Numeric, ForeignKey,
    UniqueConstraint, CheckConstraint, Index, text
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.models.base import Base


class Batch(Base):
    __tablename__ = 'batches'

    id = Column(Integer, primary_key=True)
    batch_code = Column(String, nullable=False, unique=True, index=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    notes = Column(Text)

    plants = relationship("Plant", back_populates="batch")

    def __repr__(self):
        return f"<Batch(batch_code='{self.batch_code}')>"


class Cultivar(Base):
    __tablename__ = 'cultivars'

    id = Column(Integer, primary_key=True)
    cultivar_code = Column(String, nullable=False, unique=True, index=True)
    permanent_code = Column(String, unique=True, index=True)
    manufacturer_name = Column(String)
    product_code = Column(String)
    common_name = Column(String)
    product_name = Column(String)
    planting_description = Column(Text, nullable=True)
    planting_time = Column(String, nullable=True)
    genome_type = Column(String)
    edible_part = Column(String, nullable=True)
    flowering_time = Column(String, nullable=True)
    germination_rate = Column(Numeric, nullable=True)
    seed_stock = Column(String, nullable=True)
    eppendorf_in_50cc = Column(Integer, nullable=True)
    seed_coating = Column(String, nullable=True)
    number_aluminum_bag = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    plants = relationship("Plant", back_populates="cultivar")

    def __repr__(self):
        return f"<Cultivar(cultivar_code='{self.cultivar_code}')>"


class Treatment(Base):
    __tablename__ = 'treatments'

    id = Column(Integer, primary_key=True)
    treatment_code = Column(String, nullable=False, unique=True, index=True)
    notes = Column(Text)

    plants = relationship("Plant", back_populates="treatment")

    def __repr__(self):
        return f"<Treatment(treatment_code='{self.treatment_code}')>"


class GrowthChamber(Base):
    __tablename__ = 'growth_chambers'

    id = Column(Integer, primary_key=True)
    chamber_code = Column(String, nullable=False, unique=True, index=True)
    notes = Column(Text)

    racks = relationship("Rack", back_populates="chamber")
    sensors = relationship("Sensor", back_populates="chamber")
    chamber_history = relationship("PlantChamberHistory", back_populates="chamber")

    def __repr__(self):
        return f"<GrowthChamber(chamber_code='{self.chamber_code}')>"


class GrowthCondition(Base):
    __tablename__ = 'growth_conditions'

    id = Column(Integer, primary_key=True)
    light_intensity = Column(String)
    light_photoperiod = Column(String)
    pot_size = Column(Numeric)
    water_schedule = Column(String)
    fertilizer_usage = Column(String)
    notes = Column(Text)

    # NOTE: the growth condition that applies to a plant is a property of that
    # plant's stay (plant_positions.growth_condition_id), not of the rack, so racks
    # have no growth_condition_id.
    chamber_history = relationship("PlantChamberHistory", back_populates="growth_condition")

    def __repr__(self):
        return f"<GrowthCondition(light_intensity='{self.light_intensity}')>"


class Rack(Base):
    __tablename__ = 'racks'

    id = Column(Integer, primary_key=True)
    rack_code = Column(String, nullable=True, index=True)
    chamber_id = Column(Integer, ForeignKey('growth_chambers.id'), nullable=True, index=True)
    notes = Column(Text)

    chamber = relationship("GrowthChamber", back_populates="racks")
    sensors = relationship("Sensor", back_populates="rack")
    chamber_history = relationship("PlantChamberHistory", back_populates="rack")

    def __repr__(self):
        return f"<Rack(rack_code='{self.rack_code}')>"


class Sensor(Base):
    __tablename__ = 'sensors'

    id = Column(Integer, primary_key=True)
    sensor_code = Column(String, nullable=True, index=True)
    sensor_type = Column(String, nullable=True)
    rack_id = Column(Integer, ForeignKey('racks.id'), nullable=True, index=True)
    chamber_id = Column(Integer, ForeignKey('growth_chambers.id'), nullable=True, index=True)
    notes = Column(Text)

    rack = relationship("Rack", back_populates="sensors")
    chamber = relationship("GrowthChamber", back_populates="sensors")
    environment_observations = relationship("EnvironmentObservation", back_populates="sensor")
    chamber_history = relationship("PlantChamberHistory", back_populates="sensor")

    def __repr__(self):
        return f"<Sensor(sensor_code='{self.sensor_code}', sensor_type='{self.sensor_type}')>"


class Plant(Base):
    __tablename__ = 'plants'
    # Identity constraints (also in database/init/01-schema.sql; declared here so the ORM matches):
    #   unique plant key per plant_type (partial unique indexes), the two-level structure,
    #   and no plant as its own parent. (batch, cultivar, treatment, replicate) is unique, so
    #   the database guarantees that these four fields identify one plant.
    __table_args__ = (
        Index('uq_plants_observation', 'batch_id', 'cultivar_id', 'treatment_id', 'replicate_code',
              unique=True, postgresql_where=text("plant_type = 'observation_individual'")),
        Index('uq_plants_nursery', 'batch_id', 'cultivar_id', 'treatment_id',
              unique=True, postgresql_where=text("plant_type = 'nursery_group'")),
        CheckConstraint(
            "(plant_type = 'nursery_group' AND replicate_code IS NULL AND parent_plant_id IS NULL) "
            "OR (plant_type = 'observation_individual' AND replicate_code IS NOT NULL AND parent_plant_id IS NOT NULL)",
            name='ck_plants_type_shape'),
        CheckConstraint('parent_plant_id IS NULL OR parent_plant_id <> id',
                        name='ck_plants_no_self_parent'),
    )

    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey('batches.id'), nullable=False, index=True)
    cultivar_id = Column(Integer, ForeignKey('cultivars.id'), nullable=False, index=True)
    treatment_id = Column(Integer, ForeignKey('treatments.id'), nullable=False, index=True)
    replicate_code = Column(Integer, nullable=True)
    plant_type = Column(String, nullable=True)
    parent_plant_id = Column(Integer, ForeignKey('plants.id'), nullable=True, index=True)
    notes = Column(Text, nullable=True)

    batch = relationship("Batch", back_populates="plants")
    cultivar = relationship("Cultivar", back_populates="plants")
    treatment = relationship("Treatment", back_populates="plants")
    parent_plant = relationship("Plant", remote_side=[id], backref="child_plants")

    chamber_history = relationship("PlantChamberHistory", back_populates="plant")
    physical_observations = relationship("PhysicalObservation", back_populates="plant")
    raspi_observations = relationship("RaspiObservation", back_populates="plant")
    thermal_observations = relationship("ThermalObservation", back_populates="plant")

    def __repr__(self):
        return f"<Plant(id={self.id})>"


class PlantChamberHistory(Base):
    __tablename__ = 'plant_positions'

    id = Column(Integer, primary_key=True)
    plant_id = Column(Integer, ForeignKey('plants.id'), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey('batches.id'), nullable=True, index=True)
    chamber_id = Column(Integer, ForeignKey('growth_chambers.id'), nullable=False, index=True)
    rack_id = Column(Integer, ForeignKey('racks.id'), nullable=True, index=True)
    growth_condition_id = Column(Integer, ForeignKey('growth_conditions.id'), nullable=True, index=True)
    sensor_id = Column(Integer, ForeignKey('sensors.id'), nullable=True, index=True)
    entry_date = Column(Date, nullable=False)
    entry_time = Column(String, nullable=True)
    exit_date = Column(Date)
    exit_time = Column(String)
    coordinate_x = Column(Integer, nullable=True)
    coordinate_y = Column(Integer, nullable=True)
    # Filename of the full-frame reference image the pixel coords were digitized
    # from (provenance). NOTE: Base.metadata.create_all only creates missing
    # tables, it does NOT add columns to an existing one — an existing DB needs a
    # one-off `ALTER TABLE plant_positions ADD COLUMN IF NOT EXISTS
    # coord_ref_image varchar;`. A freshly created DB gets it via create_all.
    coord_ref_image = Column(String, nullable=True)
    notes = Column(Text)

    plant = relationship("Plant", back_populates="chamber_history")
    chamber = relationship("GrowthChamber", back_populates="chamber_history")
    rack = relationship("Rack", back_populates="chamber_history")
    growth_condition = relationship("GrowthCondition", back_populates="chamber_history")
    sensor = relationship("Sensor", back_populates="chamber_history")

    def __repr__(self):
        return f"<PlantChamberHistory(plant_id={self.plant_id}, chamber_id={self.chamber_id})>"


class PhysicalObservation(Base):
    __tablename__ = 'physical_observations'

    id = Column(Integer, primary_key=True)
    plant_id = Column(Integer, ForeignKey('plants.id'), nullable=False, index=True)
    sensor_id = Column(Integer, ForeignKey('sensors.id'), nullable=True, index=True)
    observation_timestamp = Column(DateTime(timezone=True), nullable=False, index=True, default=lambda: datetime.now(timezone.utc))
    weight = Column(Numeric)
    height_baseline = Column(Numeric)
    height = Column(Numeric)
    area = Column(Numeric)
    volume = Column(Numeric)
    projected_area = Column(Numeric)
    digital_biomass = Column(Numeric)

    samplename = Column(String, nullable=True)
    project_name = Column(String, nullable=True)
    species = Column(String, nullable=True)
    project_description = Column(Text, nullable=True)
    owner = Column(String, nullable=True)
    total_points = Column(Integer, nullable=True)
    voxel_volume = Column(Numeric, nullable=True)
    voxel_count = Column(Integer, nullable=True)
    leaf_angle = Column(Numeric, nullable=True)
    gaussian_curvature = Column(Numeric, nullable=True)
    mean_curvature = Column(Numeric, nullable=True)
    total_curvature = Column(Numeric, nullable=True)
    plan_curvature = Column(Numeric, nullable=True)
    profile_curvature = Column(Numeric, nullable=True)

    plant = relationship("Plant", back_populates="physical_observations")

    def __repr__(self):
        return f"<PhysicalObservation(plant_id={self.plant_id}, height={self.height})>"


class RaspiObservation(Base):
    __tablename__ = 'trait_observations'

    id = Column(Integer, primary_key=True)
    plant_id = Column(Integer, ForeignKey('plants.id'), nullable=False, index=True)
    sensor_id = Column(Integer, ForeignKey('sensors.id'), nullable=True, index=True)
    observation_timestamp = Column(DateTime(timezone=True), nullable=False, index=True, default=lambda: datetime.now(timezone.utc))
    day_after_sewing = Column(Integer, nullable=True, index=True)

    # Basic leaf measurements
    leaf_count = Column(Integer, nullable=True)
    leaf_area = Column(Numeric, nullable=True)

    # Area and size measurements
    area_pixels = Column(Numeric, nullable=True)
    bounding_box_area = Column(Numeric, nullable=True)
    perimeter_pixels = Column(Numeric, nullable=True)
    convex_hull_area_pixels = Column(Numeric, nullable=True)
    convex_hull_perimeter = Column(Numeric, nullable=True)
    extent = Column(Numeric, nullable=True)

    # Plant dimensions
    plant_height = Column(Numeric, nullable=True)
    plant_width = Column(Numeric, nullable=True)
    equivalent_diameter = Column(Numeric, nullable=True)

    # Shape analysis (Morph # = trait number in the trait list)
    # compactness, roundness and gap_fraction_canopy_porosity are not stored; use
    # solidity, circularity_2 and canopy_porosity respectively (the last is a
    # DIFFERENT quantity: convex-hull based, not bounding-box based).
    eccentricity = Column(Numeric, nullable=True)  # Morph #4 Eccentricity2
    radial_symmetry = Column(Numeric, nullable=True)  # Morph #16

    # Further shape metrics
    solidity = Column(Numeric, nullable=True)  # Morph #12: A / A_convex
    circularity_1 = Column(Numeric, nullable=True)  # Morph #5: P² / A
    circularity_2 = Column(Numeric, nullable=True)  # Morph #6: 4πA / P²
    canopy_porosity = Column(Numeric, nullable=True)  # Morph #20: 1 - A/A_convex (convex-hull based)
    eccentricity_eigenvalue_ratio = Column(Numeric, nullable=True)  # Morph #3: λ_min / λ_max
    sift_keypoint_count = Column(Integer, nullable=True)  # Morph #1
    multiscale_straightness = Column(Numeric, nullable=True)  # Morph #21
    combined_simple_connectivity = Column(Numeric, nullable=True)  # Morph #22
    # Morph #23 mer_angle is not stored: the orientation angle depends on how the
    # plant is rotated, so it is not a stable trait.
    fuzzy_rectangularity = Column(Numeric, nullable=True)  # Morph #24

    # Ellipse fitting parameters
    major_axis_length = Column(Numeric, nullable=True)
    minor_axis_length = Column(Numeric, nullable=True)
    ellipse_aspect_ratio = Column(Numeric, nullable=True)
    ellipse_center_x = Column(Numeric, nullable=True)
    ellipse_center_y = Column(Numeric, nullable=True)
    ellipse_angle_degrees = Column(Numeric, nullable=True)

    # Radius measurements (from centroid)
    # max_/mean_/median_radius_from_centroid are not stored: they duplicate the
    # size traits.
    min_radius_from_centroid = Column(Numeric, nullable=True)
    std_radius_from_centroid = Column(Numeric, nullable=True)

    # Color channel measurements
    red_channel = Column(Numeric, nullable=True)
    green_channel = Column(Numeric, nullable=True)
    blue_channel = Column(Numeric, nullable=True)

    # Color ratios
    red_green_ratio = Column(Numeric, nullable=True)
    blue_green_ratio = Column(Numeric, nullable=True)
    blue_red_ratio = Column(Numeric, nullable=True)

    # Color indices
    excess_green_index = Column(Numeric, nullable=True)
    excess_green_minus_red = Column(Numeric, nullable=True)
    excess_red_index = Column(Numeric, nullable=True)
    green_index = Column(Numeric, nullable=True)
    green_leaf_index = Column(Numeric, nullable=True)
    green_difference = Column(Numeric, nullable=True)
    green_difference_variant = Column(Numeric, nullable=True)
    greenness = Column(Numeric, nullable=True)

    # HSL color space
    hue = Column(Numeric, nullable=True)
    saturation = Column(Numeric, nullable=True)
    lightness = Column(Numeric, nullable=True)

    # Chroma and brightness
    chroma = Column(Numeric, nullable=True)
    chroma_prime = Column(Numeric, nullable=True)
    anthocyanin_chroma_basic = Column(Numeric, nullable=True)
    anthocyanin_chroma_difference = Column(Numeric, nullable=True)
    anthocyanin_chroma_ratio = Column(Numeric, nullable=True)
    brightness = Column(Numeric, nullable=True)

    # Vegetation indices
    cive = Column(Numeric, nullable=True)
    dgci = Column(Numeric, nullable=True)
    mgrvi = Column(Numeric, nullable=True)
    ndyi = Column(Numeric, nullable=True)
    ngrdi = Column(Numeric, nullable=True)
    rgbvi = Column(Numeric, nullable=True)
    triangular_greenness_index = Column(Numeric, nullable=True)
    vari = Column(Numeric, nullable=True)
    veg = Column(Numeric, nullable=True)
    vegetation_index_2 = Column(Numeric, nullable=True)

    # Color strength
    strength_of_red = Column(Numeric, nullable=True)
    strength_of_green = Column(Numeric, nullable=True)
    strength_of_blue = Column(Numeric, nullable=True)

    # RGB Channel Skewness / Kurtosis (Color #36, #37)
    # Per-channel: R, G, B, Y (grayscale)
    skewness_r = Column(Numeric, nullable=True)
    skewness_g = Column(Numeric, nullable=True)
    skewness_b = Column(Numeric, nullable=True)
    skewness_y = Column(Numeric, nullable=True)
    kurtosis_r = Column(Numeric, nullable=True)
    kurtosis_g = Column(Numeric, nullable=True)
    kurtosis_b = Column(Numeric, nullable=True)
    kurtosis_y = Column(Numeric, nullable=True)

    # Distribution and entropy
    colour_distribution_modes = Column(Numeric, nullable=True)
    spectral_distribution_modes = Column(Numeric, nullable=True)
    num_unique_colours = Column(Numeric, nullable=True)
    pixel_entropy = Column(Numeric, nullable=True)

    # GLCM texture features
    glcm_asm = Column(Numeric, nullable=True)
    glcm_autocorrelation = Column(Numeric, nullable=True)
    glcm_cluster_prominence = Column(Numeric, nullable=True)
    glcm_cluster_shade = Column(Numeric, nullable=True)
    glcm_contrast = Column(Numeric, nullable=True)
    glcm_correlation = Column(Numeric, nullable=True)
    glcm_difference_entropy = Column(Numeric, nullable=True)
    glcm_difference_variance = Column(Numeric, nullable=True)
    glcm_dissimilarity = Column(Numeric, nullable=True)
    glcm_entropy = Column(Numeric, nullable=True)
    glcm_idm = Column(Numeric, nullable=True)
    glcm_idmn = Column(Numeric, nullable=True)
    glcm_idn = Column(Numeric, nullable=True)
    glcm_imc1 = Column(Numeric, nullable=True)
    glcm_imc2 = Column(Numeric, nullable=True)
    glcm_inverse_difference = Column(Numeric, nullable=True)
    glcm_max_probability = Column(Numeric, nullable=True)
    glcm_mcc = Column(Numeric, nullable=True)
    glcm_ssv = Column(Numeric, nullable=True)
    glcm_sum_average = Column(Numeric, nullable=True)
    glcm_sum_entropy = Column(Numeric, nullable=True)
    glcm_sum_variance = Column(Numeric, nullable=True)

    # HOG features
    hog_mean = Column(Numeric, nullable=True)
    hog_std = Column(Numeric, nullable=True)

    # Log features
    log_mean = Column(Numeric, nullable=True)
    log_std = Column(Numeric, nullable=True)

    # Image reference
    # File name of the single-plant image (<stem>.png), written by platform/ingest/load.py.
    # The image itself is located from the plant key: <batch>/<cultivar>/<treatment>/rep-<n>/.
    image_file = Column(String, nullable=True)

    # QC / provenance, written by imaging/traits_2d and platform/ingest.
    # qc_status: 'no' (older rows without leaf-to-plant assignment) | 'auto' (automatic
    # assignment) | 'verified' (reviewed).
    qc_status = Column(String, nullable=True)
    pipeline_version = Column(String, nullable=True)
    analysis_run_id = Column(Integer, nullable=True)   # -> analysis_runs.id (no ORM model; plain column)
    # Loads are idempotent through the natural key (plant_id, sensor_id, observation_timestamp);
    # file-level provenance is kept in analysis_runs.

    plant = relationship("Plant", back_populates="raspi_observations")

    def __repr__(self):
        return f"<RaspiObservation(plant_id={self.plant_id}, leaf_count={self.leaf_count})>"


class ThermalObservation(Base):
    __tablename__ = 'thermal_observations'

    id = Column(Integer, primary_key=True)
    plant_id = Column(Integer, ForeignKey('plants.id'), nullable=False, index=True)
    sensor_id = Column(Integer, ForeignKey('sensors.id'), nullable=True, index=True)
    observation_timestamp = Column(DateTime(timezone=True), nullable=False, index=True, default=lambda: datetime.now(timezone.utc))
    flir_min = Column(Numeric)
    flir_mean = Column(Numeric)
    flir_median = Column(Numeric)
    flir_max = Column(Numeric)
    flir_sd = Column(Numeric)

    plant = relationship("Plant", back_populates="thermal_observations")

    def __repr__(self):
        return f"<ThermalObservation(plant_id={self.plant_id}, mean_temp={self.flir_mean})>"


class EnvironmentObservation(Base):
    __tablename__ = 'env_observations'

    id = Column(Integer, primary_key=True)
    sensor_id = Column(Integer, ForeignKey('sensors.id'), nullable=False, index=True)
    observation_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    temperature_celsius = Column(Numeric, nullable=True)
    humidity_percent = Column(Numeric, nullable=True)
    pressure_hpa = Column(Numeric, nullable=True)

    sensor = relationship("Sensor", back_populates="environment_observations")

    def __repr__(self):
        return f"<EnvironmentObservation(sensor_id={self.sensor_id}, temp={self.temperature_celsius})>"


class BatchMilestone(Base):
    """Event-backed data stages with no observation table yet (currently the
    digital-camera shoot). Per (batch, cultivar, stage): row present = event done.
    Created automatically by Base.metadata.create_all on startup (new table).
    Extensible: more stages reuse this; a future gallery can extend with image paths."""
    __tablename__ = 'batch_milestones'
    __table_args__ = (
        UniqueConstraint('batch_id', 'cultivar_id', 'stage', name='uq_batch_milestone'),
    )

    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey('batches.id'), nullable=False, index=True)
    cultivar_id = Column(Integer, ForeignKey('cultivars.id'), nullable=False, index=True)
    stage = Column(String, nullable=False)          # e.g. 'digital_camera'
    status = Column(String, nullable=False, default='shot')
    marked_by = Column(String, nullable=True)
    marked_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    notes = Column(Text, nullable=True)

    def __repr__(self):
        return f"<BatchMilestone(batch_id={self.batch_id}, cultivar_id={self.cultivar_id}, stage={self.stage})>"
