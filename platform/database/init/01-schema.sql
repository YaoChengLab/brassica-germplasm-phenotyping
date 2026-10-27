--
-- PostgreSQL database dump
--

\restrict T4IH9UQFokPg4uh3vsu7W6dXUZHxAi7hCYRnlu1tgvQQ2YiTm7MviFvezBATm5r

-- Dumped from database version 15.17
-- Dumped by pg_dump version 15.17

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: btree_gist; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: analysis_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analysis_runs (
    id integer NOT NULL,
    modality character varying(32) NOT NULL,
    batch_code character varying(16) NOT NULL,
    pipeline_version character varying(64) NOT NULL,
    qc_snapshot_hash character varying(64),
    extractor_sha character varying(32),
    status character varying(16) NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    n_rows integer
);


--
-- Name: analysis_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.analysis_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: analysis_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.analysis_runs_id_seq OWNED BY public.analysis_runs.id;


--
-- Name: batch_milestones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.batch_milestones (
    id integer NOT NULL,
    batch_id integer NOT NULL,
    cultivar_id integer NOT NULL,
    stage character varying NOT NULL,
    status character varying NOT NULL,
    marked_by character varying,
    marked_at timestamp with time zone NOT NULL,
    notes text
);


--
-- Name: batch_milestones_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.batch_milestones_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: batch_milestones_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.batch_milestones_id_seq OWNED BY public.batch_milestones.id;


--
-- Name: batches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.batches (
    id integer NOT NULL,
    batch_code character varying NOT NULL,
    start_date date NOT NULL,
    end_date date,
    notes text
);


--
-- Name: batches_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.batches_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: batches_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.batches_id_seq OWNED BY public.batches.id;


--
-- Name: cultivars; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cultivars (
    id integer NOT NULL,
    cultivar_code character varying NOT NULL,
    permanent_code character varying,
    manufacturer_name character varying,
    product_code character varying,
    common_name character varying,
    product_name character varying,
    planting_description text,
    planting_time character varying,
    genome_type character varying,
    edible_part character varying,
    flowering_time character varying,
    germination_rate numeric,
    seed_stock character varying,
    eppendorf_in_50cc integer,
    seed_coating character varying,
    number_aluminum_bag integer,
    notes text
);


--
-- Name: cultivars_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cultivars_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cultivars_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cultivars_id_seq OWNED BY public.cultivars.id;


--
-- Name: env_observations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.env_observations (
    id integer NOT NULL,
    sensor_id integer NOT NULL,
    observation_timestamp timestamp with time zone NOT NULL,
    temperature_celsius numeric,
    humidity_percent numeric,
    pressure_hpa numeric
);


--
-- Name: env_observations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.env_observations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: env_observations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.env_observations_id_seq OWNED BY public.env_observations.id;


--
-- Name: environmentobservations; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.environmentobservations AS
 SELECT env_observations.id,
    env_observations.sensor_id,
    env_observations.observation_timestamp,
    env_observations.temperature_celsius,
    env_observations.humidity_percent,
    env_observations.pressure_hpa
   FROM public.env_observations;


--
-- Name: growth_chambers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.growth_chambers (
    id integer NOT NULL,
    chamber_code character varying NOT NULL,
    notes text
);


--
-- Name: growth_chambers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.growth_chambers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: growth_chambers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.growth_chambers_id_seq OWNED BY public.growth_chambers.id;


--
-- Name: growth_conditions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.growth_conditions (
    id integer NOT NULL,
    light_intensity character varying,
    light_photoperiod character varying,
    pot_size numeric,
    water_schedule character varying,
    fertilizer_usage character varying,
    notes text
);


--
-- Name: growth_conditions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.growth_conditions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: growth_conditions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.growth_conditions_id_seq OWNED BY public.growth_conditions.id;


--
-- Name: growthchambers; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.growthchambers AS
 SELECT growth_chambers.id,
    growth_chambers.chamber_code,
    growth_chambers.notes
   FROM public.growth_chambers;


--
-- Name: growthconditions; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.growthconditions AS
 SELECT growth_conditions.id,
    growth_conditions.light_intensity,
    growth_conditions.light_photoperiod,
    growth_conditions.pot_size,
    growth_conditions.water_schedule,
    growth_conditions.fertilizer_usage,
    growth_conditions.notes
   FROM public.growth_conditions;


