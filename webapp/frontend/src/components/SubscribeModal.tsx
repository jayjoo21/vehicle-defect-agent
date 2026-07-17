import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Bell, X } from 'lucide-react'
import { api } from '../lib/api'
import { useAccount } from '../lib/role'
import { useSubscriptions } from '../lib/subscriptions'

// role='user'로 로그인한 상태에서만 열린다(MyCar가 비로그인 시 /login으로 먼저 보냄) —
// 이미 로그인된 계정(account)으로 실제 subscriptions 테이블에 저장/삭제한다. 구독 여부는
// SubscriptionsProvider가 이미 가져온 목록(items)에서 찾아 별도 조회 없이 판단한다.
export default function SubscribeModal({ open, onClose, model }: { open: boolean; onClose: () => void; model: string }) {
  const account = useAccount()
  const { items, refresh } = useSubscriptions()
  const [busy, setBusy] = useState(false)

  const subscribed = items.some((i) => i.model === model)

  async function toggle() {
    if (!account) return
    setBusy(true)
    try {
      if (subscribed) {
        await api.unsubscribe(account, model)
      } else {
        await api.subscribe(account, model)
      }
      refresh()
    } finally {
      setBusy(false)
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
        >
          <motion.div
            className="absolute inset-0 bg-slate-900/50"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />

          <motion.div
            role="dialog"
            aria-modal="true"
            className="card relative z-10 w-full max-w-sm p-6"
            initial={{ opacity: 0, scale: 0.95, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 8 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
          >
            <button
              onClick={onClose}
              aria-label="닫기"
              className="absolute right-4 top-4"
              style={{ color: 'var(--color-ink-muted)' }}
            >
              <X size={18} strokeWidth={1.75} />
            </button>

            <span
              className="flex h-10 w-10 items-center justify-center rounded-full"
              style={{ backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }}
            >
              <Bell size={18} strokeWidth={1.75} />
            </span>
            <h2 className="mt-3 text-[16px] font-semibold" style={{ color: 'var(--color-ink)' }}>
              {subscribed ? '구독 중' : '알림 받기'}
            </h2>
            <p className="mt-1 text-[13px] leading-relaxed" style={{ color: 'var(--color-ink-muted)' }}>
              {subscribed
                ? `${account}로 ${model}의 새로운 결함·리콜 시그널을 구독하고 있습니다. 헤더의 알림 종에서 확인할 수 있습니다.`
                : `${account} 계정으로 ${model}을(를) 구독합니다. 새로운 결함·리콜 시그널이 발견되면 알림 드로어에 표시됩니다.`}
            </p>
            <button
              onClick={toggle}
              disabled={busy}
              className="btn-tension mt-4 w-full rounded-lg px-4 py-2.5 text-sm font-medium disabled:opacity-60"
              style={
                subscribed
                  ? { backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }
                  : { backgroundColor: 'var(--color-navy)', color: 'white' }
              }
            >
              {busy ? '처리 중...' : subscribed ? '구독 해제' : '구독하기'}
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
