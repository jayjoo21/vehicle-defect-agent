#!/usr/bin/env python3
"""
struct_v1v2_diff.py — v1(20건)과 v2(18건) 필드별 diff
비교 대상 필드: part_category, severity, driving_context, insufficient_info
symptoms는 순서 무시 set 비교
"""
import json
from pathlib import Path

V1_PATH = Path("data/processed/llm_struct_test_results.jsonl")
V2_PATH = Path("data/processed/llm_struct_v2_18cases.jsonl")

COMPARE_FIELDS = ["part_category", "severity", "driving_context", "insufficient_info"]

def load_jsonl(path):
    return {str(r["odino"]): r
            for r in (json.loads(l) for l in path.read_text(encoding="utf-8").strip().splitlines())}

v1 = load_jsonl(V1_PATH)
v2 = load_jsonl(V2_PATH)

print(f"v1 총 {len(v1)}건 / v2 비교 대상 {len(v2)}건\n")

diffs_found = []
clean = []

for odino, r2 in sorted(v2.items()):
    r1 = v1.get(odino)
    if not r1:
        print(f"  [WARN] ODINO={odino}: v1에 없음")
        continue

    field_diffs = {}
    for f in COMPARE_FIELDS:
        if r1.get(f) != r2.get(f):
            field_diffs[f] = {"v1": r1.get(f), "v2": r2.get(f)}

    # symptoms: set 비교
    s1 = set(r1.get("symptoms", []))
    s2 = set(r2.get("symptoms", []))
    if s1 != s2:
        field_diffs["symptoms"] = {"v1": sorted(s1), "v2": sorted(s2)}

    if field_diffs:
        diffs_found.append((odino, field_diffs, r2.get("v2_rule_notes", "")))
    else:
        clean.append(odino)

# ── 결과 출력 ──────────────────────────────
print(f"=== 변화 없음: {len(clean)}/{len(v2)}건 ===")
for odino in clean:
    r = v1[odino]
    print(f"  {odino} | {r['part_category']:<20} | {r['severity']}")

if diffs_found:
    print(f"\n=== 변화 있음: {len(diffs_found)}건 ===")
    for odino, diffs, notes in diffs_found:
        print(f"\n  ODINO: {odino}")
        for field, vals in diffs.items():
            print(f"    [{field}] v1={vals['v1']}  →  v2={vals['v2']}")
        if notes:
            print(f"    적용규칙: {notes}")
else:
    print(f"\n=== 변화 있음: 0건 ===")
    print("  18건 모두 v1과 동일")
