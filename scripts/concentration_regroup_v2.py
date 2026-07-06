"""
precision_v2.py의 base_model 정규화 결과를 반영해 집중도 표본 10건의 그룹을 재분류.
concentration_test.csv(Task 9) + precision_v2.csv(Task 10)을 병합, hit_base_observed
기준으로 group을 재산정하고 그룹별 집중도 통계를 재계산.
"""
import pandas as pd

CONC_PATH = "data/processed/concentration_test.csv"
PRECV2_PATH = "data/processed/precision_v2.csv"
OUT_PATH = "data/processed/concentration_test_v2.csv"


def main():
    conc = pd.read_csv(CONC_PATH, encoding="utf-8-sig", dtype=str)
    conc["top_part_ratio"] = conc["top_part_ratio"].astype(float)
    precv2 = pd.read_csv(PRECV2_PATH, encoding="utf-8-sig", dtype=str)
    precv2["hit_base_observed"] = precv2["hit_base_observed"].map({"True": True, "False": False})
    precv2["censored"] = precv2["censored"].map({"True": True, "False": False})

    merged = conc.merge(precv2[["model", "month", "hit_base_observed", "censored", "base_model"]],
                         on=["model", "month"], how="left")
    merged["group_v2"] = merged["hit_base_observed"].map({True: "recall_linked", False: "non_recall"})

    out = merged[["model", "month", "group", "group_v2", "hit_base_observed", "censored",
                  "top_part_category", "top_part_ratio", "mentions_existing_recall_count"]]
    out = out.sort_values("top_part_ratio", ascending=False)
    out.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")

    print("=== 집중도 표본 10건 재분류 (base_model 정규화 반영) ===")
    print(out.to_string(index=False))

    print("\n=== 그룹 이동 ===")
    moved = out[out["group"] != out["group_v2"]]
    print(moved[["model", "month", "group", "group_v2"]].to_string(index=False) if len(moved) else "없음")

    for g in ["recall_linked", "non_recall"]:
        sub = out[out["group_v2"] == g]["top_part_ratio"]
        print(f"\n{g} (n={len(sub)}): 평균={sub.mean():.3f} 중앙값={sub.median():.3f} 값={sorted(sub.tolist())}")

    print(f"\n기준선 정밀도(이 10건 표본, group_v2 기준): {(out['group_v2']=='recall_linked').sum()}/10")

    # 임계값 효과 재계산 (그룹_v2 기준)
    print("\n=== 임계값 효과 (group_v2 기준) ===")
    baseline_hits = (out["group_v2"] == "recall_linked").sum()
    baseline_n = len(out)
    print(f"임계값 없음: {baseline_hits}/{baseline_n} = {baseline_hits/baseline_n:.3f}")
    for thresh in [0.5, 0.7, 0.8]:
        passed = out[out["top_part_ratio"] >= thresh]
        if len(passed) == 0:
            continue
        hits = (passed["group_v2"] == "recall_linked").sum()
        print(f"임계값 >={thresh}: 통과 {len(passed)}건, hit={hits} -> 정밀도 {hits/len(passed):.3f} "
              f"(실제 리콜연계 {baseline_hits}건 중 {hits}건만 포착, 나머지 {baseline_hits-hits}건 누락)")

    print(f"\nsaved -> {OUT_PATH}")


if __name__ == "__main__":
    main()
