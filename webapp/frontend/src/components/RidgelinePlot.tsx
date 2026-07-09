import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as d3 from 'd3'
import type { HeatmapResponse } from '../lib/types'
import { SOURCE_LINE } from '../lib/tokens'
import { useElementSize } from '../lib/useElementSize'
import LegendDot from './LegendDot'

const ROW_HEIGHT = 34
const OVERLAP = 1.4 // 피크가 row 높이의 몇 배까지 위 row를 침범할 수 있는지(조이플롯 특유의 겹침) — 과하면 가독성이 떨어져 1.3~1.5 범위로 억제
// top 마진은 맨 위 행의 최대 피크(ROW_HEIGHT*(OVERLAP-1))를 온전히 담을 만큼 커야 한다 —
// 그보다 작으면 SVG 기본 overflow:hidden에 의해 맨 위 행의 스파이크가 잘려나간다.
const MARGIN = { top: Math.ceil(ROW_HEIGHT * (OVERLAP - 1)) + 4, right: 16, bottom: 22, left: 84 }
const BLUE = '#3B82F6'
const ROSE = '#F43F5E'

// 연속된 알람(스파이크) 월 인덱스를 [시작,끝] 구간으로 묶는다 — 구간마다 같은 area path를
// 그라디언트로 덧칠하면 빨강 경계가 파랑 곡선과 완전히 일치하면서 가장자리만 부드럽게 페이드된다.
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
  const axisRef = useRef<SVGGElement>(null)
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

  const width = Math.max(containerWidth, 1)
  const innerWidth = Math.max(width - MARGIN.left - MARGIN.right, 1)
  const height = MARGIN.top + MARGIN.bottom + data.models.length * ROW_HEIGHT

  const x = useMemo(
    () => d3.scaleLinear().domain([0, Math.max(data.months.length - 1, 1)]).range([0, innerWidth]),
    [innerWidth, data.months.length],
  )

  // 시간축 — 도메인/눈금 선은 지우고 텍스트만 옅게(slate-400) 남긴다. d3-axis는 DOM을 직접
  // 조작하는 명령형 API라 React 렌더 트리 밖에서 useEffect로 별도 실행한다.
  useEffect(() => {
    if (!axisRef.current) return
    const tickIndices = data.months.map((_, i) => i).filter((i) => i % 3 === 0)
    const axis = d3
      .axisBottom(x)
      .tickValues(tickIndices)
      .tickFormat((v) => data.months[v as number]?.slice(2) ?? '')
      .tickSizeOuter(0)
    const sel = d3.select(axisRef.current).call(axis)
    sel.select('.domain').remove()
    sel.selectAll('.tick line').remove()
    sel.selectAll('.tick text').attr('fill', '#94a3b8').attr('font-size', 11).attr('dy', '0.8em')
  }, [x, data.months])

  return (
    <div className="card flex h-full flex-col p-6">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-[13px] font-semibold" style={{ color: 'var(--color-ink)' }}>
            차종별 결함 시그널 발생 추이
          </h3>
          <p className="mt-0.5 text-[11px]" style={{ color: 'var(--color-ink-muted)' }}>
            최근 12개월간 차종별 신고 밀도 및 이상 징후(Spike) 탐지 구간
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
                // 행별 자체 정규화 — 전 차종 공통 스케일을 쓰면 한 차종의 극단값이 나머지 전부를
                // 눌러버려(대부분 밋밋) 조이플롯 특유의 겹침이 나오지 않는다. 각 행이 "자기 최댓값"
                // 기준으로 OVERLAP 배까지 차오르게 해 모든 행이 고르게 위 행을 침범하도록 한다.
                const rowMax = Math.max(...values, 1)
                const rowY = d3.scaleLinear().domain([0, rowMax]).range([0, ROW_HEIGHT * OVERLAP])
                const areaGen = d3
                  .area<number>()
                  .x((_, i) => x(i))
                  .y0(ROW_HEIGHT)
                  .y1((v) => ROW_HEIGHT - rowY(v))
                  .curve(d3.curveBasis)
                const path = areaGen(values) ?? ''
                // 능선(위쪽 경계) 윤곽선 — area와 동일한 곡선을 따로 그려 흰 선으로 앞/뒤 봉우리를
                // 시각적으로 갈라준다(안 그러면 겹치는 구간에서 앞산·뒷산이 뭉쳐 보임).
                const lineGen = d3
                  .line<number>()
                  .x((_, i) => x(i))
                  .y((v) => ROW_HEIGHT - rowY(v))
                  .curve(d3.curveBasis)
                const ridgeLine = lineGen(values) ?? ''
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
                    {/* mix-blend-mode:multiply — 겹치는 봉우리가 자연스럽게 짙어져 등고선처럼 읽힌다.
                        낮은 fill-opacity(0.45)로 여러 겹 겹쳐도 뭉개지거나 새까매지지 않게 함. */}
                    <path d={path} fill={BLUE} fillOpacity={0.45} style={{ mixBlendMode: 'multiply' }} />
                    {runs.length > 0 && (
                      <defs>
                        {runs.map(([s0, s1], ri) => {
                          const runStartX = x(s0) - cellWidth / 2
                          const runEndX = x(s1) + cellWidth / 2
                          const feather = Math.min(cellWidth * 0.6, 16)
                          const gradStart = runStartX - feather
                          const gradEnd = Math.max(runEndX + feather, gradStart + 1)
                          const fadeInPct = (feather / (gradEnd - gradStart)) * 100
                          const fadeOutPct = 100 - fadeInPct
                          return (
                            <linearGradient key={ri} id={`ridge-fade-${mi}-${ri}`} gradientUnits="userSpaceOnUse" x1={gradStart} y1={0} x2={gradEnd} y2={0}>
                              <stop offset="0%" stopColor={ROSE} stopOpacity={0} />
                              <stop offset={`${fadeInPct}%`} stopColor={ROSE} stopOpacity={0.5} />
                              <stop offset={`${fadeOutPct}%`} stopColor={ROSE} stopOpacity={0.5} />
                              <stop offset="100%" stopColor={ROSE} stopOpacity={0} />
                            </linearGradient>
                          )
                        })}
                      </defs>
                    )}
                    {runs.map((_run, ri) => (
                      <path key={`a-${ri}`} d={path} fill={`url(#ridge-fade-${mi}-${ri})`} style={{ mixBlendMode: 'multiply' }} />
                    ))}
                    {/* 능선 흰 윤곽선 — 앞/뒤 봉우리 경계를 갈라 겹침 구간에서도 각 행을 구분할 수 있게 함 */}
                    <path d={ridgeLine} fill="none" stroke="#ffffff" strokeWidth={1.5} strokeOpacity={0.8} strokeLinejoin="round" strokeLinecap="round" />
                    <text x={-14} y={ROW_HEIGHT - 8} textAnchor="end" fontSize={11} fontWeight={500} fill="#475569">
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
            <g ref={axisRef} transform={`translate(${MARGIN.left},${MARGIN.top + data.models.length * ROW_HEIGHT + 4})`} />
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
