"""GET/POST/DELETE /api/subscriptions — 일반 사용자(role='user') 차종 구독.

구독 자체는 subscriptions 테이블(account+base_model, seed.py가 채우지 않는 런타임 전용
테이블)에 저장한다. 시그널 상태는 새로 계산하지 않고 signals.py의 _build_cards()(대시보드
카드와 동일한 에피소드 상태 규칙)를 그대로 재사용해 구독 목록과 대시보드가 항상 같은
상태값을 보여주게 한다.

계정 인증 자체는 auth.py의 데모 로그인일 뿐 — 여기서는 account 문자열이 유효한 test
계정인지 재검증하지 않는다(프론트가 로그인 후에만 이 API를 호출하는 구조, v0 범위).
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_db
from engine.normalize import normalize_model
from routers.signals import _build_cards, _recall_dates_by_model

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


def _cards_by_model(conn) -> dict[str, dict]:
    latest_month = conn.execute("SELECT MAX(month) FROM signals").fetchone()[0]
    recall_dates_by_model = _recall_dates_by_model(conn)
    cards = _build_cards(conn, latest_month, recall_dates_by_model)
    return {c["model"]: c for c in cards}


@router.get("")
def list_subscriptions(account: str, conn=Depends(get_db)):
    rows = conn.execute(
        "SELECT base_model, created_at FROM subscriptions WHERE account = ? ORDER BY created_at DESC",
        (account.strip().lower(),),
    ).fetchall()
    cards = _cards_by_model(conn)

    out = []
    for r in rows:
        card = cards.get(r["base_model"])
        out.append(
            {
                "model": r["base_model"],
                "created_at": r["created_at"],
                # 아직 signals 데이터가 전혀 없는 base_model(이론상 없음, 방어적 처리)이면
                # 이력 없음으로 정직하게 표시 — 지어낸 상태를 만들지 않는다.
                "id": card["id"] if card else None,
                "state": card["state"] if card else "new",
                "top_symptom": card["top_symptom"] if card else None,
                "recent_count": card["recent_count"] if card else 0,
            }
        )
    return {"subscriptions": out}


@router.post("")
async def subscribe(request: Request, conn=Depends(get_db)):
    payload = await request.json()
    account = str(payload.get("account", "")).strip().lower()
    base_model = normalize_model(str(payload.get("base_model", "")))
    conn.execute(
        "INSERT OR IGNORE INTO subscriptions (account, base_model, created_at) VALUES (?, ?, ?)",
        (account, base_model, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return {"subscribed": True, "model": base_model}


@router.delete("")
async def unsubscribe(request: Request, conn=Depends(get_db)):
    payload = await request.json()
    account = str(payload.get("account", "")).strip().lower()
    base_model = normalize_model(str(payload.get("base_model", "")))
    conn.execute(
        "DELETE FROM subscriptions WHERE account = ? AND base_model = ?", (account, base_model)
    )
    conn.commit()
    return {"subscribed": False, "model": base_model}
