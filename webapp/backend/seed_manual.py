"""EV6 조사 채팅 데모 시나리오용 수동 seed.

seed.py 본 파이프라인은 2단계 조건에 따라 data/processed/의 4개 파일로 제한되지만,
4단계(조사 채팅) 데모는 "이력 조회"·"리콜 대조" 단계에서 라이브 쿼리 결과가 실측과
일치해야 하므로 이 두 실측 파일에서 EV6 전량을 직접 가져온다 — 지어낸 값 없음.
  - data/processed/hk_electrical_recent_full.csv → EV6 고유 불만 449건 전량
  - data/recalls/recalls_hk_by_vehicle.csv       → EV6 실제 US 리콜 4건 전량

발견 사항 (2026-07-07, 사용자 확인 완료): 스펙 4절의 EV6 데모 각본은 "EV6 계기판 리콜
없음"을 전제하지만 실제로는 다르다 — EV6는 이미 ICCU(통합충전제어장치) 12V 배터리 리콜
(24V200000, 이후 24V867000으로 확대)을 보유하고 있고, "계기판이 깜빡이다 꺼짐" 신고
대부분이 12V 방전의 전조 증상으로 이미 이 리콜에 의해 설명된다. 전력손실·ICCU 언급 없이
순수 계기판 표시 결함으로 보이는 사례(ODINO 11630458 2024-12·11670403 2025-06)는 있으나
둘 다 최근 90일보다 오래돼, "최근 재발 없음"이 정확한 서술이다. 채팅 각본은 이 현실을
반영해 작성한다(투싼 26V400000처럼 "리콜 없음" 전제를 쓰지 않음).
"""
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPLAINT_SOURCE = REPO_ROOT / "data/processed/hk_electrical_recent_full.csv"
RECALL_SOURCE = REPO_ROOT / "data/recalls/recalls_hk_by_vehicle.csv"

# 12V/ICCU 언급 없이 순수 계기판 표시 이상만 보고된 실측 2건 — 조사 채팅에서 직접 인용
CLUSTER_ONLY_ODINOS = {"11630458", "11670403"}


def ymd_to_iso(ymd: str) -> str:
    return f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}"


def load_ev6_complaints() -> list[dict]:
    df = pd.read_csv(COMPLAINT_SOURCE, dtype=str, encoding="utf-8-sig")
    ev6 = df[df["MODELTXT"].str.upper() == "EV6"].drop_duplicates(subset="ODINO")
    rows = []
    for _, r in ev6.iterrows():
        rows.append(
            {
                "odino": r["ODINO"],
                "model": "EV6",
                "year": r["YEARTXT"],
                "date": ymd_to_iso(r["LDATE"]),
                "text": r["CDESCR"],
                "part_category": "INSTRUMENT_CLUSTER" if r["ODINO"] in CLUSTER_ONLY_ODINOS else None,
                "symptom": None,
                "severity": None,
            }
        )
    return rows


def load_ev6_recalls() -> list[tuple]:
    df = pd.read_csv(RECALL_SOURCE, dtype=str, encoding="utf-8-sig")
    ev6 = df[df["Model"].str.upper() == "EV6"].drop_duplicates(subset="NHTSACampaignNumber")
    rows = []
    for _, r in ev6.iterrows():
        rows.append(
            (
                r["NHTSACampaignNumber"],
                "US",
                "EV6",
                r["report_date_iso"],
                r["Component"],
                r["Summary"],
                None,  # kr_announce_date: 국토부 보도자료 미매칭 (실제로 매칭 정보 없음)
            )
        )
    return rows


def seed(conn):
    complaints = load_ev6_complaints()
    conn.executemany(
        """INSERT OR IGNORE INTO complaints
           (odino, model, year, date, text, part_category, symptom, severity)
           VALUES (:odino, :model, :year, :date, :text, :part_category, :symptom, :severity)""",
        complaints,
    )
    recalls = load_ev6_recalls()
    conn.executemany(
        """INSERT OR IGNORE INTO recalls (campaign, country, model, report_date, component, summary, kr_announce_date)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        recalls,
    )
    conn.commit()
    print(f"seed_manual: EV6 실측 불만 {len(complaints)}건, 실측 US 리콜 {len(recalls)}건 적재")
