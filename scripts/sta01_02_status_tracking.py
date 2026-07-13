"""
STA-01 / STA-02  상태 추적 DB
─────────────────────────────────────────────────────────────────
목적: LLM 분석 결과(JSONL)의 각 ODINO에 대해
     NHTSA 리콜 API를 조회하여 결함 신규 여부를 판정하고
     SQLite에 추적 기록을 유지한다.

  STA-01 (신규 결함)        — 해당 차종·부품 리콜 이력 없음
  STA-02 (기존 리콜 후 재발) — 매핑 리콜 존재

입력:
  data/processed/llm_struct_test_results.jsonl
  data/processed/hk_electrical_recent_full.csv
  NHTSA 리콜 API (키 불필요)
    https://api.nhtsa.gov/recalls/recallsByVehicle?make={}&model={}&modelYear={}
출력:
  data/processed/defect_status_tracking.db   (SQLite)
  data/processed/defect_status_view.csv      (뷰 CSV, utf-8-sig)

⚠️ 리콜 날짜 ReportReceivedDate: DD/MM/YYYY
   → pd.to_datetime(..., dayfirst=True) → ISO(YYYY-MM-DD) 변환 필수
   불만 날짜 FAILDATE: YYYYMMDD — 반드시 ISO 통일 후 비교
⚠️ 같은 캠페인이 여러 차종에 중복 → NHTSACampaignNumber 기준 dedupe
⚠️ ODINO 중복 존재 가능 → dedupe_by_key()로 제거 후 인덱싱 (2025-XX-XX 수정)
⚠️ VIN 노출 금지 / "결함 확정" 표현 금지
⚠️ 레이(Ray) 등 미국 미판매 차종 API 미조회 → "한국 단독 리콜" 표시
"""
import json, sqlite3, time
import pandas as pd
import requests
from pathlib import Path
from datetime import datetime

JSONL_PATH   = "C:/Users/HYWOMAN/Desktop/AICPP_Work/llm_struct_v2_18cases.jsonl"
CSV_PATH     = "C:/Users/HYWOMAN/Desktop/AICPP_Work/hk_electrical_recent_full.csv"
DB_PATH      = "C:/Users/HYWOMAN/Desktop/AICPP_Work/defect_status_tracking.db"
OUT_CSV      = "C:/Users/HYWOMAN/Desktop/AICPP_Work/defect_status_view.csv"
RECALL_API   = "https://api.nhtsa.gov/recalls/recallsByVehicle"

STA_NEW    = "STA-01"   # 신규 결함
STA_RECUR  = "STA-02"   # 기존 리콜 후 재발

# part_category → NHTSA Component 포함 키워드
COMP_MAP = {
    "ELECTRICAL_SYSTEM": "ELECTRICAL",
    "ADAS":              "ELECTRONIC STABILITY",
    "POWERTRAIN_SW":     "ENGINE",
    "NON_ELECTRICAL":    "",   # 범위 광범위 → 매핑 불가
    "INSUFFICIENT_INFO": "",
}

# 미국 미판매 (한국 단독 리콜) 모델 예시 — 필요 시 추가
KR_ONLY_MODELS = {"RAY", "MORNING", "STARIA", "CASPER"}


