"""
집중도 2차 필터 검증 — 표본 10건(리콜 5 + 비리콜 5)의 part_category 집중도 집계.
data/processed/struct_concentration_new8.jsonl(8건 신규) +
struct_ev9_202409.jsonl / struct_genesis_202404.jsonl(기존 2건, 재사용) 통합.
"""
import json
from collections import Counter

import pandas as pd

SAMPLE_PATH = "data/processed/concentration_sample.csv"
NEW8_PATH = "data/processed/struct_concentration_new8.jsonl"
EV9_PATH = "data/processed/struct_ev9_202409.jsonl"
GENESIS_PATH = "data/processed/struct_genesis_202404.jsonl"
OUT_PATH = "data/processed/concentration_test.csv"


def load_jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def main():
    sample = pd.read_csv(SAMPLE_PATH, encoding="utf-8-sig", dtype=str)

    records = load_jsonl(NEW8_PATH)
    for r in records:
        r.setdefault("model", None)
        r.setdefault("month", None)

    # EV9/GENESIS는 Task 8에서 이미 구조화된 결과 재사용 (mentions_existing_recall 필드 없음).
    # report_24V757000.md / report_false_alarm.md에 기록된 집계값을 그대로 사용
    # (EV9: 0/29건, GENESIS: 9/14건이 기존 리콜 24V107000 언급) — MENTIONS_OVERRIDE로 반영
    MENTIONS_OVERRIDE = {("EV9", "2024-09"): 0, ("GENESIS", "2024-04"): 9}

    ev9 = load_jsonl(EV9_PATH)
    for r in ev9:
        r["model"] = "EV9"
        r["month"] = "2024-09"

    genesis = load_jsonl(GENESIS_PATH)
    for r in genesis:
        r["model"] = "GENESIS"
        r["month"] = "2024-04"

    all_records = records + ev9 + genesis
    df = pd.DataFrame(all_records)

    rows = []
    for _, srow in sample.iterrows():
        model, month, group, hit = srow["model"], srow["month"], srow["group"], srow["hit"]
        sub = df[(df["model"] == model) & (df["month"] == month)]
        n = len(sub)
        part_counts = Counter(sub["part_category"])
        top_part, top_count = part_counts.most_common(1)[0]
        top_ratio = top_count / n

        symptom_counts = Counter(s for lst in sub["symptoms"] for s in lst)
        top_symptom, top_symptom_count = (symptom_counts.most_common(1)[0] if symptom_counts else ("", 0))

        if (model, month) in MENTIONS_OVERRIDE:
            mentions = MENTIONS_OVERRIDE[(model, month)]
        elif "mentions_existing_recall" in sub.columns:
            mentions = int(sub["mentions_existing_recall"].fillna(False).astype(bool).sum())
        else:
            mentions = 0

        rows.append({
            "model": model, "month": month, "group": group, "hit_recall_12m": hit, "n": n,
            "top_part_category": top_part, "top_part_count": top_count,
            "top_part_ratio": round(top_ratio, 4),
            "top_symptom_tag": top_symptom, "top_symptom_count": top_symptom_count,
            "mentions_existing_recall_count": mentions,
        })

    out = pd.DataFrame(rows)
    out.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")

    print(out.to_string(index=False))

    recall_linked = out[out["group"] == "recall_linked"]["top_part_ratio"]
    non_recall = out[out["group"] == "non_recall"]["top_part_ratio"]
    print(f"\n리콜연계 그룹 집중도: 평균={recall_linked.mean():.3f} 중앙값={recall_linked.median():.3f}")
    print(f"비리콜 그룹 집중도: 평균={non_recall.mean():.3f} 중앙값={non_recall.median():.3f}")
    print(f"\nsaved -> {OUT_PATH}")


if __name__ == "__main__":
    main()
