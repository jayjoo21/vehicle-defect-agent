"""
INV-02/03: 조사 루프 (Investigation Loop) — v2

v1 대비 변경 사항 (팀원 코드에서 이식한 아이디어)
--------------------------------------------------
[가져온 것]
1. 조건 완화 4단계 사다리 (RELAXATION_LADDER)
   - v1은 "완화 재시도"를 개념으로만 뒀음 (symptom 필드 하나 빼는 수준)
   - v2는 팀원 코드의 exact -> 키워드제거 -> 연식제거 -> 모델제거 단계를
     그대로 가져와 0건일 때 순차 적용
2. 한국어-영어 키워드 매핑 (KO_EN_KEYWORD_MAP)
   - STR 산출물 symptoms가 한국어라 영어 원문(CDESCR) 검색에 필요
3. 결과 CSV 저장 (save_investigation_log)
   - Judge/대시보드가 파싱할 수 있는 고정 스키마로 flatten
4. 채팅용 즉석 조사 진입점 (investigate_ad_hoc)

[안 가져온 것 — 원칙상 유지]
- 신고 1건=가설 1개 구조 X. 여러 건을 종합한 "패턴 가설" 유지
  (조사 대상은 급증 구간 전체지, 개별 신고 하나가 아님)
- 숫자 임계값(support_count>=3)으로 코드가 유지/기각을 "확정"하는 것 X
  대신 이 숫자들은 LLM 판단 시 "참고 지표"로만 제공 (LLM이 최종 판단)
- 고정 파이프라인(조건 완화 4단계) 자체가 "LLM 개입 없이 자동 완주"하는 것 X
  완화는 여전히 "결과 0건일 때"만 코드가 자동 적용하고,
  그 외 쿼리 선택/최종 판단은 LLM이 함

2026-07-15 효선 수정 1 — 쿼리 실행부 params 처리 정리
    LLM이 select_query_or_conclude에서 params를 비우거나 일부만 채워서 보낼 때
    두 가지 문제가 있었다:
    1) get_model_distribution 등 (df, part_category, ...) 패턴 함수인데 params에
       part_category가 없으면 TypeError. -> params에 없으면 항상 채워 넣도록 보장.
    2) check_recall_match/get_us_kr_gap은 df/part_category를 아예 안 받는
       (model, ..., recalls_df) 패턴이라 시그니처 자체가 다름. 이 둘은 아직
       리콜 정답지 CSV가 조사 루프에 연결되지 않았으므로, 호출 자체를 하지 않고
       "not_available" 상태를 정직하게 반환하도록 분리 처리.
    -> 함수명 하드코딩 대신 safe_call_tool()이 inspect.signature로 각 함수가
       실제로 받는 파라미터를 확인해서 자동으로 걸러 호출하도록 일반화함.

2026-07-15 효선 수정 2 — 질문의 target_model/model_year가 LLM한테 전달 안 되던 버그
    investigate_ad_hoc()이 question_parsed(model/model_year)를 받아놓고도
    run_investigation_loop()의 hyp_context에는 이 정보를 전혀 안 넘기고 있었다.
    그 결과, "2025년식 투싼" 질문인데 정찰 결과(part_category 카테고리 전체)에
    우연히 다른 차종(EV9)만 있으면, LLM이 "질문받은 차종이 뭔지도 모른 채" 정찰에
    보이는 차종으로 엉뚱한 가설을 세우는 사고가 실제로 발생함(효선님 실행 로그로
    확인, "투싼 질문 -> EV9 답변" 사례).
    -> investigate_ad_hoc()이 target_model/target_model_year를
       run_investigation_loop()까지 명시적으로 전달하고, hyp_context/
       select_query_or_conclude/judge_hypothesis 전부에 target_model/
       target_model_year + 안내 문구를 포함시켜 LLM이 정찰 결과와 질문 대상이
       다를 때 착각하지 않고 "해당 차종 데이터 없음"으로 정직하게 판단하거나,
       get_symptom_distribution_by_model로 직접 확인하도록 유도.

2026-07-20 효선 수정 3 — investigate_ad_hoc()의 part_category 기본값이 v3
    잔재(INSUFFICIENT_INFO)였던 버그
    question_parsed에 part_category가 없을 때 기본값이 "INSUFFICIENT_INFO"였는데,
    이건 v3(8종 LLM 창작 taxonomy) 체계의 값이다. v4(NHTSA 원본 COMPDESC 그대로
    파싱) 전환 이후 실제 compdesc1 값 7종(ELECTRICAL SYSTEM/UNKNOWN OR OTHER/
    FORWARD COLLISION AVOIDANCE/VEHICLE SPEED CONTROL/LANE DEPARTURE/
    BACK OVER PREVENTION/ELECTRONIC STABILITY CONTROL (ESC)) 어디에도
    "INSUFFICIENT_INFO"라는 카테고리는 없다. 그 결과 "기아 2024년식 EV9
    불만분포 보여줘"처럼 part_category를 못 뽑은 채 이 함수로 들어오면 정찰
    단계부터 무조건 no_data가 나고, 거기에 "데이터 부족 가설=RETAINED 오판정"
    버그(2026-07-20 별도 발견, 아직 미수정)까지 겹쳐 EV9처럼 실제로 데이터가
    있는 핵심 검증 사례조차 "데이터 부족"으로 잘못 답하는 게 실행 로그로 확인됨.
    -> 기본값을 v4에서 실제로 가장 큰 비중을 차지하는 카테고리인
       "ELECTRICAL SYSTEM"(전체 16,964건 중 6,837건, 40%)으로 교체.
       완벽한 해법은 아니다(질문이 진짜 이 카테고리를 의도한 게 아닐 수 있음) —
       근본적으로는 CHT-01의 parse_question()이 카테고리를 못 뽑는 질문을
       애초에 이 함수로 보내지 않도록 라우팅을 개선하는 게 맞고, 이 기본값은
       "그래도 뭔가는 넣어야 하는" 최후 폴백일 뿐이라는 걸 알고 있을 것.
"""

