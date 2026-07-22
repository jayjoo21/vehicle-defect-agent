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
    2. check_recall_match() / get_us_kr_gap()의 서로 다른 현재 상태:
       - get_us_kr_gap(model, us_recalls_df, kr_recalls_df): 2026-07-16에
         recall_crossref.csv를 읽어 두 DataFrame으로 쪼개는 어댑터
         (_load_us_kr_recall_dfs/_us_kr_gap_lookup)를 만들어 이미 연동
         완료했다 — local_query의 "us_kr_gap" intent가 이 경로를 탄다.
       - check_recall_match(model, model_year, recalls_df): 2026-07-21
         재검토 후 **의도적으로 미연동 상태를 유지**하기로 했다. 이 함수가
         기대하는 "recalls_df"(정답지 CSV)는 경로·스키마가 끝까지 확정된 적이
         없고, 그 자리를 STA의 recall_records(rcl573_classify_compdesc.py로
         Gemini 분류한 compdesc1 정확 매칭 + 실제 NHTSA RCL573 리콜 264건)가
         이미 더 정밀하게 대체하고 있다(_query_status_db/find_all_matching_
         recalls 경유). 지금 이 함수를 원래 설계대로 연결하면 검증도 안 된
         별도 정답지로 되돌아가는 퇴보라 연결하지 않았다 — 아래 _detect_intent
         에 "리콜" 키워드를 추가해 그 질문들이 STA 경로로 가도록 대신 메웠다.
    3. safety_flag_summary는 load_enriched_df() 결과가 아니라 원본 CSV를 별도로
       한 번 더 읽는다(_safety_flag_summary 참고) — CRASH/FIRE/INJURED/DEATHS가
       enriched df 조인에서 빠지기 때문. 모집단이 달라질 수 있음(원본 CSV 전체 vs
       STR이 처리한 건수)을 알고 있을 것.


⚠️ 2026-07-20 개정 — v3(8종 LLM 창작 taxonomy) → v4(NHTSA 원본 COMPDESC 그대로
    파싱) 카테고리 체계 전환 반영.
    문제: PART_CATEGORY_BY_KO가 여전히 v3 8종(ELECTRICAL_SYSTEM/ADAS/
    INSTRUMENT_CLUSTER/PROPULSION_BATTERY/BRAKES_ELECTRONIC/POWERTRAIN_SW/
    NON_ELECTRICAL/INSUFFICIENT_INFO, 언더스코어 표기)으로 매핑돼 있었는데,
    실제 str01_sample100_v4_results.jsonl(및 이를 조인한 load_enriched_df()의
    part_category 별칭 컬럼)의 compdesc1 실측값은 NHTSA 원본 그대로인 7종
    (ELECTRICAL SYSTEM / UNKNOWN OR OTHER / FORWARD COLLISION AVOIDANCE /
    VEHICLE SPEED CONTROL / LANE DEPARTURE / BACK OVER PREVENTION /
    ELECTRONIC STABILITY CONTROL (ESC), 전부 공백 표기)이다. 그 결과 "계기판",
    "기아", "투싼" 등 카테고리가 걸리는 질문이 전부 문자열 불일치로 no_data가
    나는 게 실행 로그로 확인됨(2026-07-20).
    또한 "ADAS"처럼 v3에서는 단일 카테고리였던 개념이 v4에는 대응하는 단일
    대분류가 없고 FORWARD COLLISION AVOIDANCE/LANE DEPARTURE/BACK OVER
    PREVENTION/VEHICLE SPEED CONTROL/ELECTRONIC STABILITY CONTROL (ESC) 5개
    대분류에 흩어져 있음(원본 CSV 실측, hk_electrical_recent_full_REAL.csv).
    조치:
      - PART_CATEGORY_BY_KO를 v4 실제값(공백 표기)으로 전면 재매핑.
      - 여러 대분류를 묶어야 하는 한국어 키워드는 새 PART_CATEGORY_GROUPS로
        분리(단일 문자열이 아니라 list[str]).
      - _extract_part_and_keywords()가 (part, keywords, ko_hits, part_group)
        4개를 반환하도록 확장. part_group이 있으면 part는 None.
      - parse_question()의 기본값 폴백 "ELECTRICAL_SYSTEM" → "ELECTRICAL SYSTEM".
      - run_investigation()의 query_template 분기에 그룹 순회 조회 경로 추가
        (TOOL_REGISTRY 함수를 대분류별로 여러 번 호출 후 _merge_category_results로
        합산). 기본값도 공백 표기로 교체.
    한계(알려진 채로 남겨둠): PART_CATEGORY_BY_KO의 "계기판"/"배터리"처럼 v4에
    전용 대분류가 없는 개념은 가장 근접한 단일 카테고리(ELECTRICAL SYSTEM)로
    근사 매핑했다 — 완벽한 의미 일치는 아니며, STR 트랙에서 별도 세분류가
    추가되면 갱신 필요.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import inspect
import os
import re
import sys

import pandas as pd

# ⚠️ 2026-07-14 개정 — 효선님의 실제 INV-01/02/03 파일(query_templates.py,
# investigation_loop_v2.py) 수령 후 CHT-01을 전면 재작업했다. 기존에 CHT-01이
# 기대하던 인터페이스(run_query_template, q_vehicle_component_summary,
# load_processed, DEFAULT_CSV_PATH, investigate_ad_hoc(df, make=, model=, ...))가
# 새 파일에는 전혀 없다 — INV 트랙이 처음부터 다시 설계된 것에 가깝다. 아래는
# 새 인터페이스 기준으로 다시 연결한 것.
from query_templates import (
    INSUFFICIENT_EVIDENCE,
    INSUFFICIENT_SYMPTOM,
    RAW_CSV_PATH,
    STRUCT_JSONL_PATH,
    TOOL_REGISTRY,
    get_us_kr_gap,
    load_enriched_df,
)
from investigation_loop_v2 import investigate_ad_hoc

try:
    from sta01_02_status_tracking import (
        DEFAULT_DB_PATH,
        SIGNAL_LABEL_KO,
        SIGNAL_PRIORITY_ORDER,
        init_db,
        query_signal_summary,
    )
    _STA_IMPORT_ERROR = None
except ImportError as _e:  # STA 파일이 없는 배포에서는 통계 질의만 계속 제공한다.
    DEFAULT_DB_PATH = Path("data/processed/defect_status_tracking.db")
    init_db = None
    query_signal_summary = None
    SIGNAL_LABEL_KO = {}
    SIGNAL_PRIORITY_ORDER = {}
    _STA_IMPORT_ERROR = _e

# 2026-07-16: 효선님이 실제 Gemini 연동 함수(real_llm_call.py)를 완성해서 전달.
# google-genai 패키지가 안 깔려 있거나 GEMINI_API_KEY가 없는 환경(로컬 개발/이 코드를
# API 키 없이 열어보는 경우 등)에서도 import 자체가 죽지 않도록 방어적으로 불러온다.
# 실패하면 REAL_LLM_CALL_AVAILABLE만 False로 남고 코드는 계속 동작한다 — chat()의
# 기본 llm_call은 여전히 _stub_llm_call(아래)이라 이 import 성패와 무관하게 항상 실행
# 가능하고, 실제 LLM을 쓰려면 chat(..., llm_call=real_llm_call)로 명시하면 된다.
try:
    from real_llm_call import real_llm_call
    REAL_LLM_CALL_AVAILABLE = True
    _REAL_LLM_CALL_IMPORT_ERROR = None
