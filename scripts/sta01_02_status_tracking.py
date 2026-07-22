"""
MOBISCOPE STA-01 / STA-02 — 결함 상태 추적 SQLite DB
============================================================
목적
- LLM 구조화 결과와 원본 불만 CSV를 SQLite에 적재한다.
- 특정 ODINO/차종/부품 시그널이 신규(STA-01)인지,
  기존 리콜 후 재발(STA-02)인지 추적한다.
- 대시보드가 조회하기 쉬운 view CSV도 내보낸다.

담당 기능
- STA-01: 리콜 이력이 없는 신규 결함 후보 기록
- STA-02: 기존 리콜과 동일/유사 부품에서 리콜일 이후 재발 신고 기록

주의
- 이 모듈은 SQLite 수준의 상태 DB 뼈대다. 외부 API 호출은 기본 동작에 넣지 않았다.
- NHTSA/국내 리콜 데이터는 register_recall() 또는 import_recall_records()로 넣는다.
- VIN은 저장하지 않는다.
- 저장되는 내용은 미검증 소비자 신고와 분석 결과이며 결함 확정이 아니다.

2026-07-20 — STR v4(상진) 대응 전면 개정
================================================================
STR이 처리 단위를 ODINO→CMPLID로 바꾸고 part_category(LLM 판단 8종 enum)를
없앤 뒤 원본 COMPDESC를 코드가 그대로 잘라 채우는 compdesc1(대분류)/compdesc2
(중분류)로 교체했다(상진님 STR_트랙_정리 v4 절, str01_sample100_v4_results.jsonl
실물로 최종 확인: 실제 키 = cmplid/odino/compdesc1/compdesc2/symptoms/severity/
driving_context/evidence_quote/insufficient_info, part_category 없음).

이 파일은 이전 버전(v2/v3 시절, part_category+odino 단위)에서 그대로 남아있던
게 뒤늦게 발견됐다 — 이번에 구조를 다시 짰다. 바뀐 것:

1. `structured_results`의 PK를 odino→cmplid로 바꿨다. odino PK를 유지한 채
   v4 jsonl(한 odino가 여러 cmplid로 쪼개짐)을 적재하면 ON CONFLICT(odino)
   UPDATE가 같은 odino의 이전 cmplid 행을 계속 덮어써서 **한 odino당 딱 1개
   행만 살아남는** 심각한 데이터 유실이 있었다(발견 당시 실측 확인).
2. `part_category` 컬럼(structured_results/defect_status_tracking/
   defect_signals)을 전부 `compdesc1`로 바꿨다(structured_results에는
   `compdesc2`도 추가). PART_RECALL_KEYWORDS도 v4 실제 7종 값 기준으로
   다시 만들었다 — 안 바꾸면 _component_matches()가 항상 part_category=None을
   보고 즉시 False를 반환해 **리콜 매칭이 전부 무력화**(STA-02가 영원히 0건,
   defect_signals가 RECALLED/DORMANT/RECURRING을 절대 못 냄)되는 문제가 있었다.
3. `complaint_reports`는 odino PK를 그대로 유지했다 — 이건 원본 CSV에서
   같은 odino의 여러 cmplid 행이 CDESCR(신고 원문)은 동일하고 COMPDESC만
   다른 구조라서(상진님 STR-01 v4 "샘플링 오해" 절 참고), 신고 원문·메타데이터는
   여전히 odino 단위로 1개만 있으면 충분하다. cmplid별로 달라지는 건
   "이 신고를 어느 관점(compdesc)으로 봤을 때 어떤 판단이 나왔는가"인
   structured_results 쪽뿐이다.
4. `classify_and_track()`(STA-01/02, 신고=odino 단위 이진 판정)을 한
   odino에 딸린 여러 structured_results(cmplid) 행 전부를 보도록 다시 짰다 —
   그중 하나라도 리콜에 매칭되면 그 신고 전체를 STA-02로 본다. 대표
   compdesc1/severity는 매칭된 행(있으면) 또는 심각도가 가장 높은 행(없으면,
   SEVERITY_RANK 기준)을 쓴다.
5. DB 마이그레이션: 기존에 이미 v2/v3로 채워진 .db 파일이 있다면 이 스키마와
   안 맞다(구 컬럼명·PK). 새 스키마로 다시 만들려면 기존 .db 파일을 지우고
   init_db()부터 재실행해야 한다 — ALTER TABLE로는 PRIMARY KEY를 못 바꾸므로
   이 파일의 _ensure_column()류 무중단 마이그레이션 대상이 아니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import datetime
import json
import re
import sqlite3

import pandas as pd

DEFAULT_CSV_PATH = Path("data/processed/hk_electrical_recent_full.csv")
# 2026-07-20: 예전 기본값(llm_struct_test_results.jsonl)은 효선님이 STA/INV
# 파이프라인 테스트용으로 쓴 별개 파일(49건, 7필드 구버전 스키마)이라 지웠다 —
# STR-01 v4 100건 검증 최종본(str01_sample100_v4_results.jsonl, 9필드)으로
# 교체. 전체 16,964건 v4 결과가 나오면 그 경로로 다시 바꿔야 한다.
DEFAULT_JSONL_PATH = Path("data/processed/str01_sample100_v4_results.jsonl")
DEFAULT_DB_PATH = Path("data/processed/defect_status_tracking.db")
DEFAULT_VIEW_CSV = Path("data/processed/defect_status_view.csv")
FALLBACKS = {
    "csv": [Path("/mnt/data/hk_electrical_recent_full.csv"), Path("hk_electrical_recent_full.csv")],
    "jsonl": [
        Path("data/processed/llm_struct_test_results.jsonl"),
        Path("/mnt/data/llm_struct_test_results.jsonl"),
        Path("/mnt/data/str01_sample100_v4_results.jsonl"),
        Path("llm_struct_test_results.jsonl"),
        Path("str01_sample100_v4_results.jsonl"),
    ],
    "db": [Path("/mnt/data/defect_status_tracking_generated.db")],
    "view": [Path("/mnt/data/defect_status_view_generated.csv")],
}

STA_NEW = "STA-01"
STA_RECUR = "STA-02"
STA_LABEL = {
    STA_NEW: "신규 결함 후보",
    STA_RECUR: "기존 리콜 후 재발 후보",
}
VALID_RESOLUTION = {"OPEN", "IN_PROGRESS", "MONITORING", "RESOLVED", "DISMISSED"}
SEVERITY_RANK = {"CRITICAL": 4, "SERIOUS": 3, "MODERATE": 2, "MINOR": 1, "UNKNOWN": 0, None: 0}

# --- 차종×부품카테고리 단위 5단계 시그널 상태 -------------------------------
# defect_status_tracking(위 STA-01/02)은 "신고 1건"이 단위인 이진 판정이고,
# 그 의미는 바뀌지 않는다. 아래 SIGNAL_*은 그 위에 얹는 별도 집계 레이어
# (defect_signals 테이블)로, "이 차종 × 이 compdesc1(대분류)" 그룹 전체의
# 생애주기를 5단계로 추적한다. 실제 판정 로직은 sta_signal_state.py.
SIGNAL_NEW = "NEW"
SIGNAL_RISING = "RISING"
SIGNAL_RECALLED = "RECALLED"
SIGNAL_DORMANT = "DORMANT"
SIGNAL_RECURRING = "RECURRING"
SIGNAL_STATES = (SIGNAL_NEW, SIGNAL_RISING, SIGNAL_RECALLED, SIGNAL_DORMANT, SIGNAL_RECURRING)
SIGNAL_LABEL_KO = {
    SIGNAL_NEW: "신규",
    SIGNAL_RISING: "증가",
    SIGNAL_RECALLED: "리콜",
    SIGNAL_DORMANT: "잠잠",
    SIGNAL_RECURRING: "재발",
}
# 대시보드/채팅 답변에서 우선 검토해야 할 순서(위험도 아님, 관심순).
SIGNAL_PRIORITY_ORDER = {
    SIGNAL_RECURRING: 1, SIGNAL_RISING: 2, SIGNAL_RECALLED: 3, SIGNAL_NEW: 4, SIGNAL_DORMANT: 5,
}

# 2026-07-20: 구 PART_RECALL_KEYWORDS(ELECTRICAL_SYSTEM/ADAS/POWERTRAIN_SW 등
# 8종 enum 기준)를 STR v4의 실제 compdesc1 7종 기준으로 다시 만들었다. 각
# 키워드는 상진님 STR-01 v4 문서의 compdesc2(중분류) 실측 breakdown표에 나온
# 값들을 그대로 가져왔다 — 임의 추측이 아니라 실제 데이터에 존재하는 하위
# 분류명 기준. 그래도 이건 "리콜 CSV의 component 텍스트와 문자열이 겹치는가"만
# 보는 휴리스틱이라 팀 검수를 권장한다(특히 ELECTRICAL SYSTEM처럼 하위 분류가
# 많은 카테고리는 오탐 가능성이 상대적으로 높음).
COMPDESC1_RECALL_KEYWORDS = {
    "ELECTRICAL SYSTEM": [
        "ELECTRICAL", "IGNITION", "HORN", "INSTRUMENT", "CLUSTER", "PANEL",
        "BATTERY", "PROPULSION", "ALTERNATOR", "GENERATOR", "REGULATOR",
        "ADAS", "WIRING", "STARTER", "BODY CONTROL MODULE", "BCM",
        "SEAT HEATER", "SOFTWARE", "HAND HEATER", "CYBERSECURITY",
        "TRAILER BRAKE CONTROL", "DISPLAY",
    ],
    "FORWARD COLLISION AVOIDANCE": [
        "FORWARD COLLISION", "AUTOMATIC EMERGENCY BRAKING", "AEB", "WARNING",
        "ADAPTIVE CRUISE CONTROL", "SENSING SYSTEM", "DYNAMIC BRAKE SUPPORT",
        "BRAKE ASSIST", "COLLISION",
    ],
    "VEHICLE SPEED CONTROL": [
        "ACCELERATOR PEDAL", "CRUISE CONTROL", "THROTTLE", "CABLE", "SPRING",
        "SPEED CONTROL",
    ],
    "LANE DEPARTURE": [
        "BLIND SPOT DETECTION", "LANE DEPARTURE", "LANE KEEP", "LANE",
        "ASSIST", "WARNING", "SENSING SYSTEM",
    ],
    "BACK OVER PREVENTION": [
        "REARVIEW", "REAR VIEW", "BACK OVER", "BACKUP", "REAR CAMERA",
        "SENSING SYSTEM", "AUTOMATIC SYSTEM BRAKING", "DISPLAY FUNCTION",
        "WARNING",
    ],
    "ELECTRONIC STABILITY CONTROL (ESC)": [
        "ELECTRONIC STABILITY", "STABILITY CONTROL", "ESC", "CONTROL MODULE",
    ],
    # UNKNOWN OR OTHER는 STR 자체가 "부위를 특정 못 함"이라고 인정한 라벨이라,
    # 여기서 또 키워드로 추측 매칭을 시도하면 오탐 위험이 더 크다고 판단해
    # 의도적으로 빈 리스트(항상 매칭 안 됨)로 둔다 — 구 NON_ELECTRICAL/
    # INSUFFICIENT_INFO와 동일한 설계 원칙.
    "UNKNOWN OR OTHER": [],
}

# 기존 STR(v2/v3) 라벨을 가능한 경우 v4 대분류로 정규화한다. ADAS는 v4의
# 여러 대분류에 걸치므로 억지로 하나로 좁히지 않고 그대로 보존한다.
LEGACY_PART_CATEGORY_MAP = {
    "ELECTRICAL_SYSTEM": "ELECTRICAL SYSTEM",
    "INSTRUMENT_CLUSTER": "ELECTRICAL SYSTEM",
    "PROPULSION_BATTERY": "ELECTRICAL SYSTEM",
    "POWERTRAIN_SW": "ELECTRICAL SYSTEM",
    "NON_ELECTRICAL": "UNKNOWN OR OTHER",
    "INSUFFICIENT_INFO": "UNKNOWN OR OTHER",
}

LEGACY_RECALL_GROUPS = {
    "ADAS": {
        "FORWARD COLLISION AVOIDANCE",
        "VEHICLE SPEED CONTROL",
        "LANE DEPARTURE",
        "BACK OVER PREVENTION",
        "ELECTRONIC STABILITY CONTROL (ESC)",
    },
    "BRAKES_ELECTRONIC": {
        "FORWARD COLLISION AVOIDANCE",
        "ELECTRONIC STABILITY CONTROL (ESC)",
    },
}


def _clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_compdesc1(value: Any) -> str | None:
    text = _clean_text(value).upper()
    if not text:
        return None
    return LEGACY_PART_CATEGORY_MAP.get(text, text)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _capture_legacy_schema(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]] | None:
    """구형 part_category 스키마를 발견하면 관련 파생 테이블을 메모리에 보관한다."""
    legacy = False
    for table in ("structured_results", "defect_status_tracking", "defect_signals"):
        cols = _table_columns(conn, table)
        if cols and ("part_category" in cols or "compdesc1" not in cols):
            legacy = True
            break
    if not legacy:
        return None

    tables = (
        "structured_results",
        "defect_status_tracking",
        "status_change_log",
        "defect_signals",
        "signal_state_log",
    )
    snapshot: dict[str, list[dict[str, Any]]] = {}
    for table in tables:
        if _table_columns(conn, table):
            snapshot[table] = [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]

    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        for table in ("signal_state_log", "defect_signals", "status_change_log", "defect_status_tracking", "structured_results"):
            if _table_columns(conn, table):
                conn.execute(f"DROP TABLE {table}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    return snapshot


def _restore_legacy_schema(
    conn: sqlite3.Connection, snapshot: dict[str, list[dict[str, Any]]] | None
) -> None:
    if not snapshot:
        return

    for row in snapshot.get("structured_results", []):
        odino = _clean_text(row.get("odino"))
        if not odino:
            continue
        cmplid = _clean_text(row.get("cmplid")) or odino
        conn.execute(
            """
            INSERT OR REPLACE INTO structured_results
            (cmplid, odino, compdesc1, compdesc2, symptoms_json, severity,
             driving_context, evidence_quote, insufficient_info, rule_notes, created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                cmplid,
                odino,
                _normalize_compdesc1(row.get("compdesc1") or row.get("part_category")),
                row.get("compdesc2"),
                row.get("symptoms_json"),
                row.get("severity"),
                row.get("driving_context"),
                row.get("evidence_quote"),
                row.get("insufficient_info", 0),
                row.get("rule_notes"),
                row.get("created_at"),
            ),
        )

    for row in snapshot.get("defect_status_tracking", []):
        conn.execute(
            """
            INSERT OR REPLACE INTO defect_status_tracking
            (tracking_id, odino, vehicle_id, recall_id, status_code, status_label,
             compdesc1, severity, detection_date, recurrence_basis, resolution_status,
             resolution_date, notes, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row.get("tracking_id"), row.get("odino"), row.get("vehicle_id"),
                row.get("recall_id"), row.get("status_code"), row.get("status_label"),
                _normalize_compdesc1(row.get("compdesc1") or row.get("part_category")),
                row.get("severity"), row.get("detection_date"), row.get("recurrence_basis"),
                row.get("resolution_status"), row.get("resolution_date"), row.get("notes"),
                row.get("created_at"), row.get("updated_at"),
            ),
        )

    for row in snapshot.get("status_change_log", []):
        conn.execute(
            """
            INSERT OR REPLACE INTO status_change_log
            (log_id, tracking_id, field_name, old_value, new_value, changed_by, changed_at)
            VALUES(?,?,?,?,?,?,?)
            """,
            tuple(row.get(k) for k in (
                "log_id", "tracking_id", "field_name", "old_value", "new_value", "changed_by", "changed_at"
            )),
        )

    for row in snapshot.get("defect_signals", []):
        conn.execute(
            """
            INSERT OR REPLACE INTO defect_signals
            (signal_id, vehicle_id, compdesc1, signal_state, recall_id, complaint_count,
             first_complaint_date, last_complaint_date, recent_count, baseline_count,
             surge_ratio, surge_level, quiet_months, state_reason, computed_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row.get("signal_id"), row.get("vehicle_id"),
                _clean_text(row.get("compdesc1") or row.get("part_category")) or "UNKNOWN OR OTHER",
                row.get("signal_state"), row.get("recall_id"), row.get("complaint_count", 0),
                row.get("first_complaint_date"), row.get("last_complaint_date"),
                row.get("recent_count"), row.get("baseline_count"), row.get("surge_ratio"),
                row.get("surge_level"), row.get("quiet_months"), row.get("state_reason"),
                row.get("computed_at"),
            ),
        )

    for row in snapshot.get("signal_state_log", []):
        conn.execute(
            """
            INSERT OR REPLACE INTO signal_state_log
            (log_id, signal_id, old_state, new_state, reason, changed_at)
            VALUES(?,?,?,?,?,?)
            """,
            tuple(row.get(k) for k in (
                "log_id", "signal_id", "old_state", "new_state", "reason", "changed_at"
            )),
        )
    conn.commit()
    print("[STA MIGRATE] 구형 part_category DB를 compdesc1 스키마로 변환했습니다.")