from __future__ import annotations
import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from query_templates import INSUFFICIENT_SYMPTOM, TOOL_REGISTRY, load_enriched_df  # noqa: F401


MAX_HYPOTHESES = 3
MAX_QUERIES_PER_HYPOTHESIS = 3
SCOUTING_QUERIES = ["get_symptom_distribution", "get_model_year_breakdown"]

# ------------------------------------------------------------------
# 2026-07-20 신규: "데이터 부족/판단 불가" 오판정 방지
#
# 문제: judge_hypothesis가 "가설이 데이터와 일치하는가"만 보고 판정하는데,
# 가설 문장 자체가 "데이터가 부족하다/판단하기 어렵다"인 경우, 정찰 결과가
# 실제로 그 불확실성과 일치하면(=진짜 데이터가 없으면) LLM이 이걸 "가설 지지
# (RETAINED)"로 판정해버리는 사고가 실행 로그로 반복 확인됨(2026-07-20,
# TUCSON/RAY/오타 케이스 등 거의 매 질문에서 재현). "RETAINED"라는 라벨 자체가
# "뭔가 확인됐다"는 인상을 주는데 실제로는 "확인할 게 없다는 게 확인됐다"인
# 상태라 의미론적으로 다른 결론(가설 지지 vs 애초에 검증 불가)이 같은 상태값
# 으로 뭉개지는 것. 문서 1의 "모름 3중 장치"(② 증거 부족 → 보류) 원칙 위반.
#
# 해법: 가설 문장에 아래 마커가 있으면 judge_hypothesis API 호출 자체를
# 생략하고(비용도 아낌) 코드가 결정론적으로 HOLD 처리한다. 이건 문서 2의
# "① 역할 분리: 계산은 코드, 판단은 LLM" 원칙에도 맞는 방향 — 이렇게 명백한
# 케이스까지 매번 LLM Judge를 부르는 건 낭비이고, 코드가 걸러내는 게 맞다.
# ------------------------------------------------------------------
UNCERTAINTY_MARKERS = [
    "데이터가 부족", "데이터 부족", "판단하기 어렵", "판단하기 어려",
    "확인되지 않", "근거가 부족", "파악하기 어렵", "알 수 없",
    "데이터가 없", "데이터가 전혀 없", "가설을 세우기 어렵",
    "찾지 못", "뚜렷한 패턴이 없", "집중 패턴이 없",
]


