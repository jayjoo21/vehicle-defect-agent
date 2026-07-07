"""GET /api/vehicles/{model}/{year}/map, /api/vehicles/{model}/history."""
import sys
from pathlib import Path

from fastapi import APIRouter, Depends

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import get_db
from engine.domains import DOMAINS, classify_domain
from engine.normalize import normalize_model
from engine.state import top_state

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get("/{model}/{year}/map")
def get_vehicle_map(model: str, year: str, conn=Depends(get_db)):
    base_model = normalize_model(model)

    recalls = conn.execute(
        "SELECT campaign, component, summary, report_date FROM recalls WHERE model = ?", (base_model,)
    ).fetchall()

    complaints_year = conn.execute(
        "SELECT part_category, symptom, text, odino FROM complaints WHERE model = ? AND year = ?",
        (model, year),
    ).fetchall()
    complaints_any_year = conn.execute(
        "SELECT part_category, symptom, text, odino FROM complaints WHERE model = ?", (model,)
    ).fetchall()
    complaints_source = complaints_year if complaints_year else complaints_any_year
    year_matched = bool(complaints_year)

    domain_state = {d: "new" for d in DOMAINS}
    domain_evidence = {d: None for d in DOMAINS}

    for r in recalls:
        # component 라벨은 부정확/포괄적일 수 있어(예: EV6 24V867000의 component는 "12V/24V/48V
        # BATTERY"뿐이지만 실제 원인은 summary에만 있는 ICCU) 두 필드를 합쳐서 한 번에 매칭한다 —
        # component만 보고 먼저 매칭되면 summary의 더 구체적인 키워드를 영영 못 보는 문제가 있었음.
        domain = classify_domain(f"{r['component'] or ''} {r['summary'] or ''}")
        if domain:
            domain_state[domain] = "recalled"
            domain_evidence[domain] = {"type": "recall", "campaign": r["campaign"], "report_date": r["report_date"]}

    for c in complaints_source:
        domain = classify_domain(f"{c['part_category'] or ''} {c['symptom'] or ''}")
        if domain and domain_state[domain] == "new":
            domain_state[domain] = "active"
            domain_evidence[domain] = {"type": "complaint", "odino": c["odino"], "text": c["text"]}

    return {
        "model": base_model,
        "year": year,
        "year_matched_complaints": year_matched,
        "domains": [
            {"domain": d, "state": domain_state[d], "evidence": domain_evidence[d]} for d in DOMAINS
        ],
        "note": "도메인 분류는 recalls.component/summary·complaints.part_category 텍스트에 대한 "
        "키워드 기반 근사 매핑입니다. 실데이터에 매칭되는 것이 없으면 'new'(이력 없음)로 표시됩니다.",
    }


@router.get("/{model}/history")
def get_vehicle_history(model: str, conn=Depends(get_db)):
    base_model = normalize_model(model)
    all_rows = conn.execute("SELECT model, month, count, state FROM signals").fetchall()
    matching = [r for r in all_rows if normalize_model(r["model"]) == base_model]

    by_month: dict[str, dict] = {}
    for r in matching:
        entry = by_month.setdefault(r["month"], {"count": 0, "states": []})
        entry["count"] += r["count"]
        entry["states"].append(r["state"])

    history = [
        {"month": m, "count": v["count"], "state": top_state(v["states"])}
        for m, v in sorted(by_month.items())
    ]
    return {"model": base_model, "history": history}
