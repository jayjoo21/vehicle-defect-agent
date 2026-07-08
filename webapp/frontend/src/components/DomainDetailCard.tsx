import { useNavigate } from 'react-router-dom'
import { MessageCircle } from 'lucide-react'
import type { VehicleDomain } from '../lib/types'
import { stateColor, stateLabel } from '../lib/tokens'
import { HOTSPOT_LABELS } from '../lib/hotspots'
import Sparkline from './Sparkline'

export default function DomainDetailCard({ domain, model }: { domain: VehicleDomain; model: string }) {
  const navigate = useNavigate()
  const color = stateColor[domain.state]
  const quote = domain.evidence?.type === 'complaint' ? domain.evidence.text : null
  const label = HOTSPOT_LABELS[domain.domain] ?? domain.domain
  // 6.6단계: 신고 0건인데 매칭된 리콜은 있는 도메인(예: 국내 시판 전 이력이 없는 신형 리콜)은
  // 캠페인 카드를 상단 주인공으로 올리고, 신고 건수는 큰 숫자 대신 작은 캡션으로 내린다 —
  // 원래 레이아웃대로면 "0건"이 가장 눈에 띄는 숫자가 되어 정작 있는 정보(리콜)가 묻혔다.
  const campaignFirst = domain.complaint_count === 0 && domain.evidence?.type === 'recall'

  function investigate() {
    navigate(`/chat?q=${encodeURIComponent(`내 차 ${model}인데 ${label} 관련 증상이 있어요`)}`)
  }

  return (
    <div className="rounded-xl border p-6" style={{ borderColor: 'var(--color-border)', boxShadow: 'var(--shadow-card)' }}>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold" style={{ color: 'var(--color-ink)' }}>
          {domain.domain}
        </h3>
        <span className="rounded-full px-2 py-0.5 text-[12px] font-medium" style={{ color, backgroundColor: `${color}1A` }}>
          {stateLabel[domain.state]}
        </span>
      </div>

      {campaignFirst && domain.evidence?.type === 'recall' ? (
        <>
          <div className="mb-1.5 rounded-lg p-4" style={{ backgroundColor: `${color}0D`, border: `1px solid ${color}33` }}>
            <div className="flex items-center gap-2">
              <span className="rounded px-2 py-1 font-mono text-[13px] font-semibold" style={{ backgroundColor: '#fff', color }}>
                {domain.evidence.campaign}
              </span>
              <span className="text-[14px] font-semibold" style={{ color }}>
                리콜 진행 중
              </span>
            </div>
            <p className="mt-1.5 text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
              접수 {domain.evidence.report_date}
            </p>
            {domain.kr_gap && (
              <p className="mt-1 text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
                한국 발표 {domain.kr_gap.kr_date} ({domain.kr_gap.gap_days != null && domain.kr_gap.gap_days >= 0 ? '+' : ''}
                {domain.kr_gap.gap_days}일)
              </p>
            )}
            {domain.recall_count > 1 && (
              <p className="mt-1 text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
                관련 리콜 {domain.recall_count}건 중 최신 1건 표시
              </p>
            )}
          </div>
          <p className="mb-4 text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
            이 차종·도메인 관련 신고 0건 (리콜은 있으나 접수된 소비자 불만 없음)
          </p>
        </>
      ) : (
        <>
          <div className="mb-4 flex items-end justify-between">
            <div>
              <div className="text-2xl font-semibold" style={{ color: 'var(--color-navy)' }}>
                {domain.complaint_count.toLocaleString('ko-KR')}건
              </div>
              <div className="text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
                관련 신고 수
              </div>
            </div>
            {domain.trend.length >= 2 && (
              <Sparkline values={domain.trend.map((t) => t.count)} color={color} />
            )}
          </div>

          {domain.evidence?.type === 'recall' && (
            <div className="mb-4 rounded-lg p-3" style={{ backgroundColor: 'var(--color-bg-subtle)' }}>
              <div className="flex items-center gap-2 text-[13px]">
                <span className="rounded px-1.5 py-0.5 font-mono text-[11px]" style={{ backgroundColor: '#fff', color: 'var(--color-ink-muted)' }}>
                  {domain.evidence.campaign}
                </span>
                <span style={{ color: 'var(--color-ink-muted)' }}>접수 {domain.evidence.report_date}</span>
              </div>
              {domain.kr_gap && (
                <p className="mt-1 text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
                  한국 발표 {domain.kr_gap.kr_date} ({domain.kr_gap.gap_days != null && domain.kr_gap.gap_days >= 0 ? '+' : ''}
                  {domain.kr_gap.gap_days}일)
                </p>
              )}
              {domain.recall_count > 1 && (
                <p className="mt-1 text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
                  관련 리콜 {domain.recall_count}건 중 최신 1건 표시
                </p>
              )}
            </div>
          )}
        </>
      )}

      {quote && (
        <p className="mb-4 text-[13px] leading-relaxed" style={{ color: 'var(--color-ink-muted)' }}>
          &ldquo;{quote}&rdquo;
        </p>
      )}

      {domain.state === 'new' && (
        <p className="mb-4 text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
          이 차종·도메인으로 감지된 시그널이 없습니다.
        </p>
      )}

      <button
        onClick={investigate}
        className="inline-flex items-center gap-1.5 text-[13px] font-medium"
        style={{ color: 'var(--color-navy)' }}
      >
        <MessageCircle size={14} strokeWidth={1.5} />
        이 증상 조사하기
      </button>
    </div>
  )
}
