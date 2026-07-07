// 등록 가능 차종 27종 — data/recalls/recalls_hk_by_vehicle.csv의 실측 Model/Make 기준
// (normalize_model 적용 후 distinct 27개, 백엔드와 동일한 정본).
export interface CarModel {
  model: string
  make: 'HYUNDAI' | 'KIA'
}

export const CAR_MODELS: CarModel[] = [
  { model: 'ACCENT', make: 'HYUNDAI' },
  { model: 'ELANTRA', make: 'HYUNDAI' },
  { model: 'IONIQ 5', make: 'HYUNDAI' },
  { model: 'IONIQ 6', make: 'HYUNDAI' },
  { model: 'KONA', make: 'HYUNDAI' },
  { model: 'NEXO', make: 'HYUNDAI' },
  { model: 'PALISADE', make: 'HYUNDAI' },
  { model: 'SANTA CRUZ', make: 'HYUNDAI' },
  { model: 'SANTA FE', make: 'HYUNDAI' },
  { model: 'SONATA', make: 'HYUNDAI' },
  { model: 'TUCSON', make: 'HYUNDAI' },
  { model: 'VELOSTER', make: 'HYUNDAI' },
  { model: 'VENUE', make: 'HYUNDAI' },
  { model: 'CARNIVAL', make: 'KIA' },
  { model: 'EV6', make: 'KIA' },
  { model: 'EV9', make: 'KIA' },
  { model: 'FORTE', make: 'KIA' },
  { model: 'K5', make: 'KIA' },
  { model: 'NIRO', make: 'KIA' },
  { model: 'NIRO EV', make: 'KIA' },
  { model: 'RIO', make: 'KIA' },
  { model: 'SELTOS', make: 'KIA' },
  { model: 'SORENTO', make: 'KIA' },
  { model: 'SOUL', make: 'KIA' },
  { model: 'SPORTAGE', make: 'KIA' },
  { model: 'STINGER', make: 'KIA' },
  { model: 'TELLURIDE', make: 'KIA' },
]

export const YEAR_OPTIONS = Array.from({ length: 2026 - 2018 + 1 }, (_, i) => 2026 - i)