def _resolve(path: str | Path | None, default: Path, fallbacks: list[Path], *, create_parent: bool = False) -> Path:
    if path is not None:
        p = Path(path)
        if p.exists() or create_parent:
            if create_parent:
                p.parent.mkdir(parents=True, exist_ok=True)
            return p
        if str(p) != str(default):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {p}")
    if default.exists() or create_parent:
        if create_parent:
            default.parent.mkdir(parents=True, exist_ok=True)
        return default
    for fb in fallbacks:
        if fb.exists() or create_parent:
            if create_parent:
                fb.parent.mkdir(parents=True, exist_ok=True)
            return fb
    raise FileNotFoundError(f"파일을 찾을 수 없습니다: {default}")


def get_conn(db_path: str | Path | None = None) -> sqlite3.Connection:
    db = _resolve(db_path, DEFAULT_DB_PATH, FALLBACKS["db"], create_parent=True)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path | None = None) -> sqlite3.Connection:
    conn = get_conn(db_path)
    legacy_snapshot = _capture_legacy_schema(conn)
    # 구형 recall_records에는 아래 인덱스가 참조하는 컬럼이 없으므로
    # CREATE INDEX보다 먼저 추가해야 한다.
    if _table_columns(conn, "recall_records"):
        _ensure_column(conn, "recall_records", "part_number", "TEXT")
        _ensure_column(conn, "recall_records", "part_family", "TEXT")
        _ensure_column(conn, "recall_records", "compdesc1", "TEXT")
        conn.commit()
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS vehicles (
            vehicle_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            make         TEXT NOT NULL,
            model        TEXT NOT NULL,
            year         INTEGER,
            created_at   TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(make, model, year)
        );
        CREATE INDEX IF NOT EXISTS idx_vehicles_make_model_year ON vehicles(make, model, year);

        -- odino 단위 유지: 원본 CSV에서 같은 odino의 여러 cmplid 행은 CDESCR
        -- (신고 원문)이 동일하고 COMPDESC만 다르다 — 신고 메타데이터 자체는
        -- odino당 1행이면 충분하다(자세한 이유는 파일 상단 "2026-07-20" 절 참고).
        CREATE TABLE IF NOT EXISTS complaint_reports (
            odino          TEXT PRIMARY KEY,
            cmplid         TEXT,
            vehicle_id     INTEGER REFERENCES vehicles(vehicle_id),
            fail_date      TEXT,
            ldate          TEXT,
            component_desc TEXT,
            complaint_text TEXT,
            crash          INTEGER DEFAULT 0,
            fire           INTEGER DEFAULT 0,
            injured        INTEGER DEFAULT 0,
            deaths         INTEGER DEFAULT 0,
            miles          REAL,
            state          TEXT,
            city           TEXT,
            created_at     TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_reports_vehicle ON complaint_reports(vehicle_id);
        CREATE INDEX IF NOT EXISTS idx_reports_fail_date ON complaint_reports(fail_date);
        CREATE INDEX IF NOT EXISTS idx_reports_component ON complaint_reports(component_desc);

        -- 2026-07-20: PK를 odino→cmplid로 변경(STR v4, 한 odino가 여러 cmplid로
        -- 쪼개질 수 있음). part_category 컬럼을 compdesc1/compdesc2로 교체.
        CREATE TABLE IF NOT EXISTS structured_results (
            cmplid             TEXT PRIMARY KEY,
            odino              TEXT NOT NULL REFERENCES complaint_reports(odino),
            compdesc1          TEXT,
            compdesc2          TEXT,
            symptoms_json      TEXT,
            severity           TEXT,
            driving_context    TEXT,
            evidence_quote     TEXT,
            insufficient_info  INTEGER DEFAULT 0,
            rule_notes         TEXT,
            created_at         TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_struct_odino ON structured_results(odino);
        CREATE INDEX IF NOT EXISTS idx_struct_compdesc1 ON structured_results(compdesc1);
        CREATE INDEX IF NOT EXISTS idx_struct_severity ON structured_results(severity);

        CREATE TABLE IF NOT EXISTS recall_records (
            recall_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id      INTEGER NOT NULL REFERENCES vehicles(vehicle_id),
            campaign_no     TEXT,
            recall_date     TEXT,
            component       TEXT,
            compdesc1       TEXT,
            summary         TEXT,
            source          TEXT DEFAULT 'MANUAL',
            status          TEXT DEFAULT 'OPEN' CHECK(status IN ('OPEN','CLOSED','PARTIAL','UNKNOWN')),
            created_at      TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(vehicle_id, campaign_no)
        );
        CREATE INDEX IF NOT EXISTS idx_recall_vehicle ON recall_records(vehicle_id);
        CREATE INDEX IF NOT EXISTS idx_recall_component ON recall_records(component);
        CREATE INDEX IF NOT EXISTS idx_recall_date ON recall_records(recall_date);
        CREATE INDEX IF NOT EXISTS idx_recall_compdesc1 ON recall_records(compdesc1);

        -- odino(신고) 단위 이진 판정. 한 odino에 딸린 여러 cmplid 중 하나라도
        -- 리콜에 매칭되면 이 신고 전체를 STA-02로 본다(classify_and_track 참고).
        CREATE TABLE IF NOT EXISTS defect_status_tracking (
            tracking_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            odino             TEXT NOT NULL UNIQUE REFERENCES complaint_reports(odino),
            vehicle_id        INTEGER REFERENCES vehicles(vehicle_id),
            recall_id         INTEGER REFERENCES recall_records(recall_id),
            status_code       TEXT NOT NULL CHECK(status_code IN ('STA-01','STA-02')),
            status_label      TEXT NOT NULL,
            compdesc1         TEXT,
            severity          TEXT,
            detection_date    TEXT,
            recurrence_basis  TEXT,
            resolution_status TEXT DEFAULT 'OPEN'
                              CHECK(resolution_status IN ('OPEN','IN_PROGRESS','MONITORING','RESOLVED','DISMISSED')),
            resolution_date   TEXT,
            notes             TEXT,
            created_at        TEXT DEFAULT (datetime('now','localtime')),
            updated_at        TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_tracking_status ON defect_status_tracking(status_code);
        CREATE INDEX IF NOT EXISTS idx_tracking_resolution ON defect_status_tracking(resolution_status);
        CREATE INDEX IF NOT EXISTS idx_tracking_severity ON defect_status_tracking(severity);

        CREATE TABLE IF NOT EXISTS status_change_log (
            log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_id  INTEGER NOT NULL REFERENCES defect_status_tracking(tracking_id),
            field_name   TEXT NOT NULL,
            old_value    TEXT,
            new_value    TEXT,
            changed_by   TEXT DEFAULT 'SYSTEM',
            changed_at   TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_log_tracking ON status_change_log(tracking_id);

        -- 차종×compdesc1(대분류) 단위 5단계 시그널(신규/증가/리콜/잠잠/재발).
        -- defect_status_tracking(신고 단위)과 별개 테이블 — 기존 의미를 안 건드리고
        -- 그 위에 얹는 집계 레이어. 계산 로직은 sta_signal_state.py.
        CREATE TABLE IF NOT EXISTS defect_signals (
            signal_id            INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id           INTEGER NOT NULL REFERENCES vehicles(vehicle_id),
            compdesc1             TEXT NOT NULL,
            signal_state         TEXT NOT NULL CHECK(signal_state IN
                                  ('NEW','RISING','RECALLED','DORMANT','RECURRING')),
            recall_id            INTEGER REFERENCES recall_records(recall_id),
            complaint_count      INTEGER NOT NULL DEFAULT 0,
            first_complaint_date TEXT,
            last_complaint_date  TEXT,
            recent_count         INTEGER,
            baseline_count       INTEGER,
            surge_ratio          REAL,
            surge_level          TEXT,
            quiet_months         REAL,
            state_reason         TEXT,
            computed_at          TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(vehicle_id, compdesc1)
        );
        CREATE INDEX IF NOT EXISTS idx_signals_state ON defect_signals(signal_state);
        CREATE INDEX IF NOT EXISTS idx_signals_vehicle ON defect_signals(vehicle_id);

        CREATE TABLE IF NOT EXISTS signal_state_log (
            log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id    INTEGER NOT NULL REFERENCES defect_signals(signal_id),
            old_state    TEXT,
            new_state    TEXT NOT NULL,
            reason       TEXT,
            changed_at   TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_signal_log_signal ON signal_state_log(signal_id);
        """
    )
    conn.commit()
    _ensure_column(conn, "recall_records", "part_number", "TEXT")
    _ensure_column(conn, "recall_records", "part_family", "TEXT")
    # 2026-07-21 신규(설계 한계 C 돌파): rcl573_classify_compdesc.py가 Gemini로
    # 분류한 정확한 compdesc1을 저장할 컬럼. 이미 만들어진 .db 파일에도
    # 안전하게 추가된다(비파괴적 ALTER TABLE ADD COLUMN).
    _ensure_column(conn, "recall_records", "compdesc1", "TEXT")
    _restore_legacy_schema(conn, legacy_snapshot)
    conn.commit()
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, coltype: str) -> None:
    """이미 만들어져 있던 DB 파일에도 안전하게 컬럼을 추가한다(재실행해도 에러 없음).
    ALTER TABLE ADD COLUMN은 SQLite에서 기존 행을 안 건드리고 NULL로 채우는
    비파괴적 작업이라, 운영 중인 DB에 실행해도 안전하다.

    주의: 이건 "컬럼 추가"만 가능하고 PRIMARY KEY 변경 같은 구조 변경은 못 한다.
    이번에 structured_results의 PK를 odino→cmplid로 바꿨는데, 예전 스키마로 이미
    만들어진 .db 파일이 있다면 이 함수로는 마이그레이션이 안 되니 그 DB 파일을
    지우고 init_db()를 다시 실행해야 한다(파일 상단 개정 이력 5번 참고).
    """
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _date_to_iso(value: Any, *, dayfirst: bool = False) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        dt = pd.to_datetime(text, format="%Y%m%d", errors="coerce")
    elif ISO_DATE_RE.match(text):
        # 2026-07-21 신규 발견·수정: 이미 "YYYY-MM-DD"(ISO) 형식인 문자열을
        # dayfirst=True로 파싱하면 pandas가 "YYYY-DD-MM"으로 잘못 해석해서
        # 일/월이 뒤바뀌는 버그를 발견했다(예: register_recall()이 RCL573
        # recall_date에 항상 dayfirst=True를 넘기는데, rcl573_classify_
        # compdesc.py/rcl573_fill_recall_dates.py가 만드는 recall_date는 이미
        # ISO 형식이라 이 경로를 타고 있었음 — 실측: "2024-10-09"가
        # "2024-09-10"으로 둔갑하는 것을 직접 재현 확인함, 이번 실제 데이터는
        # 일=월(10월10일)이라 우연히 안 드러났을 뿐 구조적 버그였음). ISO
        # 형식은 연도가 항상 맨 앞 4자리라 애초에 dayfirst 애매성이 없으므로,
        # dayfirst 값과 무관하게 형식을 그대로 신뢰해서 파싱한다.
        dt = pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")
    else:
        dt = pd.to_datetime(text, dayfirst=dayfirst, errors="coerce")
    if pd.isna(dt):
        return None
    return dt.strftime("%Y-%m-%d")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or pd.isna(value):
            return default
        return int(float(value))
    except Exception:
        return default


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def upsert_vehicle(conn: sqlite3.Connection, make: str, model: str, year: int | str | None) -> int:
    make = (_clean_text(make) or "UNKNOWN").upper()
    model = (_clean_text(model) or "UNKNOWN").upper()
    year_int = _safe_int(year, default=None) if year not in (None, "") else None
    row = conn.execute(
        "SELECT vehicle_id FROM vehicles WHERE make=? AND model=? AND year IS ?",
        (make, model, year_int),
    ).fetchone()
    # SQLite의 IS ?가 환경에 따라 어색할 수 있어 보조 조회.
    if not row:
        row = conn.execute(
            "SELECT vehicle_id FROM vehicles WHERE make=? AND model=? AND COALESCE(year,-1)=COALESCE(?,-1)",
            (make, model, year_int),
        ).fetchone()
    if row:
        return int(row["vehicle_id"])
    cur = conn.execute("INSERT INTO vehicles(make, model, year) VALUES(?,?,?)", (make, model, year_int))
    conn.commit()
    return int(cur.lastrowid)


def load_complaints_csv(conn: sqlite3.Connection, csv_path: str | Path | None = None) -> int:
    csv = _resolve(csv_path, DEFAULT_CSV_PATH, FALLBACKS["csv"])
    df = pd.read_csv(csv, dtype=str, low_memory=False, encoding="utf-8-sig")
    df.columns = [str(c).strip().upper() for c in df.columns]
    if "VIN" in df.columns:
        df = df.drop(columns=["VIN"])
    before = len(df)
    if "ODINO" in df.columns:
        df["ODINO"] = df["ODINO"].map(_clean_text)
        missing_odino = int(df["ODINO"].eq("").sum())
        df = df[df["ODINO"].ne("")]
        df = df.drop_duplicates(subset="ODINO", keep="first")
    else:
        raise ValueError("원본 신고 CSV에 ODINO 컬럼이 없습니다.")

    inserted = updated = 0
    for _, row in df.iterrows():
        odino = _clean_text(row.get("ODINO"))
        if not odino:
            continue
        vid = upsert_vehicle(conn, row.get("MAKETXT"), row.get("MODELTXT"), row.get("YEARTXT"))
        payload = (
            odino,
            _clean_text(row.get("CMPLID")) or None,
            vid,
            _date_to_iso(row.get("FAILDATE")),
            _date_to_iso(row.get("LDATE")),
            _clean_text(row.get("COMPDESC")) or None,
            _clean_text(row.get("CDESCR")) or None,
            1 if _clean_text(row.get("CRASH")).upper() == "Y" else 0,
            1 if _clean_text(row.get("FIRE")).upper() == "Y" else 0,
            _safe_int(row.get("INJURED")),
            _safe_int(row.get("DEATHS")),
            _safe_float(row.get("MILES")),
            _clean_text(row.get("STATE")) or None,
            _clean_text(row.get("CITY")) or None,
        )
        exists = conn.execute("SELECT 1 FROM complaint_reports WHERE odino=?", (odino,)).fetchone()
        conn.execute(
            """
            INSERT INTO complaint_reports
            (odino, cmplid, vehicle_id, fail_date, ldate, component_desc, complaint_text,
             crash, fire, injured, deaths, miles, state, city)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(odino) DO UPDATE SET
                cmplid=excluded.cmplid,
                vehicle_id=excluded.vehicle_id,
                fail_date=excluded.fail_date,
                ldate=excluded.ldate,
                component_desc=excluded.component_desc,
                complaint_text=excluded.complaint_text,
                crash=excluded.crash,
                fire=excluded.fire,
                injured=excluded.injured,
                deaths=excluded.deaths,
                miles=excluded.miles,
                state=excluded.state,
                city=excluded.city
            """,
            payload,
        )
        inserted += 0 if exists else 1
        updated += 1 if exists else 0
    conn.commit()
    print(
        f"[STA LOAD CSV] source_rows={before:,} unique_odino={len(df):,} "
        f"missing_odino={missing_odino:,} inserted={inserted:,} updated={updated:,}"
    )
    return inserted + updated


def load_structured_jsonl(conn: sqlite3.Connection, jsonl_path: str | Path | None = None) -> int:
    """STR 산출물(JSONL)을 structured_results에 적재한다.

    2026-07-20 v4 대응: cmplid를 기본 키로 쓴다. 레코드에 cmplid가 없는
    구버전(v2/v3) jsonl이 섞여 들어와도 죽지 않도록, 그럴 땐 odino를 대신
    cmplid 자리에 쓴다(그 경우 compdesc1/compdesc2는 당연히 None으로 저장됨 —
    v2/v3 데이터는 애초에 그 필드가 없으므로 정상 동작). 신규 파이프라인은
    전부 v4라 이 폴백은 과거 파일 재적재 시의 안전판일 뿐이다.
    """
    path = _resolve(jsonl_path, DEFAULT_JSONL_PATH, FALLBACKS["jsonl"])
    count = 0
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL {path} {line_no}행 파싱 실패: {exc}") from exc
            if not isinstance(rec, dict):
                raise ValueError(f"JSONL {path} {line_no}행은 JSON 객체여야 합니다.")
            is_v4 = "cmplid" in rec or "compdesc1" in rec
            if is_v4:
                required_v4 = {
                    "cmplid", "odino", "compdesc1", "compdesc2", "symptoms",
                    "severity", "driving_context", "evidence_quote", "insufficient_info",
                }
                missing_v4 = required_v4 - set(rec)
                if missing_v4:
                    raise ValueError(
                        f"JSONL {path} {line_no}행 STR v4 필드 누락: {sorted(missing_v4)}"
                    )
                for field in ("cmplid", "odino", "compdesc1", "compdesc2"):
                    if not _clean_text(rec.get(field)):
                        raise ValueError(f"JSONL {path} {line_no}행 {field} 값이 비어 있습니다.")
            symptoms = rec.get("symptoms")
            if not isinstance(symptoms, list) or not symptoms:
                raise ValueError(f"JSONL {path} {line_no}행 symptoms가 빈 배열입니다.")
            if not _clean_text(rec.get("evidence_quote")):
                raise ValueError(f"JSONL {path} {line_no}행 evidence_quote가 비어 있습니다.")
            odino = _clean_text(rec.get("odino"))
            if not odino:
                raise ValueError(f"JSONL {path} {line_no}행에 odino가 없습니다.")
            cmplid = _clean_text(rec.get("cmplid")) or odino

            # 원본 CSV에 없는 ODINO도 구조화는 저장 가능하게 최소 complaint row 생성.
            if not conn.execute("SELECT 1 FROM complaint_reports WHERE odino=?", (odino,)).fetchone():
                conn.execute("INSERT OR IGNORE INTO complaint_reports(odino) VALUES(?)", (odino,))

            conn.execute(
                """
                INSERT INTO structured_results
                (cmplid, odino, compdesc1, compdesc2, symptoms_json, severity, driving_context,
                 evidence_quote, insufficient_info, rule_notes)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(cmplid) DO UPDATE SET
                    odino=excluded.odino,
                    compdesc1=excluded.compdesc1,
                    compdesc2=excluded.compdesc2,
                    symptoms_json=excluded.symptoms_json,
                    severity=excluded.severity,
                    driving_context=excluded.driving_context,
                    evidence_quote=excluded.evidence_quote,
                    insufficient_info=excluded.insufficient_info,
                    rule_notes=excluded.rule_notes
                """,
                (
                    cmplid,
                    odino,
                    _normalize_compdesc1(rec.get("compdesc1") or rec.get("part_category")),
                    rec.get("compdesc2"),
                    json.dumps(rec.get("symptoms") or [], ensure_ascii=False),
                    rec.get("severity"),
                    rec.get("driving_context"),
                    rec.get("evidence_quote"),
                    1 if rec.get("insufficient_info") else 0,
                    rec.get("v2_rule_notes") or rec.get("rule_notes"),
                ),
            )
            count += 1
    conn.commit()
    print(f"[STA LOAD JSONL] records={count:,} path={path}")
    return count


def register_recall(
    conn: sqlite3.Connection,
    *,
    make: str,
    model: str,
    year: int | str | None,
    campaign_no: str,
    recall_date: str | None,
    component: str,
    summary: str = "",
    source: str = "MANUAL",
    status: str = "OPEN",
    part_number: str | None = None,
    part_family: str | None = None,
    compdesc1: str | None = None,
) -> int:
    """리콜 이력 수동/외부 적재. STA-02 판정 및 defect_signals 판정의 기준 데이터가 된다.

    part_number/part_family는 RCL573 파이프라인(sta_recall_loader.py)에서만 채워지는
    선택 필드다. recall_date는 None/빈 문자열이어도 안전하게 NULL로 저장된다 — RCL573
    산출물에 리콜일이 없는 경우가 있어(sta_recall_loader.py 문서 참고) 필수값으로 두지
    않았다.

    2026-07-21 신규(설계 한계 C 돌파): compdesc1 파라미터 추가. rcl573_classify_
    compdesc.py가 리콜 결함 설명을 Gemini로 STR과 동일한 v4 7종 체계로 분류한
    값이다(문자열 겹처 추측이 아니라 STR 신고 쪽과 정확히 같은 taxonomy). 이 값이
    있으면 find_matching_recall()/find_all_matching_recalls()가 COMPDESC1_RECALL_
    KEYWORDS 휴리스틱 대신 정확값 비교를 쓴다 — None이면(구버전 데이터, 아직 분류
    안 된 리콜 등) 기존 키워드 휴리스틱으로 자동 폴백한다.
    """
    vid = upsert_vehicle(conn, make, model, year)
    iso_date = _date_to_iso(recall_date, dayfirst=True) if recall_date else None
    cur = conn.execute(
        """
        INSERT INTO recall_records(vehicle_id, campaign_no, recall_date, component, compdesc1,
                                    summary, source, status, part_number, part_family)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(vehicle_id, campaign_no) DO UPDATE SET
            recall_date=COALESCE(excluded.recall_date, recall_records.recall_date),
            component=excluded.component,
            compdesc1=COALESCE(excluded.compdesc1, recall_records.compdesc1),
            summary=excluded.summary,
            source=excluded.source,
            status=excluded.status,
            part_number=COALESCE(excluded.part_number, recall_records.part_number),
            part_family=COALESCE(excluded.part_family, recall_records.part_family)
        """,
        (vid, campaign_no, iso_date, component, compdesc1, summary, source, status, part_number, part_family),
    )
    conn.commit()
    row = conn.execute(
        "SELECT recall_id FROM recall_records WHERE vehicle_id=? AND campaign_no=?", (vid, campaign_no)
    ).fetchone()
    return int(row["recall_id"] if row else cur.lastrowid)


def import_recall_records(conn: sqlite3.Connection, recall_csv_path: str | Path) -> int:
    """
    선택 기능: 별도 리콜 CSV를 가져온다.
    필요한 컬럼: make, model, year, campaign_no, recall_date, component
    선택 컬럼: summary, source, status
    """
    df = pd.read_csv(recall_csv_path, dtype=str, encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]
    required = {"make", "model", "year", "campaign_no", "recall_date", "component"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"리콜 CSV 필수 컬럼 누락: {sorted(missing)}")
    n = 0
    for _, row in df.iterrows():
        register_recall(
            conn,
            make=row.get("make"),
            model=row.get("model"),
            year=row.get("year"),
            campaign_no=row.get("campaign_no"),
            recall_date=row.get("recall_date"),
            component=row.get("component"),
            summary=row.get("summary", ""),
            source=row.get("source", "CSV"),
            status=row.get("status", "OPEN") or "OPEN",
        )
        n += 1
    print(f"[STA LOAD RECALL] records={n:,}")
    return n


def _component_matches(compdesc1: str | None, component_text: str | None) -> bool:
    """문자열 겹침 휴리스틱 — COMPDESC1_RECALL_KEYWORDS 기반.

    2026-07-21부터 이 함수는 **폴백 전용**이다. 정상 경로는 아래 _recall_matches()가
    recall_records.compdesc1(rcl573_classify_compdesc.py가 Gemini로 분류한 정확값)로
    바로 비교하고, 그 값이 없는 리콜 레코드에 대해서만 이 함수가 호출된다(예:
    compdesc1 분류 전에 import_recall_records()로 수동 등록된 구버전 리콜).
    """
    if not compdesc1 or not component_text:
        return False
    keywords = COMPDESC1_RECALL_KEYWORDS.get(str(compdesc1).upper(), [])
    if not keywords:
        return False
    comp = component_text.upper()
    return any(k.upper() in comp for k in keywords)


def _recall_matches(report_compdesc1: str, recall_row: sqlite3.Row) -> bool:
    """2026-07-21 신규(설계 한계 C 돌파): 리콜이 이 신고(report_compdesc1)와 같은
    부품 대분류인지 판정한다.

    recall_row.compdesc1이 채워져 있으면(rcl573_classify_compdesc.py로 분류된
    리콜) STR 신고 쪽과 정확히 같은 v4 7종 taxonomy이므로 단순 값 비교(==)로
    충분하고, 이게 정답이다 — 더 이상 "component 텍스트에 이 키워드가 있을
    법하다"는 추측이 아니다. compdesc1이 비어있는 리콜(아직 분류 안 된 구버전
    데이터)만 기존 키워드 휴리스틱으로 안전하게 폴백한다.
    """
    recall_compdesc1 = recall_row["compdesc1"] if "compdesc1" in recall_row.keys() else None
    if report_compdesc1 == "UNKNOWN OR OTHER" or recall_compdesc1 == "UNKNOWN OR OTHER":
        return False
    if recall_compdesc1:
        if report_compdesc1 == recall_compdesc1:
            return True
        return recall_compdesc1 in LEGACY_RECALL_GROUPS.get(report_compdesc1, set())
    return _component_matches(report_compdesc1, recall_row["component"])


def find_matching_recall(
    conn: sqlite3.Connection,
    vehicle_id: int | None,
    compdesc1: str | None,
    detection_date: str | None,
) -> tuple[int | None, str]:
    """
    같은 차량 + 유사 부품 리콜이 있고, 리콜일이 신고일 이전이면 STA-02 후보로 본다.
    날짜가 없으면 같은 차량+부품 리콜 존재만으로 후보를 연결하되 basis에 날짜 불명 표시.
    """
    if not vehicle_id or not compdesc1:
        return None, "vehicle_id 또는 compdesc1 없음"
    rows = conn.execute(
        "SELECT * FROM recall_records WHERE vehicle_id=? ORDER BY recall_date DESC", (vehicle_id,)
    ).fetchall()
    for r in rows:
        if not _recall_matches(compdesc1, r):
            continue
        recall_date = r["recall_date"]
        if detection_date and recall_date:
            if recall_date <= detection_date:
                return int(r["recall_id"]), f"동일 차량·동일 부품군({r['compdesc1'] or r['component']}) 리콜({r['campaign_no']}, {recall_date}) 이후 신고"
            # 리콜이 신고 뒤에 있으면 '재발'이 아니라 당시에는 신규 시그널로 둔다.
            continue
        return int(r["recall_id"]), f"동일 차량·동일 부품군({r['compdesc1'] or r['component']}) 리콜({r['campaign_no']}) 존재, 날짜 비교 불완전"
    return None, "동일 차량·동일 부품군의 과거 리콜 이력 없음"


def find_all_matching_recalls(
    conn: sqlite3.Connection,
    vehicle_id: int | None,
    compdesc1: str | None,
    as_of: str | None = None,
) -> tuple[int | None, str, str | None]:
    """
    find_matching_recall()과의 차이: 그건 "신고 1건이 리콜 이후 재발인가"(날짜 선후 필수)를
    묻고, 이건 "이 차종×compdesc1에 리콜이 존재하는가"(날짜 무관)만 묻는다.
    defect_signals 시그널 판정(sta_signal_state.py)에 쓰인다.

    반환: (recall_id 또는 None, 판정 근거 설명, recall_date 또는 None)
    recall_date가 있는 레코드를 우선하고, 그중 최신순으로 첫 매치를 반환한다.
    """
    if not vehicle_id or not compdesc1:
        return None, "vehicle_id 또는 compdesc1 없음", None
    rows = conn.execute(
        "SELECT * FROM recall_records WHERE vehicle_id=? "
        "AND (? IS NULL OR recall_date IS NULL OR recall_date<=?) "
        "ORDER BY (recall_date IS NULL) ASC, recall_date DESC",
        (vehicle_id, as_of, as_of),
    ).fetchall()
    for r in rows:
        if _recall_matches(compdesc1, r):
            return (
                int(r["recall_id"]),
                f"리콜({r['campaign_no']}) 매칭: {r['compdesc1'] or r['component']}",
                r["recall_date"],
            )
    return None, "동일 차량·동일 부품군의 리콜 이력 없음", None


def classify_and_track(conn: sqlite3.Connection, odino: str, *, notes: str | None = None) -> dict[str, Any]:
    """odino(신고) 단위 STA-01/02 이진 판정.

    2026-07-20 v4 대응: 한 odino에 structured_results 행이 여러 개(cmplid별)
    있을 수 있다. 그중 하나라도 리콜에 매칭되면 이 신고 전체를 STA-02로 본다
    (예: 계기판 문제는 신규지만 같은 신고 안의 다른 행이 이미 리콜된 ADAS
    결함을 가리키면, 이 신고는 "기존 리콜과 무관하지 않다"고 보는 게 맞다).
    표시용 대표 compdesc1/severity는 리콜에 매칭된 행(있으면 그 행), 없으면
    심각도가 가장 높은 행(SEVERITY_RANK 기준)을 쓴다. structured_results 행이
    아예 없으면(구조화 전) STA-01로 두되 근거를 "구조화 결과 없음"으로 남긴다.
    """
    base = conn.execute(
        "SELECT odino, vehicle_id, fail_date FROM complaint_reports WHERE odino=?",
        (str(odino),),
    ).fetchone()
    if not base:
        raise ValueError(f"ODINO {odino} 원본 신고 없음")

    struct_rows = conn.execute(
        "SELECT cmplid, compdesc1, severity FROM structured_results WHERE odino=?",
        (str(odino),),
    ).fetchall()

    recall_id: int | None = None
    basis = "구조화 결과 없음"
    representative = None
    if struct_rows:
        # 기본 대표값: 심각도 최고 행. 리콜 매칭되는 행을 찾으면 그걸로 교체.
        representative = max(struct_rows, key=lambda r: SEVERITY_RANK.get(r["severity"], 0))
        basis = "동일 차량·유사 부품의 과거 리콜 이력 없음"
        for r in struct_rows:
            rid, rb = find_matching_recall(conn, base["vehicle_id"], r["compdesc1"], base["fail_date"])
            if rid:
                recall_id, basis, representative = rid, rb, r
                break

    compdesc1 = representative["compdesc1"] if representative else None
    severity = representative["severity"] if representative else None
    status_code = STA_RECUR if recall_id else STA_NEW
    status_label = STA_LABEL[status_code]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    existing = conn.execute(
        "SELECT tracking_id, status_code, resolution_status FROM defect_status_tracking WHERE odino=?",
        (odino,),
    ).fetchone()

    if existing:
        tid = int(existing["tracking_id"])
        old_code = existing["status_code"]
        conn.execute(
            """
            UPDATE defect_status_tracking
            SET vehicle_id=?, recall_id=?, status_code=?, status_label=?, compdesc1=?, severity=?,
                detection_date=?, recurrence_basis=?, notes=COALESCE(?, notes), updated_at=?
            WHERE tracking_id=?
            """,
            (
                base["vehicle_id"], recall_id, status_code, status_label, compdesc1, severity,
                base["fail_date"], basis, notes, now, tid,
            ),
        )
        if old_code != status_code:
            conn.execute(
                "INSERT INTO status_change_log(tracking_id, field_name, old_value, new_value) VALUES(?,?,?,?)",
                (tid, "status_code", old_code, status_code),
            )
        action = "UPDATE"
    else:
        cur = conn.execute(
            """
            INSERT INTO defect_status_tracking
            (odino, vehicle_id, recall_id, status_code, status_label, compdesc1, severity,
             detection_date, recurrence_basis, notes)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                odino, base["vehicle_id"], recall_id, status_code, status_label, compdesc1, severity,
                base["fail_date"], basis, notes,
            ),
        )
        tid = int(cur.lastrowid)
        action = "INSERT"
    conn.commit()
    return {
        "tracking_id": tid,
        "odino": odino,
        "status_code": status_code,
        "status_label": status_label,
        "compdesc1": compdesc1,
        "severity": severity,
        "recall_id": recall_id,
        "recurrence_basis": basis,
        "action": action,
    }


def classify_all(conn: sqlite3.Connection, *, strict: bool = True) -> list[dict[str, Any]]:
    # 2026-07-20: structured_results가 이제 cmplid 단위(odino당 여러 행)라
    # DISTINCT 없이 돌리면 같은 odino를 여러 번 재분류하는 중복 작업이 된다
    # (결과 자체는 같아서 틀리진 않지만, N배 느려짐 — odino 하나에 cmplid가
    # 여러 개인 신고가 실제로 있음, STR v4 표본 그룹 A_multi_cmplid 참고).
    rows = conn.execute("SELECT DISTINCT odino FROM structured_results ORDER BY odino").fetchall()
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for r in rows:
        try:
            results.append(classify_and_track(conn, r["odino"]))
        except Exception as e:
            message = f"ODINO={r['odino']} {type(e).__name__}: {e}"
            errors.append(message)
            print(f"[STA CLASSIFY][ERROR] {message}")
    counts = pd.Series([x["status_code"] for x in results]).value_counts().to_dict() if results else {}
    print(f"[STA CLASSIFY] success={len(results):,} failed={len(errors):,} counts={counts}")
    if errors and strict:
        preview = "; ".join(errors[:5])
        raise RuntimeError(f"STA 분류 {len(errors)}건 실패: {preview}")
    return results


def update_resolution(
    conn: sqlite3.Connection,
    odino: str,
    resolution_status: str,
    *,
    resolution_date: str | None = None,
    notes: str | None = None,
    changed_by: str = "SYSTEM",
) -> None:
    status = str(resolution_status).upper()
    if status not in VALID_RESOLUTION:
        raise ValueError(f"resolution_status는 {sorted(VALID_RESOLUTION)} 중 하나여야 합니다.")
    row = conn.execute(
        "SELECT tracking_id, resolution_status FROM defect_status_tracking WHERE odino=?", (odino,)
    ).fetchone()
    if not row:
        raise ValueError(f"ODINO {odino} 추적 레코드 없음")
    old = row["resolution_status"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        UPDATE defect_status_tracking
        SET resolution_status=?, resolution_date=COALESCE(?, resolution_date),
            notes=COALESCE(?, notes), updated_at=?
        WHERE odino=?
        """,
        (status, _date_to_iso(resolution_date) if resolution_date else None, notes, now, odino),
    )
    if old != status:
        conn.execute(
            """
            INSERT INTO status_change_log(tracking_id, field_name, old_value, new_value, changed_by)
            VALUES(?,?,?,?,?)
            """,
            (row["tracking_id"], "resolution_status", old, status, changed_by),
        )
    conn.commit()


def query_status_summary(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT
            dst.tracking_id,
            dst.odino,
            v.make, v.model, v.year,
            dst.status_code,
            dst.status_label,
            dst.compdesc1,
            dst.severity,
            dst.detection_date,
            dst.recurrence_basis,
            dst.resolution_status,
            r.campaign_no,
            r.recall_date,
            r.component AS recall_component,
            dst.updated_at
        FROM defect_status_tracking dst
        LEFT JOIN vehicles v ON dst.vehicle_id = v.vehicle_id
        LEFT JOIN recall_records r ON dst.recall_id = r.recall_id
        ORDER BY
            CASE dst.status_code WHEN 'STA-02' THEN 1 ELSE 2 END,
            CASE dst.severity WHEN 'CRITICAL' THEN 1 WHEN 'SERIOUS' THEN 2 WHEN 'MODERATE' THEN 3 WHEN 'MINOR' THEN 4 ELSE 5 END,
            dst.detection_date DESC
        """,
        conn,
    )


def export_status_view(conn: sqlite3.Connection, out_path: str | Path | None = None) -> Path:
    out = _resolve(out_path, DEFAULT_VIEW_CSV, FALLBACKS["view"], create_parent=True)
    df = query_status_summary(conn)
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[STA EXPORT] path={out} rows={len(df):,}")
    return out


def upsert_signal_state(conn: sqlite3.Connection, signal: dict[str, Any]) -> dict[str, Any]:
    """
    sta_signal_state.py가 계산한 판정 결과 dict 하나를 defect_signals에 INSERT/UPDATE하고,
    상태가 바뀐 경우에만 signal_state_log에 이력을 남긴다.

    이 함수는 순수 저장 담당이다 — "무엇이 신규/증가/리콜/잠잠/재발인지" 판단하는
    로직은 여기 없다(sta_signal_state.compute_signal_state가 담당). 스키마를 아는
    코드는 이 파일 하나로 모아 SQL이 여러 파일에 흩어지지 않게 했다.

    signal 필수 키: vehicle_id, compdesc1, signal_state, state_reason
    (2026-07-20: 구 part_category 키 → compdesc1로 변경. sta_signal_state.py도
    같이 맞춰야 한다.)
    선택 키(없으면 None/0으로 저장): recall_id, complaint_count, first_complaint_date,
    last_complaint_date, recent_count, baseline_count, surge_ratio, surge_level, quiet_months
    """
    if signal["signal_state"] not in SIGNAL_STATES:
        raise ValueError(f"알 수 없는 signal_state: {signal['signal_state']!r} (허용: {SIGNAL_STATES})")

    existing = conn.execute(
        "SELECT signal_id, signal_state FROM defect_signals WHERE vehicle_id=? AND compdesc1=?",
        (signal["vehicle_id"], signal["compdesc1"]),
    ).fetchone()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    g = lambda k, default=None: signal.get(k, default)

    if existing:
        sid = int(existing["signal_id"])
        old_state = existing["signal_state"]
        conn.execute(
            """
            UPDATE defect_signals SET
                signal_state=?, recall_id=?, complaint_count=?, first_complaint_date=?,
                last_complaint_date=?, recent_count=?, baseline_count=?, surge_ratio=?,
                surge_level=?, quiet_months=?, state_reason=?, computed_at=?
            WHERE signal_id=?
            """,
            (signal["signal_state"], g("recall_id"), g("complaint_count", 0), g("first_complaint_date"),
             g("last_complaint_date"), g("recent_count"), g("baseline_count"), g("surge_ratio"),
             g("surge_level"), g("quiet_months"), signal["state_reason"], now, sid),
        )
        if old_state != signal["signal_state"]:
            conn.execute(
                "INSERT INTO signal_state_log(signal_id, old_state, new_state, reason) VALUES(?,?,?,?)",
                (sid, old_state, signal["signal_state"], signal["state_reason"]),
            )
    else:
        cur = conn.execute(
            """
            INSERT INTO defect_signals(
                vehicle_id, compdesc1, signal_state, recall_id, complaint_count,
                first_complaint_date, last_complaint_date, recent_count, baseline_count,
                surge_ratio, surge_level, quiet_months, state_reason
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (signal["vehicle_id"], signal["compdesc1"], signal["signal_state"], g("recall_id"),
             g("complaint_count", 0), g("first_complaint_date"), g("last_complaint_date"), g("recent_count"),
             g("baseline_count"), g("surge_ratio"), g("surge_level"), g("quiet_months"), signal["state_reason"]),
        )
        sid = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO signal_state_log(signal_id, old_state, new_state, reason) VALUES(?,?,?,?)",
            (sid, None, signal["signal_state"], signal["state_reason"]),
        )
    conn.commit()
    out = dict(signal)
    out["signal_id"] = sid
    return out


def query_signal_summary(conn: sqlite3.Connection) -> pd.DataFrame:
    """defect_signals를 차량/리콜 정보와 조인해 대시보드·CHT-01이 바로 쓰기 좋은 형태로 반환."""
    return pd.read_sql_query(
        """
        SELECT
            ds.signal_id, v.make, v.model, v.year,
            ds.compdesc1, ds.signal_state, ds.complaint_count,
            ds.first_complaint_date, ds.last_complaint_date,
            ds.recent_count, ds.baseline_count, ds.surge_ratio, ds.surge_level,
            ds.quiet_months, ds.state_reason,
            r.campaign_no, r.recall_date, r.source AS recall_source,
            ds.computed_at
        FROM defect_signals ds
        LEFT JOIN vehicles v ON ds.vehicle_id = v.vehicle_id
        LEFT JOIN recall_records r ON ds.recall_id = r.recall_id
        ORDER BY
            CASE ds.signal_state
                WHEN 'RECURRING' THEN 1 WHEN 'RISING' THEN 2 WHEN 'RECALLED' THEN 3
                WHEN 'NEW' THEN 4 WHEN 'DORMANT' THEN 5 ELSE 6
            END,
            ds.last_complaint_date DESC
        """,
        conn,
    )


def export_signal_view(conn: sqlite3.Connection, out_path: str | Path | None = None) -> Path:
    default = DEFAULT_VIEW_CSV.parent / "defect_signal_view.csv"
    out = _resolve(out_path, default, [p.parent / "defect_signal_view_generated.csv" for p in FALLBACKS["view"]], create_parent=True)
    df = query_signal_summary(conn)
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[STA EXPORT] path={out} rows={len(df):,}")
    return out


def run_status_tracking(
    *,
    csv_path: str | Path | None = None,
    jsonl_path: str | Path | None = None,
    db_path: str | Path | None = None,
    out_csv: str | Path | None = None,
) -> sqlite3.Connection:
    conn = init_db(db_path)
    load_complaints_csv(conn, csv_path)
    load_structured_jsonl(conn, jsonl_path)
    classify_all(conn)
    export_status_view(conn, out_csv)
    return conn


if __name__ == "__main__":
    conn0 = run_status_tracking()
    print(query_status_summary(conn0).head(20).to_string(index=False))
    conn0.close()