def _hypothesis_is_uncertainty_statement(hypothesis_text: str) -> bool:
    return any(marker in hypothesis_text for marker in UNCERTAINTY_MARKERS)


# ------------------------------------------------------------------
# 2026-07-20 신규: llm_call API 레벨 예외(503 UNAVAILABLE 등 일시적 서버
# 오류) 방어
#
# real_llm_call.py에 이미 tenacity 재시도가 있지만, 그마저 소진되면
# google.genai.errors.ServerError 같은 예외가 그대로 여기까지 올라온다.
# 이 예외를 안 잡으면 run_investigation_loop() 하나가 죽는 걸 넘어서,
# __main__의 여러 질문을 순회하는 루프(chat() 호출부) 전체가 죽어버려
# 그 뒤 질문들이 아예 처리되지 않는 문제가 실행 로그로 3회 연속 확인됨
# (2026-07-20, 503 UNAVAILABLE). 여기서 마지막 방어선으로 예외를 잡아
# None을 반환하고, 호출부가 이를 보고 "API 오류로 조사 중단"이라는
# 정직한 HOLD로 안전하게 종료하게 한다 — 크래시 대신 그 질문 하나만
# 실패 처리하고 나머지 질문은 계속 진행되도록.
# ------------------------------------------------------------------
def _call_llm_safe(llm_call: Callable[..., dict], prompt_type: str, context: dict) -> dict | None:
    try:
        return llm_call(prompt_type, context)
    except Exception as e:  # noqa: BLE001 - API 클라이언트 예외 타입에 의존하지 않기 위해 폭넓게 잡음
        print(f"[INV02][WARN] llm_call({prompt_type!r}) 실패 — 일시적 API 오류로 추정: {e}")
        return None

# ------------------------------------------------------------------
# [이식 1] 조건 완화 4단계 사다리
# 결과 0건일 때, 이 순서대로 조건을 하나씩 넓혀가며 재시도한다.
# LLM이 매번 완화를 판단하게 하면 비용/시간이 크므로, "0건일 때의 복구 절차"는
# 코드가 결정론적으로 처리하고, 그 결과만 LLM에게 다시 보여준다.
# ------------------------------------------------------------------
RELAXATION_LADDER = [
    {"label": "exact", "drop": []},                       # 원 조건 그대로
    {"label": "drop_text_keyword", "drop": ["symptom"]},   # 증상 키워드 제거
    {"label": "drop_year", "drop": ["symptom", "model_year"]},  # +연식 제거
    {"label": "drop_model", "drop": ["symptom", "model_year", "model"]},  # +차종도 제거(부품군만 남김)
]


def relax_params(params: dict, drop_keys: list[str]) -> dict:
    return {k: v for k, v in params.items() if k not in drop_keys}


def run_query_with_relaxation(func: Callable, df, part_category: str | list[str], params: dict) -> tuple[dict, str]:
    """
    0건이면 RELAXATION_LADDER를 순서대로 적용해 재시도.
    각 단계도 safe_call_tool을 거치므로, func가 안 받는 파라미터가 params에
    섞여 있어도(예: get_severity_breakdown에 model이 딸려온 경우) 안전하다.
    반환: (결과, 실제 적용된 완화 단계 라벨)
    """
    for step in RELAXATION_LADDER:
        trial_params = relax_params(params, step["drop"])
        trial_func = func
        model_tool = TOOL_REGISTRY["get_symptom_distribution_by_model"]["func"]
        if "model" in step["drop"] and func is model_tool:
            trial_func = TOOL_REGISTRY["get_symptom_distribution"]["func"]
        result = safe_call_tool(trial_func, df, part_category, trial_params)
        if result.get("status") != "no_data":
            return result, step["label"]
    # 끝까지 완화해도 0건이면 마지막 결과(전부 완화된 상태)를 그대로 반환
    return result, RELAXATION_LADDER[-1]["label"] + "(그래도 0건)"


