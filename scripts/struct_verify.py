#!/usr/bin/env python3
"""
struct_verify.py — LLM 구조화 결과 자동 검증
① 스키마 검사: 필수 키·허용값
② 환각 검사: evidence_quote이 CDESCR 원문에 실제 존재하는지
③ 채점표(grading_sheet.csv) 생성
"""
import json
import re
import unicodedata
import pandas as pd
from pathlib import Path

JSONL_PATH = Path("data/processed/llm_struct_test_results.jsonl")
SAMPLE_CSV = Path("data/samples/sample_20_for_llm_test.csv")
GRADE_CSV  = Path("data/samples/grading_sheet.csv")

ALLOWED_PARTS = {
    "ELECTRICAL_SYSTEM", "ADAS", "INSTRUMENT_CLUSTER", "PROPULSION_BATTERY",
    "BRAKES_ELECTRONIC", "POWERTRAIN_SW", "NON_ELECTRICAL", "INSUFFICIENT_INFO",
}
ALLOWED_SEVERITY = {"CRITICAL", "SERIOUS", "MODERATE", "MINOR"}
REQUIRED_KEYS = {"odino", "part_category", "symptoms", "severity",
                 "driving_context", "evidence_quote", "insufficient_info"}


def normalize_text(text: str) -> str:
    """공백 정규화 + 유니코드 따옴표/아포스트로피 통일"""
    if not isinstance(text, str):
        return ""
    # 유니코드 따옴표 → 직선 따옴표
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    # 연속 공백 → 단일 스페이스
    text = re.sub(r"\s+", " ", text).strip()
    return text


def check_schema(rec: dict, idx: int) -> list[str]:
    errors = []
    missing = REQUIRED_KEYS - rec.keys()
    if missing:
        errors.append(f"누락 키: {missing}")
    if rec.get("part_category") not in ALLOWED_PARTS:
        errors.append(f"part_category 허용값 위반: {rec.get('part_category')!r}")
    if rec.get("severity") not in ALLOWED_SEVERITY:
        errors.append(f"severity 허용값 위반: {rec.get('severity')!r}")
    if not isinstance(rec.get("symptoms"), list):
        errors.append("symptoms가 list가 아님")
    if not isinstance(rec.get("insufficient_info"), bool):
        errors.append(f"insufficient_info가 bool이 아님: {rec.get('insufficient_info')!r}")
    return errors


def check_quote(quote: str, cdescr: str) -> bool:
    """evidence_quote의 핵심 부분이 CDESCR에 포함되는지 확인"""
    q_norm = normalize_text(quote)
    c_norm = normalize_text(cdescr)
    # 전체 인용 문자열이 있으면 바로 통과
    if q_norm and q_norm in c_norm:
        return True
    # 인용이 길면(20자 이상) 앞 20자만으로도 확인
    if len(q_norm) >= 20:
        return q_norm[:20] in c_norm
    return False


def main():
    # 원본 데이터 로드
    df_orig = pd.read_csv(SAMPLE_CSV, encoding="utf-8-sig")
    cdescr_map = dict(zip(df_orig["ODINO"].astype(str), df_orig["CDESCR"].astype(str)))
    compdesc_map = dict(zip(df_orig["ODINO"].astype(str), df_orig["COMPDESC"].astype(str)))

    # 결과 로드
    records = []
    with open(JSONL_PATH, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                records.append((i, rec))
            except json.JSONDecodeError as e:
                print(f"  [JSON 파싱 오류] 행 {i}: {e}")

    print(f"총 {len(records)}건 로드\n")

    schema_violations = []
    quote_mismatches = []

    # ── ① 스키마 검사 ──────────────────────────
    print("=== ① 스키마 검사 ===")
    for idx, rec in records:
        errs = check_schema(rec, idx)
        if errs:
            odino = rec.get("odino", f"행{idx}")
            schema_violations.append(odino)
            for e in errs:
                print(f"  [SCHEMA ERR] ODINO={odino}: {e}")

    if not schema_violations:
        print("  스키마 위반 없음")

    # ── ② 환각 검사 ──────────────────────────
    print("\n=== ② 환각 검사 (evidence_quote ∈ CDESCR) ===")
    for idx, rec in records:
        odino = str(rec.get("odino", ""))
        quote = rec.get("evidence_quote", "")
        cdescr = cdescr_map.get(odino, "")
        if not cdescr:
            print(f"  [WARN] ODINO={odino}: CDESCR 원문 없음 (매칭 불가)")
            continue
        if not check_quote(quote, cdescr):
            quote_mismatches.append(odino)
            print(f"  [QUOTE MISMATCH] ODINO={odino}")
            print(f"    quote : {quote[:80]}...")
            print(f"    cdescr(앞80): {normalize_text(cdescr)[:80]}...")

    if not quote_mismatches:
        print("  인용 불일치 없음")

    # ── ③ 요약 ──────────────────────────────
    print(f"\n=== 요약 ===")
    print(f"  스키마 위반: {len(schema_violations)}건"
          + (f" → ODINO {schema_violations}" if schema_violations else ""))
    print(f"  인용 불일치: {len(quote_mismatches)}건"
          + (f" → ODINO {quote_mismatches}" if quote_mismatches else ""))

    # ── 채점표 생성 ───────────────────────────
    grade_rows = []
    for idx, rec in records:
        odino = str(rec.get("odino", ""))
        cdescr_full = cdescr_map.get(odino, "")
        grade_rows.append({
            "ODINO": odino,
            "CDESCR_앞300자": cdescr_full[:300],
            "원래_COMPDESC": compdesc_map.get(odino, ""),
            "LLM_part_category": rec.get("part_category", ""),
            "LLM_symptoms": " / ".join(rec.get("symptoms", [])),
            "LLM_severity": rec.get("severity", ""),
            "LLM_driving_context": rec.get("driving_context", ""),
            "LLM_evidence_quote": rec.get("evidence_quote", ""),
            "LLM_insufficient_info": rec.get("insufficient_info", ""),
            # 수동 채점란 (빈칸)
            "부품_정오": "",
            "심각도_정오": "",
            "증상_정오": "",
            "환각_여부": "",
            "오류유형": "",
            "메모": "",
        })

    df_grade = pd.DataFrame(grade_rows)
    df_grade.to_csv(GRADE_CSV, index=False, encoding="utf-8-sig")
    print(f"\n채점표 저장: {GRADE_CSV} ({len(df_grade)}행)")


if __name__ == "__main__":
    main()
