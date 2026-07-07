import { useMemo, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import type { SignalCardData } from '../lib/types'
import type { SignalState } from '../lib/tokens'
import { stateLabel } from '../lib/tokens'
import SignalCard from './SignalCard'

const TABS: { key: SignalState | 'all'; label: string }[] = [
  { key: 'all', label: '전체' },
  { key: 'rising', label: stateLabel.rising },
  { key: 'active', label: stateLabel.active },
  { key: 'recalled', label: stateLabel.recalled },
  { key: 'resolved', label: stateLabel.resolved },
]

const STATE_PRIORITY: Record<SignalState, number> = {
  recalled: 4,
  active: 3,
  rising: 2,
  new: 1,
  resolved: 0,
}

export default function SignalCardGrid({ cards }: { cards: SignalCardData[] }) {
  const [tab, setTab] = useState<SignalState | 'all'>('all')
  const reduceMotion = useReducedMotion()

  const filtered = useMemo(() => {
    const base = tab === 'all' ? cards.filter((c) => c.state !== 'new') : cards.filter((c) => c.state === tab)
    return [...base].sort((a, b) => STATE_PRIORITY[b.state] - STATE_PRIORITY[a.state])
  }, [cards, tab])

  return (
    <section>
      <div className="mb-4 flex gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className="rounded-full px-3 py-1.5 text-[13px] font-medium transition-colors"
            style={
              tab === t.key
                ? { backgroundColor: 'var(--color-navy)', color: '#fff' }
                : { backgroundColor: 'var(--color-bg-subtle)', color: 'var(--color-ink-muted)' }
            }
          >
            {t.label}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <p className="rounded-xl border p-6 text-sm" style={{ borderColor: 'var(--color-border)', color: 'var(--color-ink-muted)' }}>
          현재 이 상태로 감지된 시그널이 없습니다.
        </p>
      ) : (
        <motion.div
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
          initial="hidden"
          animate="show"
          variants={{ hidden: {}, show: { transition: { staggerChildren: reduceMotion ? 0 : 0.06 } } }}
        >
          {filtered.map((c) => (
            <motion.div
              key={c.model}
              variants={{ hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0 } }}
              transition={{ duration: 0.25 }}
            >
              <SignalCard card={c} />
            </motion.div>
          ))}
        </motion.div>
      )}
    </section>
  )
}