# ═══════════════════════════════════════════════════════
# 1. DB 초기화 (4 테이블)
# ═══════════════════════════════════════════════════════
def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    """DB 파일 생성 + 스키마 초기화 (멱등)."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS vehicles (
        vehicle_id  INTEGER PRIMARY KEY AUTOINCREMENT,
        make        TEXT NOT NULL,
        model       TEXT NOT NULL,
        year        INTEGER,
        kr_only     INTEGER DEFAULT 0,  -- 1=한국 단독 리콜 차종
        UNIQUE(make, model, year)
    );

    -- NHTSA 리콜 API 응답 캐시
    -- ReportReceivedDate(DD/MM/YYYY) → report_date_iso(YYYY-MM-DD) 변환 저장
    CREATE TABLE IF NOT EXISTS recall_records (
        recall_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        vehicle_id       INTEGER NOT NULL REFERENCES vehicles(vehicle_id),
        campaign_no      TEXT,                -- NHTSACampaignNumber (dedupe 기준)
        report_date_iso  TEXT,               -- ISO YYYY-MM-DD
        component        TEXT,
        summary           TEXT,
        ota_update        INTEGER DEFAULT 0,  -- overTheAirUpdate Y/N
        fetched_at        TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(vehicle_id, campaign_no)      -- 캠페인 중복 방지
    );
    CREATE INDEX IF NOT EXISTS idx_rec_vid  ON recall_records(vehicle_id);
    CREATE INDEX IF NOT EXISTS idx_rec_comp ON recall_records(component);

    -- STA-01/02 판정 메인 테이블
    CREATE TABLE IF NOT EXISTS defect_status_tracking (
        tracking_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        odino             TEXT NOT NULL UNIQUE,
        vehicle_id        INTEGER REFERENCES vehicles(vehicle_id),
        recall_id         INTEGER REFERENCES recall_records(recall_id),
        status_code       TEXT NOT NULL CHECK(status_code IN ('STA-01','STA-02')),
        part_category     TEXT,
        severity          TEXT,
        detection_date    TEXT,              -- FAILDATE → ISO
        resolution_status TEXT DEFAULT 'OPEN'
                          CHECK(resolution_status IN
                                ('OPEN','IN_PROGRESS','RESOLVED','MONITORING')),
        resolution_date   TEXT,
        notes             TEXT,
        created_at        TEXT DEFAULT (datetime('now','localtime')),
        updated_at        TEXT DEFAULT (datetime('now','localtime'))
    );
    CREATE INDEX IF NOT EXISTS idx_dst_status ON defect_status_tracking(status_code);
    CREATE INDEX IF NOT EXISTS idx_dst_sev    ON defect_status_tracking(severity);

    -- 상태 변경 이력 (resolution_status, status_code 변경 시 자동 기록)
    CREATE TABLE IF NOT EXISTS status_change_log (
        log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
        tracking_id INTEGER NOT NULL REFERENCES defect_status_tracking(tracking_id),
        field_name  TEXT NOT NULL,
        old_value   TEXT,
        new_value   TEXT,
        changed_at  TEXT DEFAULT (datetime('now','localtime'))
    );
    """)
    conn.commit()
    print(f"[DB INIT] {db_path} 준비 완료")
    return conn


# ═══════════════════════════════════════════════════════
# 2. 데이터 로더
# ═══════════════════════════════════════════════════════
def load_jsonl(path: str) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    print(f"[LOAD JSONL] {len(records)}건")
    return records


def dedupe_by_key(df: pd.DataFrame, key: str, keep: str = "first") -> pd.DataFrame:
    """
    key 컬럼 기준 중복 행 제거 (재사용 가능한 유틸).
    - 제거 전 중복 건수와, 중복 행들 간 값이 실제로 다른지(진짜 충돌) 확인 로그 출력.
    - keep='first' 기본: 첫 등장 행만 유지.
    """
    dup_mask  = df.duplicated(subset=key, keep=False)
    dup_count = df[key].duplicated(keep="first").sum()

    if dup_count > 0:
        dup_rows = df[dup_mask].sort_values(key)
        # 같은 key를 가진 행들끼리 나머지 컬럼 값이 실제로 다른지 체크
        conflicting = (
            dup_rows.groupby(key)
            .nunique(dropna=False)
            .drop(columns=[key], errors="ignore")
            .gt(1).any(axis=1).sum()
        )
        print(f"[DEDUPE] '{key}' 중복 {dup_count}건 발견 "
              f"(그 중 값이 서로 다른 진짜 충돌 {conflicting}건) → keep='{keep}'로 제거")

    before = len(df)
    df = df.drop_duplicates(subset=key, keep=keep)
    print(f"[DEDUPE] {before:,}행 → {len(df):,}행")
    return df


