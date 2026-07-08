import { motion, useReducedMotion } from 'framer-motion'
import type { SignalState } from '../lib/tokens'
import { stateColor } from '../lib/tokens'
import StateIcon from './StateIcon'

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
      {/* 점 크기 1/3 축소(기존 16px→약 5px) — 이 크기에선 아이콘이 식별 불가해 점 안 아이콘은
          제거하고, 대신 호버 툴팁에 아이콘+라벨+상태를 한 줄로 병기해 색상 단독 인코딩을 피한다. */}
      <span
        className="block rounded-full ring-2 ring-white"
        style={{ width: 5, height: 5, backgroundColor: color, boxShadow: selected ? `0 0 0 3px ${color}55` : undefined }}
      />
      <div
        className="pointer-events-none absolute left-1/2 top-full z-10 mt-1.5 hidden -translate-x-1/2 items-center gap-1 whitespace-nowrap rounded-md px-2 py-1 text-[11px] text-white group-hover:flex"
        style={{ backgroundColor: '#0B1220' }}
      >
        <StateIcon state={state} size={10} color={color} />
        <span>
          {label} · {summary}
        </span>
      </div>
    </motion.button>
  )
}
