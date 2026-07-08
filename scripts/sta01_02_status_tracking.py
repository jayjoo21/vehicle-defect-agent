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
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import datetime
import json
import sqlite3

import pandas as pd

DEFAULT_CSV_PATH = Path("data/processed/hk_electrical_recent_full.csv")
DEFAULT_JSONL_PATH = Path("data/processed/llm_struct_test_results.jsonl")
DEFAULT_DB_PATH = Path("data/processed/defect_status_tracking.db")
DEFAULT_VIEW_CSV = Path("data/processed/defect_status_view.csv")
FALLBACKS = {
    "csv": [Path("/mnt/data/hk_electrical_recent_full.csv"), Path("hk_electrical_recent_full.csv")],
    "jsonl": [Path("/mnt/data/llm_struct_test_results.jsonl"), Path("/mnt/data/llm_struct_v2_18cases.jsonl"), Path("llm_struct_v2_18cases.jsonl")],
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

PART_RECALL_KEYWORDS = {
    "ELECTRICAL_SYSTEM": ["ELECTRICAL", "BATTERY", "WIRING", "INSTRUMENT", "CLUSTER", "DISPLAY", "SOFTWARE"],
    "ADAS": ["LANE", "COLLISION", "CAMERA", "RADAR", "SENSOR", "ELECTRONIC STABILITY", "FORWARD"],
    "POWERTRAIN_SW": ["ENGINE", "POWER TRAIN", "THROTTLE", "ECM", "ECU", "SOFTWARE", "FUEL"],
    "NON_ELECTRICAL": [],
    "INSUFFICIENT_INFO": [],
}


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

        CREATE TABLE IF NOT EXISTS structured_results (
            odino             TEXT PRIMARY KEY REFERENCES complaint_reports(odino),
            part_category     TEXT,
            symptoms_json     TEXT,
            severity          TEXT,
            driving_context   TEXT,
            evidence_quote    TEXT,
            insufficient_info INTEGER DEFAULT 0,
            rule_notes        TEXT,
            created_at        TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_struct_part ON structured_results(part_category);
        CREATE INDEX IF NOT EXISTS idx_struct_severity ON structured_results(severity);

        CREATE TABLE IF NOT EXISTS recall_records (
            recall_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id      INTEGER NOT NULL REFERENCES vehicles(vehicle_id),
            campaign_no     TEXT,
            recall_date     TEXT,
            component       TEXT,
            summary         TEXT,
            source          TEXT DEFAULT 'MANUAL',
            status          TEXT DEFAULT 'OPEN' CHECK(status IN ('OPEN','CLOSED','PARTIAL','UNKNOWN')),
            created_at      TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(vehicle_id, campaign_no)
        );
        CREATE INDEX IF NOT EXISTS idx_recall_vehicle ON recall_records(vehicle_id);
        CREATE INDEX IF NOT EXISTS idx_recall_component ON recall_records(component);
        CREATE INDEX IF NOT EXISTS idx_recall_date ON recall_records(recall_date);

        CREATE TABLE IF NOT EXISTS defect_status_tracking (
            tracking_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            odino             TEXT NOT NULL UNIQUE REFERENCES complaint_reports(odino),
            vehicle_id        INTEGER REFERENCES vehicles(vehicle_id),
            recall_id         INTEGER REFERENCES recall_records(recall_id),
            status_code       TEXT NOT NULL CHECK(status_code IN ('STA-01','STA-02')),
            status_label      TEXT NOT NULL,
            part_category     TEXT,
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
        """
    )
    conn.commit()
    return conn


def _date_to_iso(value: Any, *, dayfirst: bool = False) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        dt = pd.to_datetime(text, format="%Y%m%d", errors="coerce")
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
    make = str(make or "UNKNOWN").strip().upper()
    model = str(model or "UNKNOWN").strip().upper()
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
        df = df.drop_duplicates(subset="ODINO", keep="first")

    inserted = updated = 0
    for _, row in df.iterrows():
        odino = str(row.get("ODINO") or "").strip()
        if not odino:
            continue
        vid = upsert_vehicle(conn, row.get("MAKETXT"), row.get("MODELTXT"), row.get("YEARTXT"))
        payload = (
            odino,
            str(row.get("CMPLID") or "").strip() or None,
            vid,
            _date_to_iso(row.get("FAILDATE")),
            _date_to_iso(row.get("LDATE")),
            str(row.get("COMPDESC") or "").strip() or None,
            str(row.get("CDESCR") or "").strip() or None,
            1 if str(row.get("CRASH") or "").strip().upper() == "Y" else 0,
            1 if str(row.get("FIRE") or "").strip().upper() == "Y" else 0,
            _safe_int(row.get("INJURED")),
            _safe_int(row.get("DEATHS")),
            _safe_float(row.get("MILES")),
            str(row.get("STATE") or "").strip() or None,
            str(row.get("CITY") or "").strip() or None,
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
    print(f"[STA LOAD CSV] source_rows={before:,} unique_odino={len(df):,} inserted={inserted:,} updated={updated:,}")
    return inserted + updated


def load_structured_jsonl(conn: sqlite3.Connection, jsonl_path: str | Path | None = None) -> int:
    path = _resolve(jsonl_path, DEFAULT_JSONL_PATH, FALLBACKS["jsonl"])
    count = 0
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            odino = str(rec.get("odino") or "").strip()
            if not odino:
                continue
            # 원본 CSV에 없는 ODINO도 구조화는 저장 가능하게 최소 complaint row 생성.
            if not conn.execute("SELECT 1 FROM complaint_reports WHERE odino=?", (odino,)).fetchone():
                conn.execute("INSERT OR IGNORE INTO complaint_reports(odino) VALUES(?)", (odino,))
            conn.execute(
                """
                INSERT INTO structured_results
                (odino, part_category, symptoms_json, severity, driving_context,
                 evidence_quote, insufficient_info, rule_notes)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(odino) DO UPDATE SET
                    part_category=excluded.part_category,
                    symptoms_json=excluded.symptoms_json,
                    severity=excluded.severity,
                    driving_context=excluded.driving_context,
                    evidence_quote=excluded.evidence_quote,
                    insufficient_info=excluded.insufficient_info,
                    rule_notes=excluded.rule_notes
                """,
                (
                    odino,
                    rec.get("part_category"),
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
    recall_date: str,
    component: str,
    summary: str = "",
    source: str = "MANUAL",
    status: str = "OPEN",
) -> int:
    """리콜 이력 수동/외부 적재. STA-02 판정의 기준 데이터가 된다."""
    vid = upsert_vehicle(conn, make, model, year)
    cur = conn.execute(
        """
        INSERT INTO recall_records(vehicle_id, campaign_no, recall_date, component, summary, source, status)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(vehicle_id, campaign_no) DO UPDATE SET
            recall_date=excluded.recall_date,
            component=excluded.component,
            summary=excluded.summary,
            source=excluded.source,
            status=excluded.status
        """,
        (vid, campaign_no, _date_to_iso(recall_date, dayfirst=True) or recall_date, component, summary, source, status),
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


def _component_matches(part_category: str | None, component_text: str | None) -> bool:
    if not part_category or not component_text:
        return False
    keywords = PART_RECALL_KEYWORDS.get(str(part_category).upper(), [])
    if not keywords:
        return False
    comp = component_text.upper()
    return any(k.upper() in comp for k in keywords)


def find_matching_recall(
    conn: sqlite3.Connection,
    vehicle_id: int | None,
    part_category: str | None,
    detection_date: str | None,
) -> tuple[int | None, str]:
    """
    같은 차량 + 유사 부품 리콜이 있고, 리콜일이 신고일 이전이면 STA-02 후보로 본다.
    날짜가 없으면 같은 차량+부품 리콜 존재만으로 후보를 연결하되 basis에 날짜 불명 표시.
    """
    if not vehicle_id or not part_category:
        return None, "vehicle_id 또는 part_category 없음"
    rows = conn.execute(
        "SELECT * FROM recall_records WHERE vehicle_id=? ORDER BY recall_date DESC", (vehicle_id,)
    ).fetchall()
    for r in rows:
        if not _component_matches(part_category, r["component"]):
            continue
        recall_date = r["recall_date"]
        if detection_date and recall_date:
            if recall_date <= detection_date:
                return int(r["recall_id"]), f"동일 차량·유사 부품 리콜({r['campaign_no']}, {recall_date}) 이후 신고"
            # 리콜이 신고 뒤에 있으면 '재발'이 아니라 당시에는 신규 시그널로 둔다.
            continue
        return int(r["recall_id"]), f"동일 차량·유사 부품 리콜({r['campaign_no']}) 존재, 날짜 비교 불완전"
    return None, "동일 차량·유사 부품의 과거 리콜 이력 없음"


def classify_and_track(conn: sqlite3.Connection, odino: str, *, notes: str | None = None) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
            cr.odino, cr.vehicle_id, cr.fail_date,
            sr.part_category, sr.severity, sr.insufficient_info
        FROM complaint_reports cr
        LEFT JOIN structured_results sr ON cr.odino = sr.odino
        WHERE cr.odino=?
        """,
        (str(odino),),
    ).fetchone()
    if not row:
        raise ValueError(f"ODINO {odino} 원본 신고 없음")

    recall_id, basis = find_matching_recall(
        conn,
        row["vehicle_id"],
        row["part_category"],
        row["fail_date"],
    )
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
            SET vehicle_id=?, recall_id=?, status_code=?, status_label=?, part_category=?, severity=?,
                detection_date=?, recurrence_basis=?, notes=COALESCE(?, notes), updated_at=?
            WHERE tracking_id=?
            """,
            (
                row["vehicle_id"], recall_id, status_code, status_label, row["part_category"], row["severity"],
                row["fail_date"], basis, notes, now, tid,
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
            (odino, vehicle_id, recall_id, status_code, status_label, part_category, severity,
             detection_date, recurrence_basis, notes)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                odino, row["vehicle_id"], recall_id, status_code, status_label, row["part_category"], row["severity"],
                row["fail_date"], basis, notes,
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
        "part_category": row["part_category"],
        "severity": row["severity"],
        "recall_id": recall_id,
        "recurrence_basis": basis,
        "action": action,
    }


def classify_all(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT odino FROM structured_results ORDER BY odino").fetchall()
    results: list[dict[str, Any]] = []
    for r in rows:
        try:
            results.append(classify_and_track(conn, r["odino"]))
        except Exception as e:
            print(f"[STA CLASSIFY WARN] ODINO={r['odino']} {e}")
    counts = pd.Series([x["status_code"] for x in results]).value_counts().to_dict() if results else {}
    print(f"[STA CLASSIFY] total={len(results):,} counts={counts}")
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
            dst.part_category,
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
