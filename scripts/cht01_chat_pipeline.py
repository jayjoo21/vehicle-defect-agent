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

⚠️ 2026-07-14 개정 — 효선님 실제 INV-01/02/03 파일 수령 후 전면 재작업
    query_templates.py / investigation_loop_v2.py가 이전에 CHT-01이 기대하던
    인터페이스와 완전히 달라서(함수명·시그니처·반환 shape 전부 변경) 이 파일
    전체를 다시 연결했다. 바뀐 내용은 각 함수 docstring/인라인 주석에 "2026-07-14"
    표시로 남겨뒀다. 아래는 이번에 함께 정리한 알려진 제약사항 — 코드가 조용히
    기능을 빠뜨린 게 아니라 의도적으로 미룬 부분임을 명시해둔다:

    1. llm_call 스텁(_stub_llm_call): investigate_ad_hoc()이 요구하는 LLM 콜백을
       결정론적 임시 로직으로 대체했다. 실제 추론이 아니다 — 팀 공용 LLM API
       래퍼가 준비되면 chat(..., llm_call=real_llm_call)로 교체.
    2. check_recall_match() / get_us_kr_gap() 미연동: 이 두 함수는
       (model, model_year, recalls_df) / (model, us_recalls_df, kr_recalls_df)처럼
       df 하나가 아니라 별도의 리콜 CSV를 인자로 받는데, 그 CSV들의 실제 경로가
       아직 확정되지 않았다(STA 쪽 recall_records 테이블과는 다른 데이터 소스로
       보임). CHT-01의 "리콜 여부/한미 시차" 질문은 지금도 STA의 defect_signals
       (RECALLED 상태·recall_id)로 답하고 있어 기능 공백은 아니지만, 이 두 함수
       자체는 아직 CHT-01 어디에서도 호출하지 않는다 — 리콜 CSV 경로가 정해지면
       추가 연동 필요.
    3. safety_flag_summary는 load_enriched_df() 결과가 아니라 원본 CSV를 별도로
       한 번 더 읽는다(_safety_flag_summary 참고) — CRASH/FIRE/INJURED/DEATHS가
       enriched df 조인에서 빠지기 때문. 모집단이 달라질 수 있음(원본 CSV 전체 vs
       STR이 처리한 건수)을 알고 있을 것.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import inspect
import re
import sqlite3

import pandas as pd

# ⚠️ 2026-07-14 개정 — 효선님의 실제 INV-01/02/03 파일(query_templates.py,
# investigation_loop_v2.py) 수령 후 CHT-01을 전면 재작업했다. 기존에 CHT-01이
# 기대하던 인터페이스(run_query_template, q_vehicle_component_summary,
# load_processed, DEFAULT_CSV_PATH, investigate_ad_hoc(df, make=, model=, ...))가
# 새 파일에는 전혀 없다 — INV 트랙이 처음부터 다시 설계된 것에 가깝다. 아래는
# 새 인터페이스 기준으로 다시 연결한 것.
from query_templates import (
    RAW_CSV_PATH,
    STRUCT_JSONL_PATH,
    TOOL_REGISTRY,
    load_enriched_df,
)
from investigation_loop_v2 import investigate_ad_hoc

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


