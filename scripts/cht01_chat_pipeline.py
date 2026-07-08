# 담당자: 허정윤 
# 담당 기능: CHT-01 사용자 질문 → 구조화 → 조사 → 검수 → 답변 채팅 파이프라인

"""
MOBISCOPE CHT-01 — 채팅 연동 파이프라인
============================================================
목적
- 사용자 질문을 [질문 → 구조화 → 조사 → 검수 → 답변] 5단계로 연결한다.
- 현재 버전은 LLM API를 직접 호출하지 않고, 규칙 기반 구조화 + INV/STA 모듈 호출로
  데이터 단계의 작동을 검증한다.
- 추후 LLM을 붙일 때는 parse_question()과 compose_answer_text()만 교체하면 된다.

파이프라인
1. parse_question       질문에서 제조사/차종/연식/증상/intent 추출
2. structure_query      intent를 INV-01/INV-02/STA 실행 계획으로 변환
3. run_investigation    안전한 쿼리 템플릿 또는 조사 루프 호출
4. review               데이터 없음·근거 부족·확정 표현 방지 검수
5. format_answer        한국어 답변 dict 생성

주의
- "결함 확정", "리콜 확정", "사지 마라" 식 단정 금지
- 모든 답변에는 미검증 소비자 신고 기준임을 남긴다.
- VIN은 표시하지 않는다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import re
import sqlite3

import pandas as pd

from inv01_query_templates import (
    DEFAULT_CSV_PATH,
    load_processed,
    run_query_template,
    q_vehicle_component_summary,
)
from inv02_03_investigation_loop import investigate_ad_hoc

try:
    from sta01_02_status_tracking import DEFAULT_DB_PATH, get_conn, query_status_summary
except Exception:  # STA 파일이 아직 없는 환경에서도 통계 질의는 작동하게 한다.
    DEFAULT_DB_PATH = Path("data/processed/defect_status_tracking.db")
    get_conn = None
    query_status_summary = None


PART_CATEGORY_BY_KO = {
    "계기판": "ELECTRICAL_SYSTEM",
    "클러스터": "ELECTRICAL_SYSTEM",
    "전기": "ELECTRICAL_SYSTEM",
    "배터리": "ELECTRICAL_SYSTEM",
    "충전": "ELECTRICAL_SYSTEM",
    "시동": "POWERTRAIN_SW",
    "엔진": "POWERTRAIN_SW",
    "동력": "POWERTRAIN_SW",
    "출력": "POWERTRAIN_SW",
    "브레이크": "POWERTRAIN_SW",
    "제동": "POWERTRAIN_SW",
    "차선": "ADAS",
    "ADAS": "ADAS",
    "카메라": "ADAS",
    "센서": "ADAS",
    "후방": "ADAS",
}

TEXT_KEYWORDS_BY_KO = {
    "계기판": ["dashboard", "instrument", "cluster", "display", "screen", "speedometer"],
    "클러스터": ["cluster", "instrument", "dashboard"],
    "꺼짐": ["shut off", "turned off", "blank", "black", "went out"],
    "화재": ["fire", "smoke", "burn", "flame"],
    "연기": ["smoke", "smoking", "burn"],
    "시동": ["stall", "stalled", "shut off", "start", "engine"],
    "동력": ["loss of power", "lost power", "power loss", "limp"],
    "출력": ["loss of power", "lost power", "power loss"],
    "제동": ["brake", "braking", "abs"],
    "브레이크": ["brake", "braking", "abs"],
    "조향": ["steer", "steering"],
    "차선": ["lane", "departure", "assist"],
    "카메라": ["camera", "backup", "rear"],
    "배터리": ["battery", "12v"],
    "충전": ["charge", "charging", "battery"],
}

MAKE_ALIASES = {
    "HYUNDAI": ["현대", "hyundai", "현대차"],
    "KIA": ["기아", "kia"],
}

# CSV 내 모델명은 영문이므로 대표 한국어 alias만 둔다. 실제 프로젝트에서는 별도 model_alias.csv로 빼면 좋다.
MODEL_ALIASES = {
    "TUCSON": ["투싼", "tucson"],
    "SANTA FE": ["싼타페", "santa fe", "santafe"],
    "SONATA": ["쏘나타", "소나타", "sonata"],
    "ELANTRA": ["아반떼", "elantra"],
    "KONA": ["코나", "kona"],
    "IONIQ 5": ["아이오닉5", "아이오닉 5", "ioniq 5", "ioniq5"],
    "SORENTO": ["쏘렌토", "소렌토", "sorento"],
    "SPORTAGE": ["스포티지", "sportage"],
    "FORTE": ["포르테", "forte"],
    "SOUL": ["쏘울", "소울", "soul"],
    "TELLURIDE": ["텔루라이드", "telluride"],
    "PALISADE": ["팰리세이드", "palisade"],
}

INTENT_TO_TEMPLATE = {
    "year_distribution": "year_distribution",
    "monthly_trend": "monthly_trend",
    "component_distribution": "component_distribution",
    "model_ranking": "model_ranking",
    "safety_flag_summary": "safety_flag_summary",
    "component_by_year": "component_by_year",
    "recent_surge": "recent_surge",
    "evidence_samples": "text_evidence_samples",
}

_DF_CACHE: dict[str, pd.DataFrame] = {}


def _get_df(csv_path: str | Path | None = None) -> pd.DataFrame:
    key = str(csv_path or DEFAULT_CSV_PATH)
    if key not in _DF_CACHE:
        _DF_CACHE[key] = load_processed(csv_path or DEFAULT_CSV_PATH)
    return _DF_CACHE[key]


def _contains_any(text: str, aliases: list[str]) -> bool:
    t = text.lower()
    return any(a.lower() in t for a in aliases)


def _extract_make(question: str) -> str | None:
    for make, aliases in MAKE_ALIASES.items():
        if _contains_any(question, aliases):
            return make
    return None


def _extract_model(question: str, df: pd.DataFrame | None = None) -> str | None:
    q = question.lower()
    for model, aliases in MODEL_ALIASES.items():
        if any(a.lower() in q for a in aliases):
            return model
    # alias에 없더라도 CSV 모델명이 영어로 직접 들어오면 잡는다.
    if df is not None and "MODELTXT" in df.columns:
        models = sorted({str(x).strip().upper() for x in df["MODELTXT"].dropna().unique()}, key=len, reverse=True)
        for m in models:
            if m and m.lower() in q:
                return m
    return None


def _extract_year(question: str) -> str | None:
    # 2025년식, 2025 투싼, year 2025 등
    m = re.search(r"(20\d{2}|19\d{2})\s*년?\s*식?", question)
    if m:
        return m.group(1)
    m = re.search(r"\b(20\d{2}|19\d{2})\b", question)
    return m.group(1) if m else None


def _extract_months(question: str) -> int:
    m = re.search(r"(\d+)\s*(개월|month|months)", question.lower())
    if m:
        return max(1, min(int(m.group(1)), 24))
    if "분기" in question:
        return 3
    return 6


def _extract_part_and_keywords(question: str) -> tuple[str | None, list[str]]:
    part: str | None = None
    keywords: list[str] = []
    for ko, p in PART_CATEGORY_BY_KO.items():
        if ko.lower() in question.lower():
            part = p
            break
    for ko, ens in TEXT_KEYWORDS_BY_KO.items():
        if ko.lower() in question.lower():
            keywords.extend(ens)
    # 영어 증상 직접 입력 보조
    for kw in ["dashboard", "cluster", "fire", "smoke", "stall", "brake", "camera", "lane", "battery", "charging", "engine"]:
        if kw in question.lower():
            keywords.append(kw)
    seen = set()
    out = []
    for k in keywords:
        kk = k.lower()
        if kk not in seen:
            seen.add(kk)
            out.append(k)
    return part, out[:10]


def _detect_intent(question: str) -> str:
    q = question.lower()
    if any(k in q for k in ["신규", "재발", "리콜 후", "상태", "sta-01", "sta-02"]):
        return "status_tracking"
    if any(k in q for k in ["근거", "원문", "citation", "인용", "사례"]):
        return "evidence_samples"
    if any(k in q for k in ["급증", "시그널", "최근", "surge", "증가"]):
        return "investigate_signal"
    if any(k in q for k in ["연식", "year", "모델연도"]):
        return "year_distribution"
    if any(k in q for k in ["월별", "추이", "trend", "monthly"]):
        return "monthly_trend"
    if any(k in q for k in ["부품", "component", "compdesc", "라벨"]):
        return "component_distribution"
    if any(k in q for k in ["화재", "충돌", "부상", "사망", "위험", "fire", "crash"]):
        return "safety_flag_summary"
    if any(k in q for k in ["모델", "차종", "상위", "랭킹", "ranking"]):
        return "model_ranking"
    # 차종/연식/증상이 있으면 조사 의도로 본다.
    return "investigate_signal"


def parse_question(question: str, *, csv_path: str | Path | None = None) -> dict[str, Any]:
    """
    질문 → 구조화 dict.
    TODO: LLM_CALL 교체 지점. 현재는 룰 기반으로 안정적인 데모를 먼저 만든다.
    """
    df = _get_df(csv_path)
    part, keywords = _extract_part_and_keywords(question)
    intent = _detect_intent(question)
    parsed = {
        "raw_question": question,
        "intent": intent,
        "make": _extract_make(question),
        "model": _extract_model(question, df),
        "year": _extract_year(question),
        "months": _extract_months(question),
        "part_category": part,
        "text_keywords": keywords,
    }
    if parsed["part_category"] is None and keywords and intent in {"investigate_signal", "evidence_samples"}:
        # 증상 키워드가 있지만 파트가 없으면 전장/SW 프로젝트 범위에 맞춰 기본 전장으로 둔다.
        parsed["part_category"] = "ELECTRICAL_SYSTEM"
    return parsed


def structure_query(parsed: dict[str, Any]) -> dict[str, Any]:
    intent = parsed.get("intent")
    if intent == "investigate_signal":
        action = "ad_hoc_investigation"
    elif intent == "status_tracking":
        action = "status_query"
    else:
        action = "query_template"
    params = {
        "make": parsed.get("make"),
        "model": parsed.get("model"),
        "year": parsed.get("year"),
        "part_category": parsed.get("part_category"),
        "text_keywords": parsed.get("text_keywords") or None,
    }
    # 위험 플래그 요약은 FIRE/CRASH/INJURED/DEATHS 컬럼 통계가 핵심이므로
    # "화재"라는 단어가 질문에 들어갔다고 CDESCR 원문 검색으로 다시 좁히지 않는다.
    if intent == "safety_flag_summary":
        params.pop("text_keywords", None)
        params.pop("part_category", None)
    # None 값 제거. text_keywords만 None이면 템플릿에 안 넘긴다.
    params = {k: v for k, v in params.items() if v not in (None, [], "")}
    return {
        "action": action,
        "template": INTENT_TO_TEMPLATE.get(intent),
        "params": params,
        "parsed": parsed,
    }


def _query_status_db(parsed: dict[str, Any], *, db_path: str | Path | None = None) -> dict[str, Any]:
    if get_conn is None or query_status_summary is None:
        return {"status": "UNAVAILABLE", "reason": "STA 모듈을 import하지 못했습니다.", "rows": []}
    db = Path(db_path or DEFAULT_DB_PATH)
    if not db.exists():
        # 샌드박스 fallback
        fb = Path("/mnt/data/defect_status_tracking_generated.db")
        if fb.exists():
            db = fb
        else:
            return {"status": "NO_DB", "reason": f"상태 DB가 아직 없습니다: {db}", "rows": []}
    conn = get_conn(db)
    try:
        df = query_status_summary(conn)
    finally:
        conn.close()

    for col, val in [("make", parsed.get("make")), ("model", parsed.get("model")), ("year", parsed.get("year"))]:
        if val and col in df.columns:
            df = df[df[col].astype(str).str.upper() == str(val).upper()]
    if parsed.get("part_category") and "part_category" in df.columns:
        df = df[df["part_category"].astype(str).str.upper() == str(parsed["part_category"]).upper()]

    return {
        "status": "OK",
        "reason": "상태 DB 조회 완료",
        "rows": df.head(20).to_dict("records"),
        "total_count": int(len(df)),
    }


def run_investigation(plan: dict[str, Any], *, csv_path: str | Path | None = None, db_path: str | Path | None = None) -> dict[str, Any]:
    df = _get_df(csv_path)
    action = plan["action"]
    parsed = plan["parsed"]

    if action == "ad_hoc_investigation":
        result = investigate_ad_hoc(
            df,
            make=parsed.get("make"),
            model=parsed.get("model"),
            year=parsed.get("year"),
            part_category=parsed.get("part_category"),
            text_keywords=parsed.get("text_keywords") or None,
        )
        return {"kind": action, "result": result}

    if action == "status_query":
        return {"kind": action, "result": _query_status_db(parsed, db_path=db_path)}

    template = plan.get("template")
    if not template:
        return {"kind": action, "error": "질문 의도를 쿼리 템플릿에 매핑하지 못했습니다."}

    params = dict(plan.get("params") or {})
    if template == "recent_surge":
        params["months"] = parsed.get("months") or 6
    if template == "component_by_year" and not (params.get("part_category") or params.get("component_keyword")):
        params["part_category"] = parsed.get("part_category") or "ELECTRICAL_SYSTEM"
    if template == "text_evidence_samples":
        params.setdefault("limit", 8)
    result = run_query_template(template, df, params)
    return {"kind": action, "template": template, "result": result}


def review(parsed: dict[str, Any], investigation: dict[str, Any]) -> dict[str, Any]:
    """근거 부족/오류/단정 금지 검수."""
    if investigation.get("error"):
        return {"status": "FAIL", "reason": investigation["error"]}

    result = investigation.get("result")
    if result is None:
        return {"status": "INSUFFICIENT", "reason": "조회 결과가 없습니다."}

    if isinstance(result, pd.DataFrame):
        if len(result) == 0:
            return {"status": "INSUFFICIENT", "reason": "해당 조건의 데이터가 없습니다."}
        return {"status": "PASS", "reason": "조회 결과 통과"}

    if isinstance(result, dict):
        if result.get("status") in {"NO_DATA", "NO_DB", "UNAVAILABLE"}:
            return {"status": "INSUFFICIENT", "reason": result.get("reason") or result.get("status")}
        if result.get("status") == "INSUFFICIENT":
            return {"status": "INSUFFICIENT", "reason": result.get("decision_reason", "근거 부족")}
        if result.get("status") == "REJECTED":
            return {"status": "PASS", "reason": "부정/기각 결과도 답변 가능"}
        return {"status": "PASS", "reason": "dict 결과 통과"}

    return {"status": "PASS", "reason": "결과 통과"}


def _records_from_result(result: Any) -> Any:
    if isinstance(result, pd.DataFrame):
        return result.head(20).to_dict("records")
    return result


def _scope_text(parsed: dict[str, Any]) -> str:
    parts = []
    if parsed.get("make"):
        parts.append(parsed["make"])
    if parsed.get("model"):
        parts.append(parsed["model"])
    if parsed.get("year"):
        parts.append(f"{parsed['year']}년식")
    if parsed.get("part_category"):
        parts.append(parsed["part_category"])
    return " / ".join(parts) if parts else "전체 데이터"


def compose_answer_text(parsed: dict[str, Any], investigation: dict[str, Any], review_result: dict[str, Any]) -> str:
    """
    TODO: LLM_CALL 교체 지점.
    현재는 수치와 근거를 안전 문구와 함께 직접 조합한다.
    """
    scope = _scope_text(parsed)
    result = investigation.get("result")
    review_status = review_result.get("status")

    if review_status == "FAIL":
        return f"요청을 처리하지 못했습니다. 사유: {review_result.get('reason')}"

    if investigation.get("kind") == "ad_hoc_investigation" and isinstance(result, dict):
        summary = result.get("summary", {})
        surge = summary.get("recent_surge", {}) if isinstance(summary, dict) else {}
        samples = result.get("evidence_samples", []) or []
        lines = [
            f"{scope} 기준으로 조회했습니다.",
            f"판정: {result.get('status')} — {result.get('decision_reason')}",
            f"기본 범위 신고 {summary.get('base_count', 0)}건, 관련 부품/증상 신고 {result.get('support_count', 0)}건입니다.",
        ]
        if surge:
            lines.append(
                f"최근 구간 급증 판단: {surge.get('surge_level')} "
                f"(최근 {surge.get('recent_count')}건 / 기준 {surge.get('baseline_count')}건 / ratio={surge.get('ratio')})."
            )
        if samples:
            cite_bits = []
            for s in samples[:3]:
                cite_bits.append(f"ODINO {s.get('odino')}: {s.get('evidence_snippet', '')[:120]}")
            lines.append("근거 원문 후보: " + " | ".join(cite_bits))
        lines.append("단, 이는 NHTSA 소비자 신고 기반 시그널 후보이며 결함 또는 리콜 확정이 아닙니다.")
        return "\n".join(lines)

    if investigation.get("kind") == "status_query" and isinstance(result, dict):
        if result.get("status") != "OK":
            return f"상태 추적 DB 조회가 어렵습니다. 사유: {result.get('reason')}"
        rows = result.get("rows", [])
        if not rows:
            return f"{scope} 조건의 STA-01/STA-02 추적 기록은 아직 없습니다."
        counts = pd.Series([r.get("status_code") for r in rows]).value_counts().to_dict()
        return (
            f"{scope} 조건의 상태 추적 기록 {result.get('total_count', len(rows))}건을 찾았습니다. "
            f"분포는 {counts}입니다. STA-01은 신규 결함 후보, STA-02는 기존 리콜 후 재발 후보입니다."
        )

    if isinstance(result, pd.DataFrame):
        return (
            f"{scope} 기준으로 {len(result)}행의 조회 결과를 반환합니다. "
            "상위 20행만 data에 담았습니다. 미검증 소비자 신고 데이터 기준입니다."
        )

    if isinstance(result, dict):
        # 일반 쿼리 템플릿 dict 결과용: 안전 플래그, 급증 결과 등을 짧게 설명한다.
        if {"total_count", "fire_count", "crash_count"}.issubset(result.keys()):
            return (
                f"{scope} 기준 위험 플래그 요약입니다. 전체 {result.get('total_count', 0)}건 중 "
                f"화재 {result.get('fire_count', 0)}건({result.get('fire_pct', 0)}%), "
                f"충돌 {result.get('crash_count', 0)}건({result.get('crash_pct', 0)}%), "
                f"부상 {result.get('injured_count', 0)}건, 사망 {result.get('deaths_count', 0)}건입니다. "
                "미검증 소비자 신고 기준이며 결함 확정이 아닙니다."
            )
        if {"recent_count", "baseline_count", "surge_level"}.issubset(result.keys()):
            return (
                f"{scope} 기준 최근 급증 조회 결과입니다. {result.get('recent_window')} 최근 "
                f"{result.get('recent_count')}건, 기준 구간 {result.get('baseline_window')} "
                f"{result.get('baseline_count')}건, ratio={result.get('ratio')}, "
                f"판정={result.get('surge_level')}입니다. 결함 확정이 아니라 조사 우선순위 신호입니다."
            )
        return f"{scope} 기준 조회 결과입니다. 미검증 소비자 신고 데이터 기준이며 결함 확정이 아닙니다."

    return "조회 결과입니다."


def format_answer(
    question: str,
    parsed: dict[str, Any],
    plan: dict[str, Any],
    investigation: dict[str, Any],
    review_result: dict[str, Any],
) -> dict[str, Any]:
    result = investigation.get("result")
    answer_text = compose_answer_text(parsed, investigation, review_result)
    return {
        "question": question,
        "parsed": parsed,
        "plan": {"action": plan.get("action"), "template": plan.get("template"), "params": plan.get("params")},
        "review_status": review_result.get("status"),
        "review_reason": review_result.get("reason"),
        "answer_text": answer_text,
        "data": _records_from_result(result),
        "safety_notice": "소비자 신고 기반 분석이며 결함·리콜 확정 판단은 규제기관/제조사 조사 영역입니다.",
    }


def chat(
    question: str,
    session_history: list[dict[str, Any]] | None = None,
    *,
    csv_path: str | Path | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """CHT-01 단일 진입점."""
    parsed = parse_question(question, csv_path=csv_path)
    plan = structure_query(parsed)
    investigation = run_investigation(plan, csv_path=csv_path, db_path=db_path)
    review_result = review(parsed, investigation)
    answer = format_answer(question, parsed, plan, investigation, review_result)

    if session_history is not None:
        session_history.append({
            "question": question,
            "intent": parsed.get("intent"),
            "review_status": answer.get("review_status"),
            "answer_text": answer.get("answer_text"),
        })
    return answer


if __name__ == "__main__":
    history: list[dict[str, Any]] = []
    tests = [
        "2025년식 투싼 계기판 꺼짐 최근 6개월 시그널 있어?",
        "기아 연식별 불만 분포 보여줘",
        "현대 부품 라벨 상위 알려줘",
        "화재나 충돌 플래그 요약해줘",
        "리콜 후 재발 상태 추적 기록 보여줘",
    ]
    for q in tests:
        ans = chat(q, history)
        print("\nQ:", q)
        print("A:", ans["answer_text"][:800])
    print(f"\n[HISTORY] {len(history)} turns")
