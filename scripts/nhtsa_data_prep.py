import csv
import os
import re
import sys

# Windows 터미널 cp949 환경에서 한글·특수문자 깨짐 방지
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_FILE = os.path.join(BASE_DIR, "data", "raw", "FLAT_CMPL.txt")
PROC_DIR = os.path.join(BASE_DIR, "data", "processed")
SAMP_DIR = os.path.join(BASE_DIR, "data", "samples")

os.makedirs(PROC_DIR, exist_ok=True)
os.makedirs(SAMP_DIR, exist_ok=True)

# 실측 51개: PDF 스펙 49개 + NHTSA가 2021년 이후 추가한 미문서 컬럼 2개(현재 빈값)
COLS = [
    "CMPLID", "ODINO", "MFR_NAME", "MAKETXT", "MODELTXT", "YEARTXT",
    "CRASH", "FAILDATE", "FIRE", "INJURED", "DEATHS", "COMPDESC",
    "CITY", "STATE", "VIN", "DATEA", "LDATE", "MILES", "OCCURENCES",
    "CDESCR", "CMPL_TYPE", "POLICE_RPT_YN", "PURCH_DT", "ORIG_OWNER_YN",
    "ANTI_BRAKES_YN", "CRUISE_CONT_YN", "NUM_CYLS", "DRIVE_TRAIN",
    "FUEL_SYS", "FUEL_TYPE", "TRANS_TYPE", "VEH_SPEED", "DOT",
    "TIRE_SIZE", "LOC_OF_TIRE", "TIRE_FAIL_TYPE", "ORIG_EQUIP_YN",
    "MANUF_DT", "SEAT_TYPE", "RESTRAINT_TYPE", "DEALER_NAME",
    "DEALER_TEL", "DEALER_CITY", "DEALER_STATE", "DEALER_ZIP",
    "PROD_TYPE", "REPAIRED_YN", "MEDICAL_ATTN", "VEHICLES_TOWED_YN",
    "UNKNOWN_50", "UNKNOWN_51",
]

CHUNK_SIZE = 200_000
TARGET_MAKES = {"HYUNDAI", "KIA"}

COMP_PREFIXES = [
    "ELECTRICAL SYSTEM",
    "ELECTRONIC STABILITY CONTROL",
    "FORWARD COLLISION AVOIDANCE",
    "LANE DEPARTURE",
    "BACK OVER PREVENTION",
    "VEHICLE SPEED CONTROL",
    "UNKNOWN OR OTHER",
]
# str.match은 문자열 시작부터 매칭 (re.match 동작)
COMP_PATTERN = "(" + "|".join(re.escape(p) for p in COMP_PREFIXES) + ")"

KEY_COLS = [
    "ODINO", "MAKETXT", "MODELTXT", "YEARTXT", "LDATE",
    "COMPDESC", "CDESCR", "CRASH", "FIRE", "INJURED", "DEATHS",
]

DANGER_PATTERN = "SHUT DOWN|STALL|BRAKE|FIRE|ACCELERAT"