# ------------------------------------------------------------------
# LLM이 고른 쿼리를 안전하게 호출하는 공용 헬퍼
#
# 문제: TOOL_REGISTRY의 함수 9개가 전부 시그니처가 똑같지 않다.
#   - 대부분: func(df, part_category, symptom=None, ...) 패턴
#   - check_recall_match / get_us_kr_gap: df를 아예 안 받는 (model, ..., recalls_df) 패턴
# LLM이 매번 정확한 파라미터만 골라 보낸다는 보장이 없어서(실제로 model/part_category
# 누락, 안 받는 키 포함 등으로 여러 번 TypeError 발생), 함수 이름을 하드코딩해서
# 하나씩 예외처리 하는 대신 inspect.signature로 "이 함수가 실제로 받는 파라미터가
# 뭔지"를 코드가 직접 확인해서 자동으로 걸러낸다. 함수가 추가/변경돼도 이 로직은
# 안 건드려도 됨.
# ------------------------------------------------------------------

def safe_call_tool(func: Callable, df, part_category: str | list[str], params: dict) -> dict:
    """LLM이 넘긴 params를 func의 실제 시그니처에 맞게 걸러서 안전하게 호출한다.

    - func가 'df'를 파라미터로 받으면: df를 첫 인자로 넘기고, func가 실제로
      받는 이름의 파라미터만 params에서 골라 넘긴다. part_category를 받는데
      params에 없으면 채워 넣는다(호출 대상 원래 조사 대상이므로).
    - func가 'df'를 안 받으면(check_recall_match/get_us_kr_gap처럼 별도 정답지
      CSV가 필요한 함수): 아직 그 데이터가 조사 루프에 연결되지 않았으므로
      호출하지 않고 정직하게 'not_available'을 반환한다.

    2026-07-20 수정: get_symptom_distribution_by_model처럼 model(기본값 없는
    필수 파라미터)을 요구하는 함수를, LLM이 model 없이 골라서 호출한 경우
    TypeError로 그대로 죽는 버그가 실행 로그로 확인됨("차 요즘 이상하다는데
    뭐가 문제야?" 질문 처리 중 크래시). part_category는 이미 자동으로 채워
    주지만, 그 외 기본값 없는 파라미터는 아무 방어가 없었다. LLM이 매번 정확한
    파라미터만 보낸다는 보장이 없다는 게 애초에 이 함수의 존재 이유이므로,
    part_category 하나만 특별 취급하는 대신 "기본값 없는 파라미터가 filtered에
    빠져 있으면 호출하지 않고 not_available로 정직하게 반환"하도록 일반화했다.
    """
    sig = inspect.signature(func)
    sig_params = sig.parameters

    if "df" not in sig_params:
        return {
            "status": "not_available",
            "note": f"{func.__name__}은 별도 정답지 데이터가 필요해 아직 조사 루프에 연결되지 않음",
        }

    filtered = {k: v for k, v in params.items() if k in sig_params}
    if "part_category" in sig_params and "part_category" not in filtered:
        filtered["part_category"] = part_category

    # df를 제외하고 기본값이 없는(=호출 시 반드시 채워야 하는) 파라미터가
    # filtered에 빠져 있으면 TypeError로 크래시하는 대신 not_available로 처리.
    missing_required = [
        name for name, p in sig_params.items()
        if name != "df" and p.default is inspect.Parameter.empty and name not in filtered
    ]
    if missing_required:
        return {
            "status": "not_available",
            "note": f"{func.__name__} 호출에 필요한 파라미터 누락: {missing_required} "
                    "(LLM이 이 도구를 선택했지만 필수 값을 채우지 못함)",
        }

    return func(df, **filtered)


# ------------------------------------------------------------------
# [이식 2] 한국어-영어 키워드 매핑
# STR 산출물의 symptoms(한국어 명사구)를 원문(CDESCR, 영어) 검색용
# 키워드로 변환할 때 사용. query_templates의 텍스트 검색 쿼리에 넘길 수 있음.
# ------------------------------------------------------------------
KO_EN_KEYWORD_MAP = {
    "화재": ["fire", "smoke", "burn", "flame"],
    "연기": ["smoke", "smoking", "burn"],
    "계기판": ["dashboard", "instrument", "cluster", "display", "screen", "speedometer"],
    "꺼짐": ["shut off", "turned off", "blank", "black", "went out"],
    "시동": ["stall", "stalled", "engine", "shut off", "start"],
    "동력": ["loss of power", "lost power", "power loss", "limp"],
    "제동": ["brake", "braking", "abs"],
    "브레이크": ["brake", "braking", "abs"],
    "조향": ["steer", "steering"],
    "차선": ["lane", "departure", "assist"],
    "가속": ["acceleration", "accelerator", "throttle"],
    "후방": ["rear", "backup", "camera"],
    "카메라": ["camera"],
    "배터리": ["battery", "12v"],
    "충전": ["charge", "charging", "battery"],
}


