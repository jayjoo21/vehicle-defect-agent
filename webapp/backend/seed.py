"""DB 스키마 초기화 + 목데이터 적재.

스펙 9절 원칙: data/processed/·data/recalls/의 실제 산출물만 변환한다 (지어내지 않음).
사용하는 실측 파일:
  - data/processed/b1_signals.csv           → signals
  - data/processed/report_24V757000.md      → reports, signal_states
  - data/recalls/recalls_hk_by_vehicle.csv  → recalls (정본, 5단계 착수 전 재구축)
  - data/processed/kr_us_gap.csv            → kr_us_gap (한미 시차 전용, recalls와는 별개)
  - data/processed/llm_struct_test_results.jsonl → complaints (+ signals.top_symptom 보강)

recalls 재구축 이력: 원래 kr_us_gap.csv(한미 매칭용, 27행)로 recalls를 채웠으나 이 파일은
캠페인당 "조회한 차종" 하나만 기록하는 구조라 같은 캠페인이 실제로 적용되는 다른 차종이
누락되는 버그가 있었다(예: 24V204000이 IONIQ 6로만 기록돼 IONIQ 5 리콜이 통째로 빠짐).
recalls_hk_by_vehicle.csv(현대·기아 27개 차종 × 캠페인 전체 쌍, 377행)를 정본으로 재적재해
해결 — EV9 24V757000도 이 파일에 이미 있어 별도 하드코딩 불필요해짐.

llm_struct_test_results.jsonl에는 model/year/date가 없어(odino만 있음),
같은 ODINO의 실측 메타데이터(MODELTXT/YEARTXT/LDATE)를 data/processed/hk_electrical_recent_full.csv에서
조회해 조인한다 — 값을 지어내는 것이 아니라 동일 레코드의 이미 검증된 실측 필드를 가져오는 것.

EV6·IONIQ 5 조사 채팅 데모용 추가 불만 레코드는 seed_manual.py로 분리.
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
KR_US_GAP_V2_PATH = REPO_ROOT / "data/processed/kr_us_gap_v2.csv"
RECALLS_HK_PATH = REPO_ROOT / "data/recalls/recalls_hk_by_vehicle.csv"
STRUCT_JSONL_PATH = REPO_ROOT / "data/processed/llm_struct_test_results.jsonl"
COMPLAINT_META_PATH = REPO_ROOT / "data/processed/hk_electrical_recent_full.csv"
PARTS_PATH = REPO_ROOT / "data/processed/rcl573_components_normalized.csv"

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
# recalls: recalls_hk_by_vehicle.csv 전량(정본) — 차종(base_model)×캠페인 쌍마다 한 행.
# kr_us_gap.csv는 한미 시차 분석 전용(별도 테이블)이며 recalls를 채우는 데는 더 이상 쓰지 않는다.
# ---------------------------------------------------------------------------

def load_recalls_hk() -> pd.DataFrame:
    df = pd.read_csv(RECALLS_HK_PATH, dtype=str, encoding="utf-8-sig")
    df["base_model"] = df["Model"].apply(normalize_model)
    return df.drop_duplicates(subset=["base_model", "NHTSACampaignNumber"])


def seed_recalls(conn, recalls_df: pd.DataFrame):
    rows = [
        (r["NHTSACampaignNumber"], "US", r["base_model"], r["report_date_iso"], r["Component"], r["Summary"], None)
        for _, r in recalls_df.iterrows()
    ]
    conn.executemany(
        """INSERT INTO recalls (campaign, country, model, report_date, component, summary, kr_announce_date)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()


def _defect_summary(r: dict) -> str | None:
    """한국_원인 > 한국_증상 > 미국_컴포넌트(영문 원문) 순으로 사용. 없는 값을 지어내지 않는다."""
    for key in ("한국_원인", "한국_증상"):
        v = r.get(key)
        if v and pd.notna(v) and str(v).strip():
            return str(v).strip()
    v = r.get("미국_컴포넌트")
    if v and pd.notna(v) and str(v).strip():
        return str(v).strip()
    return None


