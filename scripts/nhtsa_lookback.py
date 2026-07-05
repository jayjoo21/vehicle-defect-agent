import os
import re
import sys
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SW_FILE      = os.path.join(BASE_DIR, "data", "recalls",   "recalls_sw_candidates.csv")
VEHICLE_FILE = os.path.join(BASE_DIR, "data", "recalls",   "recalls_hk_by_vehicle.csv")
CMPL_FILE    = os.path.join(BASE_DIR, "data", "processed", "hk_electrical_recent_full.csv")
OUT_FILE     = os.path.join(BASE_DIR, "data", "processed", "lookback_candidates.csv")

MONTHS_BACK = 12
EARLY_N     = 9   # 이전 9개월 (비율 분모)
RECENT_N    = 3   # 직전 3개월 (비율 분자)
CAMP_COL    = "NHTSACampaignNumber"

# m_minus_12 = 리콜 12개월 전 (가장 오래된), m_minus_01 = 리콜 직전 달
MONTH_COLS = [f"m_minus_{i:02d}" for i in range(MONTHS_BACK, 0, -1)]

# ── 데이터 로드 ──────────────────────────────────────────────
sw     = pd.read_csv(SW_FILE,      dtype=str, encoding="utf-8-sig")
by_veh = pd.read_csv(VEHICLE_FILE, dtype=str, encoding="utf-8-sig")
cmpl   = pd.read_csv(CMPL_FILE,    dtype=str, encoding="utf-8-sig")

print("=== 되감기 분석 시작 ===")
print(f"SW 후보 캠페인 : {len(sw):>4}건")
print(f"차종별 리콜    : {len(by_veh):>4}건")
print(f"불만 작업셋    : {len(cmpl):>4}건\n")

cmpl["ldate_dt"] = pd.to_datetime(cmpl["LDATE"], format="%Y%m%d", errors="coerce")

# 캠페인 -> [(make, model)] 다중 매핑
# 동일 캠페인이 TUCSON, SANTA CRUZ 등 여러 모델을 커버하는 경우 전부 포함
camp_models: dict = defaultdict(list)
for _, r in (
    by_veh[[CAMP_COL, "_query_make", "_query_model"]]
    .drop_duplicates()
    .iterrows()
):
    mk  = str(r["_query_make"]).strip().upper()
    mdl = str(r["_query_model"]).strip().upper()
    if mk and mdl and mk != "NAN" and mdl != "NAN":
        camp_models[r[CAMP_COL]].append((mk, mdl))

# ── 캠페인별 되감기 집계 ─────────────────────────────────────
rows_out = []

for _, camp in sw.iterrows():
    camp_num  = camp[CAMP_COL]
    recall_dt = pd.Timestamp(camp["report_date_iso"])
    window_start = recall_dt - pd.DateOffset(months=MONTHS_BACK)

    # 기간 부족: 작업셋(2022~)으로 12개월 확보 불가
    insufficient = recall_dt.year < 2023

    pairs = camp_models.get(camp_num, [])
    if not pairs:
        mk  = str(camp.get("_query_make", "")).strip().upper()
        mdl = str(camp.get("_query_model", "")).strip().upper()
        if mk and mdl and mk != "NAN" and mdl != "NAN":
            pairs = [(mk, mdl)]

    # 날짜 마스크: [recall_dt - 12개월, recall_dt)
    date_mask = (cmpl["ldate_dt"] >= window_start) & (cmpl["ldate_dt"] < recall_dt)

    # 차종 마스크: MAKETXT 일치 AND MODELTXT contains 모델명 (부분 일치)
    # 예: _query_model="TUCSON" -> "TUCSON HYBRID", "TUCSON PHEV" 등 커버
    veh_mask   = pd.Series(False, index=cmpl.index)
    makes_used = set()
    models_used = set()
    for mk, mdl in pairs:
        makes_used.add(mk)
        models_used.add(mdl)
        mk_mask  = cmpl["MAKETXT"].str.upper() == mk
        mdl_mask = cmpl["MODELTXT"].str.upper().str.contains(
            re.escape(mdl), na=False
        )
        veh_mask |= (mk_mask & mdl_mask)

    sub = cmpl[date_mask & veh_mask]
    sub_periods = sub["ldate_dt"].dt.to_period("M")

    # 12개 월별 버킷 (m_minus_12 = oldest, m_minus_01 = most recent)
    counts = []
    for i in range(MONTHS_BACK, 0, -1):
        period = (recall_dt - pd.DateOffset(months=i)).to_period("M")
        counts.append(int((sub_periods == period).sum()))

    # 증가비율: 직전 3개월 평균 / 이전 9개월 평균
    early_avg  = sum(counts[:EARLY_N])  / EARLY_N
    recent_avg = sum(counts[EARLY_N:])  / RECENT_N

    if early_avg > 0:
        ratio = round(recent_avg / early_avg, 3)
    elif recent_avg > 0:
        ratio = None  # 분모 0 / 분자 양수: 급등이지만 수치 미정의
    else:
        ratio = 0.0   # 둘 다 0

    row = {
        CAMP_COL:            camp_num,
        "make":              ", ".join(sorted(makes_used)),
        "model":             ", ".join(sorted(models_used)),
        "report_date_iso":   camp["report_date_iso"],
        "Component":         camp.get("Component", ""),
        "overTheAirUpdate":  camp.get("overTheAirUpdate", ""),
        "total_12m":         sum(counts),
        "recent_3m_avg":     round(recent_avg, 2),
        "early_9m_avg":      round(early_avg, 2),
        "increase_ratio":    ratio,
        "insufficient_data": insufficient,
    }
    for col, cnt in zip(MONTH_COLS, counts):
        row[col] = cnt
    rows_out.append(row)

