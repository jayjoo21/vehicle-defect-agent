import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { Bell, ChevronRight, X } from 'lucide-react'
import { api } from '../lib/api'
import { useRole } from '../lib/role'
import { useSubscriptions } from '../lib/subscriptions'
import { stateColor, stateLabel } from '../lib/tokens'

// 로그인한 사용자(role='user')의 실제 구독 차종 + 현재 시그널 상태(SubscriptionsProvider가
// 이미 가져온 값 재사용, 별도 fetch 없음)를 보여준다. 비로그인/상담사 상태에서는 로그인
// 유도만 표시.
export default function NotificationDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const role = useRole()
  const { items, loading } = useSubscriptions()
  const [sendingModel, setSendingModel] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 3000)
    return () => clearTimeout(t)
  }, [toast])

  function goToSignal(item: (typeof items)[number]) {
    onClose()
    navigate(item.id != null ? `/signals/${item.id}` : '/my-car')
  }

  // 발표 시연용 버튼 — 실제 상용 알림 발송 트리거가 아니라, 데모 중 SLACK_WEBHOOK_URL이
  // 설정된 Slack 채널로 현재 시그널 상태를 즉시 보내 "구독하면 이렇게 알림이 온다"를
  // 시연하기 위한 수동 버튼이다.
  async function sendNow(model: string) {
    setSendingModel(model)
    try {
      const res = await api.notify(model)
      if (res.sent) {
        setToast(`${model}: Slack으로 전송됨`)
      } else if (res.reason === 'not_configured') {
        setToast('SLACK_WEBHOOK_URL 미설정 — 발송되지 않았습니다')
      } else {
        setToast('발송에 실패했습니다')
      }
    } catch {
      setToast('발송에 실패했습니다')
    } finally {
      setSendingModel(null)
    }
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
              {role !== 'user' ? (
                <div className="flex flex-col items-center gap-3 px-4 py-10 text-center">
                  <Bell size={28} strokeWidth={1.5} style={{ color: 'var(--color-ink-muted)' }} />
                  <p className="text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
                    로그인 후 구독한 차종의 알림을 확인할 수 있습니다.
                  </p>
                  <button
                    onClick={() => {
                      onClose()
                      navigate('/login')
                    }}
                    className="btn-tension rounded-lg px-4 py-2 text-[13px] font-medium text-white"
                    style={{ backgroundColor: 'var(--color-navy)' }}
                  >
                    로그인하러 가기
                  </button>
                </div>
              ) : loading ? (
                <p className="px-2 py-6 text-center text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
                  불러오는 중...
                </p>
              ) : items.length === 0 ? (
                <p className="px-2 py-6 text-center text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
                  아직 구독한 차종이 없습니다. 내 차 페이지에서 &ldquo;알림 받기&rdquo;를 눌러보세요.
                </p>
              ) : (
                <ul className="flex flex-col gap-1">
                  {items.map((item) => (
                    <li key={item.model} className="rounded-lg px-3 py-3 hover:bg-slate-50">
                      <button onClick={() => goToSignal(item)} className="flex w-full items-center justify-between gap-3 text-left">
                        <div className="min-w-0">
                          <span className="text-[13px] font-bold text-slate-800">{item.model}</span>
                          {item.top_symptom && (
                            <p className="mt-1 truncate text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
                              {item.top_symptom}
                            </p>
                          )}
                          <p className="mt-0.5 text-[11px]" style={{ color: 'var(--color-ink-muted)' }}>
                            최근 신고 {item.recent_count}건
                          </p>
                        </div>
                        <div className="flex shrink-0 items-center gap-1.5">
                          <span
                            className="flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium"
                            style={{ backgroundColor: `${stateColor[item.state]}1A`, color: stateColor[item.state] }}
                          >
                            {stateLabel[item.state]}
                          </span>
                          <ChevronRight size={14} strokeWidth={1.75} style={{ color: 'var(--color-ink-muted)' }} />
                        </div>
                      </button>
                      <button
                        onClick={() => sendNow(item.model)}
                        disabled={sendingModel === item.model}
                        className="mt-2 text-[11px] font-medium disabled:opacity-50"
                        style={{ color: 'var(--color-navy)' }}
                      >
                        {sendingModel === item.model ? '보내는 중...' : '지금 알림 보내기'}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {toast && (
              <div
                className="mx-3 mb-2 rounded-lg px-3 py-2 text-[12px] text-white"
                style={{ backgroundColor: 'var(--color-navy)' }}
              >
                {toast}
              </div>
            )}

            <div className="border-t px-5 py-3 text-[11px]" style={{ borderColor: 'var(--color-border)', color: 'var(--color-ink-muted)' }}>
              &ldquo;지금 알림 보내기&rdquo;는 발표 시연용입니다. 구독은 계정에 저장되지만 데모 재시작 시 초기화될 수 있습니다.
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
