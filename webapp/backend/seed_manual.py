"""조사 채팅 데모 시나리오(EV6·IONIQ 5)용 수동 seed.

seed.py 본 파이프라인은 2단계 조건에 따라 data/processed/의 4개 파일로 제한되지만,
4단계(조사 채팅) 데모는 "이력 조회"·"리콜 대조" 단계에서 라이브 쿼리 결과가 실측과
일치해야 하므로 이 두 실측 파일에서 데모 차종 전량을 직접 가져온다 — 지어낸 값 없음.
  - data/processed/hk_electrical_recent_full.csv → 차종별 고유 불만 전량
  - data/recalls/recalls_hk_by_vehicle.csv       → 차종별 실제 US 리콜 전량

발견 사항 1 (EV6, 2026-07-07, 사용자 확인 완료): 스펙 4절의 EV6 데모 각본은 "EV6 계기판
리콜 없음"을 전제하지만 실제로는 다르다 — EV6는 이미 ICCU(통합충전제어장치) 12V 배터리
리콜(24V200000, 이후 24V867000으로 확대)을 보유하고 있고, "계기판이 깜빡이다 꺼짐" 신고
대부분이 12V 방전의 전조 증상으로 이미 이 리콜에 의해 설명된다. 전력손실·ICCU 언급 없이
순수 계기판 표시 결함으로 보이는 사례(ODINO 11630458 2024-12·11670403 2025-06)는 있으나
둘 다 최근 90일보다 오래돼, "최근 재발 없음"이 정확한 서술이다.

발견 2 (IONIQ 5): kr_us_gap.csv는 캠페인당 "조회한 차종" 하나만 기록해서(예: 24V204000은
IONIQ 6로만 기록) 같은 캠페인이 실제로 걸리는 다른 차종(IONIQ 5도 동일 ICCU 결함 대상)이
자동 seed.py 파이프라인의 recalls 테이블에서 누락되는 구조적 한계가 있다. IONIQ 5는
2026년 상반기 ICCU/12V 배터리 신고가 극단적으로 급증한 상태(최근 90일 103건 중 82건이
ICCU/12V 키워드 언급, b1_signals.csv 기준 2026-02 월 192건)라 조사 채팅 데모 차종으로
적합 — recalls_hk_by_vehicle.csv에서 IONIQ 5 실제 리콜 14건 전량을 별도로 보강한다.
(다른 차종에도 같은 누락이 있을 수 있음 — 전체 파이프라인 개선은 이 세션 범위 밖으로 남김.)
"""
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPLAINT_SOURCE = REPO_ROOT / "data/processed/hk_electrical_recent_full.csv"
RECALL_SOURCE = REPO_ROOT / "data/recalls/recalls_hk_by_vehicle.csv"

DEMO_MODELS = ["EV6", "IONIQ 5"]

# EV6: 12V/ICCU 언급 없이 순수 계기판 표시 이상만 보고된 실측 2건 — 조사 채팅에서 직접 인용
CLUSTER_ONLY_ODINOS = {"11630458", "11670403"}


def ymd_to_iso(ymd: str) -> str:
    return f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}"


def load_model_complaints(model: str) -> list[dict]:
    df = pd.read_csv(COMPLAINT_SOURCE, dtype=str, encoding="utf-8-sig")
    matched = df[df["MODELTXT"].str.upper() == model.upper()].drop_duplicates(subset="ODINO")
    rows = []
    for _, r in matched.iterrows():
        rows.append(
            {
                "odino": r["ODINO"],
                "model": model,
                "year": r["YEARTXT"],
                "date": ymd_to_iso(r["LDATE"]),
                "text": r["CDESCR"],
                "part_category": "INSTRUMENT_CLUSTER" if r["ODINO"] in CLUSTER_ONLY_ODINOS else None,
                "symptom": None,
                "severity": None,
            }
        )
    return rows


def load_model_recalls(model: str) -> list[tuple]:
    df = pd.read_csv(RECALL_SOURCE, dtype=str, encoding="utf-8-sig")
    matched = df[df["Model"].str.upper() == model.upper()].drop_duplicates(subset="NHTSACampaignNumber")
    rows = []
    for _, r in matched.iterrows():
        rows.append(
            (
                r["NHTSACampaignNumber"],
                "US",
                model,
                r["report_date_iso"],
                r["Component"],
                r["Summary"],
                None,  # kr_announce_date: 국토부 보도자료 미매칭 (실제로 매칭 정보 없음)
            )
        )
    return rows


def seed(conn):
    for model in DEMO_MODELS:
        complaints = load_model_complaints(model)
        conn.executemany(
            """INSERT OR IGNORE INTO complaints
               (odino, model, year, date, text, part_category, symptom, severity)
               VALUES (:odino, :model, :year, :date, :text, :part_category, :symptom, :severity)""",
            complaints,
        )
        recalls = load_model_recalls(model)
        conn.executemany(
            """INSERT OR IGNORE INTO recalls (campaign, country, model, report_date, component, summary, kr_announce_date)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            recalls,
        )
        print(f"seed_manual: {model} 실측 불만 {len(complaints)}건, 실측 US 리콜 {len(recalls)}건 적재")
    conn.commit()
