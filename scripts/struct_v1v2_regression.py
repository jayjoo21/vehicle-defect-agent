"""
v1(llm_struct_test_results.jsonl, 20건) vs v2(llm_struct_v2_18cases.jsonl, 18건) 필드별 회귀 검증.
sample_20 중 경계 2건(11551510, 11729316)은 이미 별도 재실험되어 제외.
비교 필드: part_category, severity, driving_context, insufficient_info, symptoms(set 비교)
출력: data/processed/llm_struct_test_v2_regression.csv
"""
import json

import pandas as pd

V1_PATH = "data/processed/llm_struct_test_results.jsonl"
V2_PATH = "data/processed/llm_struct_v2_18cases.jsonl"
EXCLUDED_ODINOS = {"11551510", "11729316"}
OUT_PATH = "data/processed/llm_struct_test_v2_regression.csv"

COMPARE_FIELDS = ["part_category", "severity", "driving_context", "insufficient_info"]


def load_jsonl(path):
    return {str(r["odino"]): r for r in (json.loads(l) for l in open(path, encoding="utf-8") if l.strip())}


def main():
    v1 = load_jsonl(V1_PATH)
    v2 = load_jsonl(V2_PATH)

    assert set(v1.keys()) - EXCLUDED_ODINOS == set(v2.keys()), "v1(20건 - 경계2건)과 v2(18건) 대상 불일치"

    rows = []
    for odino in sorted(v2.keys()):
        r1, r2 = v1[odino], v2[odino]
        row = {"odino": odino}
        any_change = False
        for f in COMPARE_FIELDS:
            row[f"{f}_v1"] = r1.get(f)
            row[f"{f}_v2"] = r2.get(f)
            changed = r1.get(f) != r2.get(f)
            row[f"{f}_changed"] = changed
            any_change = any_change or changed

        s1, s2 = set(r1.get("symptoms", [])), set(r2.get("symptoms", []))
        row["symptoms_changed"] = s1 != s2
        any_change = any_change or row["symptoms_changed"]

        row["any_change"] = any_change
        row["applied_v2_rules"] = r2.get("v2_rule_notes", "")
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")

    n = len(df)
    n_changed = df["any_change"].sum()
    print(f"=== v1({len(v1)}건, 경계 {len(EXCLUDED_ODINOS)}건 제외) vs v2({n}건) 회귀 검증 ===")
    print(f"변화 없음: {n - n_changed}/{n}건")
    print(f"변화 있음: {n_changed}/{n}건")

    if n_changed:
        changed_df = df[df["any_change"]]
        for _, row in changed_df.iterrows():
            print(f"\n  ODINO {row['odino']}:")
            for f in COMPARE_FIELDS + ["symptoms"]:
                if row.get(f"{f}_changed", False):
                    print(f"    [{f}] v1={row.get(f'{f}_v1')} -> v2={row.get(f'{f}_v2')}")
            print(f"    적용규칙: {row['applied_v2_rules']}")
    else:
        print("\n18건 전원 v1과 동일 (part_category·severity·driving_context·insufficient_info·symptoms 무변화)")

    print(f"\nsaved -> {OUT_PATH}")


if __name__ == "__main__":
    main()
