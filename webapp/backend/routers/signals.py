"""GET /api/summary, /api/signals, /api/signals/{id}, /api/heatmap, /api/gap."""
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_db
from engine.episode import DASHBOARD_PRIORITY, RECALL_RECENT_WINDOW_DAYS, aggregate_by_month, derive_episode_state
from engine.normalize import normalize_model
from engine.text import clean_quote

router = APIRouter(tags=["signals"])

HEATMAP_MONTHS = 12
CARD_SPARKLINE_MONTHS = 6


def _recall_dates_by_model(conn) -> dict:
    rows = conn.execute("SELECT model, report_date FROM recalls WHERE country = 'US'").fetchall()
    lookup: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        lookup[r["model"]].append(r["report_date"])
    return lookup


def _recall_recent(recall_dates: list[str], reference_month: str) -> bool:
    """이 base_model의 'recalled' 판정을 만든 리콜 중 기준월 기준 최근 90일 이내 접수건이 있는지.
    '주목 필요' 탭(대시보드 5.5단계)이 이미 대응 중인 오래된 리콜까지 계속 띄우지 않도록 쓰인다."""
    ref_end = pd.Period(reference_month, freq="M").end_time
    for us_date in recall_dates:
        us_ts = pd.Timestamp(us_date)
        if us_ts <= ref_end and (ref_end - us_ts).days <= RECALL_RECENT_WINDOW_DAYS:
            return True
    return False


def _representative_quote(conn, base_model: str) -> dict | None:
    rows = conn.execute("SELECT odino, model, date, text FROM complaints WHERE text != ''").fetchall()
    matching = [r for r in rows if normalize_model(r["model"]) == base_model]
    if not matching:
        return None
    latest = max(matching, key=lambda r: r["date"])
    return {"odino": latest["odino"], "text": clean_quote(latest["text"])}


def _build_cards(conn, latest_month: str, recall_dates_by_model: dict) -> list[dict]:
    all_rows = conn.execute(
        "SELECT id, model, month, count, baseline, state, top_symptom, report_id FROM signals"
    ).fetchall()

    by_base: dict[str, list] = defaultdict(list)
    for r in all_rows:
        by_base[normalize_model(r["model"])].append(r)

    cards = []
    for base_model, rows in by_base.items():
        latest_rows = [r for r in rows if r["month"] == latest_month]
        if not latest_rows:
            continue
        by_month = aggregate_by_month(rows)
        recall_dates = recall_dates_by_model.get(base_model, [])
        card_state = derive_episode_state(by_month, latest_month, recall_dates)
        count_sum = sum(r["count"] for r in latest_rows)
        top_symptom = next((r["top_symptom"] for r in latest_rows if r["top_symptom"]), None)
        # report_id는 latest_rows(최신월)가 아니라 base_model 전체 이력에서 찾는다 — EV9 리포트는
        # 스파이크가 발생한 2024-09 행에 연결돼 있어 latest_month(2026-06) 행만 보면 항상 None이었다.
        report_id = next((r["report_id"] for r in rows if r["report_id"]), None)

        months_sorted = sorted({r["month"] for r in rows})[-CARD_SPARKLINE_MONTHS:]
        sparkline = [sum(r["count"] for r in rows if r["month"] == m) for m in months_sorted]

        cards.append(
            {
                # 시그널 상세 페이지(/signals/:id) 진입용 — base_model당 대표 행 id 하나(최신월 행 중 하나).
                # 상세 페이지는 이 id로 base_model을 역산해 전체 이력을 다시 조회하므로 어떤 변형의
                # 행이든 무방하다.
                "id": latest_rows[0]["id"],
                "model": base_model,
                "state": card_state,
                "top_symptom": top_symptom,
                "recent_count": count_sum,
                "sparkline": sparkline,
                "month": latest_month,
                "report_id": report_id,
                "recall_recent": card_state == "recalled" and _recall_recent(recall_dates, latest_month),
            }
        )

    cards.sort(key=lambda c: DASHBOARD_PRIORITY[c["state"]], reverse=True)
    return cards


