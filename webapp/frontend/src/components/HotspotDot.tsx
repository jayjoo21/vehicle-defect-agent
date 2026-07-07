import { motion, useReducedMotion } from 'framer-motion'
import type { SignalState } from '../lib/tokens'
import { stateColor, stateLabel } from '../lib/tokens'

export default function HotspotDot({
  xPct,
  yPct,
  state,
  label,
  summary,
  selected,
  onClick,
  delay = 0,
}: {
  xPct: number
  yPct: number
  state: SignalState
  label: string
  summary: string
  selected: boolean
  onClick: () => void
  delay?: number
}) {
  const color = stateColor[state]
  const reduceMotion = useReducedMotion()

  return (
    <motion.button
      onClick={onClick}
      className="group absolute -translate-x-1/2 -translate-y-1/2"
      style={{ left: `${xPct}%`, top: `${yPct}%` }}
      initial={reduceMotion ? undefined : { scale: 0, opacity: 0 }}
      animate={reduceMotion ? undefined : { scale: 1, opacity: 1 }}
      transition={{ delay, duration: 0.3 }}
    >
      <span
        className="block h-4 w-4 rounded-full ring-2 ring-white"
        style={{ backgroundColor: color, boxShadow: selected ? `0 0 0 4px ${color}55` : undefined }}
      />
      <div
        className="pointer-events-none absolute left-1/2 top-full z-10 mt-2 hidden -translate-x-1/2 whitespace-nowrap rounded-md px-2.5 py-1.5 text-[12px] text-white group-hover:block"
        style={{ backgroundColor: '#0B1220' }}
      >
        <div className="font-medium">{label}</div>
        <div style={{ color: '#9CA3AF' }}>
          {stateLabel[state]} · {summary}
        </div>
      </div>
    </motion.button>
  )
}