def load_csv_meta(path: str) -> pd.DataFrame:
    """
    불만 CSV → ODINO·차량·날짜 메타만 추출.
    - VIN 즉시 제거
    - FAILDATE: YYYYMMDD → ISO(YYYY-MM-DD)
    - ODINO 중복 제거 (set_index 시 유일성 요구되므로 필수)
    - 처리 완료본이므로 청크 불필요
    """
    df = pd.read_csv(path, dtype=str, low_memory=False, encoding="utf-8-sig")
    df.columns = [c.strip().upper() for c in df.columns]

    if "VIN" in df.columns:
        df = df.drop(columns=["VIN"])

    keep = ["ODINO", "MAKETXT", "MODELTXT", "YEARTXT", "FAILDATE"]
    df = df[[c for c in keep if c in df.columns]].copy()

    # FAILDATE: YYYYMMDD → ISO
    if "FAILDATE" in df.columns:
        dt = pd.to_datetime(df["FAILDATE"], format="%Y%m%d", errors="coerce")
        df["FAILDATE"] = dt.dt.strftime("%Y-%m-%d")

    # 검증 출력
    print(f"[LOAD CSV META] 행={len(df):,}  열={len(df.columns)}")
    print(f"  FAILDATE 범위: {df['FAILDATE'].min()} ~ {df['FAILDATE'].max()}")
    null_pct = {c: f"{df[c].isnull().mean()*100:.1f}%"
                for c in df.columns if df[c].isnull().mean() > 0}
    print(f"  널비율: {null_pct}")

    # ODINO 중복 제거 (set_index("ODINO").to_dict("index") 대비)
    df = dedupe_by_key(df, key="ODINO")

    return df


