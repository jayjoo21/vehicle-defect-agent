"""조사 채팅 데모 시나리오(EV6·IONIQ 5)용 수동 seed — 불만(complaints)만 담당.

seed.py 본 파이프라인은 2단계 조건에 따라 data/processed/의 4개 파일로 제한되지만,
4단계(조사 채팅) 데모는 "이력 조회" 단계에서 라이브 쿼리 결과가 실측과 일치해야
하므로 이 실측 파일에서 데모 차종의 고유 불만 전량을 직접 가져온다 — 지어낸 값 없음.
  - data/processed/hk_electrical_recent_full.csv → 차종별 고유 불만 전량

리콜(recalls)은 5단계 착수 전 recalls_hk_by_vehicle.csv 전량으로 재구축되면서
EV6·IONIQ 5를 포함한 27개 차종 전체가 이미 seed.py의 seed_recalls()에서 채워지므로,
여기서는 더 이상 리콜을 따로 넣지 않는다(중복 삽입 방지 — recalls.campaign은
더 이상 유일키가 아니라서 중복 INSERT가 조용히 무시되지 않고 그대로 쌓인다).

발견 사항 (EV6, 2026-07-07, 사용자 확인 완료): 스펙 4절의 EV6 데모 각본은 "EV6 계기판
리콜 없음"을 전제하지만 실제로는 다르다 — EV6는 이미 ICCU(통합충전제어장치) 12V 배터리
리콜(24V200000, 이후 24V867000으로 확대)을 보유하고 있고, "계기판이 깜빡이다 꺼짐" 신고
대부분이 12V 방전의 전조 증상으로 이미 이 리콜에 의해 설명된다. 전력손실·ICCU 언급 없이
순수 계기판 표시 결함으로 보이는 사례(ODINO 11630458 2024-12·11670403 2025-06)는 있으나
둘 다 최근 90일보다 오래돼, "최근 재발 없음"이 정확한 서술이다.
"""
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPLAINT_SOURCE = REPO_ROOT / "data/processed/hk_electrical_recent_full.csv"

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


def seed(conn):
    for model in DEMO_MODELS:
        complaints = load_model_complaints(model)
        conn.executemany(
            """INSERT OR IGNORE INTO complaints
               (odino, model, year, date, text, part_category, symptom, severity)
               VALUES (:odino, :model, :year, :date, :text, :part_category, :symptom, :severity)""",
            complaints,
        )
        print(f"seed_manual: {model} 실측 불만 {len(complaints)}건 적재")
    conn.commit()
