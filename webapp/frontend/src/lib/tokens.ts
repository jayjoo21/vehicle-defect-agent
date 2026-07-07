export const colors = {
  bg: '#FFFFFF',
  bgSubtle: '#F6F7F9',
  navy: '#002C5F',
  navySoft: '#E8EEF5',
  ink: '#111318',
  inkMuted: '#6B7280',
  stateNew: '#6B7280',
  stateRising: '#F59E0B',
  stateActive: '#DC2626',
  stateRecalled: '#2563EB',
  stateResolved: '#059669',
} as const

export type SignalState = 'new' | 'rising' | 'active' | 'recalled' | 'resolved'

export const stateColor: Record<SignalState, string> = {
  new: colors.stateNew,
  rising: colors.stateRising,
  active: colors.stateActive,
  recalled: colors.stateRecalled,
  resolved: colors.stateResolved,
}

export const stateLabel: Record<SignalState, string> = {
  new: '이력 없음',
  rising: '신고 증가',
  active: '활성 시그널',
  recalled: '리콜 진행 중',
  resolved: '시정 완료',
}

export const DATA_AS_OF = '2026-07-06 05:00 KST'

export const DISCLAIMER =
  '본 정보는 NHTSA·국토부 공개 신고 및 리콜 기록 기반이며, 개별 차량의 진단이 아닙니다. 신고는 미검증 소비자 제보를 포함합니다.'
