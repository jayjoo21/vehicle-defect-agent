import { useNavigate, Link } from 'react-router-dom'
import { MessageCircle, FileText } from 'lucide-react'
import type { HeroCardData } from '../lib/types'
import { stateColor, stateLabel } from '../lib/tokens'
import Sparkline from './Sparkline'

// 대시보드 최상단 "오늘의 시그널" — DASHBOARD_PRIORITY(active>rising>recalled) 1순위 카드 1건만 확대 표시.
export default function HeroSignalCard({ hero }: { hero: HeroCardData }) {
  const navigate = useNavigate()
  const color = stateColor[hero.state]

  return (
    <div
      className="rounded-2xl border p-8"
      style={{ borderColor: color, backgroundColor: `${color}0D`, boxShadow: 'var(--shadow-card)' }}
    >
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div>
          <p className="mb-1 text-[12px] font-medium uppercase tracking-wide" style={{ color }}>
            오늘의 시그널
          </p>
          <h2 className="text-4xl font-bold hover:underline">
            <Link to={`/signals/${hero.id}`} style={{ color: 'var(--color-navy)' }}>
              {hero.model}
            </Link>
          </h2>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="rounded-full px-2.5 py-1 text-[12px] font-medium" style={{ color, backgroundColor: `${color}1A` }}>
              {stateLabel[hero.state]}
            </span>
            <span className="text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
              최근 1개월 {hero.recent_count.toLocaleString('ko-KR')}건 ({hero.month})
            </span>
          </div>
        </div>
        <Sparkline values={hero.sparkline} color={color} />
      </div>

      {hero.quote && (
        <p className="mt-5 border-l-2 pl-4 text-[14px] leading-relaxed" style={{ borderColor: color, color: 'var(--color-ink)' }}>
          &ldquo;{hero.quote.text}&rdquo;
          <span className="ml-2 whitespace-nowrap text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
            ODINO {hero.quote.odino}
          </span>
        </p>
      )}

      <div className="mt-6 flex items-center gap-4">
        <button
          onClick={() => navigate(`/chat?q=${encodeURIComponent(`내 차 ${hero.model}인데 관련 증상이 있어요`)}`)}
          className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-[13px] font-medium text-white"
          style={{ backgroundColor: 'var(--color-navy)' }}
        >
          <MessageCircle size={14} strokeWidth={1.5} />
          조사하기
        </button>
        {hero.report_id != null && (
          <Link
            to={`/reports/${hero.report_id}`}
            className="inline-flex items-center gap-1 text-[13px] font-medium"
            style={{ color: 'var(--color-navy)' }}
          >
            <FileText size={14} strokeWidth={1.5} />
            리포트 보기
          </Link>
        )}
      </div>
    </div>
  )
}