# ── 저장 ─────────────────────────────────────────────────────
col_order = (
    [CAMP_COL, "make", "model", "report_date_iso", "Component",
     "overTheAirUpdate", "total_12m", "recent_3m_avg", "early_9m_avg",
     "increase_ratio", "insufficient_data"]
    + MONTH_COLS
)
df_out = pd.DataFrame(rows_out)[col_order]
df_out.to_csv(OUT_FILE, index=False, encoding="utf-8-sig")

# ── 콘솔 보고 ────────────────────────────────────────────────
sep = "=" * 70
print(sep)
print("결과 요약")
print(sep)
valid_ratio = df_out["increase_ratio"].notna()
print(f"전체 캠페인        : {len(df_out):>4}건")
print(f"기간 부족(<2023)   : {df_out['insufficient_data'].sum():>4}건")
print(f"12m 불만 1건 이상  : {(df_out['total_12m'] > 0).sum():>4}건")
print(f"증가비율 산출 가능 : {valid_ratio.sum():>4}건")

print("\n--- 증가비율 상위 10 캠페인 ---")
print(f"  {'캠페인번호':<12} {'날짜':<12} {'make':<8} {'모델':<20}  {'ratio':>5}  "
      f"[이전 9개월: m-12..m-04]  [직전 3개월: m-03..m-01]")
print("  " + "-" * 115)

top10 = (
    df_out[valid_ratio & (df_out["increase_ratio"] > 0)]
    .sort_values("increase_ratio", ascending=False)
    .head(10)
)
for _, row in top10.iterrows():
    early_str  = " ".join(f"{int(row[c]):>3}" for c in MONTH_COLS[:EARLY_N])
    recent_str = " ".join(f"{int(row[c]):>3}" for c in MONTH_COLS[EARLY_N:])
    mdl = row["model"][:19]
    mk  = row["make"][:7]
    ota = " OTA" if str(row.get("overTheAirUpdate", "")).lower() == "true" else "    "
    insuf = "[부족]" if row["insufficient_data"] else "      "
    print(
        f"  {row[CAMP_COL]:<12} {row['report_date_iso']:<12} {mk:<8} {mdl:<20} "
        f"{float(row['increase_ratio']):>5.2f}x{ota}{insuf}  "
        f"{early_str}  |  {recent_str}"
    )

print(f"\n--- 불만 0건 캠페인 ({(df_out['total_12m'] == 0).sum()}건, 실패 분석 재료) ---")
zero = df_out[df_out["total_12m"] == 0].sort_values("report_date_iso", ascending=False)
for _, row in zero.iterrows():
    flag = "[기간부족]" if row["insufficient_data"] else "[기간충분]"
    comp = str(row["Component"])[:45]
    print(f"  {flag} {row[CAMP_COL]}  {row['make']:<8} {row['model'][:25]:<25}  "
          f"{row['report_date_iso']}  {comp}")

print(f"\n--- 검증: 26V400000·26V316000 ---")
for target in ["26V400000", "26V316000"]:
    rows_v = df_out[df_out[CAMP_COL] == target]
    if len(rows_v):
        r = rows_v.iloc[0]
        counts_str = " ".join(f"{int(r[c]):>3}" for c in MONTH_COLS)
        print(f"  {target}: total_12m={r['total_12m']}  ratio={r['increase_ratio']}  "
              f"insuf={r['insufficient_data']}")
        print(f"    월별: {counts_str}")
    else:
        print(f"  {target}: NOT FOUND")

print(f"\n--- 출력 파일 ---")
sz = os.path.getsize(OUT_FILE) / 1024
print(f"  {os.path.basename(OUT_FILE)}  {sz:.1f} KB  ({len(df_out)}행 x {len(col_order)}열)")
