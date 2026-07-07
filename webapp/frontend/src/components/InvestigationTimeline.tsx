import { motion, useReducedMotion } from 'framer-motion'
import { Car, Search, ShieldAlert, GitCompare, CheckCircle, HelpCircle, Loader2, type LucideIcon } from 'lucide-react'
import type { ChatStep } from '../lib/types'

const ICON_MAP: Record<string, LucideIcon> = {
  car: Car,
  search: Search,
  'shield-alert': ShieldAlert,
  'git-compare': GitCompare,
  'check-circle': CheckCircle,
  'help-circle': HelpCircle,
}

export default function InvestigationTimeline({ steps, pending }: { steps: ChatStep[]; pending: boolean }) {
  const reduceMotion = useReducedMotion()

  if (steps.length === 0 && !pending) {
    return (
      <p className="text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
        질문을 보내면 조사 단계가 여기 순서대로 표시됩니다.
      </p>
    )
  }

  return (
    <ol className="flex flex-col gap-4">
      {steps.map((step) => {
        const Icon = ICON_MAP[step.icon] ?? HelpCircle
        return (
          <motion.li
            key={step.id}
            className="flex gap-3"
            initial={reduceMotion ? undefined : { opacity: 0, y: 8 }}
            animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
          >
            <div
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
              style={{ backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }}
            >
              <Icon size={16} strokeWidth={1.5} />
            </div>
            <div>
              <div className="text-[13px] font-medium" style={{ color: 'var(--color-ink)' }}>
                {step.title}
              </div>
              <div className="text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
                {step.result}
              </div>
            </div>
          </motion.li>
        )
      })}
      {pending && (
        <li className="flex items-center gap-2 text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
          <Loader2 size={16} strokeWidth={1.5} className={reduceMotion ? '' : 'animate-spin'} />
          조사 중...
        </li>
      )}
    </ol>
  )
}
