import { HOTSPOTS_BY_BODY_TYPE } from '../lib/hotspots'
import type { BodyType } from '../lib/bodyType'
import type { VehicleDomain } from '../lib/types'
import { hotspotSummary } from '../lib/hotspotSummary'
import HotspotDot from './HotspotDot'
import GridOverlay from './GridOverlay'

const VIEW_W = 400
const VIEW_H = 200

// 차체형태별 측면 실루엣 — suv(높은 루프)/sedan(낮고 긴 루프)/sports(가장 낮은 캐빈)로 3종 분리.
const SVG_PATH: Record<BodyType, string> = {
  suv: 'M40,150 L40,120 Q40,100 60,95 L140,95 Q160,60 220,60 L280,60 Q320,60 330,95 L370,95 L370,150 Z',
  sedan: 'M40,150 L40,125 Q40,110 60,105 L130,105 Q155,75 210,75 L265,75 Q300,75 320,105 L370,105 L370,150 Z',
  sports: 'M40,150 L40,130 Q45,120 70,118 L150,118 Q175,90 215,88 L260,88 Q290,92 320,118 L370,118 L370,150 Z',
}

// 3D(R3F) 로딩 실패·3초 초과 시 폴백으로 쓰이는 차 측면 일러스트 SVG.
// 핫스팟 배치·상호작용은 3D 버전과 동일해야 하므로 lib/hotspots.ts 좌표를 그대로 재사용한다.
export default function CarViewerSvg({
  model,
  year,
  bodyType,
  domains,
  selectedDomain,
  onSelect,
  animateIn = false,
}: {
  model: string
  year: string
  bodyType: BodyType
  domains: VehicleDomain[]
  selectedDomain: string | null
  onSelect: (domain: string) => void
  animateIn?: boolean
}) {
  const domainByKey = Object.fromEntries(domains.map((d) => [d.domain, d]))
  const hotspots = HOTSPOTS_BY_BODY_TYPE[bodyType]

  return (
    <div className="relative aspect-video min-h-[360px] w-full overflow-hidden rounded-2xl bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-slate-100 to-transparent">
      <GridOverlay />
      <div className="absolute left-6 top-6">
        <div className="text-lg font-semibold" style={{ color: 'var(--color-ink)' }}>
          {model}
        </div>
        <div className="text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
          {year}
        </div>
      </div>

      <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} className="absolute inset-0 h-full w-full" aria-hidden>
        <line x1={20} y1={155} x2={380} y2={155} stroke="var(--color-border)" strokeWidth={2} />
        <path d={SVG_PATH[bodyType]} fill="none" stroke="var(--color-navy)" strokeWidth={2} strokeOpacity={0.6} />
        <circle cx={120} cy={155} r={20} fill="none" stroke="var(--color-navy)" strokeOpacity={0.6} strokeWidth={2} />
        <circle cx={300} cy={155} r={20} fill="none" stroke="var(--color-navy)" strokeOpacity={0.6} strokeWidth={2} />
      </svg>

      <div className="absolute inset-0">
        {hotspots.map((h, i) => {
          const d = domainByKey[h.domain]
          if (!d) return null
          return (
            <HotspotDot
              key={h.domain}
              xPct={(h.x / VIEW_W) * 100}
              yPct={(h.y / VIEW_H) * 100}
              state={d.state}
              label={h.label}
              summary={hotspotSummary(d)}
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
