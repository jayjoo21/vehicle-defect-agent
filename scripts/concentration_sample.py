"""
집중도 2차 필터 검증용 표본 추출.
b1_signals.csv의 발화 67건을 "12개월 내 리콜로 이어짐"/"안 이어짐"으로 나누고
각 그룹에서 5건씩 추출 (EV9 2024-09, GENESIS 2024-04는 이미 분석된 건으로 강제 포함).
"""
import pandas as pd

SIGNALS_PATH = "data/processed/b1_signals.csv"
RECALL_PAIRS_PATH = "data/recalls/recalls_hk_by_vehicle.csv"
PRECISION_HORIZON_MONTHS = 12
SEED = 42


def load_signals():
    s = pd.read_csv(SIGNALS_PATH, encoding="utf-8-sig", dtype=str)
    s["month"] = pd.PeriodIndex(s["month"], freq="M")
    s["count"] = s["count"].astype(int)
    s["signal"] = s["signal"].map({"True": True, "False": False})
    return s


def main():
    signals = load_signals()
    recall_pairs = pd.read_csv(RECALL_PAIRS_PATH, encoding="utf-8-sig", dtype=str)
    recall_pairs["model"] = recall_pairs["Model"].str.strip().str.upper()
    recall_pairs["recall_date"] = pd.to_datetime(recall_pairs["report_date_iso"])
    recall_pairs = recall_pairs.drop_duplicates(subset=["NHTSACampaignNumber", "model", "recall_date"])

    fired = signals[signals["signal"]].copy()
    rows = []
    for row in fired.itertuples():
        window_start = row.month.end_time.normalize()
        window_end = window_start + pd.DateOffset(months=PRECISION_HORIZON_MONTHS)
        matches = recall_pairs[
            (recall_pairs["model"] == row.model)
            & (recall_pairs["recall_date"] > window_start)
            & (recall_pairs["recall_date"] <= window_end)
        ]
        hit = len(matches) > 0
        rows.append({"model": row.model, "month": str(row.month), "count": row.count, "hit": hit})

    fired_df = pd.DataFrame(rows)
    print(f"전체 발화 {len(fired_df)}건 / hit={fired_df['hit'].sum()} / miss={(~fired_df['hit']).sum()}")

    recall_group = fired_df[fired_df["hit"]].reset_index(drop=True)
    non_recall_group = fired_df[~fired_df["hit"]].reset_index(drop=True)

    ev9 = recall_group[(recall_group["model"] == "EV9") & (recall_group["month"] == "2024-09")]
    genesis = non_recall_group[(non_recall_group["model"] == "GENESIS") & (non_recall_group["month"] == "2024-04")]
    assert len(ev9) == 1, f"EV9 2024-09 not found in recall group as expected: {ev9}"
    assert len(genesis) == 1, f"GENESIS 2024-04 not found in non-recall group as expected: {genesis}"

    def sample_with_forced(group, forced_row, n=5):
        rest = group.drop(forced_row.index)
        sampled_rest = rest.sample(n=n - 1, random_state=SEED)
        return pd.concat([forced_row, sampled_rest], ignore_index=True)

    recall_sample = sample_with_forced(recall_group, ev9, n=5)
    non_recall_sample = sample_with_forced(non_recall_group, genesis, n=5)

    recall_sample["group"] = "recall_linked"
    non_recall_sample["group"] = "non_recall"

    out = pd.concat([recall_sample, non_recall_sample], ignore_index=True)
    print("\n=== 표본 10건 ===")
    print(out.to_string(index=False))

    out.to_csv("data/processed/concentration_sample.csv", index=False, encoding="utf-8-sig")
    print("\nsaved -> data/processed/concentration_sample.csv")


if __name__ == "__main__":
    main()
