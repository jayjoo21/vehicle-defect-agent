import { useState, type FormEvent } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Bell, Mail, X } from 'lucide-react'

// UI만 구현된 더미 구독 모달 — 실제 이메일 발송·구독 저장 백엔드는 아직 연결되어 있지 않다.
export default function SubscribeModal({ open, onClose, model }: { open: boolean; onClose: () => void; model: string }) {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)

  function handleClose() {
    onClose()
    setTimeout(() => {
      setSubmitted(false)
      setEmail('')
    }, 200)
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!email.trim()) return
    setSubmitted(true)
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
            onClick={handleClose}
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
              onClick={handleClose}
              aria-label="닫기"
              className="absolute right-4 top-4"
              style={{ color: 'var(--color-ink-muted)' }}
            >
              <X size={18} strokeWidth={1.75} />
            </button>

            {!submitted ? (
              <>
                <span
                  className="flex h-10 w-10 items-center justify-center rounded-full"
                  style={{ backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }}
                >
                  <Bell size={18} strokeWidth={1.75} />
                </span>
                <h2 className="mt-3 text-[16px] font-semibold" style={{ color: 'var(--color-ink)' }}>
                  알림 받기
                </h2>
                <p className="mt-1 text-[13px] leading-relaxed" style={{ color: 'var(--color-ink-muted)' }}>
                  {model}에서 새로운 결함·리콜 시그널이 발견되면 이메일로 알려드립니다.
                </p>
                <form onSubmit={submit} className="mt-4 flex flex-col gap-2">
                  <div className="relative">
                    <Mail
                      size={14}
                      strokeWidth={1.75}
                      className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2"
                      style={{ color: 'var(--color-ink-muted)' }}
                    />
                    <input
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@example.com"
                      className="w-full rounded-lg border py-2.5 pl-9 pr-3 text-sm outline-none"
                      style={{ borderColor: 'var(--color-border)' }}
                    />
                  </div>
                  <button
                    type="submit"
                    className="btn-tension rounded-lg px-4 py-2.5 text-sm font-medium text-white"
                    style={{ backgroundColor: 'var(--color-navy)' }}
                  >
                    구독하기
                  </button>
                </form>
              </>
            ) : (
              <div className="py-4 text-center">
                <span
                  className="mx-auto flex h-10 w-10 items-center justify-center rounded-full"
                  style={{ backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }}
                >
                  <Bell size={18} strokeWidth={1.75} />
                </span>
                <p className="mt-3 text-[14px] font-medium" style={{ color: 'var(--color-ink)' }}>
                  구독 신청이 접수됐습니다
                </p>
                <p className="mt-1 text-[12px] leading-relaxed" style={{ color: 'var(--color-ink-muted)' }}>
                  {email}로 {model} 시그널 알림을 보내드릴 예정입니다. (데모 UI — 실제 발송은 아직 연결되어 있지 않습니다)
                </p>
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
