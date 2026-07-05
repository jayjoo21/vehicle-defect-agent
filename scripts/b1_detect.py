"""
B1 감지 baseline: 차종×월 불만 건수 급증 규칙 기반 시그널 탐지.
이것은 개선 대상 baseline이므로 로직을 의도적으로 단순하게 유지한다.

규칙: 해당 월 건수 >= 직전 6개월 평균 * 2  AND  해당 월 건수 >= 10  ->  시그널 발화

입력: data/processed/hk_electrical_recent_full.csv
출력: data/processed/b1_signals.csv (model, month, count, baseline_avg6, signal)
"""
import pandas as pd

IN_PATH = "data/processed/hk_electrical_recent_full.csv"
OUT_PATH = "data/processed/b1_signals.csv"
START_MONTH = "2022-07"
END_MONTH = "2026-06"
MIN_ABS_COUNT = 10
SPIKE_MULT = 2


def load_monthly_counts(path):
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, usecols=["MODELTXT", "LDATE"])
    df["model"] = df["MODELTXT"].str.strip().str.upper()
    df["month"] = pd.to_datetime(df["LDATE"], format="%Y%m%d").dt.to_period("M")
    counts = df.groupby(["model", "month"]).size().rename("count").reset_index()
    return counts


def build_full_grid(counts):
    all_months = pd.period_range(counts["month"].min(), counts["month"].max(), freq="M")
    all_models = counts["model"].unique()
    grid = pd.MultiIndex.from_product([all_models, all_months], names=["model", "month"]).to_frame(index=False)
    merged = grid.merge(counts, on=["model", "month"], how="left")
    merged["count"] = merged["count"].fillna(0).astype(int)
    return merged.sort_values(["model", "month"]).reset_index(drop=True)


def detect_signals(grid):
    grid["baseline_avg6"] = (
        grid.groupby("model")["count"]
        .transform(lambda s: s.shift(1).rolling(6, min_periods=1).mean())
    )
    grid["signal"] = (
        (grid["count"] >= grid["baseline_avg6"] * SPIKE_MULT)
        & (grid["count"] >= MIN_ABS_COUNT)
        & grid["baseline_avg6"].notna()
    )
    return grid


def main():
    counts = load_monthly_counts(IN_PATH)
    grid = build_full_grid(counts)
    grid = detect_signals(grid)

    out = grid[(grid["month"] >= START_MONTH) & (grid["month"] <= END_MONTH)].copy()
    out["month"] = out["month"].astype(str)
    out = out[["model", "month", "count", "baseline_avg6", "signal"]]
    out.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")

    n_signals = out["signal"].sum()
    n_months = out["month"].nunique()
    print(f"rows={len(out)} models={out['model'].nunique()} months={n_months}")
    print(f"total signals={n_signals} avg signals/month={n_signals / n_months:.2f}")
    print(f"saved -> {OUT_PATH}")


if __name__ == "__main__":
    main()
