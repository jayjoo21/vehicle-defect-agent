import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as d3 from 'd3'
import type { HeatmapResponse } from '../lib/types'
import { SOURCE_LINE } from '../lib/tokens'
import { useElementSize } from '../lib/useElementSize'
import LegendDot from './LegendDot'

const ROW_HEIGHT = 34
const OVERLAP = 2.4 // 피크가 row 높이의 몇 배까지 위 row를 침범할 수 있는지(조이플롯 특유의 겹침)
// top 마진은 맨 위 행의 최대 피크(ROW_HEIGHT*(OVERLAP-1))를 온전히 담을 만큼 커야 한다 —
// 그보다 작으면 SVG 기본 overflow:hidden에 의해 맨 위 행의 스파이크가 잘려나간다.
const MARGIN = { top: Math.ceil(ROW_HEIGHT * (OVERLAP - 1)) + 4, right: 16, bottom: 4, left: 78 }
const BLUE = '#3B82F6'
const ROSE = '#F43F5E'

// 연속된 알람(스파이크) 월 인덱스를 [시작,끝] 구간들로 묶는다 — 각 구간을 같은 area path에
// clipPath로 덧대면, 빨강으로 반전되는 부분도 곡선 경계가 파랑 영역과 완전히 일치한다.
function contiguousRuns(flags: boolean[]): [number, number][] {
  const runs: [number, number][] = []
  let start: number | null = null
  flags.forEach((f, i) => {
    if (f && start === null) start = i
    if (!f && start !== null) {
      runs.push([start, i - 1])
      start = null
    }
  })
  if (start !== null) runs.push([start, flags.length - 1])
  return runs
}

interface HoverInfo {
  model: string
  month: string
  count: number
  alarm: boolean
  xPct: number
  yPct: number
}

