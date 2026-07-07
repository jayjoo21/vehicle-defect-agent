import { useEffect, useRef, useState } from 'react'
import { animate, useReducedMotion } from 'framer-motion'

export default function CountUp({ value, duration = 0.8 }: { value: number; duration?: number }) {
  const [display, setDisplay] = useState(0)
  const reduceMotion = useReducedMotion()
  const first = useRef(true)

  useEffect(() => {
    if (reduceMotion) {
      setDisplay(value)
      return
    }
    const from = first.current ? 0 : display
    first.current = false
    const controls = animate(from, value, {
      duration,
      ease: 'easeOut',
      onUpdate: (v) => setDisplay(Math.round(v)),
    })
    return () => controls.stop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, duration, reduceMotion])

  return <span>{display.toLocaleString('ko-KR')}</span>
}
