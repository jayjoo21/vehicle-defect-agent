"""POST /api/notify/{base_model} — 구독 차종의 현재 시그널 상태를 Slack Incoming Webhook으로
수동 발송(발표 시연용). SLACK_WEBHOOK_URL 환경변수(webapp/.env, env_config.load_env()가
os.environ에 적재)가 없으면 발송하지 않고 "미설정" 응답을 200으로 반환한다 — 키가 없는
것은 이 프로젝트에서 에러가 아니라 정상 폴백(llm/adapter.py의 mock 모드와 같은 원칙).

메시지에 실리는 상태·건수·리콜 캠페인은 전부 기존 DB 조회값(signals.py의 _build_cards와
동일 로직) — 지어낸 값 없음. "결함 확정" 표현 금지 원칙에 따라 미검증 소비자 신고 기반
고지문을 항상 포함한다.
"""
import os
import sys
from pathlib import Path

import requests
from fastapi import APIRouter, Depends

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_db
from engine.normalize import normalize_model
from routers.signals import _build_cards, _recall_dates_by_model

router = APIRouter(prefix="/notify", tags=["notify"])

STATE_LABEL_KO = {
    "new": "이력 없음",
    "rising": "신고 증가",
    "active": "활성 시그널",
    "recalled": "리콜 진행 중",
}

DISCLAIMER = "본 알림은 NHTSA·국토부 공개 신고 데이터 기반이며, 미검증 소비자 신고를 포함합니다. 결함 확정이 아닙니다."


@router.post("/{base_model}")
def notify(base_model: str, conn=Depends(get_db)):
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return {"sent": False, "reason": "not_configured"}

    model = normalize_model(base_model)
    latest_month = conn.execute("SELECT MAX(month) FROM signals").fetchone()[0]
    recall_dates_by_model = _recall_dates_by_model(conn)
    cards = {c["model"]: c for c in _build_cards(conn, latest_month, recall_dates_by_model)}
    card = cards.get(model)

    top_recall = conn.execute(
        "SELECT campaign, report_date FROM recalls WHERE model = ? AND country = 'US' ORDER BY report_date DESC LIMIT 1",
        (model,),
    ).fetchone()

    state = card["state"] if card else "new"
    recent_count = card["recent_count"] if card else 0
    lines = [
        f"*{model}* 시그널 알림",
        f"현재 상태: {STATE_LABEL_KO.get(state, state)}",
        f"최근 신고 건수: {recent_count}건",
    ]
    if card and card.get("top_symptom"):
        lines.append(f"대표 증상: {card['top_symptom']}")
    if top_recall:
        lines.append(f"관련 리콜 캠페인: {top_recall['campaign']} (접수 {top_recall['report_date']})")
    lines.append(f"_{DISCLAIMER}_")

    resp = requests.post(webhook_url, json={"text": "\n".join(lines)}, timeout=5)
    if resp.status_code == 200:
        return {"sent": True}
    return {"sent": False, "reason": "slack_error", "status_code": resp.status_code}