--
-- Name: physical_observations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.physical_observations (
    id integer NOT NULL,
    plant_id integer NOT NULL,
    sensor_id integer,
    observation_timestamp timestamp with time zone NOT NULL,
    weight numeric,
    height_baseline numeric,
    height numeric,
    area numeric,
    volume numeric,
    projected_area numeric,
    digital_biomass numeric,
    samplename character varying,
    project_name character varying,
    species character varying,
    project_description text,
    owner character varying,
    total_points integer,
    voxel_volume numeric,
    voxel_count integer,
    leaf_angle numeric,
    gaussian_curvature numeric,
    mean_curvature numeric,
    total_curvature numeric,
    plan_curvature numeric,
    profile_curvature numeric,
    analysis_run_id integer
);


--
-- Name: physical_observations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.physical_observations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: physical_observations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.physical_observations_id_seq OWNED BY public.physical_observations.id;


--
-- Name: physicalobservations; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.physicalobservations AS
 SELECT physical_observations.id,
    physical_observations.plant_id,
    physical_observations.sensor_id,
    physical_observations.observation_timestamp,
    physical_observations.weight,
    physical_observations.height_baseline,
    physical_observations.height,
    physical_observations.area,
    physical_observations.volume,
    physical_observations.projected_area,
    physical_observations.digital_biomass,
    physical_observations.samplename,
    physical_observations.project_name,
    physical_observations.species,
    physical_observations.project_description,
    physical_observations.owner,
    physical_observations.total_points,
    physical_observations.voxel_volume,
    physical_observations.voxel_count,
    physical_observations.leaf_angle,
    physical_observations.gaussian_curvature,
    physical_observations.mean_curvature,
    physical_observations.total_curvature,
    physical_observations.plan_curvature,
    physical_observations.profile_curvature,
    physical_observations.analysis_run_id
   FROM public.physical_observations;


--
-- Name: plant_positions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plant_positions (
    id integer NOT NULL,
    plant_id integer NOT NULL,
    batch_id integer,
    chamber_id integer NOT NULL,
    rack_id integer,
    growth_condition_id integer,
    sensor_id integer,
    entry_date date NOT NULL,
    entry_time character varying,
    exit_date date,
    exit_time character varying,
    coordinate_x integer,
    coordinate_y integer,
    notes text,
    coord_ref_image character varying,
    CONSTRAINT ck_plant_positions_date_order CHECK (((exit_date IS NULL) OR (exit_date >= entry_date)))
);


--
-- Name: plant_positions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.plant_positions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: plant_positions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.plant_positions_id_seq OWNED BY public.plant_positions.id;


--
-- Name: plantchamberhistory; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.plantchamberhistory AS
 SELECT plant_positions.id,
    plant_positions.plant_id,
    plant_positions.batch_id,
    plant_positions.chamber_id,
    plant_positions.rack_id,
    plant_positions.growth_condition_id,
    plant_positions.sensor_id,
    plant_positions.entry_date,
    plant_positions.entry_time,
    plant_positions.exit_date,
    plant_positions.exit_time,
    plant_positions.coordinate_x,
    plant_positions.coordinate_y,
    plant_positions.notes,
    plant_positions.coord_ref_image
   FROM public.plant_positions;


--
-- Name: plants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plants (
    id integer NOT NULL,
    batch_id integer NOT NULL,
    cultivar_id integer NOT NULL,
    treatment_id integer NOT NULL,
    replicate_code integer,
    plant_type character varying,
    parent_plant_id integer,
    notes text,
    CONSTRAINT ck_plants_no_self_parent CHECK (((parent_plant_id IS NULL) OR (parent_plant_id <> id))),
    CONSTRAINT ck_plants_type_shape CHECK (((((plant_type)::text = 'nursery_group'::text) AND (replicate_code IS NULL) AND (parent_plant_id IS NULL)) OR (((plant_type)::text = 'observation_individual'::text) AND (replicate_code IS NOT NULL) AND (parent_plant_id IS NOT NULL))))
);


--
-- Name: plants_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.plants_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: plants_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.plants_id_seq OWNED BY public.plants.id;


--
-- Name: racks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.racks (
    id integer NOT NULL,
    rack_code character varying,
    chamber_id integer,
    notes text
);


--
-- Name: racks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.racks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: racks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.racks_id_seq OWNED BY public.racks.id;


