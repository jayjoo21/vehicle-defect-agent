"""
STA-01/02 전체 파이프라인 실행 스크립트
============================================================
sta01_02_status_tracking.py의 run_status_tracking()은 "신고 단위" 파이프라인
(CSV/JSONL 적재 -> STA-01/02 분류 -> export)만 담당하도록 그대로 뒀다(기존 호출부
호환 유지). RCL573 리콜 적재와 5단계 시그널 계산까지 포함한 "전체" 파이프라인은
이 스크립트가 새 진입점으로 담당한다 — 이렇게 나눠야 세 모듈
(sta01_02_status_tracking / sta_recall_loader / sta_signal_state)이 서로를
순환 참조하지 않는다(모듈 3개 모두 이 스크립트보다 "아래" 계층).

실행 순서
    1. init_db                        DB 스키마 생성/마이그레이션
    2. load_complaints_csv            원본 신고 CSV 적재
    3. load_structured_jsonl          STR 트랙 구조화 결과(JSONL) 적재
    4. load_rcl573_recalls            RCL573 실제 리콜 데이터 적재
    5. classify_all                   신고 단위 STA-01/02 분류(기존 로직)
    6. recompute_all_signal_states    차종×부품카테고리 단위 5단계 시그널 계산(신규)
    7. export_status_view / export_signal_view   대시보드용 CSV 내보내기

2026-07-14: 5번 단계는 더 이상 INV-01 CSV를 따로 안 읽는다. sta_signal_state.py가
INV-01 비의존으로 리팩터링되면서(효선님 실제 INV 파일에 q_recent_surge가 없어져서
자체 계산으로 대체함, sta_signal_state.py 상단 docstring 참고) 이 스크립트도
inv01_query_templates.load_processed() 호출을 걷어냈다.

사용법
    python3 sta_run_pipeline.py
    python3 sta_run_pipeline.py --csv <경로> --jsonl <경로> --recalls <경로>
"""
from __future__ import annotations

import argparse
from pathlib import Path

from sta01_02_status_tracking import (
    classify_all,
    export_signal_view,
    export_status_view,
    get_conn,
    init_db,
    load_complaints_csv,
    load_structured_jsonl,
    query_signal_summary,
    query_status_summary,
)
from sta_recall_loader import load_rcl573_recalls
from sta_signal_state import recompute_all_signal_states


def run(
    *,
    csv_path: str | Path | None = None,
    jsonl_path: str | Path | None = None,
    db_path: str | Path | None = None,
    recall_components_csv: str | Path | None = None,
    recall_shared_parts_csv: str | Path | None = None,
    skip_recall_load: bool = False,
):
    conn = init_db(db_path)
    load_complaints_csv(conn, csv_path)
    load_structured_jsonl(conn, jsonl_path)

    if not skip_recall_load:
        try:
            load_rcl573_recalls(conn, recall_components_csv, recall_shared_parts_csv)
        except FileNotFoundError as e:
            print(f"[STA PIPELINE][WARN] RCL573 리콜 데이터 적재 생략: {e}")

    classify_all(conn)
    recompute_all_signal_states(conn)

    export_status_view(conn)
    export_signal_view(conn)
    return conn


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="STA-01/02 전체 파이프라인 실행")
    parser.add_argument("--csv", dest="csv_path", default=None, help="신고 원본 CSV 경로")
    parser.add_argument("--jsonl", dest="jsonl_path", default=None, help="STR 구조화 결과 JSONL 경로")
    parser.add_argument("--db", dest="db_path", default=None, help="SQLite DB 경로")
    parser.add_argument("--recalls", dest="recall_csv", default=None, help="rcl573_components_normalized.csv 경로")
    parser.add_argument("--shared-parts", dest="shared_parts_csv", default=None, help="shared_parts.csv 경로")
    parser.add_argument("--skip-recall-load", action="store_true", help="RCL573 리콜 적재 단계 생략")
    args = parser.parse_args()

    conn0 = run(
        csv_path=args.csv_path,
        jsonl_path=args.jsonl_path,
        db_path=args.db_path,
        recall_components_csv=args.recall_csv,
        recall_shared_parts_csv=args.shared_parts_csv,
        skip_recall_load=args.skip_recall_load,
    )
    print("\n=== STA-01/02 (신고 단위) 요약 ===")
    print(query_status_summary(conn0).head(10).to_string(index=False))
    print("\n=== 시그널 (차종×부품카테고리 단위, 5단계) 요약 ===")
    print(query_signal_summary(conn0).head(10).to_string(index=False))
    conn0.close()
