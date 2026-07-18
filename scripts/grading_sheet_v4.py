#!/usr/bin/env python3
"""
grading_sheet_v4.py — v4 구조화 결과 수동 채점표 생성

struct_verify.py(Task 5, 20건, ODINO 매칭)와 같은 목적 — STR-02(인용 진짜인지)·STR-03
(모델이 자기 자신과 일관되는지)은 둘 다 "판단이 실제로 맞았는가"는 답하지 않는다.
사람이 CDESCR 원문을 읽고 LLM 판단을 채점하기 위한 시트를 만든다.

v4는 CMPLID 단위로 매칭하고, part_category가 없어진 대신 compdesc1/compdesc2
"앵커링"이 실제로 잘 지켜졌는지(형제가 다룬 내용을 잘 배제했는지 등)를 채점하는
컬럼을 새로 추가했다.
"""
import json
from pathlib import Path
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_CSV = REPO_ROOT / "data/samples/sample_100_v4.csv"
JSONL_PATH = REPO_ROOT / "data/processed/str01_sample100_v4_results.jsonl"
GRADE_CSV = REPO_ROOT / "data/samples/grading_sheet_v4.csv"


def main():
    df_orig = pd.read_csv(SAMPLE_CSV, encoding="utf-8-sig", dtype=str)
    cdescr_map = dict(zip(df_orig["CMPLID"], df_orig["CDESCR"]))

    records = []
    with open(JSONL_PATH, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  [JSON 파싱 오류] 행 {i}: {e}")

    grade_rows = []
    for rec in records:
        cmplid = str(rec.get("cmplid", ""))
        grade_rows.append({
            "CMPLID": cmplid,
            "ODINO": rec.get("odino", ""),
            "compdesc1": rec.get("compdesc1", ""),
            "compdesc2": rec.get("compdesc2", ""),
            "CDESCR": cdescr_map.get(cmplid, ""),
            "LLM_symptoms": " / ".join(rec.get("symptoms") or []),
            "LLM_severity": rec.get("severity", ""),
            "LLM_driving_context": rec.get("driving_context", ""),
            "LLM_evidence_quote": rec.get("evidence_quote", ""),
            "LLM_insufficient_info": rec.get("insufficient_info", ""),
            # 수동 채점란 (빈칸)
            "앵커링_정오": "",   # 이 compdesc1/2 범위에만 집중했는지, 형제가 다룬 내용은 잘 배제했는지
            "심각도_정오": "",
            "증상_정오": "",
            "주행상황_정오": "",
            "정보부족_정오": "",
            "환각_여부": "",
            "오류유형": "",
            "메모": "",
        })

    df_grade = pd.DataFrame(grade_rows)
    df_grade.to_csv(GRADE_CSV, index=False, encoding="utf-8-sig")
    print(f"채점표 저장: {GRADE_CSV} ({len(df_grade)}행)")


if __name__ == "__main__":
    main()