--
-- Name: trait_observations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trait_observations (
    id integer NOT NULL,
    plant_id integer NOT NULL,
    sensor_id integer,
    observation_timestamp timestamp with time zone NOT NULL,
    day_after_sewing integer,
    leaf_count integer,
    leaf_area numeric,
    area_pixels numeric,
    bounding_box_area numeric,
    perimeter_pixels numeric,
    convex_hull_area_pixels numeric,
    convex_hull_perimeter numeric,
    extent numeric,
    plant_height numeric,
    plant_width numeric,
    equivalent_diameter numeric,
    eccentricity numeric,
    radial_symmetry numeric,
    solidity numeric,
    circularity_1 numeric,
    circularity_2 numeric,
    canopy_porosity numeric,
    eccentricity_eigenvalue_ratio numeric,
    sift_keypoint_count integer,
    multiscale_straightness numeric,
    combined_simple_connectivity numeric,
    fuzzy_rectangularity numeric,
    major_axis_length numeric,
    minor_axis_length numeric,
    ellipse_aspect_ratio numeric,
    ellipse_center_x numeric,
    ellipse_center_y numeric,
    ellipse_angle_degrees numeric,
    min_radius_from_centroid numeric,
    std_radius_from_centroid numeric,
    red_channel numeric,
    green_channel numeric,
    blue_channel numeric,
    red_green_ratio numeric,
    blue_green_ratio numeric,
    blue_red_ratio numeric,
    excess_green_index numeric,
    excess_green_minus_red numeric,
    excess_red_index numeric,
    green_index numeric,
    green_leaf_index numeric,
    green_difference numeric,
    green_difference_variant numeric,
    greenness numeric,
    hue numeric,
    saturation numeric,
    lightness numeric,
    chroma numeric,
    chroma_prime numeric,
    anthocyanin_chroma_basic numeric,
    anthocyanin_chroma_difference numeric,
    anthocyanin_chroma_ratio numeric,
    brightness numeric,
    cive numeric,
    dgci numeric,
    mgrvi numeric,
    ndyi numeric,
    ngrdi numeric,
    rgbvi numeric,
    triangular_greenness_index numeric,
    vari numeric,
    veg numeric,
    vegetation_index_2 numeric,
    strength_of_red numeric,
    strength_of_green numeric,
    strength_of_blue numeric,
    skewness_r numeric,
    skewness_g numeric,
    skewness_b numeric,
    skewness_y numeric,
    kurtosis_r numeric,
    kurtosis_g numeric,
    kurtosis_b numeric,
    kurtosis_y numeric,
    colour_distribution_modes numeric,
    spectral_distribution_modes numeric,
    num_unique_colours numeric,
    pixel_entropy numeric,
    glcm_asm numeric,
    glcm_autocorrelation numeric,
    glcm_cluster_prominence numeric,
    glcm_cluster_shade numeric,
    glcm_contrast numeric,
    glcm_correlation numeric,
    glcm_difference_entropy numeric,
    glcm_difference_variance numeric,
    glcm_dissimilarity numeric,
    glcm_entropy numeric,
    glcm_idm numeric,
    glcm_idmn numeric,
    glcm_idn numeric,
    glcm_imc1 numeric,
    glcm_imc2 numeric,
    glcm_inverse_difference numeric,
    glcm_max_probability numeric,
    glcm_mcc numeric,
    glcm_ssv numeric,
    glcm_sum_average numeric,
    glcm_sum_entropy numeric,
    glcm_sum_variance numeric,
    hog_mean numeric,
    hog_std numeric,
    log_mean numeric,
    log_std numeric,
    image_file character varying,
    qc_status character varying(16),
    analysis_run_id integer,
    pipeline_version character varying(64),
    CONSTRAINT ck_trait_observations_ranges CHECK ((((leaf_count IS NULL) OR (leaf_count >= 0)) AND ((area_pixels IS NULL) OR (area_pixels >= (0)::numeric)) AND ((solidity IS NULL) OR ((solidity >= (0)::numeric) AND (solidity <= 1.001))) AND ((extent IS NULL) OR ((extent >= (0)::numeric) AND (extent <= 1.001)))))
);