def symptoms_to_en_keywords(symptoms: list[str], max_keywords: int = 8) -> list[str]:
    """구조화 결과의 한국어 symptoms 리스트 -> 원문 검색용 영어 키워드."""
    joined = " ".join(symptoms)
    out: list[str] = []
    for ko, ens in KO_EN_KEYWORD_MAP.items():
        if ko in joined:
            out.extend(ens)
    # 중복 제거, 순서 보존
    seen = set()
    deduped = []
    for k in out:
        if k not in seen:
            seen.add(k)
            deduped.append(k)
        if len(deduped) >= max_keywords:
            break
    return deduped


@dataclass
class InvestigationRecord:
    """문서1의 '조사 기록' JSON 계약과 1:1 대응."""
    hypothesis: str
    query_executed: list[str] = field(default_factory=list)
    query_result: list[dict] = field(default_factory=list)
    is_retained: bool | None = None
    status: str = "IN_PROGRESS"  # IN_PROGRESS | RETAINED | REJECTED | HOLD
    decision_reason: str = ""

    def to_json(self) -> dict:
        return {
            "hypothesis": self.hypothesis,
            "query_executed": self.query_executed,
            "query_result": self.query_result,
            "is_retained": self.is_retained,
            "status": self.status,
            "decision_reason": self.decision_reason,
        }


