"""
라벨 정제 후 정밀도 재계산 (Task 10).

① 차종명 정규화: HYBRID/PLUG-IN HYBRID/PLUG-IN/PHEV/ELECTRIC 접미어를 제거한
   base_model로 통일 후 b1 발화 67건의 리콜연계 여부·정밀도 재계산
② 우측 절단: 발화월 >= 2025-07(관측기간 12개월 미만, 데이터 종료 2026-06 기준)인 건은
   "관측기간 부족"으로 분리, 정밀도 분모에서 제외한 값을 병기
③ 집중도 표본 10건의 그룹(리콜연계/비리콜)이 base_model 적용으로 바뀌는지 확인

입력: data/processed/b1_signals.csv, data/recalls/recalls_hk_by_vehicle.csv,
      data/processed/concentration_sample.csv
출력: data/processed/precision_v2.csv (발화 67건 상세)
"""
import re

import pandas as pd

SIGNALS_PATH = "data/processed/b1_signals.csv"
RECALL_PAIRS_PATH = "data/recalls/recalls_hk_by_vehicle.csv"
SAMPLE_PATH = "data/processed/concentration_sample.csv"
OUT_PATH = "data/processed/precision_v2.csv"

PRECISION_HORIZON_MONTHS = 12
DATA_END = pd.Timestamp("2026-06-30")
CENSOR_CUTOFF_MONTH = pd.Period("2025-07", freq="M")

SUFFIXES = ["PLUG-IN HYBRID", "PLUG-IN", "HYBRID", "PHEV", "ELECTRIC"]


def normalize_model(model):
    m = model.strip().upper()
    changed = True
    while changed:
        changed = False
        for suf in SUFFIXES:
            pattern = r"\s+" + re.escape(suf) + r"$"
            new_m = re.sub(pattern, "", m)
            if new_m != m:
                m = new_m
                changed = True
    return m


def load_signals():
    s = pd.read_csv(SIGNALS_PATH, encoding="utf-8-sig", dtype=str)
    s["month"] = pd.PeriodIndex(s["month"], freq="M")
    s["count"] = s["count"].astype(int)
    s["signal"] = s["signal"].map({"True": True, "False": False})
    s["base_model"] = s["model"].map(normalize_model)
    return s


def load_recall_pairs():
    r = pd.read_csv(RECALL_PAIRS_PATH, encoding="utf-8-sig", dtype=str)
    r["model"] = r["Model"].str.strip().str.upper()
    r["base_model"] = r["model"].map(normalize_model)
    r["recall_date"] = pd.to_datetime(r["report_date_iso"])
    r = r.drop_duplicates(subset=["NHTSACampaignNumber", "base_model", "recall_date"])
    return r


def main():
    signals = load_signals()
    recall_pairs = load_recall_pairs()

    changed_models = sorted(set(
        (m, b) for m, b in zip(signals["model"], signals["base_model"]) if m != b
    ))
    print("=== base_model 정규화로 이름이 바뀐 차종 ===")
    for m, b in changed_models:
        print(f"  {m} -> {b}")

    fired = signals[signals["signal"]].copy()
    rows = []
    for row in fired.itertuples():
        window_start = row.month.end_time.normalize()
        window_end_full = window_start + pd.DateOffset(months=PRECISION_HORIZON_MONTHS)
        censored = window_end_full > DATA_END
        observed_end = min(window_end_full, DATA_END)

        matches_raw = recall_pairs[
            (recall_pairs["model"] == row.model)
            & (recall_pairs["recall_date"] > window_start)
            & (recall_pairs["recall_date"] <= window_end_full)
        ]
        matches_base_observed = recall_pairs[
            (recall_pairs["base_model"] == row.base_model)
            & (recall_pairs["recall_date"] > window_start)
            & (recall_pairs["recall_date"] <= observed_end)
        ]
        matches_base_full = recall_pairs[
            (recall_pairs["base_model"] == row.base_model)
            & (recall_pairs["recall_date"] > window_start)
            & (recall_pairs["recall_date"] <= window_end_full)
        ]

        rows.append({
            "model": row.model, "base_model": row.base_model, "month": str(row.month),
            "count": row.count,
            "hit_raw_v1": len(matches_raw) > 0,
            "hit_base_observed": len(matches_base_observed) > 0,
            "hit_base_full_window": len(matches_base_full) > 0,
            "censored": censored,
        })

    out = pd.DataFrame(rows)
    out.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")

    n = len(out)
    hits_v1 = out["hit_raw_v1"].sum()
    hits_v2_all = out["hit_base_observed"].sum()
    print(f"\n=== 정밀도 재계산 (발화 {n}건) ===")
    print(f"v1 (원 모델명, 전체 67건 분모): {hits_v1}/{n} = {hits_v1/n:.4f}")
    print(f"v2 (base_model 정규화, 전체 67건 분모, 관측가능분까지): {hits_v2_all}/{n} = {hits_v2_all/n:.4f}")

    flipped = out[out["hit_raw_v1"] != out["hit_base_observed"]]
    print(f"\n=== base_model 정규화로 hit 판정이 바뀐 발화 ({len(flipped)}건) ===")
    print(flipped[["model", "base_model", "month", "hit_raw_v1", "hit_base_observed", "censored"]].to_string(index=False))

    non_censored = out[~out["censored"]]
    censored = out[out["censored"]]
    hits_nc = non_censored["hit_base_observed"].sum()
    print(f"\n=== 우측 절단 분리 (기준: 발화월 >= {CENSOR_CUTOFF_MONTH}, 데이터 종료 {DATA_END.date()}) ===")
    print(f"관측기간 충족 (censored=False): {len(non_censored)}건, hit={hits_nc} -> 정밀도 {hits_nc/len(non_censored):.4f}")
    print(f"관측기간 부족 (censored=True, 분모 제외): {len(censored)}건, 그중 관측된 조기 hit={censored['hit_base_observed'].sum()}건")
    if len(censored):
        print(censored[["model", "base_model", "month", "hit_base_observed"]].to_string(index=False))

    # ③ 집중도 표본 10건 그룹 재확인
    sample = pd.read_csv(SAMPLE_PATH, encoding="utf-8-sig", dtype=str)
    sample["hit"] = sample["hit"].map({"True": True, "False": False})
    merged = sample.merge(out, on=["model", "month"], how="left")
    print("\n=== 집중도 표본 10건: base_model 정규화 후 그룹(hit) 변화 확인 ===")
    print(merged[["model", "month", "group", "hit", "hit_base_observed", "censored"]].to_string(index=False))
    flips_in_sample = merged[merged["hit"] != merged["hit_base_observed"]]
    if len(flips_in_sample):
        print(f"\n표본 내 그룹 라벨 변경: {len(flips_in_sample)}건")
        print(flips_in_sample[["model", "month", "group", "hit", "hit_base_observed"]].to_string(index=False))
    else:
        print("\n표본 10건 중 base_model 정규화로 그룹(hit)이 바뀐 건 없음 -> 집중도 그룹 비교 결과는 그대로 유지")

    print(f"\nsaved -> {OUT_PATH}")


if __name__ == "__main__":
    main()
