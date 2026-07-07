import { useEffect, useState } from 'react'
import { motion, useReducedMotion, AnimatePresence } from 'framer-motion'
import { Car, Search, ShieldAlert, GitCompare, CheckCircle, HelpCircle, Loader2, ChevronDown, type LucideIcon } from 'lucide-react'
import type { ChatStep } from '../lib/types'

const ICON_MAP: Record<string, LucideIcon> = {
  car: Car,
  search: Search,
  'shield-alert': ShieldAlert,
  'git-compare': GitCompare,
  'check-circle': CheckCircle,
  'help-circle': HelpCircle,
}

// 대화 흐름 인라인에 붙는 조사 타임라인 — 진행 중엔 단계가 하나씩 나타나며 스피너로 다음 단계를
// 예고하고, 완료(pending=false)되면 자동으로 접혀 요약 한 줄만 남는다(클릭하면 다시 펼침).
export default function InvestigationTimeline({ steps, pending }: { steps: ChatStep[]; pending: boolean }) {
  const reduceMotion = useReducedMotion()
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    if (!pending && steps.length > 0) setCollapsed(true)
  }, [pending, steps.length])

  if (steps.length === 0 && !pending) return null

  if (collapsed) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        className="flex items-center gap-1.5 self-start rounded-full px-3 py-1.5 text-[12px]"
        style={{ backgroundColor: 'var(--color-bg-subtle)', color: 'var(--color-ink-muted)' }}
      >
        <CheckCircle size={13} strokeWidth={1.5} />
        조사 {steps.length}단계 완료
        <ChevronDown size={13} strokeWidth={1.5} />
      </button>
    )
  }

  return (
    <div className="rounded-xl border p-4" style={{ borderColor: 'var(--color-border)' }}>
      {steps.length > 0 && (
        <button
          onClick={() => setCollapsed(true)}
          className="mb-3 text-[12px]"
          style={{ color: 'var(--color-ink-muted)' }}
        >
          조사 타임라인 접기
        </button>
      )}
      <ol className="flex flex-col gap-4">
        <AnimatePresence initial={false}>
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
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-[13px] font-medium" style={{ color: 'var(--color-ink)' }}>
                      {step.title}
                    </span>
                    <span
                      className="rounded-full px-1.5 py-0.5 text-[10px] font-medium"
                      style={{ backgroundColor: 'var(--color-bg-subtle)', color: 'var(--color-ink-muted)' }}
                    >
                      {step.tool}
                    </span>
                    <span className="text-[10px]" style={{ color: 'var(--color-ink-muted)' }}>
                      {step.duration_ms}ms
                    </span>
                  </div>
                  <div className="text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
                    {step.result}
                  </div>
                </div>
              </motion.li>
            )
          })}
        </AnimatePresence>
        {pending && (
          <li className="flex items-center gap-2 text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
            <Loader2 size={16} strokeWidth={1.5} className={reduceMotion ? '' : 'animate-spin'} />
            조사 중...
          </li>
        )}
      </ol>
    </div>
  )
}
