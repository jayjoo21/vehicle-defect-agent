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
        <h3 className="text-lg font-semibold" style={{ color: 'var(--color-ink)' }}>
          {card.model}
        </h3>
        <span
          className="rounded-full px-2 py-0.5 text-[12px] font-medium"
          style={{ color, backgroundColor: `${color}1A` }}
        >
          {stateLabel[card.state]}
        </span>
      </div>

      <p className="min-h-[20px] text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
        {card.top_symptom ?? '대표 증상 미확인 (표본 부족)'}
      </p>

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

      {card.report_id ? (
        <Link
          to={`/reports/${card.report_id}`}
          className="mt-1 inline-flex items-center gap-1 text-[13px] font-medium"
          style={{ color: 'var(--color-navy)' }}
        >
          <FileText size={14} strokeWidth={1.5} />
          리포트 보기
        </Link>
      ) : (
        <span className="mt-1 text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
          리포트 없음
        </span>
      )}
    </div>
  )
}
