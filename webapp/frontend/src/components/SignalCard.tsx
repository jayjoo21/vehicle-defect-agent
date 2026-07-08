import { Link } from 'react-router-dom'
import { FileText } from 'lucide-react'
import type { SignalCardData } from '../lib/types'
import { stateColor, stateLabel } from '../lib/tokens'
import Sparkline from './Sparkline'

export default function SignalCard({ card }: { card: SignalCardData }) {
  const color = stateColor[card.state]

  return (
    <div
      className="flex flex-col gap-3 rounded-xl border p-6"
      style={{ borderColor: 'var(--color-border)', boxShadow: 'var(--shadow-card)' }}
    >
      <div className="flex items-start justify-between">
        <Link to={`/signals/${card.id}`} className="text-lg font-semibold hover:underline" style={{ color: 'var(--color-ink)' }}>
          {card.model}
        </Link>
        <span
          className="rounded-full px-2 py-0.5 text-[12px] font-medium"
          style={{ color, backgroundColor: `${color}1A` }}
        >
          {stateLabel[card.state]}
        </span>
      </div>

      {card.top_symptom && (
        <p className="text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
          {card.top_symptom}
        </p>
      )}

      <div className="flex items-end justify-between">
        <div>
          <div className="text-2xl font-semibold" style={{ color: 'var(--color-navy)' }}>
            {card.recent_count.toLocaleString('ko-KR')}건
          </div>
          <div className="text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
            최근 1개월 신고 ({card.month})
          </div>
        </div>
        <Sparkline values={card.sparkline} color={color} />
      </div>

      {card.report_id != null && (
        <Link
          to={`/reports/${card.report_id}`}
          className="mt-1 inline-flex items-center gap-1 text-[13px] font-medium"
          style={{ color: 'var(--color-navy)' }}
        >
          <FileText size={14} strokeWidth={1.5} />
          리포트 보기
        </Link>
      )}
    </div>
  )
}
