"""GET /api/summary, /api/signals, /api/signals/{id}, /api/heatmap, /api/gap."""
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_db
from engine.normalize import normalize_model
from engine.state import STATE_PRIORITY, top_state

router = APIRouter(tags=["signals"])

HEATMAP_MONTHS = 24
CARD_SPARKLINE_MONTHS = 6


@router.get("/summary")
def get_summary(conn=Depends(get_db)):
    watched_models = conn.execute("SELECT COUNT(DISTINCT model) FROM signals").fetchone()[0]
    latest_month = conn.execute("SELECT MAX(month) FROM signals").fetchone()[0]
    active_now = conn.execute(
        "SELECT COUNT(*) FROM signals WHERE month = ? AND state = 'active'", (latest_month,)
    ).fetchone()[0]
    prev_month = str(pd.Period(latest_month, freq="M") - 1)
    new_alarms = conn.execute(
        """SELECT COUNT(*) FROM signals cur
           WHERE cur.month = ? AND cur.state = 'active'
           AND NOT EXISTS (
             SELECT 1 FROM signals prev
             WHERE prev.model = cur.model AND prev.month = ? AND prev.state = 'active'
           )""",
        (latest_month, prev_month),
    ).fetchone()[0]
    us_unremediated = conn.execute(
        "SELECT COUNT(*) FROM kr_us_gap WHERE us_date IS NOT NULL AND kr_start_date IS NULL"
    ).fetchone()[0]
    return {
        "watched_models": watched_models,
        "active_signals": active_now,
        "new_alarms_this_week": new_alarms,
        "us_recalled_kr_unremediated": us_unremediated,
        "data_as_of_month": latest_month,
        "note": "new_alarms_this_week은 월 단위 데이터의 근사치입니다 (주간 데이터 없음).",
    }


@router.get("/signals")
def list_signals(state: str | None = None, model: str | None = None, conn=Depends(get_db)):
    latest_month = conn.execute("SELECT MAX(month) FROM signals").fetchone()[0]
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
        card_state = top_state([r["state"] for r in latest_rows])
        count_sum = sum(r["count"] for r in latest_rows)
        top_symptom = next((r["top_symptom"] for r in latest_rows if r["top_symptom"]), None)
        report_id = next((r["report_id"] for r in latest_rows if r["report_id"]), None)

        months_sorted = sorted({r["month"] for r in rows})[-CARD_SPARKLINE_MONTHS:]
        sparkline = []
        for m in months_sorted:
            sparkline.append(sum(r["count"] for r in rows if r["month"] == m))

        cards.append(
            {
                "model": base_model,
                "state": card_state,
                "top_symptom": top_symptom,
                "recent_count": count_sum,
                "sparkline": sparkline,
                "month": latest_month,
                "report_id": report_id,
            }
        )

    if state:
        cards = [c for c in cards if c["state"] == state]
    if model:
        cards = [c for c in cards if c["model"] == normalize_model(model)]

    cards.sort(key=lambda c: STATE_PRIORITY[c["state"]], reverse=True)
    return {"signals": cards, "month": latest_month}


@router.get("/signals/{signal_id}")
def get_signal(signal_id: int, conn=Depends(get_db)):
    row = conn.execute(
        "SELECT id, model, month, count, baseline, state, top_symptom, report_id FROM signals WHERE id = ?",
        (signal_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="signal not found")
    states = conn.execute(
        "SELECT state, changed_at FROM signal_states WHERE signal_id = ? ORDER BY changed_at", (signal_id,)
    ).fetchall()
    return {
        "id": row["id"],
        "model": row["model"],
        "month": row["month"],
        "count": row["count"],
        "baseline": row["baseline"],
        "state": row["state"],
        "top_symptom": row["top_symptom"],
        "report_id": row["report_id"],
        "lifecycle": [dict(s) for s in states],
    }


@router.get("/heatmap")
def get_heatmap(conn=Depends(get_db)):
    all_rows = conn.execute("SELECT model, month, count, state FROM signals").fetchall()

    by_base_month: dict[tuple, dict] = defaultdict(lambda: {"count": 0, "alarm": False})
    totals: dict[str, int] = defaultdict(int)
    for r in all_rows:
        base = normalize_model(r["model"])
        key = (base, r["month"])
        by_base_month[key]["count"] += r["count"]
        if r["state"] == "active":
            by_base_month[key]["alarm"] = True
        totals[base] += r["count"]

    all_months = sorted({m for (_, m) in by_base_month})
    recent_months = all_months[-HEATMAP_MONTHS:]
    top_models = [m for m, _ in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:20]]

    cells = []
    for model_name in top_models:
        for month in recent_months:
            cell = by_base_month.get((model_name, month), {"count": 0, "alarm": False})
            cells.append({"model": model_name, "month": month, "count": cell["count"], "alarm": cell["alarm"]})

    return {"models": top_models, "months": recent_months, "cells": cells}


@router.get("/gap")
def get_gap(conn=Depends(get_db)):
    rows = conn.execute(
        "SELECT id, campaign, us_date, kr_date, kr_start_date, gap_days, note FROM kr_us_gap ORDER BY kr_date"
    ).fetchall()
    return {"gap": [dict(r) for r in rows]}