--
-- Name: raspiobservations; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.raspiobservations AS
 SELECT trait_observations.id,
    trait_observations.plant_id,
    trait_observations.sensor_id,
    trait_observations.observation_timestamp,
    trait_observations.day_after_sewing,
    trait_observations.leaf_count,
    trait_observations.leaf_area,
    trait_observations.area_pixels,
    trait_observations.bounding_box_area,
    trait_observations.perimeter_pixels,
    trait_observations.convex_hull_area_pixels,
    trait_observations.convex_hull_perimeter,
    trait_observations.extent,
    trait_observations.plant_height,
    trait_observations.plant_width,
    trait_observations.equivalent_diameter,
    trait_observations.eccentricity,
    trait_observations.radial_symmetry,
    trait_observations.solidity,
    trait_observations.circularity_1,
    trait_observations.circularity_2,
    trait_observations.canopy_porosity,
    trait_observations.eccentricity_eigenvalue_ratio,
    trait_observations.sift_keypoint_count,
    trait_observations.multiscale_straightness,
    trait_observations.combined_simple_connectivity,
    trait_observations.fuzzy_rectangularity,
    trait_observations.major_axis_length,
    trait_observations.minor_axis_length,
    trait_observations.ellipse_aspect_ratio,
    trait_observations.ellipse_center_x,
    trait_observations.ellipse_center_y,
    trait_observations.ellipse_angle_degrees,
    trait_observations.min_radius_from_centroid,
    trait_observations.std_radius_from_centroid,
    trait_observations.red_channel,
    trait_observations.green_channel,
    trait_observations.blue_channel,
    trait_observations.red_green_ratio,
    trait_observations.blue_green_ratio,
    trait_observations.blue_red_ratio,
    trait_observations.excess_green_index,
    trait_observations.excess_green_minus_red,
    trait_observations.excess_red_index,
    trait_observations.green_index,
    trait_observations.green_leaf_index,
    trait_observations.green_difference,
    trait_observations.green_difference_variant,
    trait_observations.greenness,
    trait_observations.hue,
    trait_observations.saturation,
    trait_observations.lightness,
    trait_observations.chroma,
    trait_observations.chroma_prime,
    trait_observations.anthocyanin_chroma_basic,
    trait_observations.anthocyanin_chroma_difference,
    trait_observations.anthocyanin_chroma_ratio,
    trait_observations.brightness,
    trait_observations.cive,
    trait_observations.dgci,
    trait_observations.mgrvi,
    trait_observations.ndyi,
    trait_observations.ngrdi,
    trait_observations.rgbvi,
    trait_observations.triangular_greenness_index,
    trait_observations.vari,
    trait_observations.veg,
    trait_observations.vegetation_index_2,
    trait_observations.strength_of_red,
    trait_observations.strength_of_green,
    trait_observations.strength_of_blue,
    trait_observations.skewness_r,
    trait_observations.skewness_g,
    trait_observations.skewness_b,
    trait_observations.skewness_y,
    trait_observations.kurtosis_r,
    trait_observations.kurtosis_g,
    trait_observations.kurtosis_b,
    trait_observations.kurtosis_y,
    trait_observations.colour_distribution_modes,
    trait_observations.spectral_distribution_modes,
    trait_observations.num_unique_colours,
    trait_observations.pixel_entropy,
    trait_observations.glcm_asm,
    trait_observations.glcm_autocorrelation,
    trait_observations.glcm_cluster_prominence,
    trait_observations.glcm_cluster_shade,
    trait_observations.glcm_contrast,
    trait_observations.glcm_correlation,
    trait_observations.glcm_difference_entropy,
    trait_observations.glcm_difference_variance,
    trait_observations.glcm_dissimilarity,
    trait_observations.glcm_entropy,
    trait_observations.glcm_idm,
    trait_observations.glcm_idmn,
    trait_observations.glcm_idn,
    trait_observations.glcm_imc1,
    trait_observations.glcm_imc2,
    trait_observations.glcm_inverse_difference,
    trait_observations.glcm_max_probability,
    trait_observations.glcm_mcc,
    trait_observations.glcm_ssv,
    trait_observations.glcm_sum_average,
    trait_observations.glcm_sum_entropy,
    trait_observations.glcm_sum_variance,
    trait_observations.hog_mean,
    trait_observations.hog_std,
    trait_observations.log_mean,
    trait_observations.log_std,
    trait_observations.image_file,
    trait_observations.qc_status,
    trait_observations.analysis_run_id,
    trait_observations.pipeline_version
   FROM public.trait_observations;


--
-- Name: sensors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sensors (
    id integer NOT NULL,
    sensor_code character varying,
    sensor_type character varying,
    rack_id integer,
    chamber_id integer,
    notes text,
    modality character varying(32),
    cadence character varying(16),
    view_angle character varying(16),
    calibrated boolean,
    description text
);


