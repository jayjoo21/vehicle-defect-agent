"""STA 데이터 적재, 리콜 연결, 상태 분류, 시그널 계산과 CSV 출력을 한 번에 실행한다."""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
import sys

from sta01_02_status_tracking import (
    classify_all,
    export_signal_view,
    export_status_view,
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
    jsonl_path: str | Path | Sequence[str | Path] | None = None,
    db_path: str | Path | None = None,
    recall_components_csv: str | Path | None = None,
    recall_shared_parts_csv: str | Path | None = None,
    skip_recall_load: bool = False,
    status_out_csv: str | Path | None = None,
    signal_out_csv: str | Path | None = None,
):
    conn = init_db(db_path)
    try:
        load_complaints_csv(conn, csv_path)
        multiple_jsonl = isinstance(jsonl_path, Sequence) and not isinstance(
            jsonl_path, (str, bytes, Path)
        )
        jsonl_paths = jsonl_path if multiple_jsonl else [jsonl_path]
        for path in jsonl_paths:
            load_structured_jsonl(conn, path)

        if not skip_recall_load:
            load_rcl573_recalls(conn, recall_components_csv, recall_shared_parts_csv)

        classify_all(conn, strict=True)
        recompute_all_signal_states(conn)

        if db_path:
            db_parent = Path(db_path).resolve().parent
            status_out_csv = status_out_csv or db_parent / "defect_status_view.csv"
            signal_out_csv = signal_out_csv or db_parent / "defect_signal_view.csv"
        export_status_view(conn, status_out_csv)
        export_signal_view(conn, signal_out_csv)
        return conn
    except Exception:
        conn.close()
        raise


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="STA-01/02 전체 파이프라인 실행")
    parser.add_argument("--csv", dest="csv_path", default=None, help="신고 원본 CSV 경로")
    parser.add_argument(
        "--jsonl",
        dest="jsonl_paths",
        action="append",
        default=None,
        help="STR 구조화 결과 JSONL 경로. 여러 파일이면 옵션을 반복해서 지정",
    )
    parser.add_argument("--db", dest="db_path", default=None, help="SQLite DB 경로")
    parser.add_argument("--recalls", dest="recall_csv", default=None, help="rcl573_components_normalized.csv 경로")
    parser.add_argument("--shared-parts", dest="shared_parts_csv", default=None, help="shared_parts.csv 경로")
    parser.add_argument("--skip-recall-load", action="store_true", help="RCL573 리콜 적재 단계 생략")
    parser.add_argument("--status-out", default=None, help="신고 단위 상태 CSV 출력 경로")
    parser.add_argument("--signal-out", default=None, help="5단계 시그널 CSV 출력 경로")
    args = parser.parse_args()

    conn0 = run(
        csv_path=args.csv_path,
        jsonl_path=args.jsonl_paths,
        db_path=args.db_path,
        recall_components_csv=args.recall_csv,
        recall_shared_parts_csv=args.shared_parts_csv,
        skip_recall_load=args.skip_recall_load,
        status_out_csv=args.status_out,
        signal_out_csv=args.signal_out,
    )
    print("\n=== STA-01/02 (신고 단위) 요약 ===")
    print(query_status_summary(conn0).head(10).to_string(index=False))
    print("\n=== 시그널 (차종×부품카테고리 단위, 5단계) 요약 ===")
    print(query_signal_summary(conn0).head(10).to_string(index=False))
    conn0.close()
