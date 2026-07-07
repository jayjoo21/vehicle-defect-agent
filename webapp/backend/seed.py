"""DB 스키마 초기화 + 목데이터 적재.

스펙 9절 원칙: data/processed/의 실제 산출물만 변환한다 (지어내지 않음).
사용하는 실측 파일 4종:
  - data/processed/b1_signals.csv           → signals
  - data/processed/report_24V757000.md      → reports, recalls(EV9 24V757000), signal_states
  - data/processed/kr_us_gap.csv            → recalls, kr_us_gap
  - data/processed/llm_struct_test_results.jsonl → complaints (+ signals.top_symptom 보강)

llm_struct_test_results.jsonl에는 model/year/date가 없어(odino만 있음),
같은 ODINO의 실측 메타데이터(MODELTXT/YEARTXT/LDATE)를 data/processed/hk_electrical_recent_full.csv에서
조회해 조인한다 — 값을 지어내는 것이 아니라 동일 레코드의 이미 검증된 실측 필드를 가져오는 것.

EV6 데모 시나리오(수동 seed)는 seed_manual.py로 분리되어 있으며, 실제 확인된 레코드가 없어 현재는 빈 상태.
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_connection
from models import init_schema
from engine.normalize import normalize_model

import seed_manual

REPO_ROOT = Path(__file__).resolve().parents[2]

B1_SIGNALS_PATH = REPO_ROOT / "data/processed/b1_signals.csv"
REPORT_EV9_PATH = REPO_ROOT / "data/processed/report_24V757000.md"
KR_US_GAP_PATH = REPO_ROOT / "data/processed/kr_us_gap.csv"
STRUCT_JSONL_PATH = REPO_ROOT / "data/processed/llm_struct_test_results.jsonl"
COMPLAINT_META_PATH = REPO_ROOT / "data/processed/hk_electrical_recent_full.csv"

LATEST_MONTH = pd.Period("2026-06", freq="M")


def ymd_to_iso(ymd: str) -> str:
    """YYYYMMDD -> YYYY-MM-DD"""
    return f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}"


# ---------------------------------------------------------------------------
# kr_us_gap.csv 로드 + 리콜 조회용 인덱스
# ---------------------------------------------------------------------------

def load_gap_df() -> pd.DataFrame:
    df = pd.read_csv(KR_US_GAP_PATH, dtype=str, encoding="utf-8-sig")
    df["base_model"] = df["모델_영문"].apply(normalize_model)
    return df


def build_recall_lookup(gap_df: pd.DataFrame) -> dict:
    """base_model -> [{us_date, kr_date, kr_start}, ...] (미국_캠페인번호 존재 행만)"""
    lookup: dict[str, list[dict]] = {}
    matched = gap_df[gap_df["미국_캠페인번호"].notna()]
    for _, row in matched.iterrows():
        lookup.setdefault(row["base_model"], []).append(
            {
                "campaign": row["미국_캠페인번호"],
                "us_date": pd.Timestamp(row["미국_접수일"]),
                "kr_announce_date": row["한국_발표일"],
                "kr_start_date": row["한국_시정시작일"] if pd.notna(row.get("한국_시정시작일")) else None,
            }
        )
    return lookup


# ---------------------------------------------------------------------------
# complaints (llm_struct_test_results.jsonl + hk_electrical_recent_full.csv 메타 조인)
# ---------------------------------------------------------------------------

def load_struct_complaints() -> list[dict]:
    records = []
    with open(STRUCT_JSONL_PATH, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    odinos = [r["odino"] for r in records]
    meta_df = pd.read_csv(COMPLAINT_META_PATH, dtype=str, encoding="utf-8-sig")
    meta_df = meta_df[meta_df["ODINO"].isin(odinos)][["ODINO", "MODELTXT", "YEARTXT", "LDATE"]].drop_duplicates(
        subset="ODINO"
    )
    meta = {row["ODINO"]: row for _, row in meta_df.iterrows()}

    out = []
    for r in records:
        m = meta.get(r["odino"])
        if m is None:
            continue  # 메타데이터 없는 레코드는 스킵 (지어내지 않음)
        symptoms = r.get("symptoms", [])
        out.append(
            {
                "odino": r["odino"],
                "model": m["MODELTXT"],
                "base_model": normalize_model(m["MODELTXT"]),
                "year": m["YEARTXT"],
                "date": ymd_to_iso(m["LDATE"]),
                "text": r.get("evidence_quote", ""),
                "part_category": r.get("part_category"),
                "symptom": symptoms[0] if symptoms else None,
                "severity": r.get("severity"),
            }
        )
    return out


def seed_complaints(conn, complaints: list[dict]):
    conn.executemany(
        """INSERT OR IGNORE INTO complaints (odino, model, year, date, text, part_category, symptom, severity)
           VALUES (:odino, :model, :year, :date, :text, :part_category, :symptom, :severity)""",
        complaints,
    )
    conn.commit()


# ---------------------------------------------------------------------------
# signals (b1_signals.csv) — state는 아래 규칙으로 파생, 지어낸 값 없음
#   1) 해당 base_model에 대해 kr_us_gap.csv 매칭 리콜의 us_date <= 이 달 말일 이면 'recalled'
#      (kr_start_date <= 이 달 말일이면 'resolved'로 승격)
#   2) 그 외 signal(스파이크 발화)==True 면 'active'
#   3) 그 외 count > baseline_avg6 (증가 추세)면 'rising'
#   4) 그 외 'new' (이력 없음/잠잠)
# ---------------------------------------------------------------------------

def derive_state(base_model: str, month_period: pd.Period, signal_flag: bool, count: float, baseline: float,
                  recall_lookup: dict) -> str:
    month_end = month_period.end_time
    recalls = recall_lookup.get(base_model, [])
    for rec in recalls:
        if rec["us_date"] <= month_end:
            if rec["kr_start_date"]:
                try:
                    kr_start = pd.Timestamp(rec["kr_start_date"])
                    if kr_start <= month_end:
                        return "resolved"
                except (ValueError, TypeError):
                    pass
            return "recalled"
    if signal_flag:
        return "active"
    if pd.notna(baseline) and count > baseline:
        return "rising"
    return "new"


def load_b1_signals() -> pd.DataFrame:
    """b1_signals.csv를 원본 그대로(모델 변형별 행 유지) 읽는다.

    주의: count/baseline_avg6/signal은 scripts/b1_detect.py가 이미 계산한 실측값이며,
    CLAUDE.md에 검증·기록된 baseline(총 발화 67건 등)과 정확히 일치해야 하므로
    여기서 base_model 단위로 재집계하지 않는다 — TUCSON HYBRID처럼 변형 차종을
    base 차종(TUCSON)과 합산해 재계산하면 baseline이 높아져 실제 스파이크(예:
    TUCSON HYBRID 2026-06, 26건/baseline 3.5)가 희석되어 사라지는 부작용을 확인했다.
    base_model은 리콜 매칭(derive_state)·증상 조인(top_symptom)·API 조회 시
    변형을 묶어 보여주는 용도로만 사용한다.
    """
    df = pd.read_csv(B1_SIGNALS_PATH, dtype={"model": str, "month": str})
    df["count"] = df["count"].astype(int)
    df["baseline_avg6"] = df["baseline_avg6"].astype(float)
    df["signal"] = df["signal"].astype(str).str.strip().str.lower() == "true"
    df["base_model"] = df["model"].apply(normalize_model)
    df["month_period"] = df["month"].apply(lambda m: pd.Period(m, freq="M"))
    return df


def build_top_symptom_lookup(struct_complaints: list[dict]) -> dict:
    """(base_model, YYYY-MM) -> '최빈 part_category (n/총건수)' 문자열. 표본 20건 범위 내에서만 존재."""
    from collections import Counter, defaultdict

    groups: dict[tuple, list[str]] = defaultdict(list)
    for c in struct_complaints:
        month = c["date"][:7]
        groups[(c["base_model"], month)].append(c["part_category"])

    lookup = {}
    for key, cats in groups.items():
        top, n = Counter(cats).most_common(1)[0]
        lookup[key] = f"{top} ({n}/{len(cats)})"
    return lookup


EV9_TOP_SYMPTOM = "INSTRUMENT_CLUSTER 계기판 블랙아웃 (28/29, 96.6%)"  # report_24V757000.md 실측 수치


def seed_signals(conn, b1_df: pd.DataFrame, recall_lookup: dict, symptom_lookup: dict) -> dict:
    """반환: (base_model, month_str) -> signal row id"""
    id_map = {}
    for row in b1_df.itertuples(index=False):
        state = derive_state(row.base_model, row.month_period, row.signal, row.count, row.baseline_avg6,
                              recall_lookup)
        key = (row.base_model, row.month)
        if key == ("EV9", "2024-09"):
            top_symptom = EV9_TOP_SYMPTOM
        else:
            top_symptom = symptom_lookup.get(key)
        cur = conn.execute(
            """INSERT INTO signals (model, month, count, baseline, state, top_symptom, report_id)
               VALUES (?, ?, ?, ?, ?, ?, NULL)""",
            (row.model, row.month, row.count, row.baseline_avg6, state, top_symptom),
        )
        id_map[key] = cur.lastrowid
    conn.commit()
    return id_map


# ---------------------------------------------------------------------------
# recalls: kr_us_gap.csv 매칭 행(country=US) + EV9 24V757000(report_24V757000.md, country=US)
# ---------------------------------------------------------------------------

def seed_recalls(conn, gap_df: pd.DataFrame):
    matched = gap_df[gap_df["미국_캠페인번호"].notna()].drop_duplicates(subset="미국_캠페인번호")
    rows = []
    for _, r in matched.iterrows():
        cause = r["한국_원인"] if pd.notna(r.get("한국_원인")) else ""
        symptom = r["한국_증상"] if pd.notna(r.get("한국_증상")) else ""
        summary = " / ".join(x for x in [cause, symptom] if x) or None
        rows.append(
            (
                r["미국_캠페인번호"],
                "US",
                r["base_model"],
                r["미국_접수일"],
                r["미국_컴포넌트"],
                summary,
                r["한국_발표일"],
            )
        )
    conn.executemany(
        """INSERT OR IGNORE INTO recalls (campaign, country, model, report_date, component, summary, kr_announce_date)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )

    # EV9 24V757000 — report_24V757000.md 실측 (kr_us_gap.csv에는 이 캠페인의 한국 매칭 행이 없음)
    conn.execute(
        """INSERT OR IGNORE INTO recalls (campaign, country, model, report_date, component, summary, kr_announce_date)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            "24V757000",
            "US",
            "EV9",
            "2024-10-10",
            "ELECTRICAL SYSTEM: INSTRUMENT CLUSTER/PANEL",
            "주행 중 계기판(속도계·방향지시등 표시) 화면이 갑자기 꺼지는 결함으로 인한 리콜 (report_24V757000.md)",
            None,
        ),
    )
    conn.commit()


def seed_kr_us_gap(conn, gap_df: pd.DataFrame):
    rows = []
    for _, r in gap_df.iterrows():
        campaign = r["미국_캠페인번호"] if pd.notna(r.get("미국_캠페인번호")) else r["한국_차종_원문"]
        gap_days = None
        if pd.notna(r.get("시차_일")):
            try:
                gap_days = int(float(r["시차_일"]))
            except ValueError:
                gap_days = None
        rows.append(
            (
                campaign,
                r["미국_접수일"] if pd.notna(r.get("미국_접수일")) else None,
                r["한국_발표일"] if pd.notna(r.get("한국_발표일")) else None,
                r["한국_시정시작일"] if pd.notna(r.get("한국_시정시작일")) else None,
                gap_days,
                r["분류"],
            )
        )
    conn.executemany(
        "INSERT INTO kr_us_gap (campaign, us_date, kr_date, kr_start_date, gap_days, note) VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


# ---------------------------------------------------------------------------
# reports + signal_states (EV9, report_24V757000.md 실측)
# ---------------------------------------------------------------------------

def seed_reports(conn, ev9_signal_id):
    markdown = REPORT_EV9_PATH.read_text(encoding="utf-8")
    cur = conn.execute(
        "INSERT INTO reports (signal_id, title, markdown, created_at) VALUES (?, ?, ?, ?)",
        (ev9_signal_id, "EV9 계기판 블랙아웃 시그널 리포트 — 24V757000 되감기 사례", markdown, "2026-07-06"),
    )
    conn.commit()
    report_id = cur.lastrowid
    conn.execute("UPDATE signals SET report_id = ? WHERE id = ?", (report_id, ev9_signal_id))
    conn.commit()
    return report_id, len(markdown)


def seed_signal_states(conn, ev9_signal_id):
    rows = [
        (ev9_signal_id, "active", "2024-09-01"),  # b1 발화월 (report_24V757000.md)
        (ev9_signal_id, "recalled", "2024-10-10"),  # 24V757000 접수일 (report_24V757000.md)
    ]
    conn.executemany(
        "INSERT INTO signal_states (signal_id, state, changed_at) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def seed():
    conn = get_connection()
    init_schema(conn)
    # 재실행 가능하도록 기존 데이터 초기화 (스키마는 유지)
    for table in ["signal_states", "reports", "signals", "recalls", "kr_us_gap", "complaints"]:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()

    gap_df = load_gap_df()
    recall_lookup = build_recall_lookup(gap_df)

    struct_complaints = load_struct_complaints()
    seed_complaints(conn, struct_complaints)
    seed_manual.seed(conn)

    symptom_lookup = build_top_symptom_lookup(struct_complaints)
    b1_df = load_b1_signals()
    id_map = seed_signals(conn, b1_df, recall_lookup, symptom_lookup)

    seed_recalls(conn, gap_df)
    seed_kr_us_gap(conn, gap_df)

    ev9_signal_id = id_map[("EV9", "2024-09")]
    report_id, report_len = seed_reports(conn, ev9_signal_id)
    seed_signal_states(conn, ev9_signal_id)

    print_integrity_report(conn, report_len)
    conn.close()


def print_integrity_report(conn, ev9_report_len: int):
    print("=== seed 정합성 리포트 ===")
    for table in ["complaints", "recalls", "signals", "signal_states", "reports", "kr_us_gap"]:
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {n}행")

    print("\n  signals 상태별 분포:")
    for state, n in conn.execute("SELECT state, COUNT(*) as n FROM signals GROUP BY state ORDER BY n DESC"):
        print(f"    {state}: {n}건")

    n_gap = conn.execute("SELECT COUNT(*) FROM kr_us_gap").fetchone()[0]
    santafe = conn.execute("SELECT * FROM kr_us_gap WHERE gap_days = 152").fetchall()
    tucson = conn.execute("SELECT * FROM kr_us_gap WHERE gap_days = 8").fetchall()
    print(f"\n  kr_us_gap: {n_gap}행 (원본 kr_us_gap.csv 27행 기대)")
    print(f"    싼타페 +152일 포함: {'O' if santafe else 'X'}")
    print(f"    투싼 +8일 포함: {'O' if tucson else 'X'}")

    print(f"\n  EV9 리포트 마크다운 글자 수: {ev9_report_len}자")

    # KPI 4종 실계산
    watched_models = conn.execute("SELECT COUNT(DISTINCT model) FROM signals").fetchone()[0]
    latest_month = conn.execute("SELECT MAX(month) FROM signals").fetchone()[0]
    active_now = conn.execute("SELECT COUNT(*) FROM signals WHERE month = ? AND state = 'active'",
                               (latest_month,)).fetchone()[0]
    prev_month = str(pd.Period(latest_month, freq="M") - 1)
    new_alarm = conn.execute(
        """SELECT COUNT(*) FROM signals cur
           WHERE cur.month = ? AND cur.state = 'active'
           AND NOT EXISTS (
             SELECT 1 FROM signals prev
             WHERE prev.model = cur.model AND prev.month = ? AND prev.state = 'active'
           )""",
        (latest_month, prev_month),
    ).fetchone()[0]
    # KPI4 "미국 리콜·한국 미조치": kr_us_gap.csv는 한국 보도자료를 기점으로 수집된 데이터라
    # "미국 리콜은 있으나 한국 발표 자체가 없는" 케이스는 이 4개 파일 범위 안에서 표현되지 않는다.
    # 근사치로, 미국 캠페인은 매칭됐지만 한국_시정시작일이 아직 기록되지 않은 건을 센다.
    us_unremediated_approx = conn.execute(
        "SELECT COUNT(*) FROM kr_us_gap WHERE us_date IS NOT NULL AND kr_start_date IS NULL"
    ).fetchone()[0]

    print("\n  KPI 4종 (실측 계산):")
    print(f"    감시 차종: {watched_models}")
    print(f"    활성 시그널 (최신월 {latest_month}): {active_now}")
    print(f"    신규 알람 (최신월, 전월 대비 신규 active): {new_alarm}")
    print(f"    미국 리콜·한국 시정시작일 미기재 (근사): {us_unremediated_approx}")


if __name__ == "__main__":
    seed()
