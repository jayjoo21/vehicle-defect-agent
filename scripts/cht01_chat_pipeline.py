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
    from sta01_02_status_tracking import (
        DEFAULT_DB_PATH,
        SIGNAL_LABEL_KO,
        SIGNAL_PRIORITY_ORDER,
        get_conn,
        query_signal_summary,
    )
except Exception:  # STA 파일이 아직 없는 환경에서도 통계 질의는 작동하게 한다.
    DEFAULT_DB_PATH = Path("data/processed/defect_status_tracking.db")
    get_conn = None
    query_signal_summary = None
    SIGNAL_LABEL_KO = {}
    SIGNAL_PRIORITY_ORDER = {}

# STR-05(사용자 입력에서 차종·증상 추출, 멀티턴 되물음)를 이 자리에 꽂는다 —
# 원래 코드의 "TODO: LLM_CALL 교체 지점" 자리가 여기다.
#
# 반환 shape(완료 시 {차종,차종_표시,증상} 3개 / 미완료 시 +상태+후속질문 /
# 포기 시 +상태+안내문)와 extract_slots()가 "웹앱 연동용 진입점"이라는 점,
# confirm_sentence(결과)가 별도 함수로 분리돼 있다는 점은 STR 트랙 정리 문서
# (STR_트랙_정리 (1).md, 최종 갱신 2026-07-10)로 확인됨.
# 단, extract_slots(question, existing_slots) 두 인자 시그니처 자체는 문서에
# 코드로 명시돼 있지 않아 여전히 추정이다 — extract_slots_safe() 안의 TypeError
# 폴백이 그 불확실성에 대한 안전장치.
#
# import 경로는 두 가지를 다 시도한다: bare(str05_query_understanding)와
# scripts. 패키지 경로(scripts.str05_query_understanding). 같은 문서의
# str_structurize_v3.py 검증 기록에 "webapp/backend/에서 sys.path에 루트만
# 추가하고 from scripts.str_structurize_v3 import structurize로 임포트해도
# 정상 동작"이라고 명시돼 있어 — str05도 같은 scripts/ 안에 있으니 실제
# 배포 환경에서 어느 쪽으로 import될지 몰라 둘 다 시도하게 했다.
def _try_import_str05(name: str):
    try:
        module = __import__("str05_query_understanding", fromlist=[name])
        return getattr(module, name)
    except ImportError:
        try:
            module = __import__("scripts.str05_query_understanding", fromlist=[name])
            return getattr(module, name)
        except Exception:
            return None
    except Exception:
        return None


_str05_extract_slots = _try_import_str05("extract_slots")
_str05_confirm_sentence = _try_import_str05("confirm_sentence")