@router.get("/summary")
def get_summary(conn=Depends(get_db)):
    watched_models = conn.execute("SELECT COUNT(DISTINCT model) FROM signals").fetchone()[0]
    latest_month = conn.execute("SELECT MAX(month) FROM signals").fetchone()[0]
    prev_month = str(pd.Period(latest_month, freq="M") - 1)

    all_rows = conn.execute("SELECT model, month, count, baseline FROM signals").fetchall()
    by_base: dict[str, list] = defaultdict(list)
    for r in all_rows:
        by_base[normalize_model(r["model"])].append(r)
    recall_dates_by_model = _recall_dates_by_model(conn)

    active_now = 0
    new_alarms = 0
    for base_model, rows in by_base.items():
        by_month = aggregate_by_month(rows)
        recalls = recall_dates_by_model.get(base_model, [])
        cur_state = derive_episode_state(by_month, latest_month, recalls)
        if cur_state == "active":
            active_now += 1
            prev_state = derive_episode_state(by_month, prev_month, recalls)
            if prev_state != "active":
                new_alarms += 1

    us_unremediated = conn.execute(
        "SELECT COUNT(*) FROM kr_us_gap WHERE us_date IS NOT NULL AND kr_start_date IS NULL"
    ).fetchone()[0]

    # "오늘의 시그널" 히어로 카드 — DASHBOARD_PRIORITY(active>rising>recalled>new) 1순위 카드.
    # state가 'new'뿐이면(감지된 게 아무것도 없으면) 억지로 보여줄 게 없으므로 None.
    cards = _build_cards(conn, latest_month, recall_dates_by_model)
    hero = None
    if cards and cards[0]["state"] != "new":
        top = cards[0]
        hero = {**top, "quote": _representative_quote(conn, top["model"])}

    return {
        "watched_models": watched_models,
        "active_signals": active_now,
        "new_alarms_this_week": new_alarms,
        "us_recalled_kr_unremediated": us_unremediated,
        "data_as_of_month": latest_month,
        "hero": hero,
        "note": "new_alarms_this_week은 월 단위 데이터의 근사치입니다 (주간 데이터 없음). "
        "active/rising/recalled는 v0 잠정 에피소드 규칙(engine/episode.py)으로 계산됩니다. "
        "us_recalled_kr_unremediated는 한국 발표는 확인됐으나 시정 개시일이 기록되지 않은 건수이며, "
        "한국 발표 자체가 없는 경우는 포함하지 않습니다(현재 데이터 범위에는 그런 사례가 없음).",
    }


@router.get("/signals")
def list_signals(state: str | None = None, model: str | None = None, conn=Depends(get_db)):
    latest_month = conn.execute("SELECT MAX(month) FROM signals").fetchone()[0]
    recall_dates_by_model = _recall_dates_by_model(conn)
    cards = _build_cards(conn, latest_month, recall_dates_by_model)

    if state:
        cards = [c for c in cards if c["state"] == state]
    if model:
        cards = [c for c in cards if c["model"] == normalize_model(model)]

    return {"signals": cards, "month": latest_month}