--
-- Name: sensors_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sensors_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sensors_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sensors_id_seq OWNED BY public.sensors.id;


--
-- Name: thermal_observations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.thermal_observations (
    id integer NOT NULL,
    plant_id integer NOT NULL,
    sensor_id integer,
    observation_timestamp timestamp with time zone NOT NULL,
    flir_min numeric,
    flir_mean numeric,
    flir_median numeric,
    flir_max numeric,
    flir_sd numeric,
    analysis_run_id integer
);


--
-- Name: thermal_observations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.thermal_observations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: thermal_observations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.thermal_observations_id_seq OWNED BY public.thermal_observations.id;


--
-- Name: thermalobservations; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.thermalobservations AS
 SELECT thermal_observations.id,
    thermal_observations.plant_id,
    thermal_observations.sensor_id,
    thermal_observations.observation_timestamp,
    thermal_observations.flir_min,
    thermal_observations.flir_mean,
    thermal_observations.flir_median,
    thermal_observations.flir_max,
    thermal_observations.flir_sd,
    thermal_observations.analysis_run_id
   FROM public.thermal_observations;


--
-- Name: trait_observations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.trait_observations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trait_observations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.trait_observations_id_seq OWNED BY public.trait_observations.id;


--
-- Name: treatments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.treatments (
    id integer NOT NULL,
    treatment_code character varying NOT NULL,
    notes text
);


--
-- Name: treatments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.treatments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: treatments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.treatments_id_seq OWNED BY public.treatments.id;


--
-- Name: analysis_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_runs ALTER COLUMN id SET DEFAULT nextval('public.analysis_runs_id_seq'::regclass);


--
-- Name: batch_milestones id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.batch_milestones ALTER COLUMN id SET DEFAULT nextval('public.batch_milestones_id_seq'::regclass);


--
-- Name: batches id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.batches ALTER COLUMN id SET DEFAULT nextval('public.batches_id_seq'::regclass);


--
-- Name: cultivars id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cultivars ALTER COLUMN id SET DEFAULT nextval('public.cultivars_id_seq'::regclass);


--
-- Name: env_observations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.env_observations ALTER COLUMN id SET DEFAULT nextval('public.env_observations_id_seq'::regclass);


--
-- Name: growth_chambers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_chambers ALTER COLUMN id SET DEFAULT nextval('public.growth_chambers_id_seq'::regclass);


--
-- Name: growth_conditions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_conditions ALTER COLUMN id SET DEFAULT nextval('public.growth_conditions_id_seq'::regclass);


--
-- Name: physical_observations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.physical_observations ALTER COLUMN id SET DEFAULT nextval('public.physical_observations_id_seq'::regclass);


--
-- Name: plant_positions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_positions ALTER COLUMN id SET DEFAULT nextval('public.plant_positions_id_seq'::regclass);


--
-- Name: plants id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plants ALTER COLUMN id SET DEFAULT nextval('public.plants_id_seq'::regclass);


--
-- Name: racks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.racks ALTER COLUMN id SET DEFAULT nextval('public.racks_id_seq'::regclass);


--
-- Name: sensors id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sensors ALTER COLUMN id SET DEFAULT nextval('public.sensors_id_seq'::regclass);


--
-- Name: thermal_observations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.thermal_observations ALTER COLUMN id SET DEFAULT nextval('public.thermal_observations_id_seq'::regclass);


--
-- Name: trait_observations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trait_observations ALTER COLUMN id SET DEFAULT nextval('public.trait_observations_id_seq'::regclass);


--
-- Name: treatments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatments ALTER COLUMN id SET DEFAULT nextval('public.treatments_id_seq'::regclass);


--
-- Name: analysis_runs analysis_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analysis_runs
    ADD CONSTRAINT analysis_runs_pkey PRIMARY KEY (id);


--
-- Name: batch_milestones batch_milestones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.batch_milestones
    ADD CONSTRAINT batch_milestones_pkey PRIMARY KEY (id);


--
-- Name: batches batches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.batches
    ADD CONSTRAINT batches_pkey PRIMARY KEY (id);


--
-- Name: cultivars cultivars_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cultivars
    ADD CONSTRAINT cultivars_pkey PRIMARY KEY (id);


--
-- Name: env_observations env_observations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.env_observations
    ADD CONSTRAINT env_observations_pkey PRIMARY KEY (id);


