"""
v2 shared dependencies: field selection, pagination guards, cache control.
"""

from typing import List, Optional, Set
from fastapi import Query as QueryParam, HTTPException
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Field selection
# ---------------------------------------------------------------------------

# Observation models and their valid column names (populated lazily)
_VALID_FIELDS_CACHE: dict = {}


def _get_valid_fields(model) -> Set[str]:
    """Return the set of column names for *model*, cached after first call."""
    key = model.__tablename__
    if key not in _VALID_FIELDS_CACHE:
        _VALID_FIELDS_CACHE[key] = {c.name for c in model.__table__.columns}
    return _VALID_FIELDS_CACHE[key]


def parse_fields(
    fields: Optional[str] = QueryParam(
        None,
        description="Comma-separated list of fields to include (e.g. ?fields=leaf_area,weight). "
                    "If omitted, all fields are returned.",
    ),
) -> Optional[List[str]]:
    """
    Parse ``?fields=a,b,c`` into a validated list.

    Returns ``None`` when no field filter is requested (= return all fields).
    """
    if not fields:
        return None
    parsed = [f.strip() for f in fields.split(",") if f.strip()]
    if not parsed:
        return None
    return parsed


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class PaginationParams:
    """
    Dependency that enforces pagination on every v2 list endpoint.

    Usage::

        @router.get("/items")
        async def list_items(page: PaginationParams = Depends()):
            ...
            query.offset(page.offset).limit(page.limit)
    """

    MAX_LIMIT = 5000  # absolute ceiling

    def __init__(
        self,
        limit: int = QueryParam(
            default=500,
            ge=1,
            le=5000,
            description="Number of results to return (max 5000)",
        ),
        offset: int = QueryParam(
            default=0,
            ge=0,
            description="Number of results to skip",
        ),
    ):
        self.limit = min(limit, self.MAX_LIMIT)
        self.offset = offset
