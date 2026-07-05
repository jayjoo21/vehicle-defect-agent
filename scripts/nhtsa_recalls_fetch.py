import csv
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "data", "recalls")
os.makedirs(OUT_DIR, exist_ok=True)

YEARS = range(2020, 2027)  # 2020~2026 연식

MODELS = {
    "HYUNDAI": [
        "TUCSON", "SANTA FE", "ELANTRA", "SONATA", "PALISADE", "KONA",
        "VENUE", "SANTA CRUZ", "IONIQ 5", "IONIQ 6", "NEXO", "ACCENT",
        "KONA ELECTRIC", "IONIQ", "VELOSTER",
    ],
    "KIA": [
        "SPORTAGE", "SORENTO", "TELLURIDE", "K5", "FORTE", "SOUL",
        "SELTOS", "CARNIVAL", "EV6", "EV9", "NIRO", "STINGER", "RIO",
        "NIRO EV", "OPTIMA",
    ],
}

# Component 또는 Summary에 등장하면 SW/전장 후보로 분류
SW_KEYWORDS = [
    "SOFTWARE", "ELECTRICAL", "ELECTRONIC", "INSTRUMENT PANEL", "CLUSTER",
    "DISPLAY", "CAMERA", "ICCU", "CHARGER", "BATTERY MANAGEMENT", "BMS",
    "CONTROL UNIT", "CONTROL MODULE", "ECU", "FIRMWARE", "OTA",
]

BASE_URL = "https://api.nhtsa.gov/recalls/recallsByVehicle"
CAMP_COL = "NHTSACampaignNumber"

rows = []
zero_models = []

print("=== NHTSA 리콜 수집 시작 ===")
for make, models in MODELS.items():
    for model in models:
        model_hits = 0
        for year in YEARS:
            try:
                r = requests.get(
                    BASE_URL,
                    params={"make": make, "model": model, "modelYear": year},
                    timeout=15,
                )
                for item in r.json().get("results", []):
                    item["_query_make"] = make
                    item["_query_model"] = model
                    item["_query_year"] = year
                    rows.append(item)
                    model_hits += 1
            except Exception as e:
                print(f"  실패: {make} {model} {year} -> {e}")
            time.sleep(0.3)
        print(f"  {make:<8} {model:<20} {model_hits:>4}건")
        if model_hits == 0:
            zero_models.append(f"{make} {model}")

if not rows:
    print("수집 결과 0건 -- 네트워크 또는 파라미터 확인 필요")
    raise SystemExit(1)

df = pd.DataFrame(rows)

# ReportReceivedDate (DD/MM/YYYY) -> ISO YYYY-MM-DD 정규화
# 불만 데이터 LDATE (YYYYMMDD)와 비교하려면 ISO로 통일해야 함
df["report_date_iso"] = pd.to_datetime(
    df["ReportReceivedDate"], dayfirst=True, errors="coerce"
).dt.strftime("%Y-%m-%d")

# ── 출력 1: 차종·연식 단위 전체 ────────────────────────────────
out_by_vehicle = os.path.join(OUT_DIR, "recalls_hk_by_vehicle.csv")
df.to_csv(out_by_vehicle, index=False, encoding="utf-8-sig")

# ── 출력 2: 캠페인 기준 dedupe (NHTSACampaignNumber 고유값) ────
# 같은 캠페인이 여러 차종·연식에 중복 → 캠페인 단위로 1건만 유지
if CAMP_COL in df.columns:
    df_campaigns = (
        df.sort_values("report_date_iso")
        .drop_duplicates(subset=[CAMP_COL], keep="first")
        .reset_index(drop=True)
    )
else:
    print(f"경고: {CAMP_COL} 컬럼 없음 -- 실제 컬럼: {list(df.columns)}")
    df_campaigns = df.copy()

out_campaigns = os.path.join(OUT_DIR, "recalls_hk_campaigns.csv")
df_campaigns.to_csv(out_campaigns, index=False, encoding="utf-8-sig")

# ── 출력 3: SW/전장 후보 ───────────────────────────────────────
text = (
    df_campaigns.get("Component", pd.Series(dtype=str)).fillna("") + " " +
    df_campaigns.get("Summary", pd.Series(dtype=str)).fillna("")
).str.upper()
sw_mask = text.apply(lambda t: any(kw in t for kw in SW_KEYWORDS))
df_sw = df_campaigns[sw_mask].copy()

out_sw = os.path.join(OUT_DIR, "recalls_sw_candidates.csv")
df_sw.to_csv(out_sw, index=False, encoding="utf-8-sig")

# ── 콘솔 요약 ─────────────────────────────────────────────────
sep = "=" * 62
print(f"\n{sep}")
print("결과 요약")
print(sep)
print(f"차종·연식 단위 레코드     : {len(df):>6,} 건")
print(f"고유 캠페인 수            : {len(df_campaigns):>6,} 건")
print(f"SW/전장 후보 캠페인 수    : {len(df_sw):>6,} 건")

if "Component" in df_campaigns.columns:
    print("\n--- 부품 카테고리 상위 10 ---")
    for comp, cnt in df_campaigns["Component"].value_counts().head(10).items():
        print(f"  {str(comp)[:55]:<55} {cnt:>4,}")

print(f"\n--- SW/전장 후보 목록 (접수일 최근순) ---")
if len(df_sw):
    view = df_sw.sort_values("report_date_iso", ascending=False)
    for _, row in view.iterrows():
        camp = row.get(CAMP_COL, "?")
        date = row.get("report_date_iso", "?")
        make = row.get("_query_make", "")
        model = row.get("_query_model", "")
        comp = str(row.get("Component", ""))[:50]
        ota = "OTA" if row.get("overTheAirUpdate") else "   "
        print(f"  [{date}] {ota} {camp}  {make} {model:<18} {comp}")
else:
    print("  (없음)")

if zero_models:
    print(f"\n[확인] 리콜 0건 모델 (모델명 오타 또는 실제 무리콜):")
    for m in zero_models:
        print(f"  {m}")

print(f"\n--- 검증: 26V400000·26V316000 포함 여부 ---")
for target in ["26V400000", "26V316000"]:
    found = target in df_sw[CAMP_COL].values if CAMP_COL in df_sw.columns else False
    status = "OK" if found else "MISSING"
    print(f"  {target} : {status}")

print("\n--- 출력 파일 ---")
for p in [out_by_vehicle, out_campaigns, out_sw]:
    size_kb = os.path.getsize(p) / 1024
    print(f"  {os.path.basename(p):<45} {size_kb:7.1f} KB")

print("\n--- 날짜 범위 (캠페인 기준) ---")
dates = pd.to_datetime(df_campaigns["report_date_iso"], errors="coerce")
if not dates.isna().all():
    print(f"  최소: {dates.min().date()}")
    print(f"  최대: {dates.max().date()}")

print("\n--- NULL 비율 (캠페인 기준) ---")
for col in ["Component", "Summary", "ReportReceivedDate", "report_date_iso", CAMP_COL]:
    if col in df_campaigns.columns:
        pct = df_campaigns[col].isnull().mean() * 100
        print(f"  {col:<30}: {pct:.1f}%")