def run_investigation_loop(
    struct_batch: list[dict],
    df,
    part_category: str | list[str],
    llm_call: Callable[..., dict],
    target_model: str | None = None,
    target_model_year: str | None = None,
) -> dict:
    """
    struct_batch: 급증 구간 구조화 JSON 묶음 (STR 산출물, N건. odino/symptoms/severity 등 포함)
    df: load_enriched_df()로 만든 통합 DataFrame
    part_category: 이번 조사 대상 부품 카테고리. 2026-07-20부터 list[str]도 받는다
        (정윤님 CHT-01 쪽 요청 — "ADAS"처럼 v4의 여러 compdesc1 대분류에 걸친
        질문을 한 번에 조사할 때 사용. query_templates._filter_base()가 리스트를
        네이티브로 지원하므로 여기 그대로 전달만 하면 SCOUTING_QUERIES/
        select_query_or_conclude가 고르는 함수 호출 전부에 자동 반영된다).
    llm_call: (prompt_type, context) -> LLM JSON 응답. 실제 구현은 팀 공용 API 래퍼로 교체
    target_model / target_model_year: 이 조사가 애초에 어떤 질문에서 시작됐는지
        (예: 사용자가 "2025년식 투싼"을 물어본 경우). 상시 감시(급증 감지) 경로에서는
        보통 None — 급증 구간 전체가 조사 대상이라 특정 차종을 미리 못 박지 않음.
        None이 아니면 LLM에게 명시적으로 안내해서, 정찰 결과가 우연히 다른 차종
        위주로 나오더라도 엉뚱한 차종으로 가설을 세우지 않게 한다.
    """

    usable_batch = [
        record for record in struct_batch
        if not record.get("insufficient_info")
        and any(
            str(symptom).strip() and str(symptom).strip() != INSUFFICIENT_SYMPTOM
            for symptom in (record.get("symptoms") or [])
        )
    ]
    if not usable_batch:
        return {
            "overall_status": "HOLD",
            "final_hypothesis": None,
            "full_log": [],
            "decision_reason": "구조화 배치에 검증 가능한 증상 근거가 없어 보류했습니다.",
        }

    # ---------- 0단계: 정찰 (코드가 강제 실행) ----------
    scouting_results = {}
    for query_name in SCOUTING_QUERIES:
        func = TOOL_REGISTRY[query_name]["func"]
        scouting_results[query_name] = func(df, part_category)

    if not any(result.get("status") == "ok" for result in scouting_results.values()):
        return {
            "overall_status": "HOLD",
            "final_hypothesis": None,
            "full_log": [],
            "decision_reason": "정찰 쿼리에서 조사 가능한 데이터가 없어 보류했습니다.",
        }

    # 이식 2 활용: 이후 텍스트 검색 쿼리에 쓸 대표 키워드를 배치 전체에서 미리 뽑아둠
    all_symptoms = [s for rec in usable_batch for s in (rec.get("symptoms") or [])]
    batch_en_keywords = symptoms_to_en_keywords(all_symptoms)

    log: list[InvestigationRecord] = []

    for hyp_idx in range(MAX_HYPOTHESES):
        hyp_context = {
            "target_model": target_model,
            "target_model_year": target_model_year,
            "scouting_results": scouting_results,
            "sample_reports": usable_batch[:10],
            "batch_en_keywords": batch_en_keywords,  # 원문 검색용 참고 키워드
            "previous_rejected": [r.to_json() for r in log],
        }
        if target_model:
            hyp_context["instruction_note"] = (
                f"이 조사는 사용자가 '{target_model}"
                f"{(' ' + str(target_model_year) + '년식') if target_model_year else ''}'에 "
                "대해 물어봐서 시작됐다. scouting_results가 이 차종과 다른 차종 데이터 "
                "위주로 나왔다면, 그 다른 차종에 대한 가설을 세우지 마라. 대신 "
                "get_symptom_distribution_by_model 같은 도구로 이 차종만 직접 조회해서 "
                "확인하거나, 데이터가 없다면 '해당 차종·연식의 데이터가 부족하다'고 "
                "정직하게 판단할 것."
            )
        if hyp_idx > 0:
            hyp_context["instruction"] = "이전 가설은 기각됨. 정찰 결과에서 아직 설명 안 된 다른 패턴을 찾아라."

        hyp_response = _call_llm_safe(llm_call, "generate_hypothesis", hyp_context)
        if hyp_response is None:
            # API 호출 자체가 실패(예: 503) — 이 조사는 더 진행할 수 없으므로
            # 정직하게 HOLD로 종료한다. 크래시 대신 여기서 끊어야 상위
            # chat()/여러 질문 순회 루프가 계속 동작할 수 있다.
            return {
                "overall_status": "HOLD",
                "final_hypothesis": None,
                "full_log": [r.to_json() for r in log],
                "decision_reason": "LLM API 호출 실패(일시적 서버 오류로 추정)로 조사를 진행하지 못해 보류함.",
            }
        hypothesis_text = hyp_response.get("hypothesis") if isinstance(hyp_response, dict) else None
        if not isinstance(hypothesis_text, str) or not hypothesis_text.strip():
            return {
                "overall_status": "HOLD",
                "final_hypothesis": None,
                "full_log": [r.to_json() for r in log],
                "decision_reason": "LLM 가설 응답 형식이 올바르지 않아 조사를 보류했습니다.",
            }

        record = InvestigationRecord(hypothesis=hypothesis_text)
        record.query_executed.append("SCOUTING:" + ",".join(SCOUTING_QUERIES))
        record.query_result.append(scouting_results)

        for _ in range(MAX_QUERIES_PER_HYPOTHESIS):
            tool_menu = {name: meta["when_to_use"] for name, meta in TOOL_REGISTRY.items()}
            decision = _call_llm_safe(llm_call, "select_query_or_conclude", {
                "hypothesis": hypothesis_text,
                "target_model": target_model,
                "target_model_year": target_model_year,
                "results_so_far": record.query_result,
                "available_tools": tool_menu,
            })

            if decision is None:
                # API 실패 — 더 이상 쿼리 선택을 시도하지 않고 지금까지 모은
                # 정찰 결과만으로 conclude 단계로 넘어간다(judge_hypothesis도
                # 같은 API를 쓰므로 거기서도 실패할 수 있는데, 그건 아래
                # judge_hypothesis 호출부의 별도 방어로 처리됨).
                break
            if not isinstance(decision, dict):
                record.decision_reason = "LLM 쿼리 선택 응답 형식이 올바르지 않음"
                break
            if decision.get("action") == "conclude":
                break

            query_name = decision.get("query_name")
            if query_name not in TOOL_REGISTRY:
                record.decision_reason = f"LLM이 알 수 없는 도구를 선택함: {query_name!r}"
                break
            params = decision.get("params") or {}
            func = TOOL_REGISTRY[query_name]["func"]

            # safe_call_tool이 함수 시그니처를 보고 이 함수가 실제로 받는
            # 파라미터만 걸러서 안전하게 호출한다 (df를 안 받는 함수는
            # not_available로 정직하게 처리됨). 함수별 하드코딩 예외처리 불필요.
            result = safe_call_tool(func, df, part_category, params)
            applied_label = "exact"
            if result.get("status") == "no_data":
                result, applied_label = run_query_with_relaxation(func, df, part_category, params)
            elif result.get("status") == "not_available":
                applied_label = "not_available"

            record.query_executed.append(f"{query_name}[{applied_label}]")
            record.query_result.append(result)

        # 2026-07-20 신규: 가설 문장 자체가 불확실성/데이터 부족을 진술하고
        # 있으면, judge_hypothesis를 부를 필요 없이(=API 비용도 아낌) 코드가
        # 결정론적으로 바로 HOLD 처리한다. 위 UNCERTAINTY_MARKERS 설명 참고 —
        # "가설이 정찰 결과와 일치한다"와 "가설을 지지한다(RETAINED)"는 다른
        # 뜻인데, 가설=불확실성 진술인 경우 이 둘이 문자 그대로 뒤섞여 LLM이
        # RETAINED를 주는 사고가 실측(TUCSON/RAY/오타 케이스 등)으로 반복
        # 확인됨.
        if _hypothesis_is_uncertainty_statement(hypothesis_text):
            record.is_retained = None
            record.status = "HOLD"
            record.decision_reason = (
                "가설 자체가 데이터 부족/불확실성을 진술하고 있어 "
                "'가설 지지(RETAINED)'로 판정하지 않고 코드 레벨에서 바로 "
                "보류 처리함(judge_hypothesis 호출 생략)."
            )
            log.append(record)
            break

        verdict = _call_llm_safe(llm_call, "judge_hypothesis", {
            "hypothesis": hypothesis_text,
            "target_model": target_model,
            "target_model_year": target_model_year,
            "all_results": record.query_result,
        })

        if verdict is None:
            # API 실패 — 여기까지 모은 record(가설·쿼리 결과)는 살려두고
            # 판정만 HOLD로 정직하게 마무리한다.
            record.is_retained = None
            record.status = "HOLD"
            record.decision_reason = "LLM API 호출 실패(일시적 서버 오류로 추정)로 최종 판정을 내리지 못해 보류함."
            log.append(record)
            break

        if not isinstance(verdict, dict) or verdict.get("is_retained") not in (True, False, None):
            record.is_retained = None
            record.status = "HOLD"
            record.decision_reason = "LLM 최종 판정 응답 형식이 올바르지 않음"
            log.append(record)
            break

        record.is_retained = verdict["is_retained"]
        record.decision_reason = verdict.get("reason", "")

        if verdict["is_retained"] is True:
            record.status = "RETAINED"
            log.append(record)
            break
        elif verdict["is_retained"] is False:
            record.status = "REJECTED"
            log.append(record)
            continue
        else:
            record.status = "HOLD"
            log.append(record)
            break

    final = log[-1] if log else None
    overall_status = final.status if final else "HOLD"

    return {
        "overall_status": overall_status,
        "final_hypothesis": final.to_json() if final else None,
        "full_log": [r.to_json() for r in log],
    }


