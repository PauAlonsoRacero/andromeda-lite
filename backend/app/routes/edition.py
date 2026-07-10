"""
edition.py — Endpoints de edición (Lite/Pro) y catálogo de features.

  GET /api/edition           → edición activa + mapa de features
  GET /api/edition/catalog   → comparativa Lite vs Pro (para la UI de planes)
  GET /api/edition/feature/{key} → ¿está activa una feature concreta?
"""
from fastapi import APIRouter

from app.editions import get_edition_info, catalog, feature_enabled

router = APIRouter()


@router.get("")
async def edition():
    info = get_edition_info()
    return {
        "edition": info.edition,
        "label": info.label,
        "is_pro": info.is_pro,
        "features": info.features,
        "license_holder": info.license_holder,
        "license_valid": info.license_valid,
    }


@router.get("/catalog")
async def edition_catalog():
    return {"features": catalog()}


@router.get("/feature/{key}")
async def edition_feature(key: str):
    return {"key": key, "enabled": feature_enabled(key)}
