import type { Summary } from '../lib/types'
import CountUp from './CountUp'

const ITEMS: { key: keyof Summary; label: string; caption?: string }[] = [
  { key: 'watched_models', label: '감시 차종' },
  { key: 'active_signals', label: '활성 시그널' },
  { key: 'new_alarms_this_week', label: '신규 알람 (이번 달)' },
  {
    key: 'us_recalled_kr_unremediated',
    label: '한국 시정 개시일 미확인',
    caption: '한국 발표는 확인됐으나 시정 개시 정보가 없는 건',
  },
]

export default function KpiStrip({ summary }: { summary: Summary }) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {ITEMS.map(({ key, label, caption }) => (
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
          </div>
          {caption && (
            <div className="mt-1 text-[11px]" style={{ color: 'var(--color-ink-muted)' }}>
              {caption}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