export default function RidgelinePlot({ data, modelIds }: { data: HeatmapResponse; modelIds: Record<string, number> }) {
  const navigate = useNavigate()
  const [containerRef, { width: containerWidth }] = useElementSize<HTMLDivElement>()
  const [hover, setHover] = useState<HoverInfo | null>(null)

  const countByKey = useMemo(() => {
    const map = new Map<string, number>()
    for (const c of data.cells) map.set(`${c.model}|${c.month}`, c.count)
    return map
  }, [data.cells])
  const alarmByKey = useMemo(() => {
    const map = new Map<string, boolean>()
    for (const c of data.cells) map.set(`${c.model}|${c.month}`, c.alarm)
    return map
  }, [data.cells])
  const maxCount = useMemo(() => Math.max(...data.cells.map((c) => c.count), 1), [data.cells])

  const width = Math.max(containerWidth, 1)
  const innerWidth = Math.max(width - MARGIN.left - MARGIN.right, 1)
  const height = MARGIN.top + MARGIN.bottom + data.models.length * ROW_HEIGHT

  const x = d3.scaleLinear().domain([0, Math.max(data.months.length - 1, 1)]).range([0, innerWidth])
  const y = d3.scaleLinear().domain([0, maxCount]).range([0, ROW_HEIGHT * OVERLAP])
  const areaGen = d3
    .area<number>()
    .x((_, i) => x(i))
    .y0(ROW_HEIGHT)
    .y1((v) => ROW_HEIGHT - y(v))
    .curve(d3.curveBasis)

  return (
    <div className="card flex h-full flex-col p-6">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-[13px] font-semibold" style={{ color: 'var(--color-ink)' }}>
            알람은 특정 차종에 띠를 이룬다
          </h3>
          <p className="mt-0.5 text-[11px]" style={{ color: 'var(--color-ink-muted)' }}>
            차종×월 릿지라인 · 발화 이력이 있는 차종 {data.models.length}개 · 최근 {data.months.length}개월
          </p>
        </div>
        <span className="shrink-0 text-xs text-slate-400">차종을 클릭하면 시그널 상세로 이동</span>
      </div>

      <div className="mb-4 flex flex-wrap gap-4">
        <LegendDot color={BLUE} label="신고량" />
        <LegendDot color={ROSE} label="알람 발화(스파이크)" />
      </div>

      <div ref={containerRef} className="relative h-full min-h-[500px] flex-1 overflow-hidden">
        {width > 1 && (
          <svg width={width} height={height} className="block">
            <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
              {data.models.map((model, mi) => {
                const values = data.months.map((m) => countByKey.get(`${model}|${m}`) ?? 0)
                const flags = data.months.map((m) => alarmByKey.get(`${model}|${m}`) ?? false)
                const path = areaGen(values) ?? ''
                const runs = contiguousRuns(flags)
                const signalId = modelIds[model]
                const bandTop = -(ROW_HEIGHT * (OVERLAP - 1))
                const bandHeight = ROW_HEIGHT * OVERLAP
                const cellWidth = innerWidth / data.months.length

                return (
                  <g
                    key={model}
                    transform={`translate(0, ${mi * ROW_HEIGHT})`}
                    className={signalId != null ? 'cursor-pointer' : undefined}
                    onClick={() => signalId != null && navigate(`/signals/${signalId}`)}
                  >
                    <path d={path} fill={BLUE} fillOpacity={0.3} stroke={BLUE} strokeOpacity={0.6} strokeWidth={1} />
                    {runs.map(([s0, s1], ri) => (
                      <clipPath key={ri} id={`ridge-clip-${mi}-${ri}`}>
                        <rect x={x(s0) - cellWidth / 2} y={bandTop} width={x(s1) - x(s0) + cellWidth} height={bandHeight} />
                      </clipPath>
                    ))}
                    {runs.map((_run, ri) => (
                      <path key={`a-${ri}`} d={path} fill={ROSE} fillOpacity={0.55} clipPath={`url(#ridge-clip-${mi}-${ri})`} />
                    ))}
                    <text x={-10} y={ROW_HEIGHT - 8} textAnchor="end" fontSize={11} fontWeight={500} fill="#475569">
                      {model}
                    </text>
                    {data.months.map((month, monthIdx) => (
                      <rect
                        key={month}
                        x={x(monthIdx) - cellWidth / 2}
                        y={bandTop}
                        width={cellWidth}
                        height={bandHeight}
                        fill="transparent"
                        onMouseEnter={() =>
                          setHover({
                            model,
                            month,
                            count: values[monthIdx],
                            alarm: flags[monthIdx],
                            xPct: ((MARGIN.left + x(monthIdx)) / width) * 100,
                            yPct: ((MARGIN.top + mi * ROW_HEIGHT) / height) * 100,
                          })
                        }
                        onMouseLeave={() => setHover(null)}
                      />
                    ))}
                  </g>
                )
              })}
            </g>
          </svg>
        )}

        {/* 글래스모피즘 툴팁 — 내 차 페이지 핫스팟·히트맵과 동일한 재질·전환 */}
        {hover && (
          <div
            className="pointer-events-none absolute z-20 flex -translate-x-1/2 -translate-y-full flex-col items-center whitespace-nowrap rounded-lg border border-white/40 bg-white/80 px-2.5 py-1.5 text-[11px] font-medium leading-tight text-slate-700 opacity-100 shadow-xl backdrop-blur-md transition-opacity duration-150"
            style={{ left: `${hover.xPct}%`, top: `${hover.yPct}%`, marginTop: -6 }}
          >
            <span className="font-bold text-slate-800">{hover.model}</span>
            <span>
              {hover.month} · {hover.count.toLocaleString('ko-KR')}건{hover.alarm ? ' · 알람 발화' : ''}
            </span>
          </div>
        )}
      </div>

      <div className="mt-3 flex items-end justify-end">
        <p className="shrink-0 whitespace-nowrap text-[9px]" style={{ color: 'var(--color-ink-muted)' }}>
          {SOURCE_LINE}
        </p>
      </div>
    </div>
  )
}
