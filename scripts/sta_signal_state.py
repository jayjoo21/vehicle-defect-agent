"""
STA-01/02 핵심 모듈 — 차종×부품카테고리 단위 5단계 시그널 상태 전이
============================================================
배경
- defect_status_tracking(기존 STA-01/02)은 "신고 1건"이 판정 단위인 이진 분류
  (리콜 매칭 여부)다. 그런데 "신규 -> 증가 -> 리콜 -> 잠잠 -> 재발"은 신고 1건의
  속성이 아니라 "이 차종 × 이 부품 카테고리"라는 그룹(시그널) 전체의 생애주기다.
  이 모듈은 그 그룹 단위 판정만 전담한다. DB 스키마/저장은 전부
  sta01_02_status_tracking.py(upsert_signal_state 등)에 맡기고, 여기는 순수하게
  "무엇이 어떤 상태인가"를 계산하는 알고리즘만 가진다.

5단계 판정 순서 (위에서부터 우선순위, 하나 걸리면 그 즉시 확정)
    1) RECURRING(재발): 리콜 이력이 있고, 신고 이력 안에 DORMANT_MONTHS(6개월,
       팀 확정치) 이상 공백이 있었으며, 그 공백 이후 신고가 다시 들어옴.
    2) DORMANT(잠잠):   리콜 이력이 있고, 마지막 신고 이후 지금까지
       DORMANT_MONTHS 이상 신규 신고가 없음.
    3) RECALLED(리콜):  리콜 이력이 있음(위 두 조건에 해당 안 하면).
    4) RISING(증가):    리콜 이력은 없지만 최근 신고가 급증(STRONG_SURGE /
       NEW_OR_RARE_SPIKE / WATCH)으로 판단.
    5) NEW(신규):       그 외 전부.

왜 RECURRING/DORMANT가 recall_date에 의존하지 않는가
    sta_recall_loader.py가 남긴 것처럼 recall_date가 NULL인 리콜이 섞여 있을 수
    있다(RCL573 산출물 자체의 결측 — 해당 파일 docstring 참고, 지금은 수정됐지만
    구버전 CSV를 적재한 경우 여전히 NULL일 수 있음). RECURRING/DORMANT 판정은
    recall_date가 아니라 "신고 이력 자체의 시간 공백"으로 판단하므로 recall_date
    유무와 무관하게 항상 동작한다. recall_date는 있으면 사유 문구에 참고용으로만
    덧붙인다.

⚠️ 2026-07-14 개정 — INV-01 의존성 완전 제거
    효선님이 실제 INV-01/02/03 파일(query_templates.py, investigation_loop_v2.py)을
    전달해주셨는데, 이전에 STA가 의존하던 inv01_query_templates.py의 q_recent_surge()
    /load_processed()가 새 파일에는 아예 없다(설계가 통째로 바뀜). 그래서 이 모듈이
    INV-01 데이터프레임을 빌려 쓰던 방식을 걷어내고, "최근 신고 급증" 판정 로직
    (_classify_surge)을 이 파일 안에 자체 구현으로 옮겼다.

    이건 STA 입장에서 더 안전한 구조다 — STA는 이제 INV 쪽 함수명이나 데이터프레임
    스키마가 바뀌어도 전혀 영향을 안 받는다(예전엔 q_recent_surge가 없어지는 것만
    으로 이 파일 전체가 import 단계에서부터 깨졌음). 필요한 건 "이 그룹에 속한
    신고들의 날짜 목록"뿐인데, 그건 STA 자신의 SQLite(complaint_reports +
    structured_results)에 이미 있다 — INV-01 DataFrame을 ODINO로 다시 subset하는
    우회(_subset_by_odino)도 더 이상 필요 없다.

    구 버전과의 차이 하나: 예전엔 surge 계산의 기준 시점("최근 N개월"의 "지금")이
    그룹별로 제각각(INV-01 subset 자신의 최신 신고일)이었는데, 이번에 as_of를
    전체 재계산 배치 공통 기준시점(모든 그룹을 통틀어 가장 최근 신고일) 하나로
    통일했다. DORMANT/RECURRING 판정은 원래도 이 공통 as_of를 썼으니, 이제 5단계
    전체가 같은 시계로 판정된다 — 그룹마다 "최근"의 기준일이 달랐던 예전 설계보다
    일관성이 높아진 개선이다.

사용법
    from sta01_02_status_tracking import get_conn
    from sta_signal_state import recompute_all_signal_states

    conn = get_conn()
    recompute_all_signal_states(conn)   # inv_df 인자 더 이상 필요 없음
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from sta01_02_status_tracking import (
    SIGNAL_DORMANT,
    SIGNAL_NEW,
    SIGNAL_RECALLED,
    SIGNAL_RECURRING,
    SIGNAL_RISING,
    find_all_matching_recalls,
    upsert_signal_state,
)

DORMANT_MONTHS = 6.0  # 팀 확정(2026-07-13): 6개월 신규 신고 없으면 "잠잠"
SURGE_WINDOW_MONTHS = 6.0
DAYS_PER_MONTH = 30.44  # 평균 개월 길이 근사(365.25/12)

# _classify_surge()가 반환하는 surge_level 값 중 "증가"로 볼 것들.
# 등급 산정 기준(구 INV-01 q_recent_surge와 동일한 임계값을 자체 구현으로 이식):
#   recent==0                        -> NO_RECENT_SIGNAL
#   baseline==0 and recent>=3        -> NEW_OR_RARE_SPIKE
#   ratio>=3 and recent>=5           -> STRONG_SURGE
#   ratio>=2 and recent>=3           -> WATCH
#   그 외                             -> STABLE_OR_WEAK
RISING_SURGE_LEVELS = {"STRONG_SURGE", "NEW_OR_RARE_SPIKE", "WATCH"}


def _parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _months_between(a: datetime, b: datetime) -> float:
    return abs((b - a).days) / DAYS_PER_MONTH


def _max_internal_gap_months(sorted_dates: list[datetime]) -> float:
    """정렬된 신고일 목록에서, 연속한 두 신고 사이 가장 긴 공백(개월).
    신고가 0~1건이면 공백을 정의할 수 없으니 0.0."""
    if len(sorted_dates) < 2:
        return 0.0
    return max(_months_between(a, b) for a, b in zip(sorted_dates, sorted_dates[1:]))


def _classify_surge(
    dates: list[datetime], as_of: datetime, window_months: float = SURGE_WINDOW_MONTHS
) -> dict[str, Any]:
    """그룹의 신고일 리스트만으로 급증 여부를 자체 판정한다(INV-01 비의존).

    최근 window_months개월(recent)과 그 직전 window_months개월(baseline)의
    신고 건수를 비교한다. 둘 다 as_of를 기준으로 한 "날짜 창"이라 그룹마다
    기준 시점이 달라지지 않는다(위 모듈 docstring 참고).
    """
    window = timedelta(days=window_months * DAYS_PER_MONTH)
    recent_start = as_of - window
    baseline_start = recent_start - window

    recent_count = sum(1 for d in dates if recent_start < d <= as_of)
    baseline_count = sum(1 for d in dates if baseline_start < d <= recent_start)

    ratio: float | None
    if recent_count == 0:
        level, ratio = "NO_RECENT_SIGNAL", None
    elif baseline_count == 0:
        level = "NEW_OR_RARE_SPIKE" if recent_count >= 3 else "STABLE_OR_WEAK"
        ratio = None
    else:
        ratio = recent_count / baseline_count
        if ratio >= 3 and recent_count >= 5:
            level = "STRONG_SURGE"
        elif ratio >= 2 and recent_count >= 3:
            level = "WATCH"
        else:
            level = "STABLE_OR_WEAK"

    return {
        "surge_level": level,
        "recent_count": recent_count,
        "baseline_count": baseline_count,
        "ratio": round(ratio, 2) if ratio is not None else None,
    }


def fetch_signal_groups(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """complaint_reports + structured_results를 (vehicle_id, part_category)로 묶어
    그룹별 odino 목록과 신고일 목록을 뽑는다.

    part_category가 NULL이거나 'INSUFFICIENT_INFO'인 신고는 제외한다 — STR이
    카테고리를 판단하지 못했다고 명시한 건을 "부품 카테고리 시그널"로 집계하면
    의미가 없기 때문(오히려 여러 실제 카테고리의 노이즈를 한 덩어리로 섞는 꼴).
    """
    rows = conn.execute(
        """
        SELECT cr.odino, cr.vehicle_id, cr.fail_date, cr.ldate, sr.part_category
        FROM complaint_reports cr
        JOIN structured_results sr ON cr.odino = sr.odino
        WHERE sr.part_category IS NOT NULL
              AND sr.part_category != 'INSUFFICIENT_INFO'
              AND cr.vehicle_id IS NOT NULL
        """
    ).fetchall()

    groups: dict[tuple[int, str], dict[str, Any]] = {}
    for r in rows:
        key = (r["vehicle_id"], r["part_category"])
        g = groups.setdefault(
            key, {"vehicle_id": r["vehicle_id"], "part_category": r["part_category"], "odinos": [], "dates": []}
        )
        g["odinos"].append(r["odino"])
        d = _parse_iso_date(r["ldate"]) or _parse_iso_date(r["fail_date"])
        if d:
            g["dates"].append(d)
    return list(groups.values())


def compute_signal_state(
    conn: sqlite3.Connection,
    group: dict[str, Any],
    *,
    as_of: datetime | None = None,
    dormant_months: float = DORMANT_MONTHS,
) -> dict[str, Any]:
    """그룹 하나(차종×부품카테고리)의 5단계 상태를 판정해 dict로 반환한다.
    저장은 하지 않는다 — 호출자가 sta01_02_status_tracking.upsert_signal_state()로
    저장 여부를 결정한다(계산과 저장의 책임 분리).

    2026-07-14: inv_df 인자 제거됨(INV-01 의존성 제거). 시그널 시점 신고일만
    있으면 계산 가능하므로 STA 자신의 SQLite만으로 완결된다.
    """
    vehicle_id = group["vehicle_id"]
    part_category = group["part_category"]
    dates = sorted(group["dates"])
    odinos = group["odinos"]

    first_complaint = dates[0] if dates else None
    last_complaint = dates[-1] if dates else None
    as_of = as_of or last_complaint or datetime.now()

    recall_id, recall_basis, recall_date = find_all_matching_recalls(conn, vehicle_id, part_category)
    has_recall = recall_id is not None

    months_since_last = _months_between(last_complaint, as_of) if last_complaint else None
    max_gap = _max_internal_gap_months(dates)
    surge = _classify_surge(dates, as_of)

    # --- 5단계 판정 (docstring 상단 순서 그대로) ---------------------------
    if has_recall:
        recall_note = f"({recall_basis}" + (f", 리콜일 {recall_date})" if recall_date else ", 리콜일 미상)")
        if months_since_last is not None and months_since_last >= dormant_months:
            state = SIGNAL_DORMANT
            reason = (
                f"마지막 신고({last_complaint.date()}) 이후 {months_since_last:.1f}개월간 "
                f"신규 신고 없음(기준 {dormant_months:.0f}개월) {recall_note}"
            )
        elif max_gap >= dormant_months:
            state = SIGNAL_RECURRING
            reason = (
                f"신고 이력 중 {max_gap:.1f}개월 공백 이후 재신고 발생"
                f"(마지막 신고 {last_complaint.date()}) {recall_note}"
            )
        else:
            state = SIGNAL_RECALLED
            reason = f"리콜 이력 있음, 아직 뚜렷한 공백·재발 패턴 없음 {recall_note}"
    else:
        surge_level = surge.get("surge_level")
        if surge_level in RISING_SURGE_LEVELS:
            state = SIGNAL_RISING
            reason = (
                f"리콜 이력 없음, 최근 {SURGE_WINDOW_MONTHS:.0f}개월 신고 급증 신호 "
                f"(surge_level={surge_level}, 최근 {surge.get('recent_count')}건/"
                f"기준 {surge.get('baseline_count')}건, ratio={surge.get('ratio')})"
            )
        else:
            state = SIGNAL_NEW
            reason = "리콜 이력 없음, 급증 신호도 없음 — 신규 시그널"

    return {
        "vehicle_id": vehicle_id,
        "part_category": part_category,
        "signal_state": state,
        "state_reason": reason,
        "recall_id": recall_id,
        "complaint_count": len(odinos),
        "first_complaint_date": first_complaint.strftime("%Y-%m-%d") if first_complaint else None,
        "last_complaint_date": last_complaint.strftime("%Y-%m-%d") if last_complaint else None,
        "recent_count": surge.get("recent_count", 0),
        "baseline_count": surge.get("baseline_count", 0),
        "surge_ratio": surge.get("ratio"),
        "surge_level": surge.get("surge_level"),
        "quiet_months": round(max_gap, 1),
    }


def recompute_all_signal_states(
    conn: sqlite3.Connection,
    *,
    as_of: datetime | None = None,
    dormant_months: float = DORMANT_MONTHS,
) -> list[dict[str, Any]]:
    """전체 (vehicle_id, part_category) 조합을 순회하며 defect_signals를 갱신한다.

    as_of 기본값: STA 자신의 신고 이력 중 가장 최근 날짜("데이터 자체의 현재
    시점"). 실제 실행 시각이 아니라 데이터 안의 최신 시점을 기준으로 삼는 이유는
    과거 이력이 있는 NHTSA 데이터로 배치를 몇 번을 다시 돌려도 "6개월 무신고"
    같은 판정이 실행 시각에 따라 흔들리지 않게 하기 위해서다.

    2026-07-14: inv_df 인자 제거(더 이상 INV-01 DataFrame이 필요 없음).
    """
    groups = fetch_signal_groups(conn)

    if as_of is None:
        all_dates = [d for g in groups for d in g["dates"]]
        as_of = max(all_dates) if all_dates else datetime.now()

    results = []
    for group in groups:
        computed = compute_signal_state(conn, group, as_of=as_of, dormant_months=dormant_months)
        saved = upsert_signal_state(conn, computed)
        results.append(saved)

    counts = pd.Series([r["signal_state"] for r in results]).value_counts().to_dict() if results else {}
    print(f"[STA SIGNAL] as_of={as_of} 그룹 {len(results):,}개 재계산 완료. 상태 분포={counts}")
    return results


if __name__ == "__main__":
    from sta01_02_status_tracking import get_conn, query_signal_summary

    conn0 = get_conn()
    recompute_all_signal_states(conn0)
    print(query_signal_summary(conn0).head(20).to_string(index=False))
    conn0.close()