except ImportError as _e:
    real_llm_call = None
    REAL_LLM_CALL_AVAILABLE = False
    _REAL_LLM_CALL_IMPORT_ERROR = _e

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
    except (ImportError, AttributeError):
        try:
            module = __import__("scripts.str05_query_understanding", fromlist=[name])
            return getattr(module, name)
        except (ImportError, AttributeError):
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
        target_model = context.get("target_model")
        target_year = context.get("target_model_year")
        if target_model:
            target = f"{target_model} {target_year}년식" if target_year else str(target_model)
            return {"hypothesis": f"{target}의 증상 분포가 해당 부품군에서 집중되는지 확인한다(스텁 가설)."}
        scouting = context.get("scouting_results", {})
        symptom_dist = scouting.get("get_symptom_distribution", {}) or {}
        counts = symptom_dist.get("symptom_counts") or {}
        if counts:
            top_symptom = max(counts, key=counts.get)
            return {"hypothesis": f"'{top_symptom}' 증상이 신고에서 두드러지게 반복되고 있다(스텁 가설, 실제 LLM 아님)."}
        return {"hypothesis": "정찰 결과에서 뚜렷한 패턴을 찾지 못함(스텁 가설, 실제 LLM 아님)."}

    if prompt_type == "select_query_or_conclude":
        target_model = context.get("target_model")
        results = context.get("results_so_far") or []
        if target_model and len(results) == 1:
            params = {"model": target_model}
            if context.get("target_model_year"):
                params["model_year"] = context["target_model_year"]
            return {
                "action": "query",
                "query_name": "get_symptom_distribution_by_model",
                "params": params,
            }
        return {"action": "conclude"}

    if prompt_type == "judge_hypothesis":
        all_results = context.get("all_results", [])
        if context.get("target_model") and len(all_results) > 1:
            symptom_dist = all_results[-1] if isinstance(all_results[-1], dict) else {}
        else:
            scouting = all_results[0] if all_results else {}
            symptom_dist = scouting.get("get_symptom_distribution", {}) if isinstance(scouting, dict) else {}
        total = symptom_dist.get("total_reports", 0) if isinstance(symptom_dist, dict) else 0
        if total >= 3:
            return {"is_retained": True, "reason": f"정찰 단계 관련 신고 {total}건(스텁 판정, 실제 LLM 아님)."}
        return {"is_retained": None, "reason": f"정찰 단계 관련 신고 {total}건으로 근거 부족(스텁 판정, 실제 LLM 아님)."}

    raise ValueError(f"알 수 없는 prompt_type: {prompt_type!r}")


# 2026-07-20 재작성: v3(8종 LLM 창작 taxonomy) -> v4(NHTSA 원본 COMPDESC 그대로
# 파싱) 전환 반영. v4 compdesc1 실측값 7종(공백 표기, 언더스코어 아님):
#   ELECTRICAL SYSTEM(6,837건) / UNKNOWN OR OTHER(5,711) /
#   FORWARD COLLISION AVOIDANCE(2,057) / VEHICLE SPEED CONTROL(1,439) /
#   LANE DEPARTURE(630) / BACK OVER PREVENTION(273) /
#   ELECTRONIC STABILITY CONTROL (ESC)(17)
# (hk_electrical_recent_full_REAL.csv 16,964행 전수 집계, 2026-07-20)
#
# v4엔 "계기판", "배터리", "동력" 같은 v3식 세부 대분류가 없다 — 이런 키워드는
# 가장 근접한 단일 카테고리로 근사 매핑한다(완벽한 의미 일치 아님, 알려진 한계).
PART_CATEGORY_BY_KO = {
    "계기판": "ELECTRICAL SYSTEM",
    "클러스터": "ELECTRICAL SYSTEM",
    "게이지": "ELECTRICAL SYSTEM",
    "속도계": "ELECTRICAL SYSTEM",
    "전기": "ELECTRICAL SYSTEM",
    "배터리": "ELECTRICAL SYSTEM",
    "충전": "ELECTRICAL SYSTEM",
    "고전압": "ELECTRICAL SYSTEM",
    "시동": "ELECTRICAL SYSTEM",
    "엔진": "ELECTRICAL SYSTEM",
    "차선": "LANE DEPARTURE",
    "카메라": "BACK OVER PREVENTION",
    "후방": "BACK OVER PREVENTION",
    "크루즈": "FORWARD COLLISION AVOIDANCE",
    "속도": "VEHICLE SPEED CONTROL",
}

