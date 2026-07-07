import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { useFetch } from '../lib/useFetch'
import { useMyCar } from '../lib/useMyCar'
import CarRegistration from '../components/CarRegistration'
import CarViewer from '../components/CarViewer'
import DomainDetailCard from '../components/DomainDetailCard'

export default function MyCar() {
  const { car, register, reset } = useMyCar()
  const [justRegistered, setJustRegistered] = useState(false)
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const detailRef = useRef<HTMLDivElement>(null)

  const map = useFetch(
    () => (car ? api.vehicleMap(car.model, car.year) : Promise.reject(new Error('등록된 차량 없음'))),
    [car?.model, car?.year],
  )

  useEffect(() => {
    if (!justRegistered || !map.data) return
    // 핫스팟 6개가 200ms 간격으로 순차 점등을 마친 뒤(마지막 지연 1.0s + 등장 0.3s) 토스트 표시
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

  const selected = map.data.domains.find((d) => d.domain === selectedDomain) ?? null

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold" style={{ color: 'var(--color-navy)' }}>
          내 차
        </h1>
        <button onClick={reset} className="text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
          다른 차로 변경
        </button>
      </div>

      <CarViewer
        model={map.data.model}
        year={map.data.year}
        domains={map.data.domains}
        selectedDomain={selectedDomain}
        onSelect={(d) => {
          setSelectedDomain(d)
          requestAnimationFrame(() => detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
        }}
        animateIn={justRegistered}
      />

      {!map.data.year_matched_complaints && (
        <p className="text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
          {map.data.year}년식 표본이 부족해 다른 연식 신고 이력을 함께 참고했습니다.
        </p>
      )}

      <div ref={detailRef}>
        {selected ? (
          <DomainDetailCard domain={selected} model={map.data.model} />
        ) : (
          <p className="rounded-xl border p-6 text-sm" style={{ borderColor: 'var(--color-border)', color: 'var(--color-ink-muted)' }}>
            핫스팟을 클릭하면 상세 정보가 여기에 표시됩니다.
          </p>
        )}
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
