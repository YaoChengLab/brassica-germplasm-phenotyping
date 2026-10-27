from fastapi import APIRouter
from .endpoints import admin_batches_router
# Every router is mounted under /api/v1. The query, plant-view and export routers live in
# api/v2/endpoints; the v1 services remain as base classes of the v2 services.
from ..v2.endpoints import query_router, plant_view_router, export_traits_router
from ...config.settings import settings

api_router = APIRouter()


@api_router.get("/config", tags=["Config"])
def client_config():
    """Non-sensitive client capability flags. management_enabled is false when
    ENVIRONMENT=production (browse and export only, no batch registration)."""
    return {"environment": settings.environment, "management_enabled": settings.management_enabled}


api_router.include_router(query_router.router, prefix="/query", tags=["Query"])
api_router.include_router(plant_view_router.router, prefix="/plant-view", tags=["Plant View"])
# Structured trait export (recipe-driven, manifest-backed) — the hand-off to the
# downstream analysis scripts.
api_router.include_router(export_traits_router.router, prefix="/export", tags=["Export"])

# The batch registration API (batches, coordinates) is mounted only when management is
# enabled. With ENVIRONMENT=production these endpoints do not exist, so the database
# cannot be changed through the web interface.
if settings.management_enabled:
    api_router.include_router(admin_batches_router.router, prefix="/admin", tags=["Admin Batches"])
