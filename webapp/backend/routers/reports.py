"""GET /api/reports/{id}."""
import json
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_db
from routers.chat import _campaign_parts  # NHTSA 원문 pdf_url 조회 — chat.py와 동일 로직 재사용

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{report_id}")
def get_report(report_id: int, conn=Depends(get_db)):
    row = conn.execute(
        """SELECT id, signal_id, title, markdown, created_at, model, campaign, reference_month, state, metrics
           FROM reports WHERE id = ?""",
        (report_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="report not found")
    data = dict(row)
    data["metrics"] = json.loads(data["metrics"]) if data["metrics"] else None
    # data["campaign"]은 "24V200000·24V867000"처럼 "·"로 여러 캠페인이 합쳐진 문자열일 수 있음
    # (chat.py의 iccu_campaigns 조인 규칙과 동일). NHTSA 원문 링크(pdf_url)가 있는 캠페인만
    # _campaign_parts가 반환하므로, 데이터 없는 캠페인은 자연히 빠짐(지어낸 링크 없음).
    campaigns = data["campaign"].split("·") if data["campaign"] else []
    data["parts"] = _campaign_parts(conn, campaigns)
    return data
