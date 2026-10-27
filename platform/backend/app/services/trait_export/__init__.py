"""Structured trait export — the platform's hand-off point to downstream analysis."""
from .recipe import (
    Recipe, PRESETS, PRESET_NOTES, TRAIT_COLUMNS, SIGNATURE_TRAITS,
    DOWNSTREAM_ONLY_TRAITS, DEPRECATED_TRAITS, TRAIT_ALIASES, QC_CORRECT, categories,
)
from .query import (
    Scope, Selection, build_sql, coverage, count_rows, fetch, scope_hits, selection_where,
    MAX_ROWS, MAX_SCOPES, KEY_COLUMNS,
)
from . import environment, gdd

__all__ = [
    "Recipe", "PRESETS", "PRESET_NOTES", "TRAIT_COLUMNS", "SIGNATURE_TRAITS",
    "DOWNSTREAM_ONLY_TRAITS", "DEPRECATED_TRAITS", "TRAIT_ALIASES", "QC_CORRECT",
    "categories", "Scope", "Selection", "build_sql", "coverage", "count_rows", "fetch",
    "scope_hits", "selection_where", "MAX_ROWS", "MAX_SCOPES", "KEY_COLUMNS",
    "gdd", "environment",
]
