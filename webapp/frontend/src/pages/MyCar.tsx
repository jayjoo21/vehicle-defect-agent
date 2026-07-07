import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useFetch } from '../lib/useFetch'
import { useMyCar } from '../lib/useMyCar'
import { HOTSPOT_LABELS } from '../lib/hotspots'
import { stateColor, stateLabel } from '../lib/tokens'
import CarRegistration from '../components/CarRegistration'
import CarViewer from '../components/CarViewer'
import DomainDetailCard from '../components/DomainDetailCard'

// 5.5단계: 2열 레이아웃 — 좌측 정보 기둥(차종명/상태 요약/도메인 목록/선택된 도메인 상세 카드),
// 우측 상단 3D(60% 크기, sticky). 도메인은 왼쪽 목록에서도, 3D/SVG 뷰어 핫스팟에서도 선택 가능
// 하도록 selectedDomain 상태를 공유한다.
export default function MyCar() {
  const { car, register, reset } = useMyCar()
  const [justRegistered, setJustRegistered] = useState(false)
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const map = useFetch(
    () => (car ? api.vehicleMap(car.model, car.year) : Promise.reject(new Error('등록된 차량 없음'))),
    [car?.model, car?.year],
  )

  useEffect(() => {
    if (!justRegistered || !map.data) return
    const active = map.data.domains.filter((d) => d.state === 'active').length
    const recalled = map.data.domains.filter((d) => d.state === 'recalled').length
    const showTimer = setTimeout(() => {
      setToast(`${map.data!.model} (${map.data!.year}): 활성 시그널 ${active}건, 리콜 진행 ${recalled}건`)
    }, 1400)
    const hideTimer = setTimeout(() => setToast(null), 6400)
    return () => {
      clearTimeout(showTimer)
      clearTimeout(hideTimer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [justRegistered, map.data])

  if (!car) {
    return (
      <CarRegistration
        onComplete={(model, year) => {
          setJustRegistered(true)
          register({ model, year })
        }}
      />
    )
  }

  if (map.loading) {
    return <div className="h-64 animate-pulse rounded-2xl" style={{ backgroundColor: 'var(--color-bg-subtle)' }} />
  }
  if (map.error || !map.data) {
    return <p className="text-sm text-red-600">차량 정보를 불러오지 못했습니다: {map.error}</p>
  }

  const domains = map.data.domains
  const selected = domains.find((d) => d.domain === selectedDomain) ?? null
  const stateCounts = { active: 0, rising: 0, recalled: 0, new: 0, resolved: 0 } as Record<string, number>
  for (const d of domains) stateCounts[d.state] += 1

  function selectDomain(d: string) {
    setSelectedDomain(d)
  }

  return (
    <div className="grid grid-cols-1 items-start gap-8 lg:grid-cols-2">
      {/* 좌측: 정보 기둥 */}
      <div className="order-2 flex flex-col gap-6 lg:order-1">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold" style={{ color: 'var(--color-navy)' }}>
              {map.data.model}
            </h1>
            <p className="text-sm" style={{ color: 'var(--color-ink-muted)' }}>
              {map.data.year}년식
            </p>
          </div>
          <button onClick={reset} className="text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
            다른 차로 변경
          </button>
        </div>

        <div className="flex flex-wrap gap-4 text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
          {(['active', 'rising', 'recalled'] as const).map((s) =>
            stateCounts[s] > 0 ? (
              <span key={s} className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: stateColor[s] }} />
                {stateLabel[s]} {stateCounts[s]}건
              </span>
            ) : null,
          )}
          <span>이력 없음 {stateCounts.new}건</span>
        </div>

        {!map.data.year_matched_complaints && (
          <p className="text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
            {map.data.year}년식 표본이 부족해 다른 연식 신고 이력을 함께 참고했습니다.
          </p>
        )}

        <ul className="flex flex-col gap-1.5">
          {domains.map((d) => {
            const color = stateColor[d.state]
            const isSelected = selectedDomain === d.domain
            return (
              <li key={d.domain}>
                <button
                  onClick={() => selectDomain(d.domain)}
                  className="flex w-full items-center justify-between rounded-lg border px-4 py-2.5 text-left text-[13px] transition-colors"
                  style={{
                    borderColor: isSelected ? color : 'var(--color-border)',
                    backgroundColor: isSelected ? `${color}0D` : 'transparent',
                  }}
                >
                  <span className="flex items-center gap-2" style={{ color: 'var(--color-ink)' }}>
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
                    {HOTSPOT_LABELS[d.domain] ?? d.domain}
                  </span>
                  <span style={{ color }}>{stateLabel[d.state]}</span>
                </button>
              </li>
            )
          })}
        </ul>

        {selected ? (
          <DomainDetailCard domain={selected} model={map.data.model} />
        ) : (
          <p className="rounded-xl border p-6 text-sm" style={{ borderColor: 'var(--color-border)', color: 'var(--color-ink-muted)' }}>
            도메인을 선택하면 관련 리콜·신고 상세 정보가 여기에 표시됩니다.
          </p>
        )}
      </div>

      {/* 우측: 3D/SVG 뷰어, 60% 크기로 축소, 상단 고정 */}
      <div className="order-1 lg:sticky lg:top-6 lg:order-2">
        <div className="mx-auto w-full sm:w-[60%]">
          <CarViewer
            model={map.data.model}
            year={map.data.year}
            domains={domains}
            selectedDomain={selectedDomain}
            onSelect={selectDomain}
            animateIn={justRegistered}
          />
        </div>
      </div>

      {toast && (
        <div
          className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-lg px-4 py-2.5 text-sm text-white shadow-lg"
          style={{ backgroundColor: 'var(--color-navy)' }}
        >
          {toast}
        </div>
      )}
    </div>
  )
}