# 6.6단계: kr_us_gap.csv에 한국_원인/한국_증상이 없어 _defect_summary()가 미국_컴포넌트(영문
# 원문 그대로)로 폴백하던 대시보드 덤벨차트 대표 8건 중 3건 — "영어 원문 노출 금지" 원칙에 따라
# recalls.summary(이미 DB에 있는 실측 NHTSA 영문 설명)를 한 줄로 번역·요약해 수동 매핑한다.
# 새로운 원인·진단을 지어낸 게 아니라 기존 영문 summary의 번역이다.
DEFECT_SUMMARY_KO_OVERRIDE = {
    "25V291000": "전동 오일펌프 제어기 밀봉 불량으로 인한 화재 위험",  # PALISADE, 실측 summary 번역
    "25V426000": "후방 카메라 회로기판 손상으로 화면 미표시",  # NIRO EV, 실측 summary 번역
    "25V006000": "차체제어모듈(BDC) SW 오류로 전조등·후미등 꺼짐",  # SORENTO, 실측 summary 번역
}


def _gap_row_tuple(r: dict, base_model: str, date_basis: str) -> tuple:
    campaign = r["미국_캠페인번호"] if pd.notna(r.get("미국_캠페인번호")) else r["한국_차종_원문"]
    defect_summary = DEFECT_SUMMARY_KO_OVERRIDE.get(campaign, _defect_summary(r))
    gap_days = None
    if pd.notna(r.get("시차_일")):
        try:
            gap_days = int(float(r["시차_일"]))
        except ValueError:
            gap_days = None
    return (
        campaign,
        base_model,
        defect_summary,
        date_basis,
        r["미국_접수일"] if pd.notna(r.get("미국_접수일")) else None,
        r["한국_발표일"] if pd.notna(r.get("한국_발표일")) else None,
        r["한국_시정시작일"] if pd.notna(r.get("한국_시정시작일")) else None,
        gap_days,
        r["분류"],
    )


def load_gap_v2_extra_rows() -> list[dict]:
    """kr_us_gap_v2.csv(KOTSA 기반)에서 kr_us_gap.csv엔 없는 EV9 24V757000(계기판/IEB 리콜, 대시보드
    덤벨차트 큐레이션 8건 중 하나로 명시 요청됨)만 선별 추가한다. date_basis가 '보도자료'가 아닌
    'KOTSA리콜개시일'임을 별도 표기(CLAUDE.md Task 6 원칙: 두 기준일을 반드시 구분)."""
    df = pd.read_csv(KR_US_GAP_V2_PATH, dtype=str, encoding="utf-8-sig")
    extra = df[(df["미국_캠페인번호"] == "24V757000") & (df["모델_영문"] == "EV9")]
    return extra.to_dict("records")


def seed_kr_us_gap(conn, gap_df: pd.DataFrame, extra_rows: list[dict]):
    rows = [_gap_row_tuple(r, r["base_model"], "보도자료") for _, r in gap_df.iterrows()]
    rows += [_gap_row_tuple(r, normalize_model(r["모델_영문"]), "KOTSA리콜개시일") for r in extra_rows]
    conn.executemany(
        """INSERT INTO kr_us_gap (campaign, model, defect_summary, date_basis, us_date, kr_date, kr_start_date, gap_days, note)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()


# ---------------------------------------------------------------------------
# reports + signal_states (EV9, report_24V757000.md 실측)
# ---------------------------------------------------------------------------

def seed_reports(conn, ev9_signal_id):
    markdown = REPORT_EV9_PATH.read_text(encoding="utf-8")
    # report_24V757000.md 본문에 이미 적힌 실측 수치 그대로(28/29=96.6% 집중도, 10일 선행) —
    # 여기서 새로 계산하거나 지어낸 값이 아니다.
    metrics = json.dumps({"complaint_count": 29, "concentration_pct": 96.6, "lead_days": 10})
    cur = conn.execute(
        """INSERT INTO reports (signal_id, title, markdown, created_at, model, campaign, reference_month, state, metrics)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ev9_signal_id,
            "EV9 계기판 블랙아웃 시그널 리포트 — 24V757000 되감기 사례",
            markdown,
            "2026-07-06",
            "EV9",
            "24V757000",
            "2024-09",
            "recalled",
            metrics,
        ),
    )
    conn.commit()
    report_id = cur.lastrowid
    conn.execute("UPDATE signals SET report_id = ? WHERE id = ?", (report_id, ev9_signal_id))
    conn.commit()
    return report_id, len(markdown)