# ------------------------------------------------------------------
# investigate_ad_hoc() -> run_investigation_loop()는 llm_call(prompt_type, context)
# 콜백이 반드시 있어야 동작한다(효선님 코드의 example_llm_call은 일부러
# NotImplementedError를 던짐 — "팀 공용 API 래퍼로 교체 필요"라고 명시돼 있음).
# CHT-01은 지금까지 전 구간이 규칙 기반이라 실제 LLM 호출 자체가 없었으므로,
# 여기서는 코드 경로가 죽지 않도록 "결정론적 임시 스텁"을 하나 둔다.
#
# 진짜 LLM 붙일 때는 이 함수 하나만(그리고 필요하면 실제 프롬프트) 교체하면 되고,
# chat()/run_investigation() 등 나머지 코드는 손댈 필요 없다 — investigate_ad_hoc()
# 호출부에서 llm_call 인자로 넘기는 지점 한 곳만 바꾸면 됨.
# ------------------------------------------------------------------
def _stub_llm_call(prompt_type: str, context: dict[str, Any]) -> dict[str, Any]:
    """
    임시 스텁. 3가지 prompt_type을 결정론적 규칙으로 흉내만 낸다(진짜 추론 아님):
    - generate_hypothesis: 정찰 결과(get_symptom_distribution)에서 최다 증상으로
      가설 문장을 기계적으로 조립.
    - select_query_or_conclude: 스텁 단계에서는 추가 쿼리를 고르지 않고 항상
      바로 결론(conclude)으로 넘어간다 — 실제 LLM이 붙기 전까지는 "정찰 결과만
      보고 판단"하는 최소 동작만 보장.
    - judge_hypothesis: 정찰 단계의 total_reports가 3건 이상이면 유지(retain),
      그 외엔 보류(None=HOLD). "결함 확정"처럼 보이는 과잉 판단을 피하려고
      기각(False)은 스텁에서 아예 내리지 않는다(정말 근거가 없으면 HOLD로 둠).
    """
    if prompt_type == "generate_hypothesis":
        scouting = context.get("scouting_results", {})
        symptom_dist = scouting.get("get_symptom_distribution", {}) or {}
        counts = symptom_dist.get("symptom_counts") or {}
        if counts:
            top_symptom = max(counts, key=counts.get)
            return {"hypothesis": f"'{top_symptom}' 증상이 신고에서 두드러지게 반복되고 있다(스텁 가설, 실제 LLM 아님)."}
        return {"hypothesis": "정찰 결과에서 뚜렷한 패턴을 찾지 못함(스텁 가설, 실제 LLM 아님)."}

    if prompt_type == "select_query_or_conclude":
        return {"action": "conclude"}

    if prompt_type == "judge_hypothesis":
        all_results = context.get("all_results", [])
        scouting = all_results[0] if all_results else {}
        symptom_dist = scouting.get("get_symptom_distribution", {}) if isinstance(scouting, dict) else {}
        total = symptom_dist.get("total_reports", 0) if isinstance(symptom_dist, dict) else 0
        if total >= 3:
            return {"is_retained": True, "reason": f"정찰 단계 관련 신고 {total}건(스텁 판정, 실제 LLM 아님)."}
        return {"is_retained": None, "reason": f"정찰 단계 관련 신고 {total}건으로 근거 부족(스텁 판정, 실제 LLM 아님)."}

    raise ValueError(f"알 수 없는 prompt_type: {prompt_type!r}")


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

# 2026-07-14: 새 INV-01(query_templates.py)의 TOOL_REGISTRY 실제 키 이름 기준으로
# 다시 매핑했다. 예전 이름(component_distribution/component_by_year/recent_surge/
# text_evidence_samples)은 새 INV-01에 대응 함수가 없어서 전부 정리했다:
#   - component_distribution -> get_symptom_distribution (부품 카테고리 안 증상 분포로 대체)
#   - component_by_year      -> get_model_year_breakdown (차종×연식 조합, 원래도 이 뜻이었음).
#                               단순 이름 교체가 아니라 _detect_intent()에도 전용 분기
#                               ("model_year_breakdown")를 새로 추가했다 — 기존엔 "연식"
#                               키워드 분기가 먼저 걸려서 "2025년식 투싼 조합" 같은 질문이
#                               이 템플릿에 영영 도달 못 하는 죽은 매핑이었다(테스트로 발견).
#   - recent_surge           -> 삭제. _detect_intent()가 "recent_surge"를 반환하는 경로가
#                               애초에 없어(항상 investigate_signal로 감) 죽은 코드였음.
#   - evidence_samples       -> 별도 로컬 함수(_evidence_samples_from_df)로 대체.
#                               새 INV-01엔 "원문 근거 몇 건 보여줘" 함수 자체가 없어졌음
#                               (조사 루프 안에서만 근거를 다루는 구조로 바뀜).
#   - safety_flag_summary    -> 별도 로컬 함수(_safety_flag_summary)로 대체. 새 INV-01의
#                               load_enriched_df()는 CRASH/FIRE/INJURED/DEATHS 컬럼을
#                               조인에서 아예 빼버려서(odino/model/model_year/date_filed만
#                               가져옴), TOOL_REGISTRY 함수로는 이 통계를 낼 수 없다.
#                               원본 CSV를 직접 다시 읽어 계산한다.
INTENT_TO_TEMPLATE = {
    "year_distribution": "get_year_distribution",
    "monthly_trend": "get_monthly_trend",
    "component_distribution": "get_symptom_distribution",
    "model_ranking": "get_model_distribution",
    "model_year_breakdown": "get_model_year_breakdown",
}
# TOOL_REGISTRY를 안 거치고 CHT-01이 직접 처리하는 intent들(아래 run_investigation 참고)
LOCAL_INTENTS = {"safety_flag_summary", "evidence_samples"}

_DF_CACHE: dict[tuple[str, str], pd.DataFrame] = {}


