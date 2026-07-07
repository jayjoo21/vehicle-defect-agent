import { HOTSPOTS } from '../lib/hotspots'
import type { VehicleDomain } from '../lib/types'
import HotspotDot from './HotspotDot'

const VIEW_W = 400
const VIEW_H = 200

// 3D(R3F) 로딩 실패·3초 초과 시 폴백으로 쓰이는 차 측면 일러스트 SVG.
// 핫스팟 배치·상호작용은 3D 버전과 동일해야 하므로 lib/hotspots.ts 좌표를 그대로 재사용한다.
export default function CarViewerSvg({
  model,
  year,
  domains,
  selectedDomain,
  onSelect,
  animateIn = false,
}: {
  model: string
  year: string
  domains: VehicleDomain[]
  selectedDomain: string | null
  onSelect: (domain: string) => void
  animateIn?: boolean
}) {
  const domainByKey = Object.fromEntries(domains.map((d) => [d.domain, d]))

  return (
    <div className="relative overflow-hidden rounded-2xl" style={{ backgroundColor: '#0B1220', aspectRatio: '16/9' }}>
      <div className="absolute left-6 top-6 text-white">
        <div className="text-lg font-semibold">{model}</div>
        <div className="text-[13px]" style={{ color: '#9CA3AF' }}>
          {year}
        </div>
      </div>

      <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} className="absolute inset-0 h-full w-full" aria-hidden>
        <line x1={20} y1={155} x2={380} y2={155} stroke="#1E293B" strokeWidth={2} />
        <path
          d="M40,150 L40,120 Q40,100 60,95 L140,95 Q160,60 220,60 L280,60 Q320,60 330,95 L370,95 L370,150 Z"
          fill="none"
          stroke="#334155"
          strokeWidth={2}
        />
        <circle cx={120} cy={155} r={20} fill="#0B1220" stroke="#334155" strokeWidth={2} />
        <circle cx={300} cy={155} r={20} fill="#0B1220" stroke="#334155" strokeWidth={2} />
      </svg>

      <div className="absolute inset-0">
        {HOTSPOTS.map((h, i) => {
          const d = domainByKey[h.domain]
          if (!d) return null
          const summary =
            d.complaint_count > 0
              ? `관련 신고 ${d.complaint_count}건`
              : d.recall_count > 0
                ? `리콜 ${d.recall_count}건`
                : '이력 없음'
          return (
            <HotspotDot
              key={h.domain}
              xPct={(h.x / VIEW_W) * 100}
              yPct={(h.y / VIEW_H) * 100}
              state={d.state}
              label={h.label}
              summary={summary}
              selected={selectedDomain === h.domain}
              onClick={() => onSelect(h.domain)}
              delay={animateIn ? i * 0.2 : 0}
            />
          )
        })}
      </div>
    </div>
  )
}
