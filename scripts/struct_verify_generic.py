"""
struct_verify_generic.py — 임의 jsonl 구조화 결과에 대한 스키마·환각(evidence_quote) 검증 +
part_category/severity 분포 집계. struct_verify.py(task5 전용)와 달리 입력 경로를 인자로 받는다.

사용: python scripts/struct_verify_generic.py <jsonl_path>
"""
import json
import re
import sys
import pandas as pd

SOURCE_CSV = "data/processed/hk_electrical_recent_full.csv"

ALLOWED_PARTS = {
    "ELECTRICAL_SYSTEM", "ADAS", "INSTRUMENT_CLUSTER", "PROPULSION_BATTERY",
    "BRAKES_ELECTRONIC", "POWERTRAIN_SW", "NON_ELECTRICAL", "INSUFFICIENT_INFO",
}
ALLOWED_SEVERITY = {"CRITICAL", "SERIOUS", "MODERATE", "MINOR"}
REQUIRED_KEYS = {"odino", "part_category", "symptoms", "severity",
                 "driving_context", "evidence_quote", "insufficient_info"}


def normalize_text(text):
    if not isinstance(text, str):
        return ""
    text = text.replace("'", "'").replace("'", "'").replace(""", '"').replace(""", '"')
    return re.sub(r"\s+", " ", text).strip()


def check_quote(quote, cdescr):
    q, c = normalize_text(quote), normalize_text(cdescr)
    if q and q in c:
        return True
    return len(q) >= 20 and q[:20] in c


def main(jsonl_path):
    records = [json.loads(l) for l in open(jsonl_path, encoding="utf-8") if l.strip()]
    src = pd.read_csv(SOURCE_CSV, encoding="utf-8-sig", dtype=str)
    cdescr_map = dict(zip(src["ODINO"], src["CDESCR"]))

    schema_bad, quote_bad = [], []
    for rec in records:
        missing = REQUIRED_KEYS - rec.keys()
        if missing or rec.get("part_category") not in ALLOWED_PARTS or rec.get("severity") not in ALLOWED_SEVERITY:
            schema_bad.append(rec.get("odino"))
        cdescr = cdescr_map.get(rec.get("odino"), "")
        if not check_quote(rec.get("evidence_quote", ""), cdescr):
            quote_bad.append(rec.get("odino"))

    print(f"총 {len(records)}건 / 스키마위반 {len(schema_bad)}건 {schema_bad} / 인용불일치 {len(quote_bad)}건 {quote_bad}")

    df = pd.DataFrame(records)
    print("\npart_category 분포:")
    print(df["part_category"].value_counts().to_string())
    print("\nseverity 분포:")
    print(df["severity"].value_counts().to_string())

    symptoms_flat = [s for lst in df["symptoms"] for s in lst]
    print(f"\n총 symptom 태그 수: {len(symptoms_flat)} (고유 {len(set(symptoms_flat))})")


if __name__ == "__main__":
    main(sys.argv[1])
