import { Car, Activity, Bell, AlertCircle, type LucideIcon } from 'lucide-react'
import type { Summary } from '../lib/types'
import CountUp from './CountUp'

// 각주(*)의 실제 설명 텍스트는 페이지 레벨 각주로 옮겼다(Dashboard.tsx) — 카드 자체는 라벨만 보여준다.
const ITEMS: { key: keyof Summary; label: string; icon: LucideIcon; footnote?: boolean }[] = [
  { key: 'watched_models', label: '감시 차종', icon: Car },
  { key: 'active_signals', label: '활성 시그널', icon: Activity },
  { key: 'new_alarms_this_week', label: '신규 알람 (이번 달)', icon: Bell },
  { key: 'us_recalled_kr_unremediated', label: '한국 시정 개시일 미확인', icon: AlertCircle, footnote: true },
]

export default function KpiStrip({ summary }: { summary: Summary }) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {ITEMS.map(({ key, label, icon: Icon, footnote }) => (
        <div key={key} className="card card-hover flex flex-col gap-3 p-5">
          <span
            className="flex h-9 w-9 items-center justify-center rounded-lg"
            style={{ backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }}
          >
            <Icon size={18} strokeWidth={1.75} />
          </span>
          <div className="text-[32px] font-bold leading-none" style={{ color: 'var(--color-navy)' }}>
            <CountUp value={Number(summary[key])} />
          </div>
          <div className="text-[12px] font-medium uppercase tracking-wide" style={{ color: 'var(--color-ink-muted)' }}>
            {label}
            {footnote && '*'}
          </div>
        </div>
      ))}
    </div>
  )
}
