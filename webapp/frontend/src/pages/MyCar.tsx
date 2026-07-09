import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { api } from '../lib/api'
import { useFetch } from '../lib/useFetch'
import { useMyCar } from '../lib/useMyCar'
import { HOTSPOT_LABELS } from '../lib/hotspots'
import { linkifyGlossary } from '../lib/glossary'
import { stateColor, stateLabel } from '../lib/tokens'
import CarRegistration from '../components/CarRegistration'
import CarViewer from '../components/CarViewer'
import DomainDetailCard from '../components/DomainDetailCard'
import SubscribeModal from '../components/SubscribeModal'
import Skeleton from '../components/Skeleton'

// 5.5단계: 2열 레이아웃 — 좌측 정보 기둥(차종명/상태 요약/도메인 목록), 우측 상단 3D(60% 크기,
// sticky). 도메인은 왼쪽 목록에서도, 3D/SVG 뷰어 핫스팟에서도 선택 가능하도록 selectedDomain
// 상태를 공유한다.
// 6단계: 좌측 목록은 이력 있는 도메인만 카드로 보여주고, 이력 없는 도메인은 하단에 한 줄
// 요약("계기판 외 4개 도메인: 이력 없음")으로 접는다 — 6개를 전부 카드로 나열하면 대부분
// "이력 없음"이라 신호 대비 잡음이 컸음. 선택된 도메인의 상세 카드는 우측(차 아래)으로 이동.
export default function MyCar() {
  const { car, register, reset } = useMyCar()
  const [justRegistered, setJustRegistered] = useState(false)
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [subscribeOpen, setSubscribeOpen] = useState(false)

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
    return <Skeleton height={320} />
  }
  if (map.error || !map.data) {
    return <p className="text-sm text-red-600">차량 정보를 불러오지 못했습니다: {map.error}</p>
  }

  const domains = map.data.domains
  const selected = domains.find((d) => d.domain === selectedDomain) ?? null
  const stateCounts = { active: 0, rising: 0, recalled: 0, new: 0, resolved: 0 } as Record<string, number>
  for (const d of domains) stateCounts[d.state] += 1

  const historyDomains = domains.filter((d) => d.state !== 'new')
  const emptyDomains = domains.filter((d) => d.state === 'new')
  const emptyLabel = (d: (typeof domains)[number]) => HOTSPOT_LABELS[d.domain] ?? d.domain

  function selectDomain(d: string) {
    setSelectedDomain(d)
  }

  return (
    <div className="grid grid-cols-1 items-start gap-8 lg:grid-cols-2">
      {/* 좌측: 정보 기둥 — 하나의 카드로 묶음 */}
      <div className="card order-2 flex flex-col gap-6 p-6 lg:order-1">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-3xl font-bold" style={{ color: 'var(--color-navy)' }}>
                {map.data.model}
              </h1>
              <button
                onClick={() => setSubscribeOpen(true)}
                className="btn-tension inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[12px] font-medium"
                style={{ backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }}
              >
                🔔 알림 받기
              </button>
            </div>
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

        {historyDomains.length > 0 ? (
          <ul className="flex flex-col gap-1.5">
            {historyDomains.map((d) => {
              const color = stateColor[d.state]
              const isSelected = selectedDomain === d.domain
              return (
                <li key={d.domain}>
                  <button
                    onClick={() => selectDomain(d.domain)}
                    className={`flex w-full items-center justify-between rounded-lg border px-4 py-2.5 text-left text-[13px] transition-all duration-200 ${
                      isSelected ? '' : 'hover:-translate-y-0.5 hover:bg-slate-50 hover:shadow-sm'
                    }`}
                    style={{
                      borderColor: isSelected ? color : 'var(--color-border)',
                      backgroundColor: isSelected ? `${color}0D` : undefined,
                    }}
                  >
                    <span className="flex items-center gap-2" style={{ color: 'var(--color-ink)' }}>
                      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
                      {linkifyGlossary(HOTSPOT_LABELS[d.domain] ?? d.domain)}
                    </span>
                    <span style={{ color }}>{stateLabel[d.state]}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        ) : (
          <p className="text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
            이력이 있는 도메인이 없습니다.
          </p>
        )}

        {emptyDomains.length > 0 && (
          <p className="text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
            {emptyDomains.length === 1
              ? `${emptyLabel(emptyDomains[0])}: 이력 없음`
              : `${emptyLabel(emptyDomains[0])} 외 ${emptyDomains.length - 1}개 도메인: 이력 없음`}
          </p>
        )}
      </div>

      {/* 우측: 3D/SVG 뷰어(전체 폭) + 선택된 도메인 상세 카드(차 아래), 상단 고정 */}
      <div className="order-1 flex flex-col gap-4 lg:sticky lg:top-6 lg:order-2">
        <div className="relative w-full">
          <CarViewer
            model={map.data.model}
            year={map.data.year}
            domains={domains}
            selectedDomain={selectedDomain}
            onSelect={selectDomain}
            animateIn={justRegistered}
          />
          {/* 가짜 그림자 — 차 하단에 시각적 안정감을 주는 타원형 블러 */}
          <div
            className="pointer-events-none absolute -bottom-3 left-1/2 h-6 w-[65%] -translate-x-1/2 rounded-[50%] blur-md"
            style={{ background: 'radial-gradient(ellipse, rgba(15,23,42,0.16) 0%, transparent 75%)' }}
          />
        </div>

        <AnimatePresence mode="wait" initial={false}>
          {selected ? (
            <motion.div
              key={selected.domain}
              style={{ overflow: 'hidden' }}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.25, ease: 'easeInOut' }}
            >
              <DomainDetailCard domain={selected} model={map.data.model} />
            </motion.div>
          ) : (
            <motion.p
              key="empty"
              style={{ overflow: 'hidden' }}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.25, ease: 'easeInOut' }}
              className="card p-6 text-sm"
            >
              <span style={{ color: 'var(--color-ink-muted)' }}>
                도메인을 선택하면 관련 리콜·신고 상세 정보가 여기에 표시됩니다.
              </span>
            </motion.p>
          )}
        </AnimatePresence>
      </div>

      {toast && (
        <div
          className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-lg px-4 py-2.5 text-sm text-white shadow-lg"
          style={{ backgroundColor: 'var(--color-navy)' }}
        >
          {toast}
        </div>
      )}

      <SubscribeModal open={subscribeOpen} onClose={() => setSubscribeOpen(false)} model={map.data.model} />
    </div>
  )
}
