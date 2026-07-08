import { Circle, TrendingUp, AlertTriangle, ShieldCheck, CheckCircle2 } from 'lucide-react'
import type { SignalState } from '../lib/tokens'

// 핫스팟 상태를 색상만으로 구분하지 않기 위한 아이콘 병기(색맹/그레이스케일 인쇄에서도 상태 구분 가능).
const ICON_BY_STATE: Record<SignalState, typeof Circle> = {
  new: Circle,
  rising: TrendingUp,
  active: AlertTriangle,
  recalled: ShieldCheck,
  resolved: CheckCircle2,
}

export default function StateIcon({ state, size = 9, color = '#fff' }: { state: SignalState; size?: number; color?: string }) {
  const Icon = ICON_BY_STATE[state]
  return <Icon size={size} strokeWidth={2.5} color={color} />
}
