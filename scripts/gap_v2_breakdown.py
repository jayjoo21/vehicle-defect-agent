#!/usr/bin/env python3
"""
gap_v2_breakdown.py
kr_us_gap_v2.csv의 KOTSA 기반 76건 분해 분석
① |시차| > 365일 오매칭 가드
② 미국 접수연도 × SW관련 × 분류 교차표
③ 한국선행 -90일 이상 상위 5건 상세
④ data/processed/kr_us_gap_v2_breakdown.csv 저장
"""
import pandas as pd
from pathlib import Path

IN    = Path("data/processed/kr_us_gap_v2.csv")
OUT   = Path("data/processed/kr_us_gap_v2_breakdown.csv")

KOTSA_BASE = "KOTSA리콜개시일"  # KOTSA리콜개시일
GUARD_DAYS = 365

# ── 로드 & KOTSA 행만 추출 ────────────────────────────────────────
df_all = pd.read_csv(IN, encoding="utf-8-sig", dtype=str)
df = df_all[df_all["date_basis"] == KOTSA_BASE].copy()
print(f"KOTSA 기반 행: {len(df)}건")   # "KOTSA 기반 행: N건"

df["시차_일"] = pd.to_numeric(df["시차_일"], errors="coerce")   # 시차_일
df["미국_접수일"] = pd.to_datetime(df["미국_접수일"], errors="coerce")  # 미국_접수일

# ── ① 오매칭 가드 적용 ───────────────────────────────────────────
before_counts = df["분류"].value_counts()

mask_suspect = df["시차_일"].abs() > GUARD_DAYS
df.loc[mask_suspect, "분류"] = "오매칭의심"  # "오매칭의심"

after_counts = df["분류"].value_counts()

n_suspect = mask_suspect.sum()
print(f"\n■ ±{GUARD_DAYS}일 초과 오매칭 의심: {n_suspect}건")  # "■ ±365일 초과 오매칭 의심: N건"
print("가드 전:")   # "가드 전:"
print(before_counts.to_string())
print("가드 후:")   # "가드 후:"
print(after_counts.to_string())

# 의심 건 목록
if n_suspect:
    suspect_cols = ["미국_캔페인번호", "제조사",
                    "모델_영문", "미국_접수일",
                    "한국_발표일", "시차_일"]
    # use actual column names present in df
    suspect_show = [c for c in suspect_cols if c in df.columns]
    print("\n[오매칭 의심 목록]")   # "[오매칭 의심 목록]"
    print(df[mask_suspect][suspect_show].to_string(index=False))

# ── ② 연도 × SW관련 × 분류 교차표 ────────────────────────────────
df["접수연도"] = df["미국_접수일"].dt.year.astype("Int64")  # 접수연도

# sw관련_한국: CSV에서 문자열 "True"/"False" 또는 bool
def to_bool(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "yes")

df["sw_bool"] = df["sw관련_한국"].apply(to_bool)  # sw관련_한국
df["SW관련"] = df["sw_bool"].map({True: "SW관련O", False: "SW관련X"})  # SW관련

# 가드 후 실제 매칭만 (오매칭의심 제외)
df_valid = df[df["분류"] != "오매칭의심"].copy()  # 분류 != 오매칭의심
df_valid_yrng = df_valid[df_valid["접수연도"].between(2020, 2025)]

pivot = (
    df_valid_yrng
    .groupby(["접수연도", "SW관련", "분류"])
    .size()
    .reset_index(name="건수")   # 건수
)

cross = pivot.pivot_table(
    index=["접수연도", "SW관련"],
    columns="분류",
    values="건수",
    fill_value=0
)

print(f"\n■ 미국 접수연도(2020-2025) × SW관련 × 분류 교차표")
# "■ 미국 접수연도(2020-2025) × SW관련 × 분류 교차표"
print(cross.to_string())

# 소계 행 추가
col_totals = cross.sum(axis=0)
col_totals.name = ("합계", "")   # 합계
cross_with_total = pd.concat([cross, col_totals.to_frame().T])
print(f"\n합계 (2020-2025):")   # "합계 (2020-2025):"
print(col_totals.to_string())

# ── ③ 한국선행 -90일 이상 상위 5건 ───────────────────────────────
kr_first = df_valid[
    (df_valid["분류"] == "한국선행") &   # 분류 == "한국선행"
    (df_valid["시차_일"] <= -90)
].sort_values("시차_일").head(5)  # 시차_일 오름차순

detail_cols = [
    "미국_캔페인번호",   # 미국_캠페인번호
    "제조사",                                # 제조사
    "모델_영문",                       # 모델_영문
    "미국_접수일",                # 미국_접수일
    "한국_발표일",                # 한국_발표일
    "시차_일",                              # 시차_일
    "한국_차종_원문",         # 한국_차종_원문
    "한국_원인",                       # 한국_원인
    "sw_bool",
]
detail_show = [c for c in detail_cols if c in kr_first.columns]

print(f"\n■ 한국선행 -90일 이상 상위 5건 (홈마켓 가설 눈검증용)")
# "■ 한국선행 -90일 이상 상위 5건 (홈마켓 가설 눈검증용)"
for _, r in kr_first.iterrows():
    print(f"\n  {r.get('미국_캔페인번호','')} | "
          f"{r.get('제조사','')} {r.get('모델_영문','')} | "
          f"미국 {str(r.get('미국_접수일',''))[:10]} | "
          f"한국 {str(r.get('한국_발표일',''))[:10]} | "
          f"시차 {r.get('시차_일','')}d | "
          f"SW={r.get('sw_bool','')} | "
          f"원인: {str(r.get('한국_원인',''))[:60]}")
    # "미국 | 한국 | 시차 | 원인"

# ── ④ 산출물 저장 ─────────────────────────────────────────────────
# 가드 적용된 분류 컬럼을 붙인 전체 KOTSA 행 저장
out_cols = [c for c in df.columns if c != "sw_bool" and c != "SW관련" and c != "접수연도"]
df[out_cols].to_csv(OUT, index=False, encoding="utf-8-sig")
print(f"\n[OK] {OUT} 저장 ({len(df)}행)")   # "저장 (N행)"
