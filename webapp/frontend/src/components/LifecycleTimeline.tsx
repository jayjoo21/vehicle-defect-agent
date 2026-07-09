import { useMemo, useState } from 'react'
import type { SignalRecall, TimelinePoint } from '../lib/types'
import { stateColor, stateLabel } from '../lib/tokens'

const VBW = 800
const VBH = 220
const MARGIN_L = 28
const MARGIN_R = 12
const CHART_TOP = 28
const CHART_H = 130
const LABEL_Y = CHART_TOP + CHART_H + 20

// 스펙 5절-B: 월 신고수 면적차트 + 배경 상태 밴드 + 리콜 세로선(캠페인 배지).
// 상태 밴드 색상은 대시보드 카드·핫스팟과 동일한 stateColor를 그대로 쓴다(4상태: new/rising/
// active/recalled — 스펙 예시의 5번째 색 "초록 잠잠"은 앱 전체가 쓰는 에피소드 상태 모델에
// 없어 의도적으로 제외했다. CLAUDE.md 6단계 기록 참조).
export default function LifecycleTimeline({
  timeline,
  recalls,
  title,
}: {
  timeline: TimelinePoint[]
  recalls: SignalRecall[]
  title: string
}) {
  const [hover, setHover] = useState<TimelinePoint | null>(null)
  const n = timeline.length

  const { xStep, maxCount, monthIndex } = useMemo(() => {
    const max = Math.max(...timeline.map((t) => t.count), 1)
    const step = n > 1 ? (VBW - MARGIN_L - MARGIN_R) / (n - 1) : 0
    const idx = new Map(timeline.map((t, i) => [t.month, i]))
    return { xStep: step, maxCount: max, monthIndex: idx }
  }, [timeline, n])

  if (n === 0) return null

  const xAt = (i: number) => MARGIN_L + i * xStep
  const yAt = (count: number) => CHART_TOP + CHART_H - (count / maxCount) * CHART_H

  // 상태가 바뀌는 지점마다 구간을 나눠 배경 밴드를 그린다.
  const segments: { start: number; end: number; state: TimelinePoint['state'] }[] = []
  timeline.forEach((t, i) => {
    const last = segments[segments.length - 1]
    if (last && last.state === t.state) {
      last.end = i
    } else {
      segments.push({ start: i, end: i, state: t.state })
    }
  })

  const areaPoints = timeline.map((t, i) => `${xAt(i)},${yAt(t.count)}`).join(' L ')
  const areaPath = `M ${xAt(0)},${CHART_TOP + CHART_H} L ${areaPoints} L ${xAt(n - 1)},${CHART_TOP + CHART_H} Z`

  // 리콜 세로선: report_date의 YYYY-MM이 타임라인 월 목록에 있을 때만 그린다(범위 밖이면 생략 — 지어내지 않음).
  const recallMarks = recalls
    .map((r) => ({ ...r, idx: monthIndex.get(r.report_date.slice(0, 7)) }))
    .filter((r): r is SignalRecall & { idx: number } => r.idx !== undefined)

  // x축 라벨: 48개월이면 전부 표시하면 겹치므로 6개월 간격만.
  const labelEvery = n > 18 ? 6 : n > 8 ? 3 : 1

  // y축 눈금 3개(0 / 중간 / 최댓값) — 반올림한 값으로 표시하되 0과 max가 같아지지 않게 max>=1 보장.
  const yTicks = [0, maxCount / 2, maxCount]

  return (
    <div className="card p-6">
      <h3 className="mb-1 text-sm font-semibold" style={{ color: 'var(--color-navy)' }}>
        {title}
      </h3>
      <p className="mb-3 text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
        월별 신고 수 · 배경색 = 상태(신규/증가/활성/리콜 진행) · 점선 = US 리콜 접수일
      </p>

      <svg viewBox={`0 0 ${VBW} ${VBH}`} className="w-full" style={{ height: 'auto' }}>
        {segments.map((seg, i) => {
          // 구간 경계마다 정확히 반 스텝씩 확장해 인접 밴드끼리 틈 없이 맞닿게 한다(맨 처음/끝
          // 구간만 차트 경계를 넘지 않도록 그 쪽 확장을 생략) — 이전에는 내부 경계에 확장이
          // 빠져 있어 밴드 사이에 흰 틈이 보이는 버그가 있었다.
          const left = seg.start === 0 ? xAt(0) : xAt(seg.start) - xStep / 2
          const right = seg.end === n - 1 ? xAt(n - 1) : xAt(seg.end) + xStep / 2
          return (
            <rect
              key={i}
              x={left}
              y={CHART_TOP}
              width={Math.max(right - left, 0)}
              height={CHART_H}
              fill={stateColor[seg.state]}
              opacity={0.16}
            />
          )
        })}

        {yTicks.map((v, i) => (
          <g key={i}>
            <line x1={MARGIN_L} y1={yAt(v)} x2={VBW - MARGIN_R} y2={yAt(v)} stroke="var(--color-border)" strokeWidth={1} />
            <text x={MARGIN_L - 4} y={yAt(v) + 3} fontSize={9} textAnchor="end" fill="var(--color-ink-muted)">
              {Math.round(v)}
            </text>
          </g>
        ))}

        <path d={areaPath} fill="var(--color-navy)" fillOpacity={0.18} stroke="var(--color-navy)" strokeWidth={1.5} />

        {recallMarks.map((r) => (
          <g key={r.campaign}>
            <line x1={xAt(r.idx)} y1={CHART_TOP} x2={xAt(r.idx)} y2={CHART_TOP + CHART_H} stroke="#DC2626" strokeDasharray="3,3" strokeWidth={1.5} />
            <text
              x={xAt(r.idx) + 3}
              y={CHART_TOP - 6}
              fontSize={9}
              fill="#DC2626"
              transform={`rotate(-40 ${xAt(r.idx) + 3} ${CHART_TOP - 6})`}
            >
              {r.campaign}
            </text>
          </g>
        ))}

        {timeline.map((t, i) =>
          i % labelEvery === 0 ? (
            <text key={t.month} x={xAt(i)} y={LABEL_Y} fontSize={9} textAnchor="middle" fill="var(--color-ink-muted)">
              {t.month.slice(2)}
            </text>
          ) : null,
        )}

        {timeline.map((t, i) => (
          <rect
            key={`hit-${t.month}`}
            x={xAt(i) - xStep / 2}
            y={0}
            width={xStep || 8}
            height={VBH}
            fill="transparent"
            onMouseEnter={() => setHover(t)}
            onMouseLeave={() => setHover(null)}
          />
        ))}
      </svg>

      <div className="mt-2 h-5 text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
        {hover
          ? `${hover.month} · ${hover.count}건 · ${stateLabel[hover.state]}`
          : '차트에 마우스를 올리면 월별 상세 정보가 표시됩니다.'}
      </div>
    </div>
  )
}
