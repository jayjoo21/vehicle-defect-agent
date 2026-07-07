"""GET /api/summary, /api/signals, /api/signals/{id}, /api/heatmap, /api/gap. 2단계에서 구현."""
from fastapi import APIRouter

router = APIRouter(tags=["signals"])


@router.get("/summary")
def get_summary():
    raise NotImplementedError("2단계에서 구현")


@router.get("/signals")
def list_signals(state: str | None = None, model: str | None = None):
    raise NotImplementedError("2단계에서 구현")


@router.get("/signals/{signal_id}")
def get_signal(signal_id: int):
    raise NotImplementedError("2단계에서 구현")


@router.get("/heatmap")
def get_heatmap():
    raise NotImplementedError("2단계에서 구현")


@router.get("/gap")
def get_gap():
    raise NotImplementedError("2단계에서 구현")
