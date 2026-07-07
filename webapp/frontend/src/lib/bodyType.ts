// 차종 → 차체형태(3D 모델 파일) 매핑. frontend/public/models/{suv,sedan,sports}.glb 3종만 있으므로
// 27개 차종을 이 3종으로 근사 분류한다(실제 세그먼트 판단, CLAUDE.md 판단 원칙과 동일하게 근사치임을 명시).
// 매핑에 없는 차종은 suv로 폴백.
export type BodyType = 'suv' | 'sedan' | 'sports'

const BODY_TYPE_MAP: Record<string, BodyType> = {
  // 세단
  ACCENT: 'sedan',
  ELANTRA: 'sedan',
  FORTE: 'sedan',
  'IONIQ 6': 'sedan',
  K5: 'sedan',
  RIO: 'sedan',
  SONATA: 'sedan',
  // 스포츠(퍼포먼스 쿠페/해치)
  STINGER: 'sports',
  VELOSTER: 'sports',
  // SUV/CUV/픽업(세단·스포츠가 아닌 나머지 전부)
  CARNIVAL: 'suv',
  EV6: 'suv',
  EV9: 'suv',
  'IONIQ 5': 'suv',
  KONA: 'suv',
  NEXO: 'suv',
  NIRO: 'suv',
  'NIRO EV': 'suv',
  PALISADE: 'suv',
  'SANTA CRUZ': 'suv',
  'SANTA FE': 'suv',
  SELTOS: 'suv',
  SORENTO: 'suv',
  SOUL: 'suv',
  SPORTAGE: 'suv',
  TELLURIDE: 'suv',
  VENUE: 'suv',
}

const FALLBACK_BODY_TYPE: BodyType = 'suv'

export function bodyTypeOf(model: string): BodyType {
  return BODY_TYPE_MAP[model.toUpperCase()] ?? FALLBACK_BODY_TYPE
}

export function modelGlbPath(model: string): string {
  return `/models/${bodyTypeOf(model)}.glb`
}