def main():
    total_rows = 0
    hk_total = 0
    year_dist = {}
    make_dist = {}
    filtered_chunks = []

    print("=== NHTSA 불만 데이터 스캔 시작 ===")
    print(f"입력: {RAW_FILE}\n")

    chunk_num = 0
    for chunk in pd.read_csv(
        RAW_FILE,
        sep="\t",
        header=None,
        names=COLS,
        dtype=str,
        encoding="latin-1",
        quoting=csv.QUOTE_NONE,
        on_bad_lines="skip",
        chunksize=CHUNK_SIZE,
    ):
        chunk_num += 1
        total_rows += len(chunk)

        # 접수연도 통계
        year_vals = chunk["LDATE"].str[:4].fillna("UNKNOWN")
        for yr, cnt in year_vals.value_counts().items():
            year_dist[yr] = year_dist.get(yr, 0) + int(cnt)

        # 제조사 통계
        make_upper = chunk["MAKETXT"].str.upper().fillna("")
        for mk, cnt in make_upper.value_counts().items():
            make_dist[mk] = make_dist.get(mk, 0) + int(cnt)

        # 현대·기아 마스크
        hk_mask = make_upper.isin(TARGET_MAKES)
        hk_total += int(hk_mask.sum())

        # 날짜 마스크 (2022년 이상)
        date_mask = year_vals >= "2022"

        # COMPDESC 접두어 마스크
        comp_mask = chunk["COMPDESC"].str.upper().str.match(COMP_PATTERN, na=False)

        filtered = chunk[hk_mask & date_mask & comp_mask].copy()
        if len(filtered):
            filtered_chunks.append(filtered)

        print(f"  chunk {chunk_num:>3} done -- total {total_rows:>10,} rows  (HK hits: {hk_total:,})")

    print(f"\n스캔 완료: 총 {total_rows:,}행\n")

    # ── 필터 결과 결합 ──────────────────────────────────────
    df = (
        pd.concat(filtered_chunks, ignore_index=True)
        if filtered_chunks
        else pd.DataFrame(columns=COLS)
    )
    work_rows = len(df)

    # ── 출력 1: 작업셋 전체 ────────────────────────────────
    out_full = os.path.join(PROC_DIR, "hk_electrical_recent_full.csv")
    df.to_csv(out_full, index=False, encoding="utf-8-sig")

    # ── 출력 2: 회의용 샘플 100 (핵심 컬럼, random_state=42) ─
    df_s100 = (
        df[KEY_COLS].sample(n=min(100, work_rows), random_state=42)
        if work_rows > 0
        else df[KEY_COLS]
    )
    out_s100 = os.path.join(SAMP_DIR, "sample_100_for_meeting.csv")
    df_s100.to_csv(out_s100, index=False, encoding="utf-8-sig")

    # ── 출력 3: LLM 테스트용 샘플 20 (CDESCR >= 200자) ──────
    cdescr_len = df["CDESCR"].fillna("").str.len()
    df_long = df[cdescr_len >= 200]
    df_s20 = (
        df_long[KEY_COLS].sample(n=min(20, len(df_long)), random_state=42)
        if len(df_long) > 0
        else df_long[KEY_COLS]
    )
    out_s20 = os.path.join(SAMP_DIR, "sample_20_for_llm_test.csv")
    df_s20.to_csv(out_s20, index=False, encoding="utf-8-sig")

    # ── 출력 4: evidence_unknown_but_dangerous ───────────────
    unk_mask = df["COMPDESC"].str.upper().str.startswith("UNKNOWN OR OTHER", na=False)
    df_unk = df[unk_mask]

    injured_num = pd.to_numeric(df_unk["INJURED"], errors="coerce").fillna(0)
    danger_mask = (
        (df_unk["CRASH"] == "Y")
        | (df_unk["FIRE"] == "Y")
        | (injured_num > 0)
        | df_unk["CDESCR"].str.upper().str.contains(DANGER_PATTERN, na=False)
    )
    df_evidence = df_unk[danger_mask].copy()
    out_ev = os.path.join(PROC_DIR, "evidence_unknown_but_dangerous.csv")
    df_evidence.to_csv(out_ev, index=False, encoding="utf-8-sig")

    # ── 콘솔 요약 ────────────────────────────────────────────
    sep = "=" * 62
    print(sep)
    print("결과 요약")
    print(sep)
    print(f"전체 행 수          : {total_rows:>10,}")
    print(f"현대·기아 건수      : {hk_total:>10,}")
    print(f"작업 데이터셋 건수  : {work_rows:>10,}  (HK x 전장/SW x 2022~)")

    print("\n--- 부품 카테고리 분포 ---")
    cat_dist = (
        df["COMPDESC"].str.upper()
        .str.split(":").str[0]
        .str.strip()
        .value_counts()
    )
    for cat, cnt in cat_dist.items():
        print(f"  {cat:<52} {cnt:>6,}")

    print("\n--- 차종 상위 10 ---")
    for model, cnt in df["MODELTXT"].str.upper().value_counts().head(10).items():
        print(f"  {model:<30} {cnt:>6,}")

    print("\n--- 심각도 플래그 ---")
    inj = pd.to_numeric(df["INJURED"], errors="coerce").fillna(0)
    dth = pd.to_numeric(df["DEATHS"], errors="coerce").fillna(0)
    print(f"  CRASH=Y   : {(df['CRASH'] == 'Y').sum():>6,}")
    print(f"  FIRE=Y    : {(df['FIRE']  == 'Y').sum():>6,}")
    print(f"  INJURED>0 : {(inj > 0).sum():>6,}")
    print(f"  DEATHS>0  : {(dth > 0).sum():>6,}")

    print("\n--- evidence_unknown_but_dangerous ---")
    print(f"  UNKNOWN OR OTHER 전체  : {len(df_unk):>6,}")
    print(f"  위험 조건 해당         : {len(df_evidence):>6,}")

    print("\n--- LDATE 날짜 범위 ---")
    dates = pd.to_datetime(df["LDATE"], format="%Y%m%d", errors="coerce")
    if not dates.isna().all():
        print(f"  최소: {dates.min().date()}")
        print(f"  최대: {dates.max().date()}")
    else:
        print("  날짜 파싱 불가")

    print("\n--- 주요 컬럼 NULL 비율 ---")
    for col in ["CDESCR", "COMPDESC", "LDATE", "MAKETXT", "INJURED"]:
        pct = df[col].isnull().mean() * 100
        print(f"  {col:<15}: {pct:.1f}%")

    print("\n--- 접수연도 분포 (상위 10, 전체 데이터 기준) ---")
    for yr, cnt in sorted(year_dist.items(), key=lambda x: -x[1])[:10]:
        print(f"  {yr}  {cnt:>10,}")

    print("\n--- 출력 파일 ---")
    for p in [out_full, out_s100, out_s20, out_ev]:
        size_kb = os.path.getsize(p) / 1024
        print(f"  {os.path.basename(p):<45} {size_kb:8.1f} KB")


if __name__ == "__main__":
    main()