# ------------------------------------------------------------------
# [이식 3] 결과를 Judge/대시보드가 바로 파싱 가능한 고정 스키마로 flatten
# ------------------------------------------------------------------

def flatten_result(loop_output: dict, part_category: str | list[str]) -> dict:
    """run_investigation_loop() 결과 -> CSV 한 행에 대응하는 고정 스키마."""
    final = loop_output.get("final_hypothesis") or {}
    return {
        "part_category": part_category,
        "overall_status": loop_output.get("overall_status"),
        "hypothesis": final.get("hypothesis"),
        "is_retained": final.get("is_retained"),
        "decision_reason": final.get("decision_reason"),
        "num_hypotheses_tried": len(loop_output.get("full_log", [])),
        "query_executed_json": json.dumps(final.get("query_executed", []), ensure_ascii=False),
        "query_result_json": json.dumps(final.get("query_result", []), ensure_ascii=False),
        "full_log_json": json.dumps(loop_output.get("full_log", []), ensure_ascii=False),
    }


def save_investigation_log(results: list[dict], out_path: str = "data/processed/investigation_results.csv"):
    """여러 건의 flatten된 결과를 CSV로 저장. Judge(④)와 대시보드가 이 파일을 읽는다."""
    import pandas as pd
    from pathlib import Path

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df_out = pd.DataFrame(results)
    df_out.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[INV-03 SAVE] path={out} rows={len(df_out)}")
    return out


