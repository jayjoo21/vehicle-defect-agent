export default function Sparkline({ values, color }: { values: number[]; color: string }) {
  const w = 100
  const h = 28
  const max = Math.max(...values, 1)
  const min = Math.min(...values, 0)
  const range = max - min || 1
  const step = values.length > 1 ? w / (values.length - 1) : w
  const points = values.map((v, i) => `${i * step},${h - ((v - min) / range) * h}`).join(' ')

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="overflow-visible">
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}