# STR-04에서 확정된 v3 스키마는 8종(ELECTRICAL_SYSTEM/ADAS/INSTRUMENT_CLUSTER/
# PROPULSION_BATTERY/BRAKES_ELECTRONIC/POWERTRAIN_SW/NON_ELECTRICAL/
# INSUFFICIENT_INFO)인데, 이전 버전은 3종(ELECTRICAL_SYSTEM/POWERTRAIN_SW/ADAS)
# 으로만 매핑돼 있어 "계기판"이나 "배터리" 질문이 실제보다 넓은 카테고리로
# 뭉뚱그려졌다(2026-07-13 확인, STA/INV 쪽에도 같은 종류 갭이 있어 STA는 이미
# 수정, INV-01은 담당 범위 밖이라 별도 전달). 아래는 STR v3 8종 기준 재매핑.
PART_CATEGORY_BY_KO = {
    "계기판": "INSTRUMENT_CLUSTER",
    "클러스터": "INSTRUMENT_CLUSTER",
    "게이지": "INSTRUMENT_CLUSTER",
    "속도계": "INSTRUMENT_CLUSTER",
    "전기": "ELECTRICAL_SYSTEM",
    "배터리": "PROPULSION_BATTERY",
    "충전": "PROPULSION_BATTERY",
    "고전압": "PROPULSION_BATTERY",
    "시동": "POWERTRAIN_SW",
    "엔진": "POWERTRAIN_SW",
    "동력": "POWERTRAIN_SW",
    "출력": "POWERTRAIN_SW",
    "브레이크": "BRAKES_ELECTRONIC",
    "제동": "BRAKES_ELECTRONIC",
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
    "게이지": ["gauge", "instrument", "dashboard"],
    "속도계": ["speedometer", "gauge"],
    "고전압": ["high voltage", "hv battery", "iccu"],
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
    # "증가"는 추가하지 않음: 기존에 investigate_signal 트리거(급증 조사)로 이미
    # 쓰이고 있어서, status_tracking을 먼저 체크하는 이 if-elif 순서상 여기에
    # 추가하면 "증가"가 들어간 급증-조사 질문까지 전부 status_tracking으로
    # 새치기해버린다("계기판 신고 증가하고 있어?" 같은 질문이 깨짐). "잠잠"은
    # 기존에 다른 의도로 안 쓰이고 있어 충돌 없이 추가.
    if any(k in q for k in ["신규", "재발", "잠잠", "리콜 후", "상태", "sta-01", "sta-02"]):
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


def _ro_particle(word: str) -> str:
    """한글 단어 뒤에 붙는 "로/으로" 조사를 받침 유무로 정확히 고른다.
    규칙: 받침 없음 또는 받침이 ㄹ이면 "로", 그 외 받침이 있으면 "으로"
    (예: "서울로"·"불로"는 로, "깜빡임으로"·"소음으로"는 으로).
    한글 완성형 음절이 아닌 문자로 끝나면(영문/숫자 등) 안전하게 "로"를 쓴다."""
    if not word:
        return "로"
    last = word.strip()[-1]
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        final_idx = (code - 0xAC00) % 28
        if final_idx in (0, 8):  # 0=받침 없음, 8=ㄹ받침
            return "로"
        return "으로"
    return "로"


def confirm_sentence_safe(slots: dict[str, Any]) -> str | None:
    """
    STR-05 confirm_sentence() 래퍼. 실제 함수가 로드됐으면 그대로 쓰고, 실패하거나
    아직 연동 전이면 STR 트랙 정리 문서의 예시 형식("투싼 / 계기판 깜빡임으로
    이해했어요. 맞나요?")을 그대로 흉내 낸 자체 생성으로 폴백한다 — 실제
    confirm_sentence()가 준비되면 이 폴백은 자동으로 안 쓰이게 된다.
    slots에 차종_표시/증상이 없으면(완료되지 않은 슬롯) None을 반환한다.
    """
    if _str05_confirm_sentence is not None:
        try:
            result = _str05_confirm_sentence(slots)
            if result:
                return result
        except Exception:
            pass
    model_kr = slots.get("차종_표시") or slots.get("차종")
    symptom = slots.get("증상")
    if not (model_kr and symptom):
        return None
    return f"{model_kr} / {symptom}{_ro_particle(symptom)} 이해했어요. 맞나요?"


def extract_slots_safe(question: str, slot_state: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """
    STR-05 extract_slots() 래퍼. STR-05가 없는 환경(import 실패)이면 None을 반환해
    chat()이 기존 정규식 경로(_extract_model 등)로 폴백하게 한다.

    반환 shape (STR 트랙 정리 문서, 2026-07-10 기준 추정):
    - 완료: {"차종": "TUCSON", "차종_표시": "투싼", "증상": "계기판 깜빡임"}  (3개 키)
    - 미완료: 위 3개 + {"상태": "need_차종"|"need_증상", "후속질문": "..."}
    - 포기: 위 3개 + {"상태": "unresolved", "안내문": "..."}
    """
    if _str05_extract_slots is None:
        return None
    try:
        return _str05_extract_slots(question, slot_state)
    except TypeError:
        # 혹시 실제 시그니처가 단일 인자(question)만 받는 형태일 경우의 보수적 폴백.
        try:
            return _str05_extract_slots(question)
        except Exception:
            return None
    except Exception:
        return None


def parse_question(
    question: str, *, csv_path: str | Path | None = None, slots: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    질문 → 구조화 dict.
    TODO: LLM_CALL 교체 지점. 현재는 룰 기반으로 안정적인 데모를 먼저 만든다.

    slots: STR-05 extract_slots()가 이미 완료 판정한 결과({차종,차종_표시,증상}).
    주어지면 차종은 STR-05의 carRegistry 정규화 값을 그대로 신뢰하고(자체 정규식
    재추출 안 함), 증상 키워드/부품카테고리는 STR-05가 준 "증상" 문구를 기준으로
    추출한다. 주어지지 않으면(slots=None) 기존 방식(원문 전체에 정규식) 그대로.
    """
    df = _get_df(csv_path)
    if slots and slots.get("차종"):
        model = slots["차종"]
        part, keywords = _extract_part_and_keywords(slots.get("증상") or question)
    else:
        model = _extract_model(question, df)
        part, keywords = _extract_part_and_keywords(question)
    intent = _detect_intent(question)
    parsed = {
        "raw_question": question,
        "intent": intent,
        "make": _extract_make(question),
        "model": model,
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
    """차종×부품카테고리 단위 5단계 시그널(defect_signals)을 조회한다.
    (기존에는 신고 단위 STA-01/02 이진 상태를 조회했으나, 5단계 모델 도입 후
    사용자 질문에 더 직접적으로 답이 되는 쪽은 시그널 단위 상태라 이쪽을 기본으로
    바꿨다. 신고 단위 원본 기록이 필요하면 query_status_summary()를 별도로 쓸 수
    있다 — 삭제하지 않고 남겨뒀다.)"""
    if get_conn is None or query_signal_summary is None:
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
        df = query_signal_summary(conn)
    finally:
        conn.close()

    for col, val in [("make", parsed.get("make")), ("model", parsed.get("model")), ("year", parsed.get("year"))]:
        if val and col in df.columns:
            df = df[df[col].astype(str).str.upper() == str(val).upper()]
    if parsed.get("part_category") and "part_category" in df.columns:
        df = df[df["part_category"].astype(str).str.upper() == str(parsed["part_category"]).upper()]

    return {
        "status": "OK",
        "reason": "시그널 상태 조회 완료",
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
            return f"{scope} 조건의 결함 시그널 추적 기록은 아직 없습니다."
        counts = pd.Series([r.get("signal_state") for r in rows]).value_counts().to_dict()
        label_counts = {SIGNAL_LABEL_KO.get(k, k): v for k, v in counts.items()}
        top = min(rows, key=lambda r: SIGNAL_PRIORITY_ORDER.get(r.get("signal_state"), 99))
        top_label = SIGNAL_LABEL_KO.get(top.get("signal_state"), top.get("signal_state"))
        top_vehicle = " ".join(str(top.get(k)) for k in ("make", "model", "year") if top.get(k)) or scope
        return (
            f"{scope} 조건의 결함 시그널 {result.get('total_count', len(rows))}건을 찾았습니다. "
            f"상태 분포는 {label_counts}입니다. "
            f"가장 우선 확인이 필요한 시그널: {top_vehicle} {top.get('part_category')} — {top_label} "
            f"({top.get('state_reason', '')}) "
            "신규(NEW)→증가(RISING)→리콜(RECALLED)→잠잠(DORMANT)→재발(RECURRING) 생애주기 기준이며, "
            "재발·증가 상태를 우선 검토 대상으로 봅니다."
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


# STR-05는 "부품명 단독"은 증상으로 인정하지 않는다(STR 트랙 정리 문서, 시행착오
# 5번: "브레이크"만 있으면 거부하고 되묻는다). 그래서 애초에 구체적 증상 서술이
# 필요 없는 의도(상태 조회, 통계 조회)까지 STR-05 게이트를 거치게 하면
# "브레이크 상태 어때?" 같은 정상적인 질문이 불필요하게 되물어진다. 실제로
# "차종+증상"이 핵심인 의도(조사/근거조회)만 게이트를 거치게 제한한다.
_SLOT_GATED_INTENTS = {"investigate_signal", "evidence_samples"}


def _is_incomplete_slot_state(state: Any) -> bool:
    """
    STR-05의 "상태" 값 중 미완료/포기를 판정한다.

    STR 트랙 정리 문서(STR_트랙_정리 (1).md, 2026-07-10)의 시행착오 4번 예시에
    "need_둘다"(여러 차종이 동시에 언급돼 특정 못 하는 경우)가 등장하는데, 이건
    처음 문서(PDF)에는 없던 값이라 need_차종/need_증상 두 개만 하드코딩해뒀던
    구버전 코드가 이 경우를 놓치고 있었다(발견 즉시 수정). "need_*" 전부를
    나열하는 대신 접두사로 판정해서, 앞으로 문서에 없는 다른 need_* 변형이
    추가되더라도 자동으로 커버되게 했다.
    """
    return state == "unresolved" or (isinstance(state, str) and state.startswith("need_"))


def chat(
    question: str,
    session_history: list[dict[str, Any]] | None = None,
    *,
    csv_path: str | Path | None = None,
    db_path: str | Path | None = None,
    slot_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    CHT-01 단일 진입점.

    slot_state: STR-05 extract_slots()가 이전 턴까지 쌓아온 차종/증상 슬롯
    ({차종,차종_표시,증상[,상태,후속질문/안내문]}). 첫 턴은 None으로 시작.
    이번 턴 응답의 "slot_state" 값을 다음 chat() 호출에 그대로 넘기면 멀티턴
    되물음이 이어진다 — 상위(웹앱/세션) 레이어가 이 값을 턴 사이에 보관해야 한다.
    완료(turn_status="OK") 후에는 slot_state가 None으로 초기화되어 돌아오므로,
    다음 질문은 새 대화로 자연스럽게 시작된다.

    STR-05가 아직 연동 안 된 환경(extract_slots_safe가 None 반환)에서는 이 슬롯
    단계를 건너뛰고 기존 단일턴 정규식 경로로 동작한다 — 동작이 끊기지 않는다.
    """
    # 이미 진행 중인 슬롯 대화(slot_state 있음)는 이번 발화의 의도가 뭐로 보이든
    # 끝까지 이어가야 한다("투싼이요" 한마디만으로는 의도를 제대로 못 읽는다).
    # 새 대화라면 빠른 의도 판별로 게이트 필요 여부만 먼저 본다.
    quick_intent = _detect_intent(question)
    use_slot_gate = slot_state is not None or quick_intent in _SLOT_GATED_INTENTS
    slots = extract_slots_safe(question, slot_state) if use_slot_gate else None

    if slots is not None and _is_incomplete_slot_state(slots.get("상태")):
        turn_status = "UNRESOLVED" if slots["상태"] == "unresolved" else "NEED_MORE_INFO"
        answer_text = slots.get("안내문") or slots.get("후속질문") or "차종과 증상을 조금 더 알려주시겠어요?"
        result = {
            "question": question,
            "turn_status": turn_status,
            "slot_state": slots,
            "answer_text": answer_text,
            "safety_notice": "소비자 신고 기반 분석이며 결함·리콜 확정 판단은 규제기관/제조사 조사 영역입니다.",
        }
        if session_history is not None:
            session_history.append({"question": question, "turn_status": turn_status, "answer_text": answer_text})
        return result

    # 여기 도달 = slots가 None(STR-05 미연동, 기존 정규식 경로) 이거나 슬롯이 완료된 상태.
    parsed = parse_question(question, csv_path=csv_path, slots=slots)
    plan = structure_query(parsed)
    investigation = run_investigation(plan, csv_path=csv_path, db_path=db_path)
    review_result = review(parsed, investigation)
    answer = format_answer(question, parsed, plan, investigation, review_result)
    answer["turn_status"] = "OK"
    answer["slot_state"] = None  # 슬롯이 완료됐으니 다음 질문은 새 대화로 취급

    # STR-05가 이번 턴에 실제로 관여해 완료됐다면(slots is not None), 조사 결과보다
    # 먼저 "이렇게 이해했어요, 맞나요?" 확인 문구를 보여준다(요청 반영, 2026-07-13).
    # answer_text 안에 이어붙이는 것과 별개로 confirm_sentence 키로도 따로 담아서,
    # UI가 원하면 확인 문구만 별도 말풍선으로 먼저 보여주는 식으로 나눠 쓸 수 있게 했다.
    answer["confirm_sentence"] = None
    if slots is not None:
        confirm = confirm_sentence_safe(slots)
        if confirm:
            answer["confirm_sentence"] = confirm
            answer["answer_text"] = f"{confirm}\n\n{answer['answer_text']}"

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