def seed_chat_reports(conn) -> dict:
    """CHT-03: 조사 채팅 목 시나리오(EV6/IONIQ 5)의 [상세 리포트 보기]가 연결할 리포트를
    미리 생성한다. chat.py의 컨텍스트 빌더 함수(ev6_build_context 등)를 그대로 재사용해
    실제 채팅 응답과 정확히 같은 쿼리·같은 템플릿으로 렌더링하므로, 리포트 내용을 별도로
    새로 작성하지 않아도 답변 markdown과 100% 일치한다.

    6.6단계: 메타(model/campaign/reference_month/state)·metrics도 함께 채운다. state는 지어내지
    않고, 대시보드 카드·시그널 상세와 동일한 에피소드 상태 규칙(engine/episode.py)을 그대로
    재사용해 계산한다 — signals.state(셀 상태)를 직접 쓰면 "지금 리콜 대응 중"이라는 의미가
    아니라 특정 월 한 칸의 관측치만 보여줘 이 리포트의 결론("이미 ICCU 리콜과 연결됨")과
    불일치할 수 있다(예: IONIQ 5의 최신월 셀 상태는 'new'이지만 에피소드 상태는 'recalled')."""
    from engine.episode import aggregate_by_month, derive_episode_state
    from engine.normalize import normalize_model
    from routers.chat import (
        DATA_AS_OF,
        RECENT_CUTOFF,
        EV6_REPORT_TITLE,
        IONIQ5_REPORT_TITLE,
        ev6_build_context,
        ev6_cluster_rows,
        ev6_iccu_campaigns,
        ev6_recent_count,
        ioniq5_build_context,
        ioniq5_iccu_campaigns,
        ioniq5_iccu_hits,
        ioniq5_recent_rows,
    )
    from routers.signals import _recall_dates_by_model
    from llm.adapter import LLM

    llm = LLM()
    reference_month = f"{RECENT_CUTOFF[:7]}~{DATA_AS_OF[:7]}"
    latest_month = conn.execute("SELECT MAX(month) FROM signals").fetchone()[0]
    recall_dates_by_model = _recall_dates_by_model(conn)

    all_signal_rows = conn.execute("SELECT model, month, count, baseline FROM signals").fetchall()

    def current_state(model: str) -> str:
        base_model = normalize_model(model)
        rows = [dict(r) for r in all_signal_rows if normalize_model(r["model"]) == base_model]
        by_month = aggregate_by_month(rows)
        return derive_episode_state(by_month, latest_month, recall_dates_by_model.get(base_model, []))

    ev6_context, _ = ev6_build_context(ev6_recent_count(conn), ev6_iccu_campaigns(conn), ev6_cluster_rows(conn))
    ev6_markdown = llm.call("answer", "ev6_cluster", ev6_context)["markdown"]
    ev6_metrics = json.dumps(
        {"complaint_count": ev6_context["recent_count"], "concentration_pct": None, "lead_days": None}
    )

    i5_recent = ioniq5_recent_rows(conn)
    i5_campaigns = ioniq5_iccu_campaigns(conn)
    ioniq5_context, _ = ioniq5_build_context(i5_recent, i5_campaigns, ioniq5_iccu_hits(i5_recent))
    ioniq5_markdown = llm.call("answer", "ioniq5_charging", ioniq5_context)["markdown"]
    ioniq5_metrics = json.dumps(
        {"complaint_count": ioniq5_context["recent_count"], "concentration_pct": ioniq5_context["iccu_ratio"], "lead_days": None}
    )

    rows = [
        (None, EV6_REPORT_TITLE, ev6_markdown, "2026-07-08", "EV6", ev6_context["iccu_campaigns"], reference_month,
         current_state("EV6"), ev6_metrics),
        (None, IONIQ5_REPORT_TITLE, ioniq5_markdown, "2026-07-08", "IONIQ 5", ioniq5_context["iccu_campaigns"],
         reference_month, current_state("IONIQ 5"), ioniq5_metrics),
    ]
    conn.executemany(
        """INSERT INTO reports (signal_id, title, markdown, created_at, model, campaign, reference_month, state, metrics)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    return {"ev6_len": len(ev6_markdown), "ioniq5_len": len(ioniq5_markdown)}


# ---------------------------------------------------------------------------
# parts (rcl573_components_normalized.csv 실측 — Part 573 원문 + 공급사 정규화)
# ---------------------------------------------------------------------------

def load_parts_df() -> pd.DataFrame:
    return pd.read_csv(PARTS_PATH, dtype=str, encoding="utf-8-sig").fillna("")


def seed_parts(conn, parts_df: pd.DataFrame):
    rows = [
        (
            r["campaign"], r["component_name"] or None, r["part_number"] or None,
            r["supplier_canonical"] or None, r["supplier_group"] or None,
            r["supplier_country"] or None, r["defect_cause"] or None,
            r["fmvss"] or None, r["remedy_type"] or None, r["pdf_url"] or None,
        )
        for _, r in parts_df.iterrows()
    ]
    conn.executemany(
        """INSERT INTO parts (campaign, component_name, part_number, supplier_canonical,
                               supplier_group, supplier_country, defect_cause, fmvss, remedy_type, pdf_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()


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
    for table in ["signal_states", "reports", "signals", "recalls", "kr_us_gap", "complaints", "parts"]:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()

    gap_df = load_gap_df()
    recall_lookup = build_recall_lookup(gap_df)  # signals 셀 상태 전용 (kr_us_gap.csv 기반, recalls 테이블과 무관)

    struct_complaints = load_struct_complaints()
    seed_complaints(conn, struct_complaints)
    seed_manual.seed(conn)

    symptom_lookup = build_top_symptom_lookup(struct_complaints)
    b1_df = load_b1_signals()
    id_map = seed_signals(conn, b1_df, recall_lookup, symptom_lookup)

    recalls_df = load_recalls_hk()
    seed_recalls(conn, recalls_df)
    gap_v2_extra = load_gap_v2_extra_rows()
    seed_kr_us_gap(conn, gap_df, gap_v2_extra)

    parts_df = load_parts_df()
    seed_parts(conn, parts_df)

    ev9_signal_id = id_map[("EV9", "2024-09")]
    report_id, report_len = seed_reports(conn, ev9_signal_id)
    seed_signal_states(conn, ev9_signal_id)
    chat_report_lens = seed_chat_reports(conn)

    print_integrity_report(conn, report_len, chat_report_lens)
    conn.close()


def print_integrity_report(conn, ev9_report_len: int, chat_report_lens: dict):
    print("=== seed 정합성 리포트 ===")
    for table in ["complaints", "recalls", "signals", "signal_states", "reports", "kr_us_gap", "parts"]:
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {n}행")

    n_parts_campaigns = conn.execute("SELECT COUNT(DISTINCT campaign) FROM parts").fetchone()[0]
    n_recalls_campaigns = conn.execute("SELECT COUNT(DISTINCT campaign) FROM recalls").fetchone()[0]
    n_joined = conn.execute(
        "SELECT COUNT(DISTINCT p.campaign) FROM parts p JOIN recalls r ON p.campaign = r.campaign"
    ).fetchone()[0]
    print(f"\n  parts campaign 커버리지: recalls 테이블의 {n_recalls_campaigns}개 캠페인 중 {n_joined}개가 parts에도 존재 (parts 자체 캠페인 수 {n_parts_campaigns})")

    print("\n  parts supplier_group 상위 5:")
    for group, n in conn.execute(
        "SELECT supplier_group, COUNT(*) as n FROM parts WHERE supplier_group != '' AND supplier_group IS NOT NULL GROUP BY supplier_group ORDER BY n DESC LIMIT 5"
    ):
        print(f"    {group}: {n}건")

    print("\n  signals 상태별 분포:")
    for state, n in conn.execute("SELECT state, COUNT(*) as n FROM signals GROUP BY state ORDER BY n DESC"):
        print(f"    {state}: {n}건")

    n_gap = conn.execute("SELECT COUNT(*) FROM kr_us_gap").fetchone()[0]
    santafe = conn.execute("SELECT * FROM kr_us_gap WHERE gap_days = 152").fetchall()
    tucson = conn.execute("SELECT * FROM kr_us_gap WHERE gap_days = 8").fetchall()
    print(f"\n  kr_us_gap: {n_gap}행 (원본 kr_us_gap.csv 27행 + kr_us_gap_v2.csv 큐레이션 EV9 1행 기대)")
    print(f"    싼타페 +152일 포함: {'O' if santafe else 'X'}")
    print(f"    투싼 +8일 포함: {'O' if tucson else 'X'}")

    print(f"\n  EV9 리포트 마크다운 글자 수: {ev9_report_len}자")
    print(f"  CHT-03 사전 리포트 (EV6/IONIQ5) 마크다운 글자 수: {chat_report_lens['ev6_len']}자 / {chat_report_lens['ioniq5_len']}자")

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
