"""
v2 Query response schemas with fields support and new endpoints.
"""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, date


# ---------------------------------------------------------------------------
# Cultivar summary (lightweight list)
# ---------------------------------------------------------------------------

class CultivarSummaryItem(BaseModel):
    id: int
    cultivar_code: str
    product_name: Optional[str] = None

    class Config:
        from_attributes = True


class CultivarSummaryResponse(BaseModel):
    total_count: int
    data: List[CultivarSummaryItem]


# ---------------------------------------------------------------------------
# Paginated v2 response wrapper
# ---------------------------------------------------------------------------

class PaginatedResponseV2(BaseModel):
    """Generic paginated response."""
    total_count: int
    limit: int
    offset: int
    data: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Batches with cultivars (admin batch list + cultivar comparison)
# ---------------------------------------------------------------------------

class BatchCultivarItem(BaseModel):
    id: int
    cultivar_code: str
    product_name: Optional[str] = None
    plant_count: int
    imaged_plant_count: int = 0  # plants with at least one trait observation


class BatchWithCultivarsItem(BaseModel):
    batch_code: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    # Retained for backward compatibility with earlier consumers.
    batch_start_date: Optional[str] = None
    plant_count: int
    imaged_plant_count: int = 0  # plants with at least one trait observation
    cultivar_count: int
    cultivars: List[BatchCultivarItem]


class BatchesWithCultivarsResponse(BaseModel):
    batches: List[BatchWithCultivarsItem]
