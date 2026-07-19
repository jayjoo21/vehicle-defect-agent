"""sample_20_for_llm_test.csv 기반으로 새 7종 NEW_COMPDESC 채점 틀 생성.
채점 컬럼(NEW_COMPDESC 등)은 전부 빈 값으로 남긴다 — 사람이 채점할 정답지이므로
AI가 값을 채우면 순환 평가 오류가 발생한다.
"""
import pandas as pd

SRC = "data/samples/sample_20_for_llm_test.csv"
OUT = "data/samples/grading_sheet_v2.csv"

df = pd.read_csv(SRC, dtype=str)

sheet = pd.DataFrame({
    "ODINO": df["ODINO"],
    "MAKETXT": df["MAKETXT"],
    "MODELTXT": df["MODELTXT"],
    "YEARTXT": df["YEARTXT"],
    "LDATE": df["LDATE"],
    "COMPDESC_원본": df["COMPDESC"],
    "CDESCR": df["CDESCR"],
    "CRASH": df["CRASH"],
    "FIRE": df["FIRE"],
    "INJURED": df["INJURED"],
    "DEATHS": df["DEATHS"],
    "NEW_COMPDESC": "",
    "NEW_COMPDESC_REASON": "",
    "SEVERITY": "",
    "SEVERITY_REASON": "",
    "SYMPTOMS_TF": "",
    "SYMPTOMS_REASON": "",
    "HALLUCINATION": "",
    "ERROR_TYPE": "",
})

sheet.to_csv(OUT, index=False, encoding="utf-8-sig")

# 검증
grading_cols = [
    "NEW_COMPDESC", "NEW_COMPDESC_REASON", "SEVERITY", "SEVERITY_REASON",
    "SYMPTOMS_TF", "SYMPTOMS_REASON", "HALLUCINATION", "ERROR_TYPE",
]
non_empty = sheet[grading_cols].apply(lambda c: c.astype(str).str.strip().ne("")).sum()
print(f"행 수: {len(sheet)}")
print(f"컬럼 수: {len(sheet.columns)}")
print("채점 컬럼별 비어있지 않은 값 개수 (전부 0이어야 정상):")
print(non_empty)
print("\n참고용 컬럼 원본 일치 확인:")
print("ODINO 일치:", (sheet["ODINO"] == df["ODINO"]).all())
print("CDESCR 일치:", (sheet["CDESCR"] == df["CDESCR"]).all())
