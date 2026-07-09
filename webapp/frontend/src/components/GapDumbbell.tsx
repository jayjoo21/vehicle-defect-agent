import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { motion, useReducedMotion } from 'framer-motion'
import type { GapResponse, GapRow } from '../lib/types'
import { SOURCE_LINE } from '../lib/tokens'

// 사용자 지정값 — CLAUDE.md Task 6 "미국선행 14건, 중앙값 ~33일"과 동일한 실측 중앙값을
// 이 8건 큐레이션 차트의 시각적 기준선으로 사용한다(이 8건만의 중앙값을 별도로 재계산하지 않음).
const MEDIAN_GAP_DAYS = 33
const SANTA_FE_CAMPAIGN = '25V808000'

function dayOffset(iso: string, epoch: number): number {
  return (new Date(iso).getTime() - epoch) / 86_400_000
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}…` : text
}

export default function GapDumbbell({ data, modelIds }: { data: GapResponse; modelIds: Record<string, number> }) {
  const reduceMotion = useReducedMotion()

  // 백엔드(get_gap)가 이미 |gap_days|<=365 필터 + 캠페인당 대표 1행 dedup을 적용해 반환한다.
  const rows = data.gap as (GapRow & { us_date: string; kr_date: string })[]

  const { epoch, span } = useMemo(() => {
    if (rows.length === 0) return { epoch: 0, span: 1 }
    const allDates = rows.flatMap((r) => [new Date(r.us_date).getTime(), new Date(r.kr_date).getTime()])
    const min = Math.min(...allDates)
    const max = Math.max(...allDates)
    return { epoch: min, span: (max - min) / 86_400_000 || 1 }
  }, [rows])

  const medianPct = (MEDIAN_GAP_DAYS / span) * 100

  return (
    <div className="card p-4">
      <h3 className="mb-0.5 text-[13px] font-semibold" style={{ color: 'var(--color-ink)' }}>
        미국 신고는 한국 리콜보다 빨랐다 — 최대 152일
      </h3>
      <p className="mb-2.5 text-[11px]" style={{ color: 'var(--color-ink-muted)' }}>
        한·미 시차 · 대표 {rows.length}건 · <span style={{ color: 'var(--color-navy)' }}>●</span> 미국 접수 — <span style={{ color: '#DC2626' }}>●</span>{' '}
        한국 발표 · 회색 점 = 한국 시정 개시일 미확인*
      </p>

      <div className="mb-3 flex items-center gap-2 text-[11px]" style={{ color: 'var(--color-ink-muted)' }}>
        <span className="w-24 shrink-0">기준선</span>
        <div className="relative h-4 max-w-[200px] flex-1">
          <div
            className="absolute top-1/2 h-0 -translate-y-1/2 border-t-2 border-dashed"
            style={{ width: `${medianPct}%`, borderColor: 'var(--color-ink-muted)' }}
          />
          <span className="absolute whitespace-nowrap" style={{ left: `${medianPct}%`, top: '50%', transform: 'translate(4px, -50%)' }}>
            중앙값 +{MEDIAN_GAP_DAYS}일
          </span>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        {rows.map((r, i) => {
          const usPct = (dayOffset(r.us_date, epoch) / span) * 100
          const krPct = (dayOffset(r.kr_date, epoch) / span) * 100
          const left = Math.min(usPct, krPct)
          const width = Math.abs(krPct - usPct)
          const highlighted = r.campaign === SANTA_FE_CAMPAIGN
          const label = r.model && r.defect_summary ? `${r.model} · ${truncate(r.defect_summary, 22)}` : r.campaign
          const signalId = r.model ? modelIds[r.model] : undefined
          return (
            <div key={`${r.campaign}-${r.id}`} className={highlighted ? 'rounded-lg p-2' : ''} style={highlighted ? { backgroundColor: 'var(--color-navy-soft)' } : undefined}>
              <div className="mb-1 flex items-center justify-between gap-2 text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
                <span className="truncate" title={r.defect_summary ?? undefined}>
                  {signalId != null ? (
                    <Link to={`/signals/${signalId}`} className="hover:underline" style={{ color: 'var(--color-ink)' }}>
                      {label}
                    </Link>
                  ) : (
                    <span style={{ color: 'var(--color-ink)' }}>{label}</span>
                  )}{' '}
                  <span className="font-mono" style={{ color: 'var(--color-ink-muted)' }}>{r.campaign}</span>
                </span>
                <span className="shrink-0 font-medium" style={{ color: r.gap_days && r.gap_days < 0 ? '#DC2626' : 'var(--color-navy)' }}>
                  {r.gap_days !== null ? `${r.gap_days > 0 ? '+' : ''}${r.gap_days}일` : '-'}
                </span>
              </div>
              <div className="relative h-5">
                <motion.div
                  className="absolute top-1/2 h-[2px] -translate-y-1/2"
                  style={{ left: `${left}%`, width: `${width}%`, backgroundColor: 'var(--color-border)', transformOrigin: usPct <= krPct ? 'left' : 'right' }}
                  initial={reduceMotion ? undefined : { scaleX: 0 }}
                  animate={reduceMotion ? undefined : { scaleX: 1 }}
                  transition={{ duration: 0.6, delay: i * 0.12, ease: 'easeOut' }}
                />
                <div
                  className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full"
                  style={{ left: `${usPct}%`, backgroundColor: 'var(--color-navy)' }}
                  title={`미국 접수 ${r.us_date}`}
                />
                <div
                  className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full"
                  style={{ left: `${krPct}%`, backgroundColor: '#DC2626' }}
                  title={`한국 발표 ${r.kr_date}`}
                />
                {!r.kr_start_date && (
                  <div
                    className="absolute top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-white"
                    style={{ left: `${krPct}%`, backgroundColor: 'var(--color-ink-muted)' }}
                    title="한국 시정 시작일 미기재"
                  />
                )}
              </div>
              {highlighted && (
                <p className="mt-1 text-[11px] italic" style={{ color: 'var(--color-ink-muted)' }}>
                  리콜까지 5개월, 국내 무조치 기간
                </p>
              )}
            </div>
          )
        })}
      </div>

      <div className="mt-4 flex items-end justify-between gap-3 border-t pt-3" style={{ borderColor: 'var(--color-border)' }}>
        <p className="text-[11px]" style={{ color: 'var(--color-ink-muted)' }}>
          {data.excluded_note} · * 한국 발표는 확인됐으나 시정 개시 정보가 없는 건
        </p>
        <p className="shrink-0 whitespace-nowrap text-[9px]" style={{ color: 'var(--color-ink-muted)' }}>
          {SOURCE_LINE}
        </p>
      </div>
    </div>
  )
}
