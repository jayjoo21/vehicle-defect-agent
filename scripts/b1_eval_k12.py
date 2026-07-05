"""
K12 되감기 평가: B1 baseline이 실제 리콜 발표 이전에 시그널을 발화했는지 채점.

방법: 캠페인의 컷오프(report_date_iso) 이전 12개월 내에, 해당 캠페인의 차종 중
하나라도 B1 시그널이 발화했으면 "포착"으로 간주. 최초 발화월의 월말일을 탐지
시점으로 보고 컷오프까지의 선행일수를 계산한다 (월 집계 기반이라 그 달이
끝나야 카운트를 알 수 있다는 전제).

입력: docs/k12_list.csv, data/recalls/recalls_hk_by_vehicle.csv, data/processed/b1_signals.csv
출력: data/processed/b1_eval_k12.csv
"""
import pandas as pd

K12_PATH = "docs/k12_list.csv"
RECALLS_PATH = "data/recalls/recalls_hk_by_vehicle.csv"
SIGNALS_PATH = "data/processed/b1_signals.csv"
OUT_PATH = "data/processed/b1_eval_k12.csv"
LOOKBACK_MONTHS = 12


def load_campaign_models():
    df = pd.read_csv(RECALLS_PATH, encoding="utf-8-sig", dtype=str)
    df["model"] = df["Model"].str.strip().str.upper()
    grouped = df.groupby("NHTSACampaignNumber").agg(
        report_date_iso=("report_date_iso", "first"),
        models=("model", lambda s: sorted(s.unique())),
    )
    return grouped


def main():
    k12 = pd.read_csv(K12_PATH, encoding="utf-8-sig", dtype=str)
    campaign_models = load_campaign_models()
    signals = pd.read_csv(SIGNALS_PATH, encoding="utf-8-sig", dtype=str)
    signals["month"] = pd.PeriodIndex(signals["month"], freq="M")
    signals["count"] = signals["count"].astype(int)
    signals["baseline_avg6"] = signals["baseline_avg6"].astype(float)
    signals["signal"] = signals["signal"].map({"True": True, "False": False})

    rows = []
    for _, r in k12.iterrows():
        campaign = r["campaign"]
        ctype = r["type"]
        info = campaign_models.loc[campaign]
        cutoff = pd.Timestamp(info["report_date_iso"])
        models = info["models"]
        cutoff_month = cutoff.to_period("M")
        window_start = cutoff_month - LOOKBACK_MONTHS
        window_end = cutoff_month - 1

        window = signals[
            signals["model"].isin(models)
            & (signals["month"] >= window_start)
            & (signals["month"] <= window_end)
        ].sort_values("month")

        fired = window[window["signal"]]
        captured = len(fired) > 0

        if captured:
            first = fired.iloc[0]
            first_signal_month = str(first["month"])
            lead_days = (cutoff - first["month"].end_time.normalize()).days
            trigger_model = first["model"]
        else:
            first_signal_month = ""
            lead_days = ""
            trigger_model = ""

        trend = "; ".join(
            f"{row.model} {row.month} count={row.count} base={row.baseline_avg6:.1f}"
            for row in window.itertuples()
        )

        rows.append({
            "campaign": campaign,
            "type": ctype,
            "models": "|".join(models),
            "report_date_iso": info["report_date_iso"],
            "window_start": str(window_start),
            "window_end": str(window_end),
            "captured": captured,
            "trigger_model": trigger_model,
            "first_signal_month": first_signal_month,
            "lead_days": lead_days,
            "window_trend": trend,
        })

    out = pd.DataFrame(rows)
    out.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")

    n_captured = out["captured"].sum()
    print(f"K12 captured: {n_captured}/12")
    print(out.groupby("type")["captured"].agg(["sum", "count"]))
    leads = out.loc[out["captured"], "lead_days"]
    if len(leads):
        print(f"avg lead_days (captured only): {leads.mean():.1f}")
    print(f"saved -> {OUT_PATH}")


if __name__ == "__main__":
    main()
