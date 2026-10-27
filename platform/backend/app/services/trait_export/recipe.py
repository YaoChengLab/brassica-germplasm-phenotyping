"""The single definition of the trait-sampling recipe.

The platform's job ends at "get traceable data out": growth-model fitting, batch
correction and statistical testing live in the downstream analysis scripts, not
here. What the platform *must* do is state exactly which frames a value came
from, because that choice is not recoverable from the numbers afterwards.

A table of static trait values that records only `n_frames_sampled = 4` is the
cautionary example: the values are means of four images, but which days, and which
image within each day, cannot be recovered from the table.

So every knob here is explicit, and every export carries the resolved recipe plus
the DAS and frame counts actually hit — see `manifest()` in the router.

Recipes are shared: the cultivar page's signature-trait table and the CSV export
resolve the same `Recipe`, so a number on the page is the number in the file.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Dict, List, Optional, Sequence

from ...models.phenotype import RaspiObservation

# Columns of trait_observations that identify or annotate a row rather than
# measure the plant. Everything else is an exportable trait.
# File-level provenance (pipeline version, extractor hash) lives in analysis_runs.
NON_TRAIT_COLUMNS = {
    "id", "plant_id", "sensor_id", "observation_timestamp", "day_after_sewing",
    "image_file", "qc_status", "pipeline_version", "analysis_run_id",
}

TRAIT_COLUMNS: List[str] = [
    c.name for c in RaspiObservation.__table__.columns if c.name not in NON_TRAIT_COLUMNS
]

# Shown first in the picker and used as the cultivar page's signature set.
SIGNATURE_TRAITS = [
    "leaf_count", "leaf_area", "circularity_2", "anthocyanin_chroma_basic", "glcm_contrast",
]

# Groups for the export picker. A hundred-plus flat checkboxes are unusable, and the grouping
# belongs next to the trait list rather than in the UI: the deprecation and alias
# notes below are statements about the data, not about how it is displayed.
# `categories()` guarantees every exportable column appears exactly once.
_CATEGORIES = {
    "Leaf count & area": [
        "leaf_count", "leaf_area", "area_pixels", "bounding_box_area", "perimeter_pixels",
        "convex_hull_area_pixels", "convex_hull_perimeter", "extent",
    ],
    "Plant dimensions": ["plant_height", "plant_width", "equivalent_diameter"],
    "Shape": [
        "solidity", "circularity_1", "circularity_2", "canopy_porosity", "eccentricity",
        "eccentricity_eigenvalue_ratio", "radial_symmetry", "multiscale_straightness",
        "combined_simple_connectivity", "fuzzy_rectangularity", "sift_keypoint_count",
    ],
    "Ellipse fit": [
        "major_axis_length", "minor_axis_length", "ellipse_aspect_ratio",
        "ellipse_center_x", "ellipse_center_y", "ellipse_angle_degrees",
    ],
    "Radius from centroid": [
        "min_radius_from_centroid", "std_radius_from_centroid",
    ],
    "Colour channels & ratios": [
        "red_channel", "green_channel", "blue_channel",
        "red_green_ratio", "blue_green_ratio", "blue_red_ratio",
        "strength_of_red", "strength_of_green", "strength_of_blue",
    ],
    "Colour indices": [
        "excess_green_index", "excess_green_minus_red", "excess_red_index", "green_index",
        "green_leaf_index", "green_difference", "green_difference_variant", "greenness",
    ],
    "Hue, chroma & brightness": [
        "hue", "saturation", "lightness", "chroma", "chroma_prime", "brightness",
        "anthocyanin_chroma_basic", "anthocyanin_chroma_difference", "anthocyanin_chroma_ratio",
    ],
    "Vegetation indices": [
        "cive", "dgci", "mgrvi", "ndyi", "ngrdi", "rgbvi",
        "triangular_greenness_index", "vari", "veg", "vegetation_index_2",
    ],
    "Channel distribution": [
        "skewness_r", "skewness_g", "skewness_b", "skewness_y",
        "kurtosis_r", "kurtosis_g", "kurtosis_b", "kurtosis_y",
        "colour_distribution_modes", "spectral_distribution_modes",
        "num_unique_colours", "pixel_entropy",
    ],
    "GLCM texture": [c for c in TRAIT_COLUMNS if c.startswith("glcm_")],
    "Other texture": ["hog_mean", "hog_std", "log_mean", "log_std"],
}

# Superseded columns that are still exportable, mapped to what to use instead.
# The picker surfaces these hints; the API contract keeps the key even when empty.
#
# Currently empty: the former members (compactness, roundness,
# gap_fraction_canopy_porosity) are no longer stored.
DEPRECATED_TRAITS: Dict[str, str] = {}

# Two columns holding the same measurement (they can differ only where an empty mask
# is NULL in one and 0.0 in the other). Listed so the picker does not offer them as
# two independent traits.
TRAIT_ALIASES = {
    "area_pixels": {
        "same_as": "leaf_area",
        "note": "Duplicate column of leaf_area (identical values; differs only in how an "
                "empty mask is stored: NULL here, 0.0 there). Pick one.",
    },
}


def categories() -> "dict[str, List[str]]":
    """Category -> columns, with anything unlisted collected under "Other" so a
    new model column shows up in the picker instead of silently disappearing."""
    known = {c for cols in _CATEGORIES.values() for c in cols}
    out = {name: [c for c in cols if c in set(TRAIT_COLUMNS)] for name, cols in _CATEGORIES.items()}
    leftover = [c for c in TRAIT_COLUMNS if c not in known]
    if leftover:
        out["Other"] = leftover
    return out

# Traits the platform cannot export because they are not per-frame measurements:
# they are fitted or differentiated over a whole trajectory by the downstream
# scripts (Gompertz asymptote, emergence rate, solidity dynamics, …) and no such
# column exists in trait_observations. Listed so the UI can say so out loud
# instead of the user wondering why the master table has 19 more columns.
DOWNSTREAM_ONLY_TRAITS = [
    "das_ref", "bolt_das", "emg_rate", "area_rate", "rgr_slope", "area_ref", "count_ref",
    "A", "t_inf", "agr_max", "rgr50", "fit_r2", "fit_valid", "area_plateau_ratio",
    "sol_trough_das", "sol_peak", "sol_rise", "sol_t50_close", "sol_onset_das",
    "sol_max_rate", "circ_peak", "circ_rise", "circ_onset",
]

QC_CORRECT = ("auto", "verified")

DAY_MODES = ("tail", "list", "range", "dates", "all")
FRAME_PICKS = ("nearest_hour", "all", "first", "last")
LEVELS = ("frame", "day", "plant", "cultivar")


@dataclass
class Recipe:
    """Which frames go into a value, and how far they are merged."""

    # --- which days -------------------------------------------------------
    day_mode: str = "tail"          # tail | list | range | all
    n_days: int = 4                 # tail: how many imaging days, counted back
    das_list: Optional[List[int]] = None   # list: exact DAS values
    das_from: Optional[int] = None   # range: DAS bounds
    das_to: Optional[int] = None
    date_from: Optional[date] = None  # dates: calendar bounds on the imaging date
    date_to: Optional[date] = None

    # --- which frame within a day ----------------------------------------
    frame_pick: str = "nearest_hour"   # nearest_hour | all | first | last
    pick_hour: float = 14.0            # local hour targeted by nearest_hour
    require_leaves: bool = True        # skip frames with no retained leaf

    # --- what counts, and how far to merge -------------------------------
    qc_status: Sequence[str] = QC_CORRECT
    level: str = "plant"               # frame | day | plant | cultivar
    traits: List[str] = field(default_factory=lambda: list(SIGNATURE_TRAITS))

    # --- thermal time -----------------------------------------------------
    # GDD is not a stored column: it is walked per plant through
    # plant_positions over the chamber's daily environment records, so it
    # is attached after the SQL rather than joined in it.
    include_gdd: bool = True
    gdd_anchor: str = "G120"           # chamber whose entry day is GDD = 0

    def validate(self) -> None:
        if self.day_mode not in DAY_MODES:
            raise ValueError(f"day_mode must be one of {DAY_MODES}")
        if self.frame_pick not in FRAME_PICKS:
            raise ValueError(f"frame_pick must be one of {FRAME_PICKS}")
        if self.level not in LEVELS:
            raise ValueError(f"level must be one of {LEVELS}")
        if self.day_mode == "tail" and not (1 <= int(self.n_days) <= 400):
            raise ValueError("n_days must be between 1 and 400")
        if self.day_mode == "list" and not self.das_list:
            raise ValueError("day_mode=list needs das_list")
        if self.day_mode == "range" and (self.das_from is None or self.das_to is None):
            raise ValueError("day_mode=range needs das_from and das_to")
        if self.day_mode == "range" and self.das_from > self.das_to:
            raise ValueError("das_from must be <= das_to")
        if self.day_mode == "dates" and (self.date_from is None or self.date_to is None):
            raise ValueError("day_mode=dates needs date_from and date_to")
        if self.day_mode == "dates" and self.date_from > self.date_to:
            raise ValueError("date_from must be <= date_to")
        if not 0 <= float(self.pick_hour) <= 24:
            raise ValueError("pick_hour must be between 0 and 24")
        bad_qc = [q for q in self.qc_status if q not in ("auto", "verified", "no")]
        if bad_qc:
            raise ValueError(f"unknown qc_status: {bad_qc}")
        if not self.qc_status:
            raise ValueError("qc_status must not be empty")
        unknown = [t for t in self.traits if t not in TRAIT_COLUMNS]
        if unknown:
            downstream = [t for t in unknown if t in DOWNSTREAM_ONLY_TRAITS]
            if downstream:
                raise ValueError(
                    f"{downstream} are fitted over a whole trajectory by the downstream "
                    "analysis scripts and are not stored per single-plant image — the platform cannot "
                    "export them. Export the per-day series (level=day) and fit them there."
                )
            raise ValueError(f"unknown traits: {unknown}")
        if not self.traits:
            raise ValueError("traits must not be empty")

    # Human-readable one-liner, reused in the manifest and the UI caption so the
    # sampling recipe travels with the numbers. Kept ASCII on purpose: it is also
    # sent as an HTTP response header, and headers are latin-1 only — an en dash
    # here used to 500 the whole download.
    def describe(self) -> str:
        if self.day_mode == "tail":
            days = f"the last {self.n_days} imaging day(s) of each plant"
        elif self.day_mode == "list":
            days = "DAS " + "/".join(str(d) for d in (self.das_list or []))
        elif self.day_mode == "range":
            days = f"DAS {self.das_from}-{self.das_to}"
        elif self.day_mode == "dates":
            days = f"imaging dates {self.date_from} to {self.date_to}"
        else:
            days = "every imaging day"
        if self.frame_pick == "nearest_hour":
            frames = f"one single-plant image per day, nearest {self.pick_hour:g}:00"
        elif self.frame_pick == "all":
            frames = "every single-plant image of those days"
        else:
            frames = f"the {self.frame_pick} single-plant image of each day"
        merge = {
            "frame": "no averaging (one row per single-plant image)",
            "day": "averaged per plant-day",
            "plant": "averaged per plant-day, then across days",
            "cultivar": "averaged per plant, then mean ± SD across replicates",
        }[self.level]
        leaves = "; single-plant images with no retained leaf skipped" if self.require_leaves else ""
        gdd = f"; GDD aligned on {self.gdd_anchor} entry" if self.include_gdd else ""
        return f"{days}; {frames}; {merge}; QC {'/'.join(self.qc_status)}{leaves}{gdd}"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["qc_status"] = list(self.qc_status)
        d["date_from"] = self.date_from.isoformat() if self.date_from else None
        d["date_to"] = self.date_to.isoformat() if self.date_to else None
        d["description"] = self.describe()
        return d


# Named recipes. `default` is the platform default.
PRESETS = {
    "default": Recipe(),
    "daily_series": Recipe(day_mode="all", frame_pick="all", level="day"),
    "every_frame": Recipe(day_mode="all", frame_pick="all", level="frame"),
}

PRESET_NOTES = {
    "default": "Last 4 imaging days, the single-plant image nearest 14:00, averaged per plant.",
    "daily_series": "Every imaging day, every single-plant image, averaged per plant-day — the input for downstream growth fitting.",
    "every_frame": "One row per single-plant image, nothing averaged.",
}
