"""
B1 baseline 평가 검증 3종.

(1) 우연 포착 대조: K12 각 캠페인의 차종에 대해 컷오프를 2023-07~2026-06 전 구간으로
    옮겨가며 "이전 12개월 내 발화 존재" 비율을 계산 (실제 포착 10/12와 비교용 귀무 기준선)
(2) 정밀도: b1_signals.csv의 발화 67건 각각에 대해, 발화월 이후 12개월 내 해당 차종의
    리콜(recalls_hk_campaigns.csv, 164건)이 접수됐는지 확인
(3) 민감도: K12 포착 인정 창을 12개월 -> 6개월로 좁혔을 때 포착 건수 변화

입력: docs/k12_list.csv, data/processed/b1_signals.csv,
      data/recalls/recalls_hk_by_vehicle.csv, data/recalls/recalls_hk_campaigns.csv
출력: data/processed/b1_eval_validation.csv
"""
import pandas as pd

K12_PATH = "docs/k12_list.csv"
SIGNALS_PATH = "data/processed/b1_signals.csv"
CAMPAIGN_MODELS_PATH = "data/recalls/recalls_hk_by_vehicle.csv"
RECALL_PAIRS_PATH = "data/recalls/recalls_hk_by_vehicle.csv"
OUT_PATH = "data/processed/b1_eval_validation.csv"

CHANCE_RANGE_START = "2023-07"
CHANCE_RANGE_END = "2026-06"
LOOKBACK_12 = 12
LOOKBACK_6 = 6
PRECISION_HORIZON_MONTHS = 12


def load_signals():
    s = pd.read_csv(SIGNALS_PATH, encoding="utf-8-sig", dtype=str)
    s["month"] = pd.PeriodIndex(s["month"], freq="M")
    s["count"] = s["count"].astype(int)
    s["signal"] = s["signal"].map({"True": True, "False": False})
    return s


def load_campaign_models():
    df = pd.read_csv(CAMPAIGN_MODELS_PATH, encoding="utf-8-sig", dtype=str)
    df["model"] = df["Model"].str.strip().str.upper()
    return df.groupby("NHTSACampaignNumber").agg(
        report_date_iso=("report_date_iso", "first"),
        models=("model", lambda x: sorted(x.unique())),
    )


def any_signal_in_window(signals, models, window_start, window_end):
    win = signals[
        signals["model"].isin(models)
        & (signals["month"] >= window_start)
        & (signals["month"] <= window_end)
    ]
    return bool(win["signal"].any())


def check_chance_capture(k12, campaign_models, signals):
    months = pd.period_range(CHANCE_RANGE_START, CHANCE_RANGE_END, freq="M")
    rows = []
    for _, r in k12.iterrows():
        campaign, ctype = r["campaign"], r["type"]
        models = campaign_models.loc[campaign, "models"]
        hits = 0
        for m in months:
            w_start, w_end = m - LOOKBACK_12, m - 1
            if any_signal_in_window(signals, models, w_start, w_end):
                hits += 1
        prob = hits / len(months)
        rows.append({
            "check": "chance_capture", "campaign": campaign, "type": ctype,
            "value": round(prob, 4),
            "detail": f"hits={hits}/{len(months)} months ({CHANCE_RANGE_START}~{CHANCE_RANGE_END})",
        })
    avg_prob = sum(r["value"] for r in rows) / len(rows)
    rows.append({
        "check": "chance_capture_avg", "campaign": "ALL", "type": "",
        "value": round(avg_prob, 4),
        "detail": "평균 우연 포착 확률 (12개 캠페인 평균, vs 실제 포착 10/12=0.833)",
    })
    return rows


def check_precision(signals, recall_pairs):
    recall_pairs = recall_pairs.copy()
    recall_pairs["model"] = recall_pairs["Model"].str.strip().str.upper()
    recall_pairs["recall_date"] = pd.to_datetime(recall_pairs["report_date_iso"])
    recall_pairs = recall_pairs.drop_duplicates(subset=["NHTSACampaignNumber", "model", "recall_date"])

    fired = signals[signals["signal"]].copy()
    hits = 0
    detail_rows = []
    for row in fired.itertuples():
        window_start = row.month.end_time.normalize()
        window_end = window_start + pd.DateOffset(months=PRECISION_HORIZON_MONTHS)
        matches = recall_pairs[
            (recall_pairs["model"] == row.model)
            & (recall_pairs["recall_date"] > window_start)
            & (recall_pairs["recall_date"] <= window_end)
        ]
        hit = len(matches) > 0
        hits += hit
        detail_rows.append((row.model, str(row.month), hit))

    precision = hits / len(fired)
    rows = [{
        "check": "precision", "campaign": "ALL", "type": "",
        "value": round(precision, 4),
        "detail": f"hits={hits}/{len(fired)} signals -> 12개월 내 리콜(recalls_hk_by_vehicle.csv, "
                  f"차종-캠페인 전체 쌍 {len(recall_pairs)}행) 접수",
    }]
    return rows, detail_rows


def check_sensitivity(k12, campaign_models, signals):
    rows = []
    n_captured_6 = 0
    for _, r in k12.iterrows():
        campaign, ctype = r["campaign"], r["type"]
        info = campaign_models.loc[campaign]
        cutoff_month = pd.Timestamp(info["report_date_iso"]).to_period("M")
        models = info["models"]
        captured_6 = any_signal_in_window(signals, models, cutoff_month - LOOKBACK_6, cutoff_month - 1)
        n_captured_6 += captured_6
        rows.append({
            "check": "sensitivity_6m", "campaign": campaign, "type": ctype,
            "value": int(captured_6),
            "detail": f"6개월 창 포착 여부 (12개월 창 결과는 b1_eval_k12.csv 참조)",
        })
    rows.append({
        "check": "sensitivity_6m_summary", "campaign": "ALL", "type": "",
        "value": n_captured_6,
        "detail": f"{n_captured_6}/12 captured with 6-month window (vs 10/12 with 12-month window)",
    })
    return rows


def main():
    k12 = pd.read_csv(K12_PATH, encoding="utf-8-sig", dtype=str)
    campaign_models = load_campaign_models()
    signals = load_signals()
    recall_pairs = pd.read_csv(RECALL_PAIRS_PATH, encoding="utf-8-sig", dtype=str)

    rows = []
    rows += check_chance_capture(k12, campaign_models, signals)
    precision_rows, precision_detail = check_precision(signals, recall_pairs)
    rows += precision_rows
    rows += check_sensitivity(k12, campaign_models, signals)

    out = pd.DataFrame(rows)
    out.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")

    print("=== 우연 포착 대조 ===")
    chance = out[out["check"] == "chance_capture"]
    print(chance[["campaign", "type", "value"]].to_string(index=False))
    avg_row = out[out["check"] == "chance_capture_avg"].iloc[0]
    print(f"평균 우연 포착 확률: {avg_row['value']:.3f} (실제 포착률 10/12=0.833)")

    print("\n=== 정밀도 ===")
    prec_row = out[out["check"] == "precision"].iloc[0]
    print(f"정밀도: {prec_row['value']:.3f} ({prec_row['detail']})")

    print("\n=== 민감도 (12개월 -> 6개월 창) ===")
    sens = out[out["check"] == "sensitivity_6m"]
    print(sens[["campaign", "type", "value"]].to_string(index=False))
    summary_row = out[out["check"] == "sensitivity_6m_summary"].iloc[0]
    print(summary_row["detail"])

    print(f"\nsaved -> {OUT_PATH}")


if __name__ == "__main__":
    main()