@router.get("/signals/{signal_id}")
def get_signal(signal_id: int, conn=Depends(get_db)):
    """시그널 상세 + 생애 타임라인(스펙 5절-B). id는 base_model당 대표 행 하나를 가리키며,
    이 엔드포인트는 그 행에서 base_model을 역산해 전체 이력(모든 변형·모든 월)을 다시 모아
    돌려준다 — 어느 변형의 행을 클릭해도 같은 base_model 타임라인에 도달한다."""
    row = conn.execute(
        "SELECT id, model, month, count, baseline, state, top_symptom, report_id FROM signals WHERE id = ?",
        (signal_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="signal not found")
    base_model = normalize_model(row["model"])

    all_rows = conn.execute(
        "SELECT id, model, month, count, baseline, top_symptom, report_id FROM signals"
    ).fetchall()
    rows_for_model = [r for r in all_rows if normalize_model(r["model"]) == base_model]

    recall_dates_by_model = _recall_dates_by_model(conn)
    recall_dates = recall_dates_by_model.get(base_model, [])

    # 생애 타임라인: 대시보드 카드와 동일한 derive_episode_state를 월별로 반복 적용한다
    # (같은 함수를 재사용하므로 카드의 상태·색상과 항상 일치한다). 스펙 원문의 5색 예시(초록
    # "잠잠" 포함)는 대시보드 전역에서 쓰는 4상태(new/rising/active/recalled) 모델과 어긋나
    # 일부러 따르지 않았다 — 카드·핫스팟·탭 등 앱 전체와 일관된 상태만 사용한다.
    by_month = aggregate_by_month(rows_for_model)
    months_sorted = sorted(by_month)
    timeline = [
        {
            "month": m,
            "count": by_month[m]["count"],
            "baseline": by_month[m]["baseline"] or None,
            "state": derive_episode_state(by_month, m, recall_dates),
        }
        for m in months_sorted
    ]
    current_state = timeline[-1]["state"] if timeline else row["state"]

    recalls = conn.execute(
        "SELECT campaign, report_date, component, summary FROM recalls WHERE model = ? AND country = 'US' ORDER BY report_date",
        (base_model,),
    ).fetchall()

    kr_gap = conn.execute(
        """SELECT campaign, defect_summary, date_basis, us_date, kr_date, kr_start_date, gap_days
           FROM kr_us_gap WHERE model = ? ORDER BY us_date""",
        (base_model,),
    ).fetchall()

    top_symptom = next((r["top_symptom"] for r in rows_for_model if r["top_symptom"]), None)
    report_id = next((r["report_id"] for r in rows_for_model if r["report_id"]), None)

    states = conn.execute(
        "SELECT state, changed_at FROM signal_states WHERE signal_id = ? ORDER BY changed_at", (signal_id,)
    ).fetchall()

    return {
        "id": row["id"],
        "model": base_model,
        "month": row["month"],
        "count": row["count"],
        "baseline": row["baseline"],
        "state": current_state,
        "top_symptom": top_symptom,
        "report_id": report_id,
        "lifecycle": [dict(s) for s in states],
        "timeline": timeline,
        "recalls": [dict(r) for r in recalls],
        "kr_gap": [dict(r) for r in kr_gap],
    }


HEATMAP_MAX_MODELS = 12


@router.get("/heatmap")
def get_heatmap(conn=Depends(get_db)):
    all_rows = conn.execute("SELECT model, month, count, state FROM signals").fetchall()

    by_base_month: dict[tuple, dict] = defaultdict(lambda: {"count": 0, "alarm": False})
    totals: dict[str, int] = defaultdict(int)
    fired_models: set[str] = set()
    for r in all_rows:
        base = normalize_model(r["model"])
        key = (base, r["month"])
        by_base_month[key]["count"] += r["count"]
        if r["state"] == "active":
            by_base_month[key]["alarm"] = True
            fired_models.add(base)
        totals[base] += r["count"]

    all_months = sorted({m for (_, m) in by_base_month})
    recent_months = all_months[-HEATMAP_MONTHS:]

    # 발화(alarm) 이력이 한 번이라도 있는 차종만 — 조용한 차종을 채워 넣어 압축 취지를 해치지 않는다.
    top_models = [m for m, _ in sorted(totals.items(), key=lambda kv: kv[1], reverse=True) if m in fired_models][
        :HEATMAP_MAX_MODELS
    ]

    cells = []
    for model_name in top_models:
        for month in recent_months:
            cell = by_base_month.get((model_name, month), {"count": 0, "alarm": False})
            cells.append({"model": model_name, "month": month, "count": cell["count"], "alarm": cell["alarm"]})

    return {"models": top_models, "months": recent_months, "cells": cells}


GAP_WINDOW_DAYS = 365


@router.get("/gap")
def get_gap(conn=Depends(get_db)):
    rows = conn.execute(
        """SELECT id, campaign, model, defect_summary, date_basis, us_date, kr_date, kr_start_date, gap_days, note
           FROM kr_us_gap WHERE us_date IS NOT NULL AND kr_date IS NOT NULL"""
    ).fetchall()
    matched = [dict(r) for r in rows]

    in_range = [r for r in matched if r["gap_days"] is not None and abs(r["gap_days"]) <= GAP_WINDOW_DAYS]

    # 캠페인당 대표 1행만 남긴다 — 같은 캠페인이 여러 차종·보도자료에 중복 매칭된 경우
    # |gap_days|가 가장 작은(가장 확실한 매칭) 행을 대표로 채택 (id로 동률 결정, 재현 가능하게).
    best_by_campaign: dict[str, dict] = {}
    for r in in_range:
        cur = best_by_campaign.get(r["campaign"])
        if cur is None or (abs(r["gap_days"]), r["id"]) < (abs(cur["gap_days"]), cur["id"]):
            best_by_campaign[r["campaign"]] = r

    deduped = sorted(best_by_campaign.values(), key=lambda r: r["kr_date"], reverse=True)

    excluded_campaigns = {r["campaign"] for r in matched} - {r["campaign"] for r in deduped}
    return {
        "gap": deduped,
        "excluded_count": len(excluded_campaigns),
        "excluded_note": f"±{GAP_WINDOW_DAYS}일 초과 등으로 매칭 검증 필요 {len(excluded_campaigns)}건은 제외",
    }
