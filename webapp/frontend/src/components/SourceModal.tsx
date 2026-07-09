import { AnimatePresence, motion } from 'framer-motion'
import { FileText, X } from 'lucide-react'

// 출처 칩 클릭 시 뜨는 더미 모달 — 실제 원문 연동은 아직 없고, 그 사실을 정직하게 안내만 한다.
export default function SourceModal({ open, title, onClose }: { open: boolean; title: string | null; onClose: () => void }) {
  return (
    <AnimatePresence>
      {open && title && (
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
            <button onClick={onClose} aria-label="닫기" className="absolute right-4 top-4" style={{ color: 'var(--color-ink-muted)' }}>
              <X size={18} strokeWidth={1.75} />
            </button>

            <span
              className="flex h-10 w-10 items-center justify-center rounded-full"
              style={{ backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }}
            >
              <FileText size={18} strokeWidth={1.75} />
            </span>
            <h2 className="mt-3 text-[15px] font-semibold" style={{ color: 'var(--color-ink)' }}>
              {title}
            </h2>
            <p className="mt-2 text-[13px] leading-relaxed" style={{ color: 'var(--color-ink-muted)' }}>
              원문 연동은 아직 준비 중입니다. 실제 서비스에서는 이 버튼이 해당 기관의 원문 페이지로 직접 연결됩니다. (데모 UI)
            </p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
