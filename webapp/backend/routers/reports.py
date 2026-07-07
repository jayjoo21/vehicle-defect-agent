"""GET /api/reports/{id}. 2단계에서 구현."""
from fastapi import APIRouter

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{report_id}")
def get_report(report_id: int):
    raise NotImplementedError("2단계에서 구현")