# ------------------------------------------------------------------
# [이식 4] 채팅(CHT-01)용 즉석 조사 진입점
# 급증 감지가 아니라 사용자가 직접 질문했을 때, 같은 파이프라인을 그대로 태운다.
# STR-05(질문 이해 모듈)가 뽑아준 {model, model_year, symptom_keyword}를 받아
# struct_batch 형태로 감싸서 동일한 run_investigation_loop를 재사용한다.
#
# 2026-07-15 효선 수정: question_parsed의 model/model_year를 run_investigation_loop
# 까지 명시적으로 전달하도록 변경 (target_model/target_model_year). 예전에는
# part_category만 넘기고 이 값들은 버려져서, 정찰 결과가 다른 차종 위주로 나오면
# LLM이 질문받은 차종을 모른 채 엉뚱한 차종으로 가설을 세우는 문제가 있었음.
# ------------------------------------------------------------------

def investigate_ad_hoc(
    question_parsed: dict,  # STR-05 출력: {"model": "투싼", "model_year": 2025, "symptom": "계기판 꺼짐"} 등
    df,
    llm_call: Callable[..., dict],
) -> dict:
    # 2026-07-20 수정: 기본값을 v3 잔재("INSUFFICIENT_INFO")에서 v4 실제
    # 최대 비중 카테고리("ELECTRICAL SYSTEM", 16,964건 중 6,837건/40%)로 교체.
    # 위 "2026-07-20 효선 수정 3" 참고 — 근본 해법은 CHT-01 라우팅 개선이고,
    # 이건 그래도 뭔가는 넣어야 하는 최후 폴백일 뿐이다.
    # 2026-07-20 추가: question_parsed["part_category"]가 list[str]이어도 그대로
    # 통과된다("ADAS"처럼 여러 대분류에 걸친 질문 — CHT-01이 이제 카테고리
    # 그룹을 하나로 묶어서 넘겨줄 수 있다. 아래 run_investigation_loop()가
    # 리스트를 네이티브로 받는다). 빈 리스트([])는 or 폴백에 안 걸리는 게
    # 아니라 falsy라 정상적으로 "ELECTRICAL SYSTEM" 기본값으로 빠진다.
    part_category = question_parsed.get("part_category") or "ELECTRICAL SYSTEM"
    target_model = question_parsed.get("model")
    target_model_year = question_parsed.get("model_year")

    # STR-05가 뽑아준 정보 부족하면 바로 보류 (감지 파이프라인과 동일한 원칙: 모르면 모른다)
    if not any([question_parsed.get("model"), question_parsed.get("symptom")]):
        return {
            "overall_status": "HOLD",
            "final_hypothesis": None,
            "full_log": [],
            "decision_reason": "질문에서 차종/증상 정보를 충분히 추출하지 못함",
        }

    pseudo_batch = [{
        "odino": "ADHOC",
        "part_category": part_category,
        "symptoms": [question_parsed.get("symptom")] if question_parsed.get("symptom") else [],
        "severity": "UNKNOWN",
        "evidence_quote": "",
        "insufficient_info": False,
    }]

    return run_investigation_loop(
        pseudo_batch, df, part_category, llm_call,
        target_model=target_model, target_model_year=target_model_year,
    )


def example_llm_call(prompt_type: str, context: dict) -> dict:
    """실제 구현 시 팀 공용 API 래퍼(scripts/llm_client.py 등)로 교체."""
    raise NotImplementedError("팀 공용 API 래퍼로 교체 필요")


if __name__ == "__main__":
    print("run_investigation_loop(struct_batch, df, part_category, llm_call) 형태로 호출")
