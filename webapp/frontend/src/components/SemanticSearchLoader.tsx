import { useEffect, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { CheckCircle2, Circle, Loader2 } from 'lucide-react'

const PHASES = [
  '의미론적 간극(Semantic Gap) 분석 중...',
  'NHTSA 불만 데이터 컨텍스트 매칭 중...',
  '리콜 인과관계 추론 중...',
]

// 실제 백엔드 SSE 스텝(InvestigationTimeline의 steps)과는 별개로, 답변이 도착하기 전까지 항상
// 정해진 순서로 1초 간격 진행하는 연출용 로더 — 목(mock) 모드처럼 응답이 아주 빨리 오더라도
// "AI가 분석 중"이라는 인상을 주기 위함. 3단계를 넘기면 마지막 단계에서 멈춰 대기한다.
export default function SemanticSearchLoader() {
  const [activeIndex, setActiveIndex] = useState(0)
  const reduceMotion = useReducedMotion()

  useEffect(() => {
    const id = setInterval(() => {
      setActiveIndex((i) => Math.min(i + 1, PHASES.length - 1))
    }, 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <ul className="flex flex-col gap-2">
      {PHASES.map((label, i) => {
        const state = i < activeIndex ? 'done' : i === activeIndex ? 'active' : 'pending'
        return (
          <motion.li
            key={label}
            className="flex items-center gap-2 text-[13px]"
            initial={reduceMotion ? undefined : { opacity: 0, y: 4 }}
            animate={{ opacity: state === 'pending' ? 0.4 : 1, y: 0 }}
            transition={{ duration: 0.3 }}
            style={{ color: state === 'active' ? 'var(--color-navy)' : 'var(--color-ink-muted)' }}
          >
            {state === 'done' && <CheckCircle2 size={15} strokeWidth={1.75} style={{ color: 'var(--color-state-recalled)' }} />}
            {state === 'active' && <Loader2 size={15} strokeWidth={1.75} className={reduceMotion ? '' : 'animate-spin'} />}
            {state === 'pending' && <Circle size={15} strokeWidth={1.75} />}
            <span className={state === 'active' ? 'font-medium' : undefined}>{label}</span>
          </motion.li>
        )
      })}
    </ul>
  )
}