--
-- Name: plant_positions ex_plant_positions_position_time; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_positions
    ADD CONSTRAINT ex_plant_positions_position_time EXCLUDE USING gist (rack_id WITH =, coordinate_x WITH =, coordinate_y WITH =, daterange(entry_date, exit_date, '[)'::text) WITH &&) WHERE (((rack_id IS NOT NULL) AND (coordinate_x IS NOT NULL) AND (coordinate_y IS NOT NULL)));


--
-- Name: growth_chambers growth_chambers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_chambers
    ADD CONSTRAINT growth_chambers_pkey PRIMARY KEY (id);


--
-- Name: growth_conditions growth_conditions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_conditions
    ADD CONSTRAINT growth_conditions_pkey PRIMARY KEY (id);


--
-- Name: physical_observations physical_observations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.physical_observations
    ADD CONSTRAINT physical_observations_pkey PRIMARY KEY (id);


--
-- Name: plant_positions plant_positions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_positions
    ADD CONSTRAINT plant_positions_pkey PRIMARY KEY (id);


--
-- Name: plants plants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plants
    ADD CONSTRAINT plants_pkey PRIMARY KEY (id);


--
-- Name: racks racks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.racks
    ADD CONSTRAINT racks_pkey PRIMARY KEY (id);


--
-- Name: sensors sensors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sensors
    ADD CONSTRAINT sensors_pkey PRIMARY KEY (id);


--
-- Name: thermal_observations thermal_observations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.thermal_observations
    ADD CONSTRAINT thermal_observations_pkey PRIMARY KEY (id);


--
-- Name: trait_observations trait_observations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trait_observations
    ADD CONSTRAINT trait_observations_pkey PRIMARY KEY (id);


--
-- Name: treatments treatments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treatments
    ADD CONSTRAINT treatments_pkey PRIMARY KEY (id);


--
-- Name: batch_milestones uq_batch_milestone; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.batch_milestones
    ADD CONSTRAINT uq_batch_milestone UNIQUE (batch_id, cultivar_id, stage);


--
-- Name: physical_observations uq_physical_observations_natural; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.physical_observations
    ADD CONSTRAINT uq_physical_observations_natural UNIQUE NULLS NOT DISTINCT (plant_id, sensor_id, observation_timestamp);


--
-- Name: trait_observations uq_trait_observations_natural; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trait_observations
    ADD CONSTRAINT uq_trait_observations_natural UNIQUE (plant_id, sensor_id, observation_timestamp);


--
-- Name: ix_batch_milestones_batch_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_batch_milestones_batch_id ON public.batch_milestones USING btree (batch_id);


--
-- Name: ix_batch_milestones_cultivar_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_batch_milestones_cultivar_id ON public.batch_milestones USING btree (cultivar_id);


--
-- Name: ix_batches_batch_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_batches_batch_code ON public.batches USING btree (batch_code);


--
-- Name: ix_cultivars_cultivar_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_cultivars_cultivar_code ON public.cultivars USING btree (cultivar_code);


--
-- Name: ix_cultivars_permanent_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_cultivars_permanent_code ON public.cultivars USING btree (permanent_code);


--
-- Name: ix_env_observations_observation_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_env_observations_observation_timestamp ON public.env_observations USING btree (observation_timestamp);


--
-- Name: ix_env_observations_sensor_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_env_observations_sensor_id ON public.env_observations USING btree (sensor_id);


--
-- Name: ix_growth_chambers_chamber_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_growth_chambers_chamber_code ON public.growth_chambers USING btree (chamber_code);


--
-- Name: ix_physical_observations_observation_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_physical_observations_observation_timestamp ON public.physical_observations USING btree (observation_timestamp);


--
-- Name: ix_physical_observations_plant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_physical_observations_plant_id ON public.physical_observations USING btree (plant_id);


--
-- Name: ix_physical_observations_sensor_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_physical_observations_sensor_id ON public.physical_observations USING btree (sensor_id);


--
-- Name: ix_plant_positions_batch_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_plant_positions_batch_id ON public.plant_positions USING btree (batch_id);


--
-- Name: ix_plant_positions_chamber_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_plant_positions_chamber_id ON public.plant_positions USING btree (chamber_id);


--
-- Name: ix_plant_positions_growth_condition_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_plant_positions_growth_condition_id ON public.plant_positions USING btree (growth_condition_id);


--
-- Name: ix_plant_positions_plant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_plant_positions_plant_id ON public.plant_positions USING btree (plant_id);