# ═══════════════════════════════════════════════════════
# 3. NHTSA 리콜 API 조회
# ═══════════════════════════════════════════════════════
def fetch_recalls(make: str, model: str, year, sleep_sec: float = 0.3) -> list[dict]:
    """
    NHTSA 리콜 API 1건 호출.
    ⚠️ ReportReceivedDate: DD/MM/YYYY → dayfirst=True → ISO
    API 실패 시 빈 리스트 반환 (전체 중단 금지).
    """
    params = {"make": make, "model": model, "modelYear": year}
    try:
        resp = requests.get(RECALL_API, params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("results", [])
        for item in items:
            raw = item.get("ReportReceivedDate", "")
            try:
                item["report_date_iso"] = (
                    pd.to_datetime(raw, dayfirst=True).strftime("%Y-%m-%d")
                )
            except Exception:
                item["report_date_iso"] = None
        time.sleep(sleep_sec)
        return items
    except Exception as e:
        print(f"  [API WARN] {make}/{model}/{year}: {e}")
        return []


# ═══════════════════════════════════════════════════════
# 4. 차량 마스터 + 리콜 적재
# ═══════════════════════════════════════════════════════
def upsert_vehicle(conn, make: str, model: str, year) -> int:
    row = conn.execute(
        "SELECT vehicle_id FROM vehicles WHERE make=? AND model=? AND year=?",
        (make, model, year)
    ).fetchone()
    if row:
        return row["vehicle_id"]
    kr_only = 1 if model.upper() in KR_ONLY_MODELS else 0
    cur = conn.execute(
        "INSERT INTO vehicles(make, model, year, kr_only) VALUES(?,?,?,?)",
        (make, model, year, kr_only)
    )
    conn.commit()
    return cur.lastrowid


def insert_recalls(conn, vehicle_id: int, recalls: list[dict]):
    """
    API 응답 → recall_records 적재.
    NHTSACampaignNumber 기준 dedupe (UNIQUE 제약).
    """
    for r in recalls:
        ota = 1 if str(r.get("overTheAirUpdate","")).strip().upper() == "Y" else 0
        try:
            conn.execute("""
                INSERT OR IGNORE INTO recall_records
                (vehicle_id, campaign_no, report_date_iso, component, summary, ota_update)
                VALUES(?,?,?,?,?,?)
            """, (vehicle_id,
                  r.get("NHTSACampaignNumber",""),
                  r.get("report_date_iso"),
                  r.get("Component",""),
                  r.get("Summary",""),
                  ota))
        except sqlite3.Error:
            pass
    conn.commit()


# ═══════════════════════════════════════════════════════
# 5. STA-01 / STA-02 판정
# ═══════════════════════════════════════════════════════
def _find_recall(conn, vehicle_id: int, part_category: str):
    """
    vehicle_id + part_category 키워드로 매핑 리콜 조회.
    반환: recall_id(int) 또는 None → STA-01
    """
    keyword = COMP_MAP.get(part_category, "")
    if not keyword:
        return None
    row = conn.execute("""
        SELECT recall_id FROM recall_records
        WHERE vehicle_id = ?
          AND UPPER(component) LIKE ?
        ORDER BY report_date_iso DESC LIMIT 1
    """, (vehicle_id, f"%{keyword}%")).fetchone()
    return row["recall_id"] if row else None


def classify_and_record(conn, odino: str, vehicle_id,
                        part_category: str, severity: str,
                        detection_date: str) -> str:
    """
    ODINO 1건 STA-01/02 판정 + DB 기록.
    이미 존재하면 UPDATE + 변경 로그.
    반환: status_code
    """
    recall_id   = _find_recall(conn, vehicle_id, part_category) if vehicle_id else None
    status_code = STA_RECUR if recall_id else STA_NEW
    now         = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    existing = conn.execute(
        "SELECT tracking_id, status_code FROM defect_status_tracking WHERE odino=?",
        (odino,)
    ).fetchone()

    if existing:
        tid, old_code = existing["tracking_id"], existing["status_code"]
        conn.execute("""
            UPDATE defect_status_tracking
            SET status_code=?, recall_id=?, severity=?, updated_at=?
            WHERE tracking_id=?
        """, (status_code, recall_id, severity, now, tid))
        if old_code != status_code:
            conn.execute("""
                INSERT INTO status_change_log(tracking_id, field_name, old_value, new_value)
                VALUES(?,?,?,?)
            """, (tid, "status_code", old_code, status_code))
    else:
        conn.execute("""
            INSERT INTO defect_status_tracking
            (odino, vehicle_id, recall_id, status_code,
             part_category, severity, detection_date)
            VALUES(?,?,?,?,?,?,?)
        """, (odino, vehicle_id, recall_id, status_code,
              part_category, severity, detection_date))

    conn.commit()
    return status_code


# ═══════════════════════════════════════════════════════
# 6. 해소 상태 갱신
# ═══════════════════════════════════════════════════════
VALID_RESOLUTION = {"OPEN", "IN_PROGRESS", "RESOLVED", "MONITORING"}

def update_resolution(conn, odino: str, resolution_status: str,
                      resolution_date: str = None, notes: str = None):
    """
    resolution_status 갱신 + 변경 로그 기록.
    """
    if resolution_status not in VALID_RESOLUTION:
        raise ValueError(f"resolution_status must be one of {VALID_RESOLUTION}")
    row = conn.execute(
        "SELECT tracking_id, resolution_status FROM defect_status_tracking WHERE odino=?",
        (odino,)
    ).fetchone()
    if not row:
        raise ValueError(f"ODINO {odino} 없음")
    old_val = row["resolution_status"]
    now     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        UPDATE defect_status_tracking
        SET resolution_status=?,
            resolution_date=COALESCE(?, resolution_date),
            notes=COALESCE(?, notes),
            updated_at=?
        WHERE odino=?
    """, (resolution_status, resolution_date, notes, now, odino))
    conn.execute("""
        INSERT INTO status_change_log(tracking_id, field_name, old_value, new_value)
        VALUES(?,?,?,?)
    """, (row["tracking_id"], "resolution_status", old_val, resolution_status))
    conn.commit()
    print(f"[UPDATE] {odino}: {old_val} → {resolution_status}")


# ═══════════════════════════════════════════════════════
# 7. 전체 실행
# ═══════════════════════════════════════════════════════


def run(jsonl_path=JSONL_PATH, csv_path=CSV_PATH, db_path=DB_PATH) -> sqlite3.Connection:
    conn     = init_db(db_path)
    llm_recs = load_jsonl(jsonl_path)
    meta_df  = load_csv_meta(csv_path)
    meta_idx = meta_df.set_index("ODINO").to_dict("index")  # O(1) 룩업

    print(f"\n[CLASSIFY START] {len(llm_recs)}건 ─────────────────────────────")
    for rec in llm_recs:
        odino    = str(rec["odino"])
        m        = meta_idx.get(odino, {})
        make     = str(m.get("MAKETXT","")).strip().upper() or None
        model    = str(m.get("MODELTXT","")).strip().upper() or None
        yr_raw   = m.get("YEARTXT","")
        year     = int(yr_raw) if str(yr_raw).isdigit() else None
        fail_iso = m.get("FAILDATE", None)

        vid = None
        if make and model and year:
            vid = upsert_vehicle(conn, make, model, year)
            # 리콜 API: 처음 등록 차량만 조회 (kr_only 차종 제외)
            kr_only = conn.execute(
                "SELECT kr_only FROM vehicles WHERE vehicle_id=?", (vid,)
            ).fetchone()["kr_only"]
            existing_cnt = conn.execute(
                "SELECT COUNT(*) FROM recall_records WHERE vehicle_id=?", (vid,)
            ).fetchone()[0]
            if not kr_only and existing_cnt == 0:
                recalls = fetch_recalls(make, model, year)
                insert_recalls(conn, vid, recalls)
                print(f"  [API] {make}/{model}/{year} → 리콜 {len(recalls)}건 적재")

        code = classify_and_record(
            conn, odino, vid,
            rec.get("part_category",""),
            rec.get("severity",""),
            fail_iso
        )
        print(f"  {odino} → {code}  ({rec.get('part_category')}, {rec.get('severity')})")

    # 검증 출력
    n01  = conn.execute("SELECT COUNT(*) FROM defect_status_tracking WHERE status_code='STA-01'").fetchone()[0]
    n02  = conn.execute("SELECT COUNT(*) FROM defect_status_tracking WHERE status_code='STA-02'").fetchone()[0]
    nrec = conn.execute("SELECT COUNT(*) FROM recall_records").fetchone()[0]
    nveh = conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
    print(f"\n[DB 검증] STA-01={n01}  STA-02={n02}  recall_records={nrec}  vehicles={nveh}")
    return conn


# ═══════════════════════════════════════════════════════
# 8. 뷰 CSV 내보내기
# ═══════════════════════════════════════════════════════
def export_view_csv(conn, out_path: str = OUT_CSV):
    """추적 결과 + 차량 + 리콜 조인 뷰 → CSV 저장."""
    df = pd.read_sql_query("""
        SELECT
            dst.odino,
            v.make, v.model, v.year,
            CASE v.kr_only WHEN 1 THEN '한국 단독 리콜' ELSE '미국 조회' END AS recall_scope,
            dst.status_code,
            dst.part_category,
            dst.severity,
            dst.detection_date,
            dst.resolution_status,
            dst.resolution_date,
            r.campaign_no,
            r.report_date_iso   AS recall_date,
            r.component         AS recall_component,
            CASE r.ota_update WHEN 1 THEN 'Y' ELSE 'N' END AS ota_update,
            dst.notes,
            dst.created_at
        FROM defect_status_tracking dst
        LEFT JOIN vehicles v       ON dst.vehicle_id = v.vehicle_id
        LEFT JOIN recall_records r ON dst.recall_id  = r.recall_id
        ORDER BY
            CASE dst.severity
                WHEN 'CRITICAL' THEN 1 WHEN 'SERIOUS' THEN 2
                WHEN 'MODERATE' THEN 3 WHEN 'MINOR'   THEN 4 ELSE 5
            END,
            dst.status_code
    """, conn)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    # 검증 출력
    print(f"[EXPORT] {out_path}  행={len(df)}  열={len(df.columns)}")
    conn.close()


# ── 메인 실행 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    conn = run()
    export_view_csv(conn)