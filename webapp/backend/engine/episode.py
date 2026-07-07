"""에피소드 단위 신호 상태 (v0 잠정안).

signals 테이블의 state 컬럼은 "셀 상태"다 — 모델×월 한 칸의 관측치를 그대로 보여준다
(seed.py의 derive_state: 리콜 매칭 시 recalled/resolved, 아니면 signal 발화=active,
count>baseline=rising, 그 외 new). 이 셀 상태는 스펙 9절 baseline(총 발화 67건 등,
CLAUDE.md 기록)과 정확히 일치해야 하므로 이 파일에서 절대 건드리지 않는다.

반면 대시보드 카드·KPI가 보여줘야 하는 건 "지금 이 결함이 진행 중인 에피소드인가"이므로
아래 규칙으로 최신월(reference_month) 기준 에피소드 상태를 signals 테이블과 별도로,
count/baseline로부터 매 요청마다 다시 계산한다(저장하지 않음).

규칙 (우선순위 순, 이 중 먼저 만족하는 것 하나만 반환):
  1) recalled — 매칭된 US 리콜의 report_date가 기준월 말일 이전이며, 기준월이 그
     접수일로부터 12개월(365일) 이내
  2) active   — (위 recalled 조건에 해당하지 않고) 최근 3개월(기준월 포함) 중
     하나라도 b1 스파이크 규칙 발화(당월count >= 직전6개월평균baseline*2 AND
     당월count >= 10건, scripts/b1_detect.py와 동일 기준) 조건을 만족
  3) rising   — 최근 2개월 연속으로 count >= baseline*1.5 AND count >= 5건
  4) new      — 그 외 (이력 없음, 회색)

"해당 결함 리콜 없음"은 "지금 이 시점에 12개월 이내 리콜 진행 중이 아님"을 뜻한다 —
훨씬 이전(예: 3년 전)의 리콜이 있었다는 사실만으로 이후의 완전히 새로운 급증까지
영구히 active 판정에서 배제하지는 않는다(그 급증 시점엔 이미 recalled 창을 벗어나
있으므로). 실측 검증(78개 base_model, 기준월 2026-06): active 1건(NIRO) + rising
1건(IONIQ 9) — CLAUDE.md에 기록된 baseline 발화 빈도(월평균 1.4건/78모델, 전체의
1.8%)와 정확히 같은 자릿수로, "이 달엔 조용하다"가 정상 상태임을 재확인한다.

한계 (v0 잠정안이며 본편 상태추적 모듈로 대체 예정):
  - 원인 결함 단위로 리콜을 구분하지 않으므로, 같은 모델에 여러 개의 서로 다른
    결함이 존재해도 리콜 하나로 전체를 뭉뚱그린다(근사치).
  - 여러 파워트레인 변형(base_model 동일, 예: TUCSON/TUCSON HYBRID)은 월별로
    count·baseline을 단순 합산해 하나의 에피소드로 취급한다.
"""
import pandas as pd

FIRE_MULTIPLIER = 2
FIRE_MIN_COUNT = 10
ACTIVE_LOOKBACK_MONTHS = 3

RISING_MULTIPLIER = 1.5
RISING_MIN_COUNT = 5
RISING_LOOKBACK_MONTHS = 2

RECALL_WINDOW_DAYS = 365


def _fired(count: float, baseline: float | None) -> bool:
    return bool(baseline) and count >= FIRE_MIN_COUNT and count >= FIRE_MULTIPLIER * baseline


def aggregate_by_month(rows) -> dict:
    """행 리스트([{month, count, baseline}, ...], 변형 여러 개 섞여 있을 수 있음)를
    월별로 합산한다. baseline은 None을 0으로 취급해 합산(초기 몇 개월은 6개월치
    이력이 없어 NULL일 수 있음)."""
    by_month: dict[str, dict] = {}
    for r in rows:
        entry = by_month.setdefault(r["month"], {"count": 0, "baseline": 0.0})
        entry["count"] += r["count"]
        entry["baseline"] += r["baseline"] or 0.0
    return by_month


def derive_episode_state(by_month: dict, reference_month: str, recall_report_dates) -> str:
    """by_month: aggregate_by_month() 결과. recall_report_dates: 이 base_model에
    매칭된 US 리콜들의 report_date(ISO) 리스트 (비어 있으면 리콜 없음)."""
    ref_end = pd.Period(reference_month, freq="M").end_time

    has_current_recall = False
    for us_date in recall_report_dates:
        us_ts = pd.Timestamp(us_date)
        if us_ts <= ref_end and (ref_end - us_ts).days <= RECALL_WINDOW_DAYS:
            has_current_recall = True
            break
    if has_current_recall:
        return "recalled"

    months_upto_ref = sorted(m for m in by_month if m <= reference_month)

    last3 = months_upto_ref[-ACTIVE_LOOKBACK_MONTHS:]
    if any(_fired(by_month[m]["count"], by_month[m]["baseline"]) for m in last3):
        return "active"

    last2 = months_upto_ref[-RISING_LOOKBACK_MONTHS:]
    if len(last2) == RISING_LOOKBACK_MONTHS and all(
        by_month[m]["baseline"] and by_month[m]["count"] >= RISING_MULTIPLIER * by_month[m]["baseline"]
        and by_month[m]["count"] >= RISING_MIN_COUNT
        for m in last2
    ):
        return "rising"

    return "new"
