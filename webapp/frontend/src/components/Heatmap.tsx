import { useMemo, useState } from 'react'
import type { HeatmapResponse } from '../lib/types'

function cellColor(count: number, max: number): string {
  if (count === 0) return 'var(--color-bg-subtle)'
  // 감마 보정(0.55)으로 중저값 구간의 명도 차를 벌려 대비를 강화한다(선형 보간은 대부분의
  // 셀이 낮은 값에 몰려 회색빛으로 뭉뚱그려 보였음).
  const t = Math.min(count / max, 1) ** 0.55
  // bgSubtle(#F6F7F9) -> navy(#002C5F) 보간
  const from = [0xf6, 0xf7, 0xf9]
  const to = [0x00, 0x2c, 0x5f]
  const rgb = from.map((f, i) => Math.round(f + (to[i] - f) * t))
  return `rgb(${rgb.join(',')})`
}

export default function Heatmap({ data }: { data: HeatmapResponse }) {
  const [hover, setHover] = useState<{ model: string; month: string; count: number; alarm: boolean } | null>(null)
  const max = useMemo(() => Math.max(...data.cells.map((c) => c.count), 1), [data.cells])
  const cellByKey = useMemo(() => {
    const map = new Map<string, (typeof data.cells)[number]>()
    for (const c of data.cells) map.set(`${c.model}|${c.month}`, c)
    return map
  }, [data.cells])

  return (
    <div className="rounded-xl border p-6" style={{ borderColor: 'var(--color-border)', boxShadow: 'var(--shadow-card)' }}>
      <h3 className="mb-1 text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
        차종×월 히트맵
      </h3>
      <p className="mb-4 text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
        발화(스파이크) 이력이 있는 차종 {data.models.length}개 · 최근 {data.months.length}개월 · 빨강 테두리 = 알람 발화
      </p>
      <div className="overflow-x-auto">
        <table className="border-collapse text-[12px]">
          <thead>
            <tr>
              <th className="sticky left-0 bg-white pr-2 text-left" style={{ color: 'var(--color-ink-muted)' }}></th>
              {data.months.map((m, i) => (
                <th key={m} className="px-[1px] pb-1 text-center font-normal" style={{ color: 'var(--color-ink-muted)' }}>
                  <span className="block whitespace-nowrap">{i % 3 === 0 ? m.slice(2) : ''}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.models.map((model) => (
              <tr key={model}>
                <td
                  className="sticky left-0 whitespace-nowrap bg-white pr-2 text-right font-medium"
                  style={{ color: 'var(--color-ink)' }}
                >
                  {model}
                </td>
                {data.months.map((month) => {
                  const cell = cellByKey.get(`${model}|${month}`)
                  const count = cell?.count ?? 0
                  const alarm = cell?.alarm ?? false
                  return (
                    <td key={month} className="p-[1px]">
                      <div
                        className="h-6 w-6 cursor-pointer rounded-sm"
                        style={{
                          backgroundColor: cellColor(count, max),
                          border: alarm ? '2px solid var(--color-state-active)' : 'none',
                        }}
                        onMouseEnter={() => setHover({ model, month, count, alarm })}
                        onMouseLeave={() => setHover(null)}
                      />
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 h-5 text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
        {hover
          ? `${hover.model} · ${hover.month} · ${hover.count}건${hover.alarm ? ' · 알람 발화' : ''}`
          : '셀에 마우스를 올리면 상세 정보가 표시됩니다.'}
      </div>
    </div>
  )
}
