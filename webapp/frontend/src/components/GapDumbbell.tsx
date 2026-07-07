import { useMemo } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import type { GapResponse, GapRow } from '../lib/types'

function dayOffset(iso: string, epoch: number): number {
  return (new Date(iso).getTime() - epoch) / 86_400_000
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}…` : text
}

export default function GapDumbbell({ data }: { data: GapResponse }) {
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

  return (
    <div className="rounded-xl border p-6" style={{ borderColor: 'var(--color-border)', boxShadow: 'var(--shadow-card)' }}>
      <h3 className="mb-1 text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
        한·미 시차 (대표 {rows.length}건)
      </h3>
      <p className="mb-4 text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
        <span style={{ color: 'var(--color-navy)' }}>●</span> 미국 접수 — <span style={{ color: '#DC2626' }}>●</span> 한국 발표 · 회색 점 =
        한국 시정 개시일 미확인*
      </p>

      <div className="flex flex-col gap-4">
        {rows.map((r, i) => {
          const usPct = (dayOffset(r.us_date, epoch) / span) * 100
          const krPct = (dayOffset(r.kr_date, epoch) / span) * 100
          const left = Math.min(usPct, krPct)
          const width = Math.abs(krPct - usPct)
          const highlighted = r.campaign === '25V808000'
          const label = r.model && r.defect_summary ? `${r.model} · ${truncate(r.defect_summary, 22)}` : r.campaign
          return (
            <div key={`${r.campaign}-${r.id}`} className={highlighted ? 'rounded-lg p-2' : ''} style={highlighted ? { backgroundColor: 'var(--color-navy-soft)' } : undefined}>
              <div className="mb-1 flex items-center justify-between gap-2 text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
                <span className="truncate" style={{ color: 'var(--color-ink)' }} title={r.defect_summary ?? undefined}>
                  {label} <span className="font-mono" style={{ color: 'var(--color-ink-muted)' }}>{r.campaign}</span>
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
            </div>
          )
        })}
      </div>

      <p className="mt-4 border-t pt-3 text-[11px]" style={{ borderColor: 'var(--color-border)', color: 'var(--color-ink-muted)' }}>
        {data.excluded_note} · * 한국 발표는 확인됐으나 시정 개시 정보가 없는 건
      </p>
    </div>
  )
}
