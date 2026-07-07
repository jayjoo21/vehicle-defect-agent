import { useEffect, useMemo, useState } from 'react'
import CarViewer3D from './CarViewer3D'
import CarViewerSvg from './CarViewerSvg'
import CarViewerErrorBoundary from './CarViewerErrorBoundary'
import { modelGlbPath } from '../lib/bodyType'
import type { VehicleDomain } from '../lib/types'

const LOAD_TIMEOUT_MS = 3000

function supportsWebGL(): boolean {
  try {
    const canvas = document.createElement('canvas')
    return !!(canvas.getContext('webgl2') || canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
  } catch {
    return false
  }
}

type Mode = 'checking' | '3d' | 'svg'

// 3D(R3F)가 기본이고, WebGL 미지원·로딩 3초 초과·런타임 에러 시 SVG 폴백으로 전환한다.
// 폴백은 핫스팟 배치·상태색·클릭 동작이 3D와 동일해야 하므로 CarViewerSvg를 그대로 재사용.
export default function CarViewer({
  model,
  year,
  domains,
  selectedDomain,
  onSelect,
  animateIn,
}: {
  model: string
  year: string
  domains: VehicleDomain[]
  selectedDomain: string | null
  onSelect: (domain: string) => void
  animateIn?: boolean
}) {
  const [mode, setMode] = useState<Mode>('checking')
  const [loaded, setLoaded] = useState(false)
  const path = useMemo(() => modelGlbPath(model), [model])

  useEffect(() => {
    setMode(supportsWebGL() ? '3d' : 'svg')
    setLoaded(false)
  }, [path])

  useEffect(() => {
    if (mode !== '3d' || loaded) return
    const timeout = setTimeout(() => setMode('svg'), LOAD_TIMEOUT_MS)
    return () => clearTimeout(timeout)
  }, [mode, loaded])

  if (mode === 'checking') {
    return <div className="rounded-2xl" style={{ backgroundColor: '#0B1220', aspectRatio: '16/9' }} />
  }

  if (mode === 'svg') {
    return (
      <CarViewerSvg model={model} year={year} domains={domains} selectedDomain={selectedDomain} onSelect={onSelect} animateIn={animateIn} />
    )
  }

  return (
    <div className="relative overflow-hidden rounded-2xl" style={{ backgroundColor: '#0B1220', aspectRatio: '16/9' }}>
      <div className="pointer-events-none absolute left-6 top-6 z-10 text-white">
        <div className="text-lg font-semibold">{model}</div>
        <div className="text-[13px]" style={{ color: '#9CA3AF' }}>
          {year}
        </div>
      </div>
      <CarViewerErrorBoundary onError={() => setMode('svg')}>
        <CarViewer3D
          path={path}
          domains={domains}
          selectedDomain={selectedDomain}
          onSelect={onSelect}
          onLoaded={() => setLoaded(true)}
        />
      </CarViewerErrorBoundary>
    </div>
  )
}
