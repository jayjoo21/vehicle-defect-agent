import type { Summary } from '../lib/types'
import CountUp from './CountUp'

// 각주(*)의 실제 설명 텍스트는 페이지 레벨 각주로 옮겼다(Dashboard.tsx) — 카드 자체는 라벨만 보여준다.
const ITEMS: { key: keyof Summary; label: string; footnote?: boolean }[] = [
  { key: 'watched_models', label: '감시 차종' },
  { key: 'active_signals', label: '활성 시그널' },
  { key: 'new_alarms_this_week', label: '신규 알람 (이번 달)' },
  { key: 'us_recalled_kr_unremediated', label: '한국 시정 개시일 미확인', footnote: true },
]

export default function KpiStrip({ summary }: { summary: Summary }) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {ITEMS.map(({ key, label, footnote }) => (
        <div
          key={key}
          className="rounded-xl border p-6"
          style={{ borderColor: 'var(--color-border)', boxShadow: 'var(--shadow-card)' }}
        >
          <div className="text-[36px] font-semibold leading-none" style={{ color: 'var(--color-navy)' }}>
            <CountUp value={Number(summary[key])} />
          </div>
          <div className="mt-2 text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
            {label}
            {footnote && '*'}
          </div>
        </div>
      ))}
    </div>
  )
}