--
-- Name: ix_plant_positions_rack_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_plant_positions_rack_id ON public.plant_positions USING btree (rack_id);


--
-- Name: ix_plant_positions_sensor_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_plant_positions_sensor_id ON public.plant_positions USING btree (sensor_id);


--
-- Name: ix_plants_batch_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_plants_batch_id ON public.plants USING btree (batch_id);


--
-- Name: ix_plants_cultivar_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_plants_cultivar_id ON public.plants USING btree (cultivar_id);


--
-- Name: ix_plants_parent_plant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_plants_parent_plant_id ON public.plants USING btree (parent_plant_id);


--
-- Name: ix_plants_treatment_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_plants_treatment_id ON public.plants USING btree (treatment_id);


--
-- Name: ix_racks_chamber_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_racks_chamber_id ON public.racks USING btree (chamber_id);


--
-- Name: ix_racks_rack_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_racks_rack_code ON public.racks USING btree (rack_code);


--
-- Name: ix_sensors_chamber_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sensors_chamber_id ON public.sensors USING btree (chamber_id);


--
-- Name: ix_sensors_rack_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sensors_rack_id ON public.sensors USING btree (rack_id);


--
-- Name: ix_sensors_sensor_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sensors_sensor_code ON public.sensors USING btree (sensor_code);


--
-- Name: ix_thermal_observations_observation_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_thermal_observations_observation_timestamp ON public.thermal_observations USING btree (observation_timestamp);


--
-- Name: ix_thermal_observations_plant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_thermal_observations_plant_id ON public.thermal_observations USING btree (plant_id);


--
-- Name: ix_thermal_observations_sensor_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_thermal_observations_sensor_id ON public.thermal_observations USING btree (sensor_id);


--
-- Name: ix_trait_observations_day_after_sewing; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trait_observations_day_after_sewing ON public.trait_observations USING btree (day_after_sewing);


--
-- Name: ix_trait_observations_observation_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trait_observations_observation_timestamp ON public.trait_observations USING btree (observation_timestamp);


--
-- Name: ix_trait_observations_plant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trait_observations_plant_id ON public.trait_observations USING btree (plant_id);


--
-- Name: ix_trait_observations_sensor_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trait_observations_sensor_id ON public.trait_observations USING btree (sensor_id);


--
-- Name: ix_treatments_treatment_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_treatments_treatment_code ON public.treatments USING btree (treatment_code);


--
-- Name: uq_env_observations_natural; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_env_observations_natural ON public.env_observations USING btree (sensor_id, observation_timestamp);


--
-- Name: uq_plant_positions_natural; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_plant_positions_natural ON public.plant_positions USING btree (plant_id, chamber_id, entry_date, entry_time) NULLS NOT DISTINCT;


--
-- Name: uq_plants_nursery; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_plants_nursery ON public.plants USING btree (batch_id, cultivar_id, treatment_id) WHERE ((plant_type)::text = 'nursery_group'::text);


--
-- Name: uq_plants_observation; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_plants_observation ON public.plants USING btree (batch_id, cultivar_id, treatment_id, replicate_code) WHERE ((plant_type)::text = 'observation_individual'::text);


--
-- Name: uq_racks_business; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_racks_business ON public.racks USING btree (chamber_id, rack_code);


--
-- Name: uq_sensors_business; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_sensors_business ON public.sensors USING btree (rack_id, sensor_code);


--
-- Name: uq_thermal_observations_natural; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_thermal_observations_natural ON public.thermal_observations USING btree (plant_id, sensor_id, observation_timestamp) NULLS NOT DISTINCT;


--
-- Name: batch_milestones batch_milestones_batch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.batch_milestones
    ADD CONSTRAINT batch_milestones_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES public.batches(id);


--
-- Name: batch_milestones batch_milestones_cultivar_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.batch_milestones
    ADD CONSTRAINT batch_milestones_cultivar_id_fkey FOREIGN KEY (cultivar_id) REFERENCES public.cultivars(id);


--
-- Name: env_observations env_observations_sensor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.env_observations
    ADD CONSTRAINT env_observations_sensor_id_fkey FOREIGN KEY (sensor_id) REFERENCES public.sensors(id);


--
-- Name: physical_observations physical_observations_analysis_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.physical_observations
    ADD CONSTRAINT physical_observations_analysis_run_id_fkey FOREIGN KEY (analysis_run_id) REFERENCES public.analysis_runs(id);


