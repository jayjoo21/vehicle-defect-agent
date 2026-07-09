import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, X } from 'lucide-react'
import { api } from '../lib/api'

interface SubscriptionItem {
  model: string
  year: string
  message: string
  badgeLabel: string
  badgeColor: string
  badgeBg: string
}

// 데모용 구독 목록 — 실제 구독 저장·발송 백엔드는 아직 없다(MyCar의 SubscribeModal과 동일 원칙).
export const MOCK_SUBSCRIPTIONS: SubscriptionItem[] = [
  { model: 'ELANTRA', year: '2021', message: 'ADAS 카메라 리콜 진행 중', badgeLabel: '리콜', badgeColor: '#DC2626', badgeBg: '#FEE2E2' },
  { model: 'IONIQ 5', year: '2023', message: 'ICCU 관련 불만 급증 감지', badgeLabel: '급증', badgeColor: '#EA580C', badgeBg: '#FFEDD5' },
]

// 항목 클릭 시 이동할 곳은 진짜 데이터로 연결한다 — 목록 자체는 더미지만, 클릭했을 때 가는
// 곳까지 가짜일 필요는 없어서 실제 signals 조회로 해당 차종의 시그널 상세를 찾아 이동한다
// (없으면 내 차 페이지로 폴백).
export default function NotificationDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const [modelIds, setModelIds] = useState<Record<string, number>>({})

  useEffect(() => {
    if (!open) return
    api
      .signals()
      .then((res) => setModelIds(Object.fromEntries(res.signals.map((s) => [s.model, s.id]))))
      .catch(() => {})
  }, [open])

  function goToSignal(model: string) {
    const id = modelIds[model]
    onClose()
    navigate(id != null ? `/signals/${id}` : '/my-car')
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="fixed inset-0 z-40 bg-slate-900/50 backdrop-blur-sm"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          />
          <motion.div
            role="dialog"
            aria-label="구독 중인 시그널 알림"
            className="fixed right-0 top-0 z-50 flex h-full w-96 max-w-full flex-col bg-white shadow-2xl"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ duration: 0.28, ease: 'easeOut' }}
          >
            <div className="flex items-center justify-between border-b px-5 py-4" style={{ borderColor: 'var(--color-border)' }}>
              <h2 className="text-[15px] font-semibold" style={{ color: 'var(--color-ink)' }}>
                구독 중인 시그널 알림
              </h2>
              <button onClick={onClose} aria-label="닫기" style={{ color: 'var(--color-ink-muted)' }}>
                <X size={18} strokeWidth={1.75} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-3">
              <ul className="flex flex-col gap-1">
                {MOCK_SUBSCRIPTIONS.map((item) => (
                  <li key={item.model}>
                    <button
                      onClick={() => goToSignal(item.model)}
                      className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-3 text-left transition-colors hover:bg-slate-50"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-[13px] font-bold text-slate-800">{item.model}</span>
                          <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">{item.year}</span>
                        </div>
                        <p className="mt-1 truncate text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
                          {item.message}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1.5">
                        <span
                          className="rounded-full px-2 py-0.5 text-[11px] font-medium"
                          style={{ backgroundColor: item.badgeBg, color: item.badgeColor }}
                        >
                          {item.badgeLabel}
                        </span>
                        <ChevronRight size={14} strokeWidth={1.75} style={{ color: 'var(--color-ink-muted)' }} />
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            </div>

            <div className="border-t px-5 py-3 text-[11px]" style={{ borderColor: 'var(--color-border)', color: 'var(--color-ink-muted)' }}>
              데모 데이터 — 실제 구독 저장·알림 발송은 아직 연결되어 있지 않습니다.
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
