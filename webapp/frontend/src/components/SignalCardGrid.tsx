import { useMemo, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import type { SignalCardData } from '../lib/types'
import type { SignalState } from '../lib/tokens'
import { stateLabel } from '../lib/tokens'
import SignalCard from './SignalCard'

type TabKey = SignalState | 'all' | 'focus'

// active→rising→recalled→new: 지금 당장 봐야 할 것(아직 리콜 없는 급증)을 이미 대응 중인 리콜보다 앞에 둔다.
// (engine/episode.py DASHBOARD_PRIORITY와 동일 순서 — resolved는 에피소드 상태에 없어 목록에서 제외)
const TABS: { key: TabKey; label: string }[] = [
  { key: 'focus', label: '주목 필요' },
  { key: 'all', label: '전체' },
  { key: 'rising', label: stateLabel.rising },
  { key: 'active', label: stateLabel.active },
  { key: 'recalled', label: stateLabel.recalled },
]

const STATE_PRIORITY: Record<SignalState, number> = {
  active: 4,
  rising: 3,
  recalled: 2,
  new: 1,
  resolved: 0,
}

export default function SignalCardGrid({ cards }: { cards: SignalCardData[] }) {
  const [tab, setTab] = useState<TabKey>('focus')
  const reduceMotion = useReducedMotion()

  const filtered = useMemo(() => {
    let base: SignalCardData[]
    if (tab === 'focus') {
      base = cards.filter((c) => c.state === 'active' || c.state === 'rising' || (c.state === 'recalled' && c.recall_recent))
    } else if (tab === 'all') {
      base = cards.filter((c) => c.state !== 'new')
    } else {
      base = cards.filter((c) => c.state === tab)
    }
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