def _get_df(csv_path: str | Path | None = None, jsonl_path: str | Path | None = None) -> pd.DataFrame:
    """INV-01 load_enriched_df() 결과를 캐싱해서 재사용한다.
    2026-07-14: 예전엔 원본 CSV 하나만 읽는 load_processed(csv_path)였는데,
    새 INV-01은 원본 CSV + STR JSONL을 조인한 load_enriched_df(raw, jsonl)로
    바뀌어서 캐시 키도 (csv, jsonl) 튜플로 바꿨다."""
    csv_key = str(csv_path or RAW_CSV_PATH)
    jsonl_key = str(jsonl_path or STRUCT_JSONL_PATH)
    key = (csv_key, jsonl_key)
    if key not in _DF_CACHE:
        _DF_CACHE[key] = load_enriched_df(csv_key, jsonl_key)
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
    # 2026-07-14: 새 load_enriched_df()는 컬럼명이 소문자 "model"이다
    # (구 inv01_query_templates.load_processed()의 대문자 "MODELTXT"에서 변경됨).
    if df is not None and "model" in df.columns:
        models = sorted({str(x).strip().upper() for x in df["model"].dropna().unique()}, key=len, reverse=True)
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


def _extract_part_and_keywords(question: str) -> tuple[str | None, list[str], list[str]]:
    """반환: (part_category, 영문 키워드 목록, 매칭된 한국어 키워드 목록).

    2026-07-14: 새 INV-01의 _filter_base(df, part_category, symptom)는 symptom을
    STR 구조화 결과의 한국어 symptoms 리스트와 "부분 문자열 포함" 방식으로
    대조한다(원문 CDESCR 영어 검색이 아님). 그래서 영문 키워드만으론 새 INV-01
    필터에 못 넘기고, 매칭된 한국어 트리거 단어 자체가 필요해졌다 — 세 번째
    반환값이 그 용도다(예: "계기판" -> STR이 뽑은 "계기판 깜빡임" 같은 문구와
    부분 일치).
    """
    part: str | None = None
    keywords: list[str] = []
    ko_hits: list[str] = []
    for ko, p in PART_CATEGORY_BY_KO.items():
        if ko.lower() in question.lower():
            part = p
            break
    for ko, ens in TEXT_KEYWORDS_BY_KO.items():
        if ko.lower() in question.lower():
            keywords.extend(ens)
            ko_hits.append(ko)
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
    seen_ko = set()
    ko_out = []
    for k in ko_hits:
        if k not in seen_ko:
            seen_ko.add(k)
            ko_out.append(k)
    return part, out[:10], ko_out[:5]


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
    # 2026-07-14 신규: "차종×연식 조합"(예: "2025년식 투싼 집중도")은 반드시
    # "연식" 단독 체크보다 먼저 검사해야 한다 — 순서를 바꾸면 아래 "연식" 분기가
    # 먼저 걸려서 이 경로 자체가 영영 도달 불가능해진다(실제로 리팩터링 중
    # "차종별연식별 조합 알려줘"가 year_distribution으로 잘못 빠지는 걸 테스트로
    # 발견함). "차종"+"연식"이 함께 있거나 "조합"이 명시되면 이쪽으로 보낸다.
    if "조합" in q or ("차종" in q and ("연식" in q or "년식" in q)):
        return "model_year_breakdown"
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
    question: str,
    *,
    csv_path: str | Path | None = None,
    jsonl_path: str | Path | None = None,
    slots: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    질문 → 구조화 dict.
    TODO: LLM_CALL 교체 지점. 현재는 룰 기반으로 안정적인 데모를 먼저 만든다.

    slots: STR-05 extract_slots()가 이미 완료 판정한 결과({차종,차종_표시,증상}).
    주어지면 차종은 STR-05의 carRegistry 정규화 값을 그대로 신뢰하고(자체 정규식
    재추출 안 함), 증상 키워드/부품카테고리는 STR-05가 준 "증상" 문구를 기준으로
    추출한다. 주어지지 않으면(slots=None) 기존 방식(원문 전체에 정규식) 그대로.
    """
    df = _get_df(csv_path, jsonl_path)
    symptom_source = (slots.get("증상") if slots else None) or question
    if slots and slots.get("차종"):
        model = slots["차종"]
        part, keywords, ko_hits = _extract_part_and_keywords(symptom_source)
    else:
        model = _extract_model(question, df)
        part, keywords, ko_hits = _extract_part_and_keywords(question)
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
        # 2026-07-14 신규: 새 INV-01 _filter_base()가 요구하는 한국어 symptom 필터값.
        # STR-05 slots가 있으면 그 "증상" 문구를 그대로(가장 정확), 없으면 매칭된
        # 한국어 트리거 단어 중 첫 번째를 쓴다. 아무것도 없으면 None(필터 생략).
        "symptom_text": (slots.get("증상") if slots else None) or (ko_hits[0] if ko_hits else None),
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
    elif intent in LOCAL_INTENTS:
        action = "local_query"
    else:
        action = "query_template"

    # 2026-07-14: 새 INV-01 쿼리 함수들은 part_category/symptom 2개만 받는다
    # (구버전의 make/model/year/text_keywords 필터는 새 함수 시그니처에 없음 —
    # _filter_base(df, part_category, symptom) 참고). make/model/year는 여전히
    # parsed에 남겨서 화면 표시(scope 문구)와, 조합 조회 결과에서 특정
    # 차종·연식만 뽑아내는 후처리(run_investigation의 _slice_breakdown)에 쓴다.
    params = {
        "part_category": parsed.get("part_category"),
        "symptom": parsed.get("symptom_text"),
    }
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


_RAW_DF_CACHE: dict[str, pd.DataFrame] = {}


def _get_raw_df(csv_path: str | Path | None = None) -> pd.DataFrame:
    """원본 신고 CSV를 가공 없이 그대로 읽어 캐싱한다.

    2026-07-14 신규: 새 INV-01의 load_enriched_df()는 CRASH/FIRE/INJURED/DEATHS
    컬럼을 조인에서 아예 빼버린다(odino/model/model_year/date_filed만 원본에서
    가져옴 — query_templates.py의 load_enriched_df 본문 참고). 위험 플래그 요약은
    이 컬럼들이 있어야 계산되므로, enriched df를 거치지 않고 원본을 별도로 한 번
    더 읽는다. STR 구조화 결과와 조인할 필요가 없는 단순 집계라 이렇게 해도
    안전하다(원본 신고 전체 모집단 기준 통계가 오히려 더 정확함 — enriched df는
    STR이 이미 처리한 건으로만 한정돼 있어 모집단이 더 작음).
    """
    key = str(csv_path or RAW_CSV_PATH)
    if key not in _RAW_DF_CACHE:
        _RAW_DF_CACHE[key] = pd.read_csv(key)
    return _RAW_DF_CACHE[key]


def _flag_true(series: pd.Series) -> pd.Series:
    """CRASH/FIRE 같은 플래그 컬럼을 Y/N, True/False, 1/0 어떤 표기든 bool로 통일."""
    return series.astype(str).str.strip().str.upper().isin({"Y", "YES", "TRUE", "1"})


def _safety_flag_summary(csv_path: str | Path | None = None) -> dict[str, Any]:
    """화재/충돌/부상/사망 플래그 요약. 원본 CSV를 직접 읽는다(위 docstring 참고).

    반환 shape은 리팩터링 전과 동일하게 유지했다(total_count/fire_count/fire_pct/
    crash_count/crash_pct/injured_count/deaths_count) — compose_answer_text()의
    기존 분기를 그대로 재사용하기 위해서다.
    """
    try:
        raw = _get_raw_df(csv_path)
    except Exception as e:
        return {"status": "NO_DATA", "reason": f"원본 CSV를 읽지 못했습니다: {e}"}

    missing = [c for c in ("CRASH", "FIRE", "INJURED", "DEATHS") if c not in raw.columns]
    if missing:
        return {"status": "NO_DATA", "reason": f"원본 CSV에 다음 컬럼이 없습니다: {missing}"}

    total = len(raw)
    if total == 0:
        return {"status": "NO_DATA", "reason": "원본 CSV에 행이 없습니다."}

    fire_count = int(_flag_true(raw["FIRE"]).sum())
    crash_count = int(_flag_true(raw["CRASH"]).sum())
    injured_count = int(pd.to_numeric(raw["INJURED"], errors="coerce").fillna(0).sum())
    deaths_count = int(pd.to_numeric(raw["DEATHS"], errors="coerce").fillna(0).sum())

    return {
        "status": "ok",
        "total_count": total,
        "fire_count": fire_count,
        "fire_pct": round(fire_count / total * 100, 1),
        "crash_count": crash_count,
        "crash_pct": round(crash_count / total * 100, 1),
        "injured_count": injured_count,
        "deaths_count": deaths_count,
    }


def _evidence_samples_from_df(
    df: pd.DataFrame, part_category: str | None, symptom: str | None, limit: int = 8
) -> dict[str, Any]:
    """원문 근거(evidence_quote) 몇 건을 골라서 보여준다.

    2026-07-14 신규: 새 INV-01(query_templates.py)에는 "근거 샘플 몇 건 보여줘"에
    해당하는 함수가 없다(TOOL_REGISTRY에 없음 — 새 설계는 근거를 조사 루프
    내부에서만 다룬다). CHT-01이 필요로 하는 건 단순 필터+샘플링이라 INV-01
    조사 루프(투입 비용이 훨씬 큰 LLM 다단계 루프)까지 갈 필요 없이, enriched df
    (STR 구조화 결과가 이미 evidence_quote를 포함하고 있음)에서 직접 뽑는다.
    """
    if "evidence_quote" not in df.columns:
        return {"status": "no_data", "count": 0, "reason": "evidence_quote 컬럼이 없습니다(STR 산출물 확인 필요)."}

    sub = df.copy()
    if part_category and "part_category" in sub.columns:
        sub = sub[sub["part_category"] == part_category]
    if symptom and "symptoms" in sub.columns:
        sub = sub[sub["symptoms"].apply(lambda lst: any(symptom in s for s in lst) if isinstance(lst, list) else False)]
    sub = sub[sub["evidence_quote"].notna() & (sub["evidence_quote"].astype(str).str.strip() != "")]

    if len(sub) == 0:
        return {"status": "no_data", "count": 0}

    cols = [c for c in ("odino", "evidence_quote", "severity", "symptoms") if c in sub.columns]
    samples = sub[cols].head(limit).to_dict("records")
    return {"status": "ok", "count": len(sub), "samples": samples}


def run_investigation(
    plan: dict[str, Any],
    *,
    csv_path: str | Path | None = None,
    jsonl_path: str | Path | None = None,
    db_path: str | Path | None = None,
    llm_call: Callable[..., dict] = _stub_llm_call,
) -> dict[str, Any]:
    df = _get_df(csv_path, jsonl_path)
    action = plan["action"]
    parsed = plan["parsed"]

    if action == "ad_hoc_investigation":
        # 2026-07-14: investigate_ad_hoc() 시그니처가 통째로 바뀌었다.
        #   구: investigate_ad_hoc(df, make=, model=, year=, part_category=, text_keywords=)
        #   신: investigate_ad_hoc(question_parsed: dict, df, llm_call)
        # question_parsed의 키("model","symptom","part_category")는 investigation_loop_v2.py의
        # investigate_ad_hoc() 본문이 실제로 읽는 키만 맞추면 된다(model_year는 주석 예시에는
        # 있지만 본문에서 안 씀 - any([model, symptom]) 게이트에만 관여). "model"은 STR-05
        # 실제 산출물이 영문 코드(예: "TUCSON")라 그대로 넣는다 — 함수 내부에서 model 값 자체를
        # 문자열로 다시 파싱하지 않고 존재 여부만 확인하므로 영문 코드로도 문제없다.
        question_parsed = {
            "model": parsed.get("model"),
            "model_year": parsed.get("year"),
            "symptom": parsed.get("symptom_text"),
            "part_category": parsed.get("part_category"),
        }
        result = investigate_ad_hoc(question_parsed, df, llm_call)
        return {"kind": action, "result": result}

    if action == "status_query":
        return {"kind": action, "result": _query_status_db(parsed, db_path=db_path)}

    if action == "local_query":
        intent = parsed.get("intent")
        if intent == "safety_flag_summary":
            return {"kind": action, "template": "safety_flag_summary", "result": _safety_flag_summary(csv_path)}
        if intent == "evidence_samples":
            result = _evidence_samples_from_df(
                df, parsed.get("part_category"), parsed.get("symptom_text"), limit=8
            )
            return {"kind": action, "template": "evidence_samples", "result": result}
        return {"kind": action, "error": f"알 수 없는 로컬 intent: {intent}"}

    template = plan.get("template")
    if not template:
        return {"kind": action, "error": "질문 의도를 쿼리 템플릿에 매핑하지 못했습니다."}
    if template not in TOOL_REGISTRY:
        return {"kind": action, "error": f"INV-01 TOOL_REGISTRY에 없는 템플릿입니다: {template}"}

    func = TOOL_REGISTRY[template]["func"]
    params = dict(plan.get("params") or {})
    if template == "get_monthly_trend":
        params.setdefault("months", parsed.get("months") or 12)

    # 2026-07-14: TOOL_REGISTRY 6개 함수 전부 part_category가 "필수" 위치 인자다
    # (기본값 없음 - inspect.signature로 실측 확인함, 하나라도 안 넘기면
    # TypeError). 질문에서 부품 카테고리를 못 뽑았으면 프로젝트 기본 범위인
    # 전장/SW로 채우되, 사용자가 요청하지 않은 범위로 조용히 좁혀지는 것이므로
    # defaulted 플래그를 남겨서 답변에서 투명하게 밝힌다("전체" 아니라
    # "ELECTRICAL_SYSTEM 기준"이라고).
    defaulted_part_category = "part_category" not in params
    params.setdefault("part_category", "ELECTRICAL_SYSTEM")

    # get_symptom_distribution(df, part_category)만 symptom 인자 자체가 없다
    # (나머지 5개는 symptom=None 기본값 있음 - 역시 실측 확인). 함수가 실제로
    # 받는 키워드만 골라 넘겨서, TOOL_REGISTRY 쪽 시그니처가 앞으로 바뀌어도
    # 이 호출부가 안 죽게 했다(하드코딩 특례를 늘리는 대신 시그니처 기반으로).
    accepted = set(inspect.signature(func).parameters.keys())
    params = {k: v for k, v in params.items() if k in accepted}

    result = func(df, **params)

    # 2026-07-14: 새 INV-01 함수들은 make/model/year로 필터링하지 않고 항상
    # "part_category(+symptom) 전체 분포"를 돌려준다(_filter_base 참고 - 그 두
    # 파라미터만 받음). 사용자가 특정 차종·연식을 물었으면(예: "2025년식 투싼"),
    # 전체 분포에서 그 조합만 뽑아 answer 단계에서 강조할 수 있도록 slice를 같이
    # 담아 보낸다. compose_answer_text가 이 slice를 우선 사용한다.
    sliced = _slice_breakdown(result, template, parsed.get("model"), parsed.get("year"))
    return {
        "kind": action,
        "template": template,
        "result": result,
        "sliced": sliced,
        "part_category_used": params.get("part_category"),
        "part_category_defaulted": defaulted_part_category,
    }


def _slice_breakdown(result: dict[str, Any], template: str, model: str | None, year: str | None) -> dict[str, Any] | None:
    """get_model_year_breakdown/get_year_distribution/get_model_distribution 결과에서
    사용자가 물은 특정 차종·연식 조합만 뽑아낸다. 해당 없으면 None."""
    if not isinstance(result, dict) or result.get("status") != "ok":
        return None

    if template == "get_model_year_breakdown" and (model or year):
        breakdown = result.get("breakdown", {})
        if model and model in breakdown:
            model_years = breakdown[model]
            if year and year in model_years:
                return {"model": model, "year": year, "count": model_years[year]}
            return {"model": model, "years": model_years, "count": sum(model_years.values())}
        return None

    if template == "get_year_distribution" and year:
        count = result.get("year_counts", {}).get(str(year))
        return {"year": year, "count": count} if count is not None else None

    if template == "get_model_distribution" and model:
        count = result.get("model_counts", {}).get(model)
        return {"model": model, "count": count} if count is not None else None

    return None


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
        # investigate_ad_hoc()(run_investigation_loop) 결과는 "status"가 아니라
        # "overall_status"를 쓴다(RETAINED/REJECTED/HOLD). 2026-07-14 신규 분기.
        if investigation.get("kind") == "ad_hoc_investigation":
            overall = result.get("overall_status")
            if overall == "HOLD":
                return {"status": "INSUFFICIENT", "reason": result.get("decision_reason") or "근거 부족(HOLD)"}
            if overall in {"RETAINED", "REJECTED"}:
                return {"status": "PASS", "reason": f"조사 루프 완료({overall})"}
            return {"status": "INSUFFICIENT", "reason": f"알 수 없는 overall_status: {overall!r}"}

        # 새 INV-01 쿼리 함수는 status를 소문자로 준다("no_data"/"ok").
        # STA 쪽(_query_status_db)과 safety_flag_summary는 기존처럼 대문자를 쓴다
        # (STA는 이 파일이 직접 관리하는 값이라 원래 관례 유지) — 그래서 대소문자
        # 둘 다 받아야 한다.
        status_val = result.get("status")
        if status_val in {"no_data", "NO_DATA", "NO_DB", "UNAVAILABLE", "no_match", "no_us_recall"}:
            return {"status": "INSUFFICIENT", "reason": result.get("reason") or str(status_val)}
        if status_val == "INSUFFICIENT":
            return {"status": "INSUFFICIENT", "reason": result.get("decision_reason", "근거 부족")}
        if status_val == "REJECTED":
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
    kind = investigation.get("kind")

    if review_status == "FAIL":
        return f"요청을 처리하지 못했습니다. 사유: {review_result.get('reason')}"

    # ---------------------------------------------------------------
    # ad_hoc_investigation: investigate_ad_hoc() -> run_investigation_loop() 결과.
    # 2026-07-14: 결과 shape이 완전히 바뀌었다.
    #   구: {status, decision_reason, support_count, summary:{base_count,recent_surge}, evidence_samples}
    #   신: {overall_status, final_hypothesis:{hypothesis,query_executed,query_result,
    #        is_retained,status,decision_reason}, full_log:[...]}
    # ---------------------------------------------------------------
    if kind == "ad_hoc_investigation" and isinstance(result, dict):
        overall = result.get("overall_status")
        final = result.get("final_hypothesis") or {}
        full_log = result.get("full_log") or []

        if overall == "HOLD" and not final:
            return (
                f"{scope} 기준으로 조사했지만, {result.get('decision_reason', '근거가 부족해 판단을 보류했습니다.')} "
                "차종·증상을 조금 더 구체적으로 알려주시면 다시 조사해볼게요."
            )

        lines = [
            f"{scope} 기준으로 조사했습니다. (가설 {len(full_log)}개 검토, 최종 상태: {overall})",
            f"가설: {final.get('hypothesis', '(가설 없음)')}",
        ]
        if final.get("decision_reason"):
            lines.append(f"판단 근거: {final['decision_reason']}")

        # query_executed/query_result에 실제 조사 로그가 남아있으면 몇 줄만 요약해서 보여준다.
        query_executed = final.get("query_executed") or []
        if query_executed:
            lines.append(f"조사 단계: {' → '.join(query_executed[:4])}" + (" …" if len(query_executed) > 4 else ""))

        is_retained = final.get("is_retained")
        if is_retained is True:
            lines.append("결론: 가설이 데이터로 뒷받침됨(RETAINED).")
        elif is_retained is False:
            lines.append("결론: 가설이 데이터로 뒷받침되지 않음(REJECTED) — 다른 원인을 볼 필요가 있습니다.")
        else:
            lines.append("결론: 근거가 애매해 확정하지 않고 보류(HOLD)했습니다.")

        lines.append("단, 이는 NHTSA 소비자 신고 기반 시그널 후보이며 결함 또는 리콜 확정이 아닙니다.")
        return "\n".join(lines)

    # ---------------------------------------------------------------
    # status_query: STA defect_signals 조회 — INV 변경과 무관, 기존 그대로.
    # ---------------------------------------------------------------
    if kind == "status_query" and isinstance(result, dict):
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

    # ---------------------------------------------------------------
    # local_query: safety_flag_summary(원본 CSV 직접 집계) / evidence_samples(자체 필터)
    # ---------------------------------------------------------------
    if kind == "local_query" and isinstance(result, dict):
        template = investigation.get("template")
        if template == "safety_flag_summary":
            if result.get("status") not in {"ok", "OK"}:
                return f"위험 플래그 요약을 계산하지 못했습니다. 사유: {result.get('reason')}"
            return (
                f"{scope} 기준 위험 플래그 요약입니다. 전체 {result.get('total_count', 0)}건 중 "
                f"화재 {result.get('fire_count', 0)}건({result.get('fire_pct', 0)}%), "
                f"충돌 {result.get('crash_count', 0)}건({result.get('crash_pct', 0)}%), "
                f"부상 {result.get('injured_count', 0)}건, 사망 {result.get('deaths_count', 0)}건입니다. "
                "미검증 소비자 신고 기준이며 결함 확정이 아닙니다."
            )
        if template == "evidence_samples":
            if result.get("status") != "ok":
                return f"{scope} 조건의 원문 근거를 찾지 못했습니다."
            samples = result.get("samples", [])
            cite_bits = [f"ODINO {s.get('odino')}: {str(s.get('evidence_quote', ''))[:120]}" for s in samples[:3]]
            return (
                f"{scope} 조건의 원문 근거 {result.get('count', 0)}건 중 일부입니다.\n"
                + " | ".join(cite_bits)
                + "\n단, 이는 소비자 신고 원문 발췌이며 결함 확정이 아닙니다."
            )
        return f"{scope} 기준 조회 결과입니다. 미검증 소비자 신고 데이터 기준이며 결함 확정이 아닙니다."

    # ---------------------------------------------------------------
    # query_template: 새 INV-01 TOOL_REGISTRY 함수들의 결과.
    # sliced가 있으면(사용자가 특정 차종·연식을 물었을 때) 그걸 우선 강조하고,
    # 없으면 전체 분포를 요약한다.
    # ---------------------------------------------------------------
    if isinstance(result, dict):
        sliced = investigation.get("sliced")
        template = investigation.get("template")
        defaulted = investigation.get("part_category_defaulted")
        used_category = investigation.get("part_category_used")
        default_note = (
            f" (부품 카테고리를 지정하지 않아 기본값 {used_category} 기준으로 좁혀 조회했습니다.)"
            if defaulted else ""
        )

        if result.get("status") not in {"ok", "OK"}:
            return f"{scope} 조건의 데이터를 찾지 못했습니다.{default_note}"

        core_text: str
        if sliced is not None and "year" in sliced:
            core_text = (
                f"{scope} 조건에서 {sliced['model']} {sliced['year']}년식은 {sliced['count']}건입니다 "
                f"(전체 {result.get('total_reports', '?')}건 중). 미검증 소비자 신고 기준이며 결함 확정이 아닙니다."
            )
        elif sliced is not None and "model" in sliced and "years" in sliced:
            years_txt = ", ".join(f"{y}년식 {c}건" for y, c in sliced["years"].items())
            core_text = (
                f"{scope} 조건에서 {sliced['model']}은 총 {sliced['count']}건입니다 ({years_txt}). "
                "미검증 소비자 신고 기준이며 결함 확정이 아닙니다."
            )
        elif sliced is not None and "model" in sliced:
            core_text = (
                f"{scope} 조건에서 {sliced['model']}은 {sliced['count']}건입니다 "
                f"(전체 {result.get('total_reports', '?')}건 중). 미검증 소비자 신고 기준이며 결함 확정이 아닙니다."
            )
        elif template == "get_model_year_breakdown":
            top = result.get("top_combo", {})
            core_text = (
                f"{scope} 기준 차종×연식 분포입니다. 전체 {result.get('total_reports', 0)}건 중 "
                f"가장 집중된 조합은 {top.get('model')} {top.get('model_year')}년식으로 "
                f"{top.get('count', 0)}건({top.get('share_pct', 0)}%)입니다. "
                "미검증 소비자 신고 기준이며 결함 확정이 아닙니다."
            )
        elif template == "get_year_distribution":
            counts = result.get("year_counts", {})
            top_year = max(counts, key=counts.get) if counts else None
            core_text = (
                f"{scope} 기준 연식별 분포입니다. 전체 {result.get('total_reports', 0)}건, "
                + (f"가장 많은 연식은 {top_year}년식({counts.get(top_year, 0)}건)입니다. " if top_year else "")
                + "미검증 소비자 신고 기준이며 결함 확정이 아닙니다."
            )
        elif template == "get_model_distribution":
            counts = result.get("model_counts", {})
            top_model = max(counts, key=counts.get) if counts else None
            core_text = (
                f"{scope} 기준 차종별 분포입니다. 전체 {result.get('total_reports', 0)}건, "
                + (f"가장 많은 차종은 {top_model}({counts.get(top_model, 0)}건)입니다. " if top_model else "")
                + "미검증 소비자 신고 기준이며 결함 확정이 아닙니다."
            )
        elif template == "get_monthly_trend":
            counts = result.get("monthly_counts", {})
            core_text = (
                f"{scope} 기준 최근 월별 추이입니다(총 {result.get('total_reports', 0)}건). "
                f"월별 건수: {counts}. 미검증 소비자 신고 기준이며 결함 확정이 아닙니다."
            )
        elif template == "get_symptom_distribution":
            counts = result.get("symptom_counts", {})
            top_symptom = max(counts, key=counts.get) if counts else None
            core_text = (
                f"{scope} 기준 증상 분포입니다. 전체 {result.get('total_reports', 0)}건, "
                + (f"가장 흔한 증상은 '{top_symptom}'({counts.get(top_symptom, 0)}건)입니다. " if top_symptom else "")
                + "미검증 소비자 신고 기준이며 결함 확정이 아닙니다."
            )
        else:
            core_text = f"{scope} 기준 조회 결과입니다. 미검증 소비자 신고 데이터 기준이며 결함 확정이 아닙니다."

        return core_text + default_note

    if isinstance(result, pd.DataFrame):
        return (
            f"{scope} 기준으로 {len(result)}행의 조회 결과를 반환합니다. "
            "상위 20행만 data에 담았습니다. 미검증 소비자 신고 데이터 기준입니다."
        )

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
    jsonl_path: str | Path | None = None,
    db_path: str | Path | None = None,
    slot_state: dict[str, Any] | None = None,
    llm_call: Callable[..., dict] = _stub_llm_call,
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

    jsonl_path: 2026-07-14 신규. 새 INV-01(load_enriched_df)이 원본 CSV와 STR
    구조화 JSONL을 조인해서 쓰기 때문에 CHT-01도 이제 이 경로가 필요하다.
    기본값은 query_templates.STRUCT_JSONL_PATH.

    llm_call: investigate_ad_hoc()(조사 루프)이 내부적으로 호출할 LLM 콜백.
    팀 공용 API 래퍼가 준비되면 이 인자로 실제 함수를 넘기면 되고, 그 전까지는
    기본값(_stub_llm_call, 결정론적 임시 동작)으로 데모가 계속 돌아간다.
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
    parsed = parse_question(question, csv_path=csv_path, jsonl_path=jsonl_path, slots=slots)
    plan = structure_query(parsed)
    investigation = run_investigation(plan, csv_path=csv_path, jsonl_path=jsonl_path, db_path=db_path, llm_call=llm_call)
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
    # 실제 팀 데이터 경로(query_templates.RAW_CSV_PATH/STRUCT_JSONL_PATH,
    # sta01_02_status_tracking.DEFAULT_DB_PATH) 기준 스모크 테스트.
    # llm_call은 명시 안 하면 _stub_llm_call(결정론적 임시 동작)이 자동 사용된다 —
    # 실제 LLM 붙일 때는 chat(..., llm_call=real_llm_call)로 넘기면 됨.
    history: list[dict[str, Any]] = []
    tests = [
        "2025년식 투싼 계기판 꺼짐 최근 6개월 시그널 있어?",
        "기아 연식별 불만 분포 보여줘",
        "현대 부품 라벨 상위 알려줘",
        "화재나 충돌 플래그 요약해줘",
        "리콜 후 재발 상태 추적 기록 보여줘",
        "투싼 차종별 연식별 조합 알려줘",
    ]
    for q in tests:
        ans = chat(q, history)
        print("\nQ:", q)
        print("A:", ans["answer_text"][:800])
    print(f"\n[HISTORY] {len(history)} turns")