# 2026-07-20 신규: 한 한국어 키워드가 v4의 여러 compdesc1에 걸쳐 있는 경우.
# PART_CATEGORY_BY_KO(단일 매핑)보다 먼저 확인되며, 매칭되면 여러 대분류를
# 순회 조회해서 결과를 합산한다(_merge_category_results 참고). 원본 CSV 실측
# 근거(2026-07-20): FORWARD COLLISION AVOIDANCE/LANE DEPARTURE/BACK OVER
# PREVENTION/VEHICLE SPEED CONTROL/ELECTRONIC STABILITY CONTROL (ESC)가 전부
# "주행 보조/능동 안전" 성격이라 "ADAS"라는 통합 질문은 이 5개를 다 봐야 답이 됨.
PART_CATEGORY_GROUPS: dict[str, list[str]] = {
    "ADAS": [
        "FORWARD COLLISION AVOIDANCE",
        "LANE DEPARTURE",
        "BACK OVER PREVENTION",
        "VEHICLE SPEED CONTROL",
        "ELECTRONIC STABILITY CONTROL (ESC)",
    ],
    "센서": ["FORWARD COLLISION AVOIDANCE", "LANE DEPARTURE", "BACK OVER PREVENTION"],
    "제동": ["FORWARD COLLISION AVOIDANCE", "BACK OVER PREVENTION"],
    "브레이크": ["FORWARD COLLISION AVOIDANCE", "BACK OVER PREVENTION"],
    "동력": ["VEHICLE SPEED CONTROL"],
    "출력": ["VEHICLE SPEED CONTROL"],
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
# 2026-07-20 수정: STR-05(str05_query_understanding.py)의 CAR_MODELS 27종
# registry와 대조해서 13종만 반영돼 있던 걸 27종 전부로 확장했다(EV9 등 15종
# 누락 — EV9은 이 프로젝트 대표 실증 사례라 특히 치명적). 접두어 충돌 방지를
# 위해 "NIRO EV"를 "NIRO"보다 먼저 배치(dict는 삽입 순서를 유지하므로
# _extract_model의 순차 매칭에서 긴 별칭이 먼저 걸린다).
MODEL_ALIASES = {
    "TUCSON": ["투싼", "tucson"],
    "SANTA FE": ["싼타페", "santa fe", "santafe"],
    "SANTA CRUZ": ["싼타크루즈", "santa cruz", "santacruz"],
    "SONATA": ["쏘나타", "소나타", "sonata"],
    "ELANTRA": ["아반떼", "elantra"],
    "KONA": ["코나", "kona"],
    "IONIQ 5": ["아이오닉5", "아이오닉 5", "ioniq 5", "ioniq5"],
    "IONIQ 6": ["아이오닉6", "아이오닉 6", "ioniq 6", "ioniq6"],
    "ACCENT": ["엑센트", "accent"],
    "VELOSTER": ["벨로스터", "veloster"],
    "VENUE": ["베뉴", "venue"],
    "NEXO": ["넥쏘", "넥소", "nexo"],
    "SORENTO": ["쏘렌토", "소렌토", "sorento"],
    "SPORTAGE": ["스포티지", "sportage"],
    "FORTE": ["포르테", "forte"],
    "SOUL": ["쏘울", "소울", "soul"],
    "TELLURIDE": ["텔루라이드", "telluride"],
    "CARNIVAL": ["카니발", "carnival"],
    "STINGER": ["스팅어", "stinger"],
    "SELTOS": ["셀토스", "seltos"],
    "RIO": ["리오", "rio"],
    "K5": ["K5", "k5"],
    "EV6": ["EV6", "ev6", "이브이6", "이브이식스"],
    "EV9": ["EV9", "ev9", "이브이9", "이브나인"],
    "NIRO EV": ["니로EV", "니로ev", "니로 ev", "niro ev", "niroev", "니로이브이"],
    "NIRO": ["니로", "niro"],
    "PALISADE": ["팰리세이드", "palisade"],
    "RAY": ["레이", "ray"],
}

# 2026-07-20 신규: "브레이크 문제 있어?" 질문에서 RAY(별칭 "레이")가 엉뚱하게
# 잡히던 버그(실행 로그로 확인) — "레이"가 "브레이크"라는 흔한 단어 안에
# 우연히 통째로 들어있어서, 단순 부분 문자열 포함 검사(a.lower() in q)로는
# 구분이 안 됐다. 정규식 단어 경계(\b)로는 못 고친다 — 한글은 조사가 붙어도
# (예: "레이가", "레이는") 공백 없이 이어지는 한 글자 흐름이라 \b가 모델명과
# 조사 사이에서도 걸리지 않기 때문에, 오히려 "레이가 이상해요" 같은 정상
# 케이스까지 깨진다(실측 확인). 대신 "이 별칭이 오직 이 특정 상위 단어의
# 일부로만 등장한다"를 알고 있는 경우만 그 상위 단어를 제거하고 나서
# 남아있는지 재확인하는 방식으로 좁혀 잡는다 — 정상적인 "레이가/레이는" 등은
# 그대로 유지하면서 "브레이크"만 걸러진다(아래 _alias_hits로 전수 검증 완료:
# 현재 MODEL_ALIASES/MAKE_ALIASES 중 이 케이스가 유일한 실충돌).
MODEL_ALIAS_EXCLUSIONS: dict[str, list[str]] = {
    "레이": ["브레이크"],
    "ray": ["brake"],
}


def _alias_hits(question_lower: str, alias_lower: str) -> bool:
    """별칭이 질문에 등장하는지 확인하되, MODEL_ALIAS_EXCLUSIONS에 등록된 더 큰
    단어의 일부로만 등장하는 경우는 오탐으로 제외한다."""
    if alias_lower not in question_lower:
        return False
    exclusions = MODEL_ALIAS_EXCLUSIONS.get(alias_lower)
    if not exclusions:
        return True
    stripped = question_lower
    for bad in exclusions:
        stripped = stripped.replace(bad, "")
    return alias_lower in stripped

# 2026-07-16: MODEL_ALIASES의 첫 번째 별칭이 한국어 표기다 — recall_crossref.csv처럼
# 한국어 모델명을 쓰는 데이터와 매칭할 때 역방향(영문 코드 -> 한국어 표기)이 필요해서
# 여기서 한 번만 만들어 재사용한다.
MODEL_EN_TO_KO: dict[str, str] = {en: aliases[0] for en, aliases in MODEL_ALIASES.items()}

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
LOCAL_INTENTS = {"safety_flag_summary", "evidence_samples", "us_kr_gap"}

_DF_CACHE: dict[tuple[str, str], pd.DataFrame] = {}


def _repair_date_filed(df: pd.DataFrame) -> pd.DataFrame:
    """구버전 쿼리 모듈이 YYYYMMDD 정수를 나노초로 읽은 경우 날짜를 복구한다."""
    if "date_filed" not in df.columns or df["date_filed"].isna().all():
        return df
    sample = df["date_filed"].dropna()
    if len(sample) == 0:
        return df
    # 깨졌으면 전부 1970-01-02 이전(=epoch 근처 나노초 값)에 몰려있다.
    looks_broken = (sample < pd.Timestamp("1970-01-02")).mean() > 0.95
    if not looks_broken:
        return df

    as_int = df["date_filed"].astype("int64")  # NaT는 int64 최소값이 됨
    repaired = pd.to_datetime(
        as_int.where(as_int > 0).astype("Int64").astype(str),
        format="%Y%m%d", errors="coerce",
    )
    df = df.copy()
    df["date_filed"] = repaired
    n_fixed = repaired.notna().sum()
    print(
        f"[CHT01][WARN] date_filed가 깨진 상태(FAILDATE 정수 오인식, query_templates.py "
        f"쪽 이슈)로 감지되어 자체 복구했습니다. 복구된 날짜 {n_fixed:,}/{len(df):,}건. "
        "query_templates.py도 dtype=str로 읽는지 확인하세요."
    )
    return df


def _get_df(csv_path: str | Path | None = None, jsonl_path: str | Path | None = None) -> pd.DataFrame:
    """INV-01 load_enriched_df() 결과를 캐싱해서 재사용한다.
    2026-07-14: 예전엔 원본 CSV 하나만 읽는 load_processed(csv_path)였는데,
    새 INV-01은 원본 CSV + STR JSONL을 조인한 load_enriched_df(raw, jsonl)로
    바뀌어서 캐시 키도 (csv, jsonl) 튜플로 바꿨다.
    2026-07-16: load_enriched_df() 결과의 date_filed를 _repair_date_filed()로
    한 번 더 방어적으로 검증·복구한다(바로 위 함수 docstring 참고)."""
    csv_key = str(csv_path or RAW_CSV_PATH)
    jsonl_key = str(jsonl_path or STRUCT_JSONL_PATH)
    key = (csv_key, jsonl_key)
    if key not in _DF_CACHE:
        _DF_CACHE[key] = _repair_date_filed(load_enriched_df(csv_key, jsonl_key))
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
        if any(_alias_hits(q, a.lower()) for a in aliases):
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


def _extract_part_and_keywords(question: str) -> tuple[str | None, list[str], list[str], list[str] | None]:
    """반환: (part_category, 영문 키워드 목록, 매칭된 한국어 키워드 목록, part_category_group).

    2026-07-14: 새 INV-01의 _filter_base(df, part_category, symptom)는 symptom을
    STR 구조화 결과의 한국어 symptoms 리스트와 "부분 문자열 포함" 방식으로
    대조한다(원문 CDESCR 영어 검색이 아님). 그래서 영문 키워드만으론 새 INV-01
    필터에 못 넘기고, 매칭된 한국어 트리거 단어 자체가 필요해졌다 — 세 번째
    반환값이 그 용도다(예: "계기판" -> STR이 뽑은 "계기판 깜빡임" 같은 문구와
    부분 일치).

    2026-07-20 신규: 네 번째 반환값 part_category_group. "ADAS"처럼 v4의 여러
    compdesc1에 걸쳐 있는 한국어 키워드는 PART_CATEGORY_GROUPS에서 먼저 확인해
    list[str]로 돌려준다(매칭되면 part는 None으로 둠 — 호출부가 그룹 순회
    조회 경로로 가야 하므로 단일 part_category와 동시에 값을 갖지 않게 함).
    """
    part: str | None = None
    part_group: list[str] | None = None
    keywords: list[str] = []
    ko_hits: list[str] = []

    # 그룹 매핑을 단일 매핑보다 먼저 확인 — "ADAS"처럼 더 포괄적인 질문이
    # 단일 카테고리 하나로 좁혀지는 걸 방지.
    for ko, group in PART_CATEGORY_GROUPS.items():
        if ko.lower() in question.lower():
            part_group = group
            break
    if part_group is None:
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
    return part, out[:10], ko_out[:5], part_group


def _detect_intent(question: str) -> str:
    q = question.lower()
    # 2026-07-16 신규: "한미 시차"류 질문은 반드시 맨 먼저 체크해야 한다.
    # "국내 리콜 미조치 상태야?"처럼 "상태"라는 단어가 같이 들어가는 경우가 많아서,
    # 아래 status_tracking 체크보다 뒤에 두면 "상태"에 먼저 걸려 이 분기가 죽는다
    # (실제로 테스트하다 발견 — model_year_breakdown 때와 같은 종류의 순서 문제).
    if any(k in q for k in ["시차", "국내 미조치", "한미", "한국 리콜", "국내 리콜", "us_kr", "kr_gap"]):
        return "us_kr_gap"
    # "증가"는 추가하지 않음: 기존에 investigate_signal 트리거(급증 조사)로 이미
    # 쓰이고 있어서, status_tracking을 먼저 체크하는 이 if-elif 순서상 여기에
    # 추가하면 "증가"가 들어간 급증-조사 질문까지 전부 status_tracking으로
    # 새치기해버린다("계기판 신고 증가하고 있어?" 같은 질문이 깨짐). "잠잠"은
    # 기존에 다른 의도로 안 쓰이고 있어 충돌 없이 추가.
    # 2026-07-21 신규 발견·수정: "이 차 리콜됐어?"처럼 "리콜"이라는 단어만 있는
    # 질문이 지금까지 아래 키워드 어디에도 안 걸려서 investigate_signal(LLM 조사
    # 루프)로 새고 있었다 — 근데 그 루프는 STR 데이터만 보고 STA의
    # recall_records(실제 NHTSA 리콜 264건 + compdesc1 정확 매칭)는 아예 안
    # 건드리므로, 정작 리콜 여부를 묻는 질문에 리콜 데이터를 한 번도 안 보고
    # 답하는 상태였다(테스트로 확인). "리콜"을 status_tracking 키워드에 추가해
    # 실제 리콜 데이터를 보는 경로로 보낸다 — 5단계 시그널(RECALLED/DORMANT/
    # RECURRING이면 리콜 있음, NEW/RISING이면 없음) 답변이 "리콜됐냐"는 질문에
    # 대한 완전한 답이 되므로 별도 intent를 새로 만들지 않고 기존 경로를
    # 재사용했다(로직 중복 방지). "국내 리콜"/"한국 리콜"은 위 us_kr_gap
    # 분기가 먼저 걸러가므로 순서 충돌 없음.
    if any(k in q for k in ["신규", "재발", "잠잠", "리콜 후", "상태", "리콜", "sta-01", "sta-02"]):
        return "status_tracking"
    if any(k in q for k in ["근거", "원문", "citation", "인용", "사례"]):
        return "evidence_samples"
    # 2026-07-20 신규(순서 수정): monthly_trend를 investigate_signal보다 먼저
    # 체크해야 한다. "기아 최근 3개월 월별 추이 알려줘"처럼 "최근"이 들어간
    # 질문이 이 분기보다 늦게 있던 investigate_signal의 "최근" 키워드에 먼저
    # 채여서 "차종/증상 정보 부족"으로 잘못 실패하는 게 실행 로그로 확인됨
    # (2026-07-20). "월별"/"추이"/"trend"/"monthly"는 investigate_signal의
    # 나머지 키워드(급증/시그널/surge/증가)와 안 겹치는 구체적인 단어라
    # 먼저 체크해도 다른 케이스를 오탐하지 않는다.
    if any(k in q for k in ["월별", "추이", "trend", "monthly"]):
        return "monthly_trend"
    # 2026-07-20: "최근"은 위 이유로 제거. "최근 급증/시그널"류 질문은 이미
    # "급증"/"시그널" 자체가 걸리므로 "최근"이 없어도 investigate_signal로
    # 정상 라우팅된다(예: "...최근 6개월 시그널 있어?"는 "시그널"로 매칭됨).
    if any(k in q for k in ["급증", "시그널", "surge", "증가"]):
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
    # 2026-07-20 신규: "분포" 추가. "EV9 불만분포 보여줘"처럼 부품/라벨 단어 없이
    # "분포"만 있는 질문이 여기 못 걸려서 investigate_signal(LLM 조사 루프)로
    # 새는 문제가 실제로 발견됨(효선님 실행 로그, 2026-07-20). "연식"/"월별" 등은
    # 이 분기보다 앞에서 먼저 체크되므로 순서 충돌 없음.
    if any(k in q for k in ["부품", "component", "compdesc", "라벨", "분포"]):
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
        except Exception as exc:  # 사용자 응답은 유지하되 연동 오류를 숨기지 않는다.
            print(f"[CHT01][WARN] STR-05 confirm_sentence 실패: {type(exc).__name__}: {exc}")
    model_kr = slots.get("차종_표시") or slots.get("차종")
    symptom = slots.get("증상")
    if not (model_kr and symptom):
        return None
    return f"{model_kr} / {symptom}{_ro_particle(symptom)} 이해했어요. 맞나요?"


def extract_slots_safe(
    question: str, slot_state: dict[str, Any] | None = None
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """
    STR-05 extract_slots() 래퍼.

    2026-07-20 수정(중요): 실제 extract_slots()는 dict 하나가 아니라
    (갱신된 내부 slots, 결과 dict) **튜플**을 반환한다 — str05_query_understanding.py
    실물 코드로 확인(이전엔 문서만 보고 dict 단일 반환으로 추정했었고, 그 추정이
    틀려서 이 함수가 튜플을 그대로 호출부에 흘려보내고 있었다: chat()의
    slots.get("상태")가 슬롯이 완료되는 시나리오마다 AttributeError로 죽는
    상태였다 — 실제 목킹 테스트로 재현·확인함). 이제 두 값을 분리해서
    반환한다 — chat()이 이 둘을 다른 용도로 써야 하기 때문:

      - updated_slots (1번째 값, 내부용): "_no_progress"(무진전 카운터) 등
        대화 진행 상태를 담고 있다. 다음 턴 extract_slots() 호출 시
        slot_state로 그대로 다시 넘겨야 카운터가 턴을 넘어 누적된다 — 결과
        dict만 돌려쓰면 _no_progress가 매 턴 유실돼 "2회 연속 무진전 시
        포기(unresolved)" 로직이 실제로는 절대 발동하지 않는다.
      - result (2번째 값, 공개용): {차종,차종_표시,증상[,상태,후속질문/안내문]}.
        화면에 보여줄 답변·확인문장 생성, parse_question()에 넘기는 용도.

    STR-05가 없는 환경(import 실패)이면 (None, None)을 반환해 chat()이 기존
    정규식 경로(_extract_model 등)로 폴백하게 한다.
    """
    if _str05_extract_slots is None:
        return None, None
    signature = inspect.signature(_str05_extract_slots)
    try:
        signature.bind(question, slot_state)
    except TypeError:
        signature.bind(question)
        updated_slots, result = _str05_extract_slots(question)
    else:
        updated_slots, result = _str05_extract_slots(question, slot_state)
    if not isinstance(updated_slots, dict) or not isinstance(result, dict):
        raise TypeError("STR-05 extract_slots는 (dict, dict) 튜플을 반환해야 합니다.")
    return updated_slots, result


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
    intent = _detect_intent(question)
    needs_enriched_df = intent not in {"status_tracking", "safety_flag_summary", "us_kr_gap"}
    df = _get_df(csv_path, jsonl_path) if needs_enriched_df else None
    symptom_source = (slots.get("증상") if slots else None) or question
    if slots and slots.get("차종"):
        model = slots["차종"]
        part, keywords, ko_hits, part_group = _extract_part_and_keywords(symptom_source)
    else:
        model = _extract_model(question, df)
        part, keywords, ko_hits, part_group = _extract_part_and_keywords(question)
    parsed = {
        "raw_question": question,
        "intent": intent,
        "make": _extract_make(question),
        "model": model,
        "year": _extract_year(question),
        "months": _extract_months(question),
        "part_category": part,
        # 2026-07-20 신규: "ADAS"처럼 v4의 여러 compdesc1에 걸친 질문이면 리스트가
        # 담긴다. 있으면 run_investigation()이 단일 part_category 대신 이걸로
        # 순회 조회+합산한다(_merge_category_results 참고).
        "part_category_group": part_group,
        "text_keywords": keywords,
        # 2026-07-14 신규: 새 INV-01 _filter_base()가 요구하는 한국어 symptom 필터값.
        # STR-05 slots가 있으면 그 "증상" 문구를 그대로(가장 정확), 없으면 매칭된
        # 한국어 트리거 단어 중 첫 번째를 쓴다. 아무것도 없으면 None(필터 생략).
        "symptom_text": (slots.get("증상") if slots else None) or (ko_hits[0] if ko_hits else None),
    }
    if (
        parsed["part_category"] is None
        and parsed["part_category_group"] is None
        and keywords
        and intent in {"investigate_signal", "evidence_samples"}
    ):
        # 증상 키워드가 있지만 파트가 없으면 전장/SW 프로젝트 범위에 맞춰 기본 전장으로 둔다.
        # 2026-07-20: v4 실제값 기준 공백 표기("ELECTRICAL_SYSTEM" -> "ELECTRICAL SYSTEM").
        parsed["part_category"] = "ELECTRICAL SYSTEM"
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

    # 2026-07-20 신규(복원): investigate_signal로 판별됐지만 차종·증상 없이
    # 부품 카테고리(단일 또는 그룹)만 있는 경우, investigate_ad_hoc()의
    # any([model, symptom]) 게이트에 걸려 항상 "차종/증상 정보 부족"으로
    # 실패한다("기아 ADAS 관련 신고 다 보여줘" 실행 로그로 재현·확인,
    # 2026-07-20). 이런 질문은 "이 카테고리 통계 보여줘"에 가까우므로
    # LLM 조사 루프 대신 query_template(증상 분포, 필요시 그룹 순회+합산)로
    # 보낸다.
    template = INTENT_TO_TEMPLATE.get(intent)
    if (
        action == "ad_hoc_investigation"
        and not parsed.get("model")
        and not parsed.get("symptom_text")
        and (parsed.get("part_category") or parsed.get("part_category_group"))
    ):
        action = "query_template"
        template = "get_symptom_distribution"

    # 2026-07-14: 새 INV-01 쿼리 함수들은 원래 part_category/symptom 2개만 받았다
    # (model/year 필터는 없었음 — _filter_base(df, part_category, symptom) 참고).
    # 2026-07-20: make는 이제 모든 함수가 선택적으로 받는다(하위 호환, 기본값
    # None). model/year는 여전히 함수 시그니처에 없어서 parsed에만 남겨
    # 화면 표시(scope 문구)와, 조합 조회 결과에서 특정 차종·연식만 뽑아내는
    # 후처리(run_investigation의 _slice_breakdown, get_symptom_distribution_by_model
    # 치환 로직)에 쓴다.
    # 2026-07-20 신규: query_templates.py의 _filter_base()가 이제 part_category로
    # 리스트도 받는다(효선님 파일에 직접 반영, TOOL_REGISTRY 7개 함수 전부 자동
    # 적용). 그래서 여기서도 단일 카테고리 대신 part_category_group이 있으면
    # 그 리스트를 그대로 넘긴다 — 예전엔 이걸 못 받아서 CHT-01이 카테고리마다
    # 따로 호출하고 직접 합산하는 우회 로직(_merge_category_results, 아래
    # run_investigation()의 그룹 순회 블록)이 있었는데, 이제 INV-01/02·03이
    # 네이티브로 지원하므로 그 우회 로직은 걷어냈다.
    params = {
        "part_category": parsed.get("part_category_group") or parsed.get("part_category"),
        "symptom": parsed.get("symptom_text"),
        # 2026-07-20 신규: query_templates.py의 모든 get_* 함수에 make(선택적,
        # 기본값 None) 파라미터가 추가됨(하위 호환). "기아"/"현대"로 좁힌 질문이
        # 화면 표시("KIA 기준")와 실제 계산이 따로 놀던 문제를 해결.
        "make": parsed.get("make"),
    }
    params = {k: v for k, v in params.items() if v not in (None, [], "")}
    return {
        "action": action,
        "template": template,
        "params": params,
        "parsed": parsed,
    }


def _query_status_db(parsed: dict[str, Any], *, db_path: str | Path | None = None) -> dict[str, Any]:
    """차종×부품카테고리 단위 5단계 시그널(defect_signals)을 조회한다.
    (기존에는 신고 단위 STA-01/02 이진 상태를 조회했으나, 5단계 모델 도입 후
    사용자 질문에 더 직접적으로 답이 되는 쪽은 시그널 단위 상태라 이쪽을 기본으로
    바꿨다. 신고 단위 원본 기록이 필요하면 query_status_summary()를 별도로 쓸 수
    있다 — 삭제하지 않고 남겨뒀다.)"""
    if init_db is None or query_signal_summary is None:
        reason = f"STA 모듈을 import하지 못했습니다: {_STA_IMPORT_ERROR}"
        return {"status": "UNAVAILABLE", "reason": reason, "rows": []}
    db = Path(db_path or DEFAULT_DB_PATH)
    if not db.exists():
        # 샌드박스 fallback
        fb = Path("/mnt/data/defect_status_tracking_generated.db")
        if fb.exists():
            db = fb
        else:
            return {"status": "NO_DB", "reason": f"상태 DB가 아직 없습니다: {db}", "rows": []}
    conn = init_db(db)
    try:
        df = query_signal_summary(conn)
    finally:
        conn.close()

    model = parsed.get("model")
    if not model and "model" in df.columns:
        question = str(parsed.get("raw_question") or "").upper()
        candidates = sorted(
            {str(value).strip().upper() for value in df["model"].dropna() if str(value).strip()},
            key=len,
            reverse=True,
        )
        model = next((candidate for candidate in candidates if candidate in question), None)

    for col, val in (("make", parsed.get("make")), ("model", model)):
        if val and col in df.columns:
            df = df[df[col].astype(str).str.upper() == str(val).upper()]
    if parsed.get("year") and "year" in df.columns:
        df = df[pd.to_numeric(df["year"], errors="coerce") == int(parsed["year"])]
    # 2026-07-20 수정: query_signal_summary()가 실제로 반환하는 컬럼명은
    # "part_category"가 아니라 "compdesc1"이다(sta01_02_status_tracking.py가
    # STR v4에 맞춰 스키마를 재설계하면서 이 이름으로 확정됨 — STA 쪽 실물 코드로
    # 확인). 이 파일의 다른 곳(INV 쪽)은 "part_category"라는 이름을 그대로 쓰는 게
    # 맞다(query_templates.py의 load_enriched_df가 compdesc1을 part_category로
    # 별칭 처리해주기 때문) — 하지만 STA 조회 결과는 그 별칭을 거치지 않으므로
    # 여기서만 compdesc1을 직접 써야 한다.
    requested_categories = parsed.get("part_category_group") or parsed.get("part_category")
    if requested_categories and "compdesc1" in df.columns:
        categories = requested_categories if isinstance(requested_categories, list) else [requested_categories]
        expanded = {str(category).upper() for category in categories}
        if parsed.get("part_category_group"):
            expanded.add("ADAS")
        if "ELECTRICAL SYSTEM" in expanded:
            expanded.update({"ELECTRICAL_SYSTEM", "INSTRUMENT_CLUSTER", "PROPULSION_BATTERY", "POWERTRAIN_SW"})
        if "ELECTRONIC STABILITY CONTROL (ESC)" in expanded:
            expanded.add("BRAKES_ELECTRONIC")
        df = df[df["compdesc1"].astype(str).str.upper().isin(expanded)]

    state_counts = df["signal_state"].value_counts().to_dict() if "signal_state" in df.columns else {}

    return {
        "status": "OK",
        "reason": "시그널 상태 조회 완료",
        "rows": df.head(20).to_dict("records"),
        "total_count": int(len(df)),
        "state_counts": state_counts,
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
        _RAW_DF_CACHE[key] = pd.read_csv(key, dtype=str, low_memory=False, encoding="utf-8-sig")
    return _RAW_DF_CACHE[key]


def _flag_true(series: pd.Series) -> pd.Series:
    """CRASH/FIRE 같은 플래그 컬럼을 Y/N, True/False, 1/0 어떤 표기든 bool로 통일."""
    return series.astype(str).str.strip().str.upper().isin({"Y", "YES", "TRUE", "1"})


def _safety_flag_summary(
    csv_path: str | Path | None = None,
    *,
    make: str | None = None,
    model: str | None = None,
    year: str | None = None,
) -> dict[str, Any]:
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

    filtered = raw
    for column, value in (("MAKETXT", make), ("MODELTXT", model)):
        if value:
            if column not in filtered.columns:
                return {"status": "NO_DATA", "reason": f"원본 CSV에 {column} 컬럼이 없습니다."}
            filtered = filtered[
                filtered[column].astype(str).str.strip().str.upper() == str(value).strip().upper()
            ]
    if year:
        if "YEARTXT" not in filtered.columns:
            return {"status": "NO_DATA", "reason": "원본 CSV에 YEARTXT 컬럼이 없습니다."}
        filtered = filtered[pd.to_numeric(filtered["YEARTXT"], errors="coerce") == int(year)]

    total = len(filtered)
    if total == 0:
        return {"status": "NO_DATA", "reason": "요청 조건과 일치하는 원본 신고가 없습니다."}

    fire_count = int(_flag_true(filtered["FIRE"]).sum())
    crash_count = int(_flag_true(filtered["CRASH"]).sum())
    injured_count = int(pd.to_numeric(filtered["INJURED"], errors="coerce").fillna(0).sum())
    deaths_count = int(pd.to_numeric(filtered["DEATHS"], errors="coerce").fillna(0).sum())

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
    df: pd.DataFrame, part_category: str | list[str] | None, symptom: str | None,
    make: str | None = None, limit: int = 8
) -> dict[str, Any]:
    """원문 근거(evidence_quote) 몇 건을 골라서 보여준다.

    2026-07-14 신규: 새 INV-01(query_templates.py)에는 "근거 샘플 몇 건 보여줘"에
    해당하는 함수가 없다(TOOL_REGISTRY에 없음 — 새 설계는 근거를 조사 루프
    내부에서만 다룬다). CHT-01이 필요로 하는 건 단순 필터+샘플링이라 INV-01
    조사 루프(투입 비용이 훨씬 큰 LLM 다단계 루프)까지 갈 필요 없이, enriched df
    (STR 구조화 결과가 이미 evidence_quote를 포함하고 있음)에서 직접 뽑는다.

    2026-07-20 수정: make 파라미터가 아예 없어서, "기아 근거 원문 보여줘"처럼
    제조사를 지정해도 실제로는 전체(현대+기아 다 포함) 100건 중 일부를 그대로
    보여주면서 화면엔 "KIA 조건"이라고 표시만 하는 버그가 있었다(표시와 실제
    필터링이 따로 노는 것 — TOOL_REGISTRY 쪽 함수들엔 이미 make가 추가돼있는데
    이 로컬 함수만 빠져있었음, 실행 로그로 확인). 다른 쿼리 함수들과 동일하게
    선택적 파라미터로 추가.
    """
    if "evidence_quote" not in df.columns:
        return {"status": "no_data", "count": 0, "reason": "evidence_quote 컬럼이 없습니다(STR 산출물 확인 필요)."}

    sub = df.copy()
    if "insufficient_info" in sub.columns:
        insufficient = sub["insufficient_info"].map(
            lambda value: value is True
            or str(value).strip().lower() in {"1", "true", "yes", "y"}
        )
        sub = sub[~insufficient]
    if part_category and "part_category" in sub.columns:
        if isinstance(part_category, list):
            sub = sub[sub["part_category"].isin(part_category)]
        else:
            sub = sub[sub["part_category"] == part_category]
    if symptom and "symptoms" in sub.columns:
        sub = sub[sub["symptoms"].apply(lambda lst: any(symptom in s for s in lst) if isinstance(lst, list) else False)]
    if make and "make" in sub.columns:
        sub = sub[sub["make"].astype(str).str.upper() == str(make).strip().upper()]
    quotes = sub["evidence_quote"].astype(str).str.strip()
    sub = sub[
        sub["evidence_quote"].notna()
        & (quotes != "")
        & (quotes != INSUFFICIENT_EVIDENCE)
    ]
    if "symptoms" in sub.columns:
        sub = sub[sub["symptoms"].map(
            lambda values: isinstance(values, list)
            and any(str(value).strip() != INSUFFICIENT_SYMPTOM for value in values)
        )]

    if len(sub) == 0:
        return {"status": "no_data", "count": 0}

    cols = [c for c in ("cmplid", "odino", "compdesc1", "compdesc2", "evidence_quote", "severity", "symptoms")
            if c in sub.columns]
    samples = sub[cols].head(limit).to_dict("records")
    return {"status": "ok", "count": len(sub), "samples": samples}


# ------------------------------------------------------------------
# 2026-07-16 신규: recall_crossref.csv -> get_us_kr_gap() 연동
# 효선님이 "check_recall_match/get_us_kr_gap이 아직 CHT-01에 안 붙어있다"고
# 남긴 known limitation을 여기서 해소한다. recall_crossref.csv를 실제로 열어보니
# 컬럼이 (model, model_year, component, us_recall_date, kr_recall_date) —
# get_us_kr_gap(model, us_recalls_df, kr_recalls_df)가 기대하는 "차종별 리콜일"
# 정보를 담고 있는 게 맞지만, us/kr이 한 행에 같이 있어서 그대로 넘길 수 없다
# (함수는 model+recall_date 컬럼을 가진 "서로 다른 두 DataFrame"을 요구함).
# 그래서 여기서 한 파일을 두 개로 쪼갠다. 모델명도 원본이 한국어 표기라서
# (예: "투싼") MODEL_EN_TO_KO로 변환해서 넘긴다.
# ------------------------------------------------------------------
DEFAULT_RECALL_CROSSREF_CSV = "data/processed/recall_crossref.csv"
_CROSSREF_CACHE: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}


def _load_us_kr_recall_dfs(path: str | Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """recall_crossref.csv를 읽어 (us_recalls_df, kr_recalls_df) 튜플로 분리한다.
    파일이 없으면 None을 반환한다(예외를 던지지 않음 — 호출부에서 '데이터 없음'으로
    자연스럽게 처리하도록)."""
    key = str(path or DEFAULT_RECALL_CROSSREF_CSV)
    if key in _CROSSREF_CACHE:
        return _CROSSREF_CACHE[key]
    try:
        raw = pd.read_csv(key)
    except (FileNotFoundError, OSError):
        return None

    required = {"model", "model_year", "us_recall_date", "kr_recall_date"}
    missing = required - set(raw.columns)
    if missing:
        print(f"[CHT01][WARN] recall_crossref.csv에 필요한 컬럼이 없습니다: {missing}")
        return None

    us_df = raw.loc[raw["us_recall_date"].notna(), ["model", "us_recall_date"]].rename(
        columns={"us_recall_date": "recall_date"}
    )
    kr_df = raw.loc[raw["kr_recall_date"].notna(), ["model", "kr_recall_date"]].rename(
        columns={"kr_recall_date": "recall_date"}
    )
    result = (us_df, kr_df)
    _CROSSREF_CACHE[key] = result
    return result


def _us_kr_gap_lookup(model_en: str | None, crossref_csv: str | Path | None = None) -> dict[str, Any]:
    """영문 모델 코드(예: "TUCSON")를 받아 한국어 표기로 변환한 뒤 get_us_kr_gap 호출."""
    if not model_en:
        return {"status": "no_data", "reason": "차종 정보가 없어 한·미 시차를 조회할 수 없습니다."}

    dfs = _load_us_kr_recall_dfs(crossref_csv)
    if dfs is None:
        return {
            "status": "no_data",
            "reason": "recall_crossref.csv를 찾을 수 없습니다(팀 데이터 경로 확인 필요).",
        }
    us_df, kr_df = dfs
    model_ko = MODEL_EN_TO_KO.get(model_en, model_en)  # 매핑 없으면 원래 값 그대로 시도
    return get_us_kr_gap(model_ko, us_df, kr_df)


def run_investigation(
    plan: dict[str, Any],
    *,
    csv_path: str | Path | None = None,
    jsonl_path: str | Path | None = None,
    db_path: str | Path | None = None,
    llm_call: Callable[..., dict] = _stub_llm_call,
) -> dict[str, Any]:
    action = plan["action"]
    parsed = plan["parsed"]
    needs_enriched_df = action in {"ad_hoc_investigation", "query_template"} or (
        action == "local_query" and parsed.get("intent") == "evidence_samples"
    )
    df = _get_df(csv_path, jsonl_path) if needs_enriched_df else None

    if action == "ad_hoc_investigation":
        # 2026-07-14: investigate_ad_hoc() 시그니처가 통째로 바뀌었다.
        #   구: investigate_ad_hoc(df, make=, model=, year=, part_category=, text_keywords=)
        #   신: investigate_ad_hoc(question_parsed: dict, df, llm_call)
        # question_parsed의 키("model","model_year","symptom","part_category")는
        # investigation_loop_v4.py의 investigate_ad_hoc() 본문이 실제로 읽는 키다.
        # 2026-07-20 정정: 이전 주석엔 "model_year는 본문에서 안 씀"이라고 적혀
        # 있었는데, investigation_loop_v4.py 실물 코드 확인 결과 이건 틀렸다 —
        # investigate_ad_hoc()이 target_model_year로 읽어서 run_investigation_loop()
        # 까지 명시적으로 전달하고(효선님 2026-07-15 수정 2), LLM 프롬프트
        # 컨텍스트(hyp_context의 instruction_note)에도 실제로 반영된다. "model"은
        # STR-05 실제 산출물이 영문 코드(예: "TUCSON")라 그대로 넣는다.
        # 2026-07-20 신규(설계 한계 돌파): query_templates.py(_filter_base)와
        # investigation_loop_v2.py(run_investigation_loop)가 이제 part_category로
        # list[str]도 네이티브 지원한다(효선님 파일에 직접 반영). 그래서 "브레이크"
        # 처럼 parsed["part_category"]가 None이고 parsed["part_category_group"]만
        # 있는 경우, 예전엔 그룹의 대표 카테고리 1개로 근사(narrowed_from_group)
        # 했었는데 이제는 그룹 전체를 그대로 넘겨 실제로 다 조사한다 — 화면
        # scope 표시와 실제 조사 대상이 완전히 일치한다.
        question_parsed = {
            "model": parsed.get("model"),
            "model_year": parsed.get("year"),
            "symptom": parsed.get("symptom_text"),
            "part_category": parsed.get("part_category_group") or parsed.get("part_category"),
        }
        result = investigate_ad_hoc(question_parsed, df, llm_call)
        return {"kind": action, "result": result}

    if action == "status_query":
        return {"kind": action, "result": _query_status_db(parsed, db_path=db_path)}

    if action == "local_query":
        intent = parsed.get("intent")
        if intent == "safety_flag_summary":
            result = _safety_flag_summary(
                csv_path,
                make=parsed.get("make"),
                model=parsed.get("model"),
                year=parsed.get("year"),
            )
            return {"kind": action, "template": "safety_flag_summary", "result": result}
        if intent == "evidence_samples":
            assert df is not None
            result = _evidence_samples_from_df(
                df, parsed.get("part_category_group") or parsed.get("part_category"), parsed.get("symptom_text"),
                make=parsed.get("make"), limit=8,
            )
            return {"kind": action, "template": "evidence_samples", "result": result}
        if intent == "us_kr_gap":
            result = _us_kr_gap_lookup(parsed.get("model"))
            return {"kind": action, "template": "us_kr_gap", "result": result}
        return {"kind": action, "error": f"알 수 없는 로컬 intent: {intent}"}

    template = plan.get("template")
    if not template:
        return {"kind": action, "error": "질문 의도를 쿼리 템플릿에 매핑하지 못했습니다."}
    if template not in TOOL_REGISTRY:
        return {"kind": action, "error": f"INV-01 TOOL_REGISTRY에 없는 템플릿입니다: {template}"}

    # 2026-07-20 신규: get_symptom_distribution(df, part_category)은 model을 아예
    # 안 받는다 — "EV9 2024 불만분포 보여줘"처럼 model이 파싱돼 있어도 그 정보가
    # 버려지고 전체(모든 차종 합산) 분포가 나오는 문제가 실측으로 확인됨
    # (효선님 실행 로그, 2026-07-20). TOOL_REGISTRY에 이미 있는
    # get_symptom_distribution_by_model(df, part_category, model, model_year=None)로
    # 바꿔치기해서 실제로 model·model_year까지 반영되게 한다.
    if template == "get_symptom_distribution" and parsed.get("model") and "get_symptom_distribution_by_model" in TOOL_REGISTRY:
        template = "get_symptom_distribution_by_model"

    # 2026-07-20 (설계 한계 돌파): "ADAS"처럼 여러 compdesc1에 걸친 질문
    # (part_category_group)도 이제 별도 순회 로직 없이 아래 단일 호출 경로로
    # 그대로 처리된다 — structure_query()가 이미 params["part_category"]에
    # 그룹(list)을 넣어줬고, query_templates.py(_filter_base)가 리스트를
    # 네이티브로 지원하기 때문(효선님 파일에 직접 반영). 예전엔 여기서
    # 카테고리별로 함수를 여러 번 호출하고 _merge_category_results로 직접
    # 합산하는 우회 로직이 있었는데, 그 필요가 없어져 제거했다 — 로직이 한
    # 곳(query_templates.py)에만 있으니 합산 방식이 바뀌어도 여기를 안 고쳐도
    # 된다.

    func = TOOL_REGISTRY[template]["func"]
    assert df is not None
    params = dict(plan.get("params") or {})
    if template == "get_monthly_trend":
        params.setdefault("months", parsed.get("months") or 12)

    # 2026-07-20 신규: 위에서 get_symptom_distribution_by_model로 치환됐으면
    # 그 함수가 요구하는 model(필수)·model_year(선택)를 채워 넣는다.
    if template == "get_symptom_distribution_by_model":
        params["model"] = parsed.get("model")
        if parsed.get("year"):
            params["model_year"] = parsed["year"]

    # 2026-07-14: TOOL_REGISTRY 6개 함수 전부 part_category가 "필수" 위치 인자다
    # (기본값 없음 - inspect.signature로 실측 확인함, 하나라도 안 넘기면
    # TypeError). 질문에서 부품 카테고리를 못 뽑았으면 프로젝트 기본 범위인
    # 전장/SW로 채우되, 사용자가 요청하지 않은 범위로 조용히 좁혀지는 것이므로
    # defaulted 플래그를 남겨서 답변에서 투명하게 밝힌다("전체" 아니라
    # "ELECTRICAL SYSTEM 기준"이라고).
    # 2026-07-20: 기본값을 v4 실제값(공백 표기)으로 교체. part_category_group이
    # 있어서 이미 리스트가 들어있는 경우 setdefault는 아무 영향 없음(이미 키가
    # 있으므로) — defaulted_part_category도 자동으로 False가 된다.
    defaulted_part_category = "part_category" not in params
    params.setdefault("part_category", "ELECTRICAL SYSTEM")

    # get_symptom_distribution(df, part_category)만 symptom 인자 자체가 없다
    # (나머지 5개는 symptom=None 기본값 있음 - 역시 실측 확인). 함수가 실제로
    # 받는 키워드만 골라 넘겨서, TOOL_REGISTRY 쪽 시그니처가 앞으로 바뀌어도
    # 이 호출부가 안 죽게 했다(하드코딩 특례를 늘리는 대신 시그니처 기반으로).
    accepted = set(inspect.signature(func).parameters.keys())
    params = {k: v for k, v in params.items() if k in accepted}

    result = func(df, **params)

    # 2026-07-14: 새 INV-01 함수들은 원래 model/year로 필터링하지 않고 항상
    # "part_category(+symptom) 전체 분포"를 돌려줬다(2026-07-20: make는 이제
    # 필터링됨 — 위 params에 이미 반영). 사용자가 특정 차종·연식을 물었으면
    # (예: "2025년식 투싼"), 전체 분포에서 그 조합만 뽑아 answer 단계에서
    # 강조할 수 있도록 slice를 같이 담아 보낸다. compose_answer_text가 이
    # slice를 우선 사용한다.
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
    if parsed.get("part_category_group"):
        parts.append("/".join(parsed["part_category_group"]))
    elif parsed.get("part_category"):
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
        counts = result.get("state_counts") or pd.Series(
            [r.get("signal_state") for r in rows]
        ).value_counts().to_dict()
        label_counts = {SIGNAL_LABEL_KO.get(k, k): v for k, v in counts.items()}
        top = min(rows, key=lambda r: SIGNAL_PRIORITY_ORDER.get(r.get("signal_state"), 99))
        top_label = SIGNAL_LABEL_KO.get(top.get("signal_state"), top.get("signal_state"))
        # 2026-07-20 수정: top은 query_signal_summary()의 행이라 "part_category"가
        # 아니라 "compdesc1"이 실제 컬럼명이다(위 _query_status_db 주석 참고).
        top_vehicle = " ".join(str(top.get(k)) for k in ("make", "model", "year") if top.get(k)) or scope
        return (
            f"{scope} 조건의 결함 시그널 {result.get('total_count', len(rows))}건을 찾았습니다. "
            f"상태 분포는 {label_counts}입니다. "
            f"가장 우선 확인이 필요한 시그널: {top_vehicle} {top.get('compdesc1')} — {top_label} "
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
            # 2026-07-20 신규 발견·수정: odino만 표시하면 v4에서 헷갈린다 — 한
            # ODINO 안에 CMPLID가 여러 개(=결함 유형별로 여러 행) 있을 수 있어서,
            # "ODINO 11497859" 같은 표기가 인용문 3개 중 2개에서 반복돼 마치
            # 데이터가 중복/깨진 것처럼 보이는 문제가 실측으로 확인됨(동일
            # ODINO의 서로 다른 CMPLID가 우연히 같은 문장을 근거로 인용한 경우,
            # 예: "Check BSD" 경고문이 LANE DEPARTURE와 FORWARD COLLISION
            # AVOIDANCE 양쪽 앵커에서 다 근거로 뽑힘). CMPLID(v4의 실제 고유
            # 식별자)와 compdesc1(어느 결함 유형 관점인지)을 같이 보여주면 각
            # 줄이 실제로 왜 다른 레코드인지 바로 구분된다.
            cite_bits = [
                f"CMPLID {s.get('cmplid', s.get('odino'))}({s.get('compdesc1', '')}): "
                f"{str(s.get('evidence_quote', ''))[:120]}"
                for s in samples[:3]
            ]
            return (
                f"{scope} 조건의 원문 근거 {result.get('count', 0)}건 중 일부입니다.\n"
                + " | ".join(cite_bits)
                + "\n단, 이는 소비자 신고 원문 발췌이며 결함 확정이 아닙니다."
            )
        if template == "us_kr_gap":
            status = result.get("status")
            if status == "ok":
                gap = result.get("gap_days")
                gap_desc = f"국내가 미국보다 {gap}일 늦게 리콜" if isinstance(gap, int) and gap >= 0 else \
                           (f"국내가 미국보다 {-gap}일 먼저 리콜" if isinstance(gap, int) else "시차 계산 불가")
                return (
                    f"{scope} 리콜 시차입니다. 미국 리콜일 {result.get('us_recall_date')}, "
                    f"국내 리콜일 {result.get('kr_recall_date')} — {gap_desc}했습니다. "
                    "공개된 리콜 발표일 기준 비교이며 원인·책임 판단은 포함하지 않습니다."
                )
            if status == "us_recalled_kr_not_yet":
                return (
                    f"{scope}은 미국에서 {result.get('us_recall_date')}에 리콜됐지만, "
                    "국내 리콜 발표는 아직 확인되지 않았습니다(국내 미조치 가능성). "
                    "국내 발표 정보가 누락됐을 수도 있어 확정적으로 판단하지 마세요."
                )
            if status == "no_us_recall":
                return f"{scope}에 대한 미국 리콜 기록을 찾지 못했습니다."
            return f"{scope}의 한·미 리콜 시차를 조회하지 못했습니다. 사유: {result.get('reason', status)}"
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
        elif template in {"get_symptom_distribution", "get_symptom_distribution_by_model"}:
            # 2026-07-20: by_model로 치환된 경우도 반환 shape이 동일(symptom_counts)
            # 이라 같은 문구로 처리한다.
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

    slot_state: extract_slots()가 이전 턴까지 쌓아온 "내부" 슬롯 dict
    ({차종,차종_표시,증상,_no_progress}, 무진전 카운터 포함). 첫 턴은 None으로
    시작. 이번 턴 응답의 "slot_state" 값을 다음 chat() 호출에 그대로 넘기면
    멀티턴 되물음이 이어진다 — 상위(웹앱/세션) 레이어가 이 값을 턴 사이에
    보관해야 한다. 완료(turn_status="OK") 후에는 slot_state가 None으로
    초기화되어 돌아오므로, 다음 질문은 새 대화로 자연스럽게 시작된다.
    (2026-07-20 수정: 이전엔 화면 노출용 결과 dict를 그대로 slot_state로
    돌려주고 있었는데, 그 dict엔 "_no_progress"가 없어서 무진전 카운터가 매
    턴 유실되는 문제가 있었다 — 지금은 내부 dict를 돌려준다.)

    STR-05가 아직 연동 안 된 환경(extract_slots_safe가 (None, None) 반환)에서는
    이 슬롯 단계를 건너뛰고 기존 단일턴 정규식 경로로 동작한다 — 동작이 끊기지
    않는다.

    jsonl_path: 2026-07-14 신규. 새 INV-01(load_enriched_df)이 원본 CSV와 STR
    구조화 JSONL을 조인해서 쓰기 때문에 CHT-01도 이제 이 경로가 필요하다.
    기본값은 query_templates.STRUCT_JSONL_PATH.

    llm_call: investigate_ad_hoc()(조사 루프)이 내부적으로 호출할 LLM 콜백.
    팀 공용 API 래퍼가 준비되면 이 인자로 실제 함수를 넘기면 되고, 그 전까지는
    기본값(_stub_llm_call, 결정론적 임시 동작)으로 데모가 계속 돌아간다.
    """
    # 2026-07-20 신규 발견·수정: 빈 문자열/공백만 있는 질문도 _detect_intent()의
    # 기본 분기(investigate_signal)로 떨어져 슬롯 게이트 대상이 되고, 그 결과
    # extract_slots_safe() -> (연동됐다면) 실제 LLM 호출까지 이어지는 게 테스트로
    # 확인됨 — 아무 정보도 없는 입력에 굳이 API 비용을 쓸 이유가 없어서, 여기서
    # 먼저 걸러 즉시 안내한다.
    if not question or not question.strip():
        answer_text = "질문을 입력해주세요 — 예: '투싼 계기판 꺼짐 최근 신고 있어?'"
        result = {
            "question": question,
            "turn_status": "NEED_MORE_INFO",
            "slot_state": None,
            "answer_text": answer_text,
            "safety_notice": "소비자 신고 기반 분석이며 결함·리콜 확정 판단은 규제기관/제조사 조사 영역입니다.",
        }
        if session_history is not None:
            session_history.append({"question": question, "turn_status": "NEED_MORE_INFO", "answer_text": answer_text})
        return result

    # 이미 진행 중인 슬롯 대화(slot_state 있음)는 이번 발화의 의도가 뭐로 보이든
    # 끝까지 이어가야 한다("투싼이요" 한마디만으로는 의도를 제대로 못 읽는다).
    # 새 대화라면 빠른 의도 판별로 게이트 필요 여부만 먼저 본다.
    quick_intent = _detect_intent(question)
    use_slot_gate = slot_state is not None or quick_intent in _SLOT_GATED_INTENTS
    if use_slot_gate:
        # 2026-07-20 수정: extract_slots_safe()가 이제 (updated_slots, result)
        # 튜플을 반환한다 — 반드시 둘로 나눠 받아야 한다(과거엔 튜플을 통째로
        # slots에 담아 slots.get("상태")에서 바로 AttributeError로 죽었다).
        updated_slot_state, slots = extract_slots_safe(question, slot_state)
    else:
        updated_slot_state, slots = None, None

    if slots is not None and _is_incomplete_slot_state(slots.get("상태")):
        turn_status = "UNRESOLVED" if slots["상태"] == "unresolved" else "NEED_MORE_INFO"
        answer_text = slots.get("안내문") or slots.get("후속질문") or "차종과 증상을 조금 더 알려주시겠어요?"
        result = {
            "question": question,
            "turn_status": turn_status,
            # updated_slot_state(내부 dict, "_no_progress" 포함)를 다음 턴
            # slot_state로 돌려준다. slots(공개용 dict)를 대신 돌려주면 무진전
            # 카운터가 매 턴 유실돼 MAX_NO_PROGRESS 포기 로직이 실질적으로
            # 동작하지 않는다.
            "slot_state": updated_slot_state,
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
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    # 실제 팀 데이터 경로(query_templates.RAW_CSV_PATH/STRUCT_JSONL_PATH,
    # sta01_02_status_tracking.DEFAULT_DB_PATH) 기준 스모크 테스트.
    # GEMINI_API_KEY가 설정돼 있으면 실제 LLM(real_llm_call)로, 아니면 스텁으로 자동 전환.
    use_real_llm = REAL_LLM_CALL_AVAILABLE and bool(os.environ.get("GEMINI_API_KEY"))
    _main_llm_call = real_llm_call if use_real_llm else _stub_llm_call
    print(f"[MAIN] llm_call = {'real_llm_call (Gemini)' if use_real_llm else '_stub_llm_call (임시)'}")

    history: list[dict[str, Any]] = []
    tests = [
        "2025년식 투싼 계기판 꺼짐 최근 6개월 시그널 있어?",
        "기아 연식별 불만 분포 보여줘",
        "현대 부품 라벨 상위 알려줘",
        "투싼 인포테인먼트 화면 버벅거리는 거 불편해",
        "게기판 꺼짐 투싼 마니 신고됨?",
        "2028년식 아이오닉 시그널 있어?",
        "차 요즘 이상하다는데 뭐가 문제야?",
        "브레이크 문제 있어?",
        "기아 근거 원문 보여줘",
    ]

    for q in tests:
        ans = chat(q, history, llm_call=_main_llm_call)
        print("\nQ:", q)
        print("A:", ans["answer_text"][:800])
    print(f"\n[HISTORY] {len(history)} turns")