--
-- Name: physical_observations physical_observations_plant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.physical_observations
    ADD CONSTRAINT physical_observations_plant_id_fkey FOREIGN KEY (plant_id) REFERENCES public.plants(id);


--
-- Name: physical_observations physical_observations_sensor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.physical_observations
    ADD CONSTRAINT physical_observations_sensor_id_fkey FOREIGN KEY (sensor_id) REFERENCES public.sensors(id);


--
-- Name: plant_positions plant_positions_batch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_positions
    ADD CONSTRAINT plant_positions_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES public.batches(id);


--
-- Name: plant_positions plant_positions_chamber_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_positions
    ADD CONSTRAINT plant_positions_chamber_id_fkey FOREIGN KEY (chamber_id) REFERENCES public.growth_chambers(id);


--
-- Name: plant_positions plant_positions_growth_condition_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_positions
    ADD CONSTRAINT plant_positions_growth_condition_id_fkey FOREIGN KEY (growth_condition_id) REFERENCES public.growth_conditions(id);


--
-- Name: plant_positions plant_positions_plant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_positions
    ADD CONSTRAINT plant_positions_plant_id_fkey FOREIGN KEY (plant_id) REFERENCES public.plants(id);


--
-- Name: plant_positions plant_positions_rack_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_positions
    ADD CONSTRAINT plant_positions_rack_id_fkey FOREIGN KEY (rack_id) REFERENCES public.racks(id);


--
-- Name: plant_positions plant_positions_sensor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_positions
    ADD CONSTRAINT plant_positions_sensor_id_fkey FOREIGN KEY (sensor_id) REFERENCES public.sensors(id);


--
-- Name: plants plants_batch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plants
    ADD CONSTRAINT plants_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES public.batches(id);


--
-- Name: plants plants_cultivar_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plants
    ADD CONSTRAINT plants_cultivar_id_fkey FOREIGN KEY (cultivar_id) REFERENCES public.cultivars(id);


--
-- Name: plants plants_parent_plant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plants
    ADD CONSTRAINT plants_parent_plant_id_fkey FOREIGN KEY (parent_plant_id) REFERENCES public.plants(id);


--
-- Name: plants plants_treatment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plants
    ADD CONSTRAINT plants_treatment_id_fkey FOREIGN KEY (treatment_id) REFERENCES public.treatments(id);


--
-- Name: racks racks_chamber_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.racks
    ADD CONSTRAINT racks_chamber_id_fkey FOREIGN KEY (chamber_id) REFERENCES public.growth_chambers(id);


--
-- Name: sensors sensors_chamber_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sensors
    ADD CONSTRAINT sensors_chamber_id_fkey FOREIGN KEY (chamber_id) REFERENCES public.growth_chambers(id);


--
-- Name: sensors sensors_rack_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sensors
    ADD CONSTRAINT sensors_rack_id_fkey FOREIGN KEY (rack_id) REFERENCES public.racks(id);


--
-- Name: thermal_observations thermal_observations_analysis_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.thermal_observations
    ADD CONSTRAINT thermal_observations_analysis_run_id_fkey FOREIGN KEY (analysis_run_id) REFERENCES public.analysis_runs(id);


--
-- Name: thermal_observations thermal_observations_plant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.thermal_observations
    ADD CONSTRAINT thermal_observations_plant_id_fkey FOREIGN KEY (plant_id) REFERENCES public.plants(id);


--
-- Name: thermal_observations thermal_observations_sensor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.thermal_observations
    ADD CONSTRAINT thermal_observations_sensor_id_fkey FOREIGN KEY (sensor_id) REFERENCES public.sensors(id);


--
-- Name: trait_observations trait_observations_analysis_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trait_observations
    ADD CONSTRAINT trait_observations_analysis_run_id_fkey FOREIGN KEY (analysis_run_id) REFERENCES public.analysis_runs(id);


--
-- Name: trait_observations trait_observations_plant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trait_observations
    ADD CONSTRAINT trait_observations_plant_id_fkey FOREIGN KEY (plant_id) REFERENCES public.plants(id);


--
-- Name: trait_observations trait_observations_sensor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trait_observations
    ADD CONSTRAINT trait_observations_sensor_id_fkey FOREIGN KEY (sensor_id) REFERENCES public.sensors(id);


--
-- PostgreSQL database dump complete
--

\unrestrict T4IH9UQFokPg4uh3vsu7W6dXUZHxAi7hCYRnlu1tgvQQ2YiTm7MviFvezBATm5r

