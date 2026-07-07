"""GET /api/vehicles/{model}/{year}/map, /api/vehicles/{model}/history. 2단계에서 구현."""
from fastapi import APIRouter

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get("/{model}/{year}/map")
def get_vehicle_map(model: str, year: str):
    raise NotImplementedError("2단계에서 구현")


@router.get("/{model}/history")
def get_vehicle_history(model: str):
    raise NotImplementedError("2단계에서 구현")
