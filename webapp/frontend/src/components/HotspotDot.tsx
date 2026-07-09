import { useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import type { SignalState } from '../lib/tokens'
import { stateColor } from '../lib/tokens'
import StateIcon from './StateIcon'

const GLOW_BLUE = '#3B82F6'

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
  const [hovered, setHovered] = useState(false)
  // 인라인 style은 항상 클래스보다 우선 적용되므로, hover 시 파란 글로우를 Tailwind hover
  // 클래스로 표현할 수 없다(고정 배경색을 계속 인라인으로 걸어두면 :hover가 절대 못 이김) —
  // 로컬 hover 상태로 직접 계산해 인라인 값 자체를 바꾼다.
  const active = selected || hovered

  return (
    <motion.button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className="group absolute -translate-x-1/2 -translate-y-1/2"
      style={{ left: `${xPct}%`, top: `${yPct}%` }}
      initial={reduceMotion ? undefined : { scale: 0, opacity: 0 }}
      animate={reduceMotion ? undefined : { scale: 1, opacity: 1 }}
      transition={{ delay, duration: 0.3 }}
    >
      {/* 살아있는 데이터처럼 은은하게 맥박(idle), hover/선택 시 파란 빛 링 + 확대(active) */}
      <span
        className={`block rounded-full transition-all duration-300 ${
          active ? 'scale-110 ring-4 ring-blue-500/30' : `ring-2 ring-white ${reduceMotion ? '' : 'animate-pulse'}`
        }`}
        style={{ width: 5, height: 5, backgroundColor: active ? GLOW_BLUE : color }}
      />
      <div className="pointer-events-none absolute -top-8 left-1/2 z-10 flex -translate-x-1/2 translate-y-1 items-center gap-1 whitespace-nowrap rounded-full border border-white/40 bg-white/80 px-2 py-1 text-[12px] font-medium leading-tight text-slate-700 opacity-0 shadow-xl backdrop-blur-md transition-all duration-200 group-hover:translate-y-0 group-hover:opacity-100">
        <StateIcon state={state} size={10} color={color} />
        <span>
          {label} · {summary}
        </span>
      </div>
    </motion.button>
  )
}
