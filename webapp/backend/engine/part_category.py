"""part_category 코드 -> 한국어 라벨 (frontend/src/lib/partCategory.ts의 PART_CATEGORY_KO와 동일 매핑,
표시용 별칭). LLM 구조화 파이프라인(struct_verify로 환각 검증됨)이 이미 산출한 값을 그대로
옮길 뿐 새로운 판단이나 번역을 추가하지 않는다."""

PART_CATEGORY_KO = {
    "ELECTRICAL_SYSTEM": "전장 시스템",
    "INSTRUMENT_CLUSTER": "계기판",
    "PROPULSION_BATTERY": "구동배터리",
    "ADAS": "ADAS",
    "POWERTRAIN_SW": "파워트레인 SW",
    "NON_ELECTRICAL": "비전장",
    "INSUFFICIENT_INFO": "정보 부족",
}


def ko_gloss(part_category: str | None, symptom: str | None) -> str | None:
    label = PART_CATEGORY_KO.get(part_category, part_category) if part_category else None
    if label and symptom:
        return f"{label} · {symptom}"
    return label or symptom
