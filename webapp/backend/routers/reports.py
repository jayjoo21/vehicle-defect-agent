"""GET /api/reports/{id}."""
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_db

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{report_id}")
def get_report(report_id: int, conn=Depends(get_db)):
    row = conn.execute(
        "SELECT id, signal_id, title, markdown, created_at FROM reports WHERE id = ?", (report_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="report not found")
    return dict(row)
