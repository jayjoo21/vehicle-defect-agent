"""
struct_verify_v4.py — v4(CMPLID 단위, 9필드) 구조화 결과 독립 재검증.

struct_verify_generic.py(v2/v3, ODINO 단위)와 스키마가 달라 별도 스크립트로 분리:
- 매칭 키: odino → cmplid
- 스키마: part_category 없음, driving_context 허용값(주행 중/정차·주차 중/시동 시/불명) 검사 추가
- evidence_quote 검사: insufficient_info=true + evidence_quote=""는 예외로 허용(v4 설계상 정상)
- compdesc1/compdesc2가 원본 COMPDESC 파싱과 일치하는지도 함께 검증(코드가 채운 필드라 항상 일치해야 함)

사용: python scripts/struct_verify_v4.py <jsonl_path> [sample_csv_path]
"""
import json
import re
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from str01_batch_structurize import fix_mojibake

DEFAULT_SAMPLE_CSV = "data/samples/sample_100_v4.csv"
EMPTY_QUOTE_PLACEHOLDER = "(정보 부족으로 근거 문장 없음)"

ALLOWED_SEVERITY = {"CRITICAL", "SERIOUS", "MODERATE", "MINOR"}
ALLOWED_DRIVING_CONTEXT = {"주행 중", "정차·주차 중", "시동 시", "불명"}
REQUIRED_KEYS = {"cmplid", "odino", "compdesc1", "compdesc2", "symptoms",
                 "severity", "driving_context", "evidence_quote", "insufficient_info"}


def normalize_text(text):
    if not isinstance(text, str):
        return ""
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


def check_quote(quote, cdescr):
    q, c = normalize_text(quote), normalize_text(cdescr)
    if q and q in c:
        return True
    return len(q) >= 20 and q[:20] in c


def parse_compdesc(raw):
    parts = [p.strip() for p in str(raw or "").split(":")]
    c1 = parts[0] if parts and parts[0] else str(raw or "")
    c2 = parts[1] if len(parts) >= 2 and parts[1] else "no"
    return c1, c2


def main(jsonl_path, sample_csv_path=DEFAULT_SAMPLE_CSV):
    records = [json.loads(l) for l in open(jsonl_path, encoding="utf-8") if l.strip()]
    src = pd.read_csv(sample_csv_path, encoding="utf-8-sig", dtype=str)
    cdescr_map = {cid: fix_mojibake(cdescr) for cid, cdescr in zip(src["CMPLID"], src["CDESCR"])}
    compdesc_map = dict(zip(src["CMPLID"], src["COMPDESC"]))

    schema_bad, quote_bad, empty_quote_ok, compdesc_mismatch = [], [], [], []
    for rec in records:
        cmplid = rec.get("cmplid")
        missing = REQUIRED_KEYS - rec.keys()
        errs = []
        if missing:
            errs.append(f"누락 키 {sorted(missing)}")
        if rec.get("severity") not in ALLOWED_SEVERITY:
            errs.append(f"severity 위반 {rec.get('severity')!r}")
        if rec.get("driving_context") not in ALLOWED_DRIVING_CONTEXT:
            errs.append(f"driving_context 위반 {rec.get('driving_context')!r}")
        if not isinstance(rec.get("symptoms"), list):
            errs.append("symptoms가 list 아님")
        if not isinstance(rec.get("insufficient_info"), bool):
            errs.append("insufficient_info가 bool 아님")
        if errs:
            schema_bad.append((cmplid, errs))

        # compdesc1/compdesc2가 원본 COMPDESC 파싱과 일치하는지 (코드가 채운 필드 검증)
        exp_c1, exp_c2 = parse_compdesc(compdesc_map.get(cmplid, ""))
        if rec.get("compdesc1") != exp_c1 or rec.get("compdesc2") != exp_c2:
            compdesc_mismatch.append((cmplid, rec.get("compdesc1"), rec.get("compdesc2"), exp_c1, exp_c2))

        cdescr = cdescr_map.get(cmplid, "")
        quote = rec.get("evidence_quote", "")
        if rec.get("insufficient_info") is True and quote == EMPTY_QUOTE_PLACEHOLDER:
            empty_quote_ok.append(cmplid)
        elif not check_quote(quote, cdescr):
            quote_bad.append(cmplid)

    print(f"총 {len(records)}건")
    print(f"스키마 위반 {len(schema_bad)}건: {schema_bad}")
    print(f"compdesc1/2 불일치(코드 필드 검증) {len(compdesc_mismatch)}건: {compdesc_mismatch}")
    print(f"인용 불일치(환각) {len(quote_bad)}건: {quote_bad}")
    print(f"insufficient_info=true + 빈 인용 예외 허용 {len(empty_quote_ok)}건: {empty_quote_ok}")

    df = pd.DataFrame(records)
    print("\nseverity 분포:")
    print(df["severity"].value_counts().to_string())
    print("\ndriving_context 분포:")
    print(df["driving_context"].value_counts().to_string())
    print("\ncompdesc1 분포:")
    print(df["compdesc1"].value_counts().to_string())
    print(f"\ninsufficient_info=true 건수: {df['insufficient_info'].sum()}")

    symptoms_flat = [s for lst in df["symptoms"] for s in lst]
    print(f"\n총 symptom 태그 수: {len(symptoms_flat)} (고유 {len(set(symptoms_flat))})")

    print("\n=== sample_group별 분포 ===")
    group_map = dict(zip(src["CMPLID"], src["sample_group"]))
    df["sample_group"] = df["cmplid"].map(group_map)
    print(df["sample_group"].value_counts().to_string())


if __name__ == "__main__":
    main(*sys.argv[1:])
