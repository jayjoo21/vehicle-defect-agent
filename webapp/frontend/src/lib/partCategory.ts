// LLM 구조화 파이프라인(struct_verify로 환각 검증됨)이 이미 산출한 part_category 코드를
// 한국어 라벨로만 옮긴다 — 새로운 판단이나 번역을 추가하는 게 아니라 기존 검증된 필드의 표시용 별칭.
export const PART_CATEGORY_KO: Record<string, string> = {
  ELECTRICAL_SYSTEM: '전장 시스템',
  INSTRUMENT_CLUSTER: '계기판',
  PROPULSION_BATTERY: '구동배터리',
  ADAS: 'ADAS',
  POWERTRAIN_SW: '파워트레인 SW',
  NON_ELECTRICAL: '비전장',
  INSUFFICIENT_INFO: '정보 부족',
}

export function koGloss(partCategory: string | null, symptom: string | null): string | null {
  const label = partCategory ? (PART_CATEGORY_KO[partCategory] ?? partCategory) : null
  if (label && symptom) return `${label} · ${symptom}`
  return label ?? symptom ?? null
}
