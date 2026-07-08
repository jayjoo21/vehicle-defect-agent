import type { VehicleDomain } from './types'
import { stateLabel } from './tokens'

// 핫스팟 툴팁 한 줄 요약. state='new'일 때 stateLabel('이력 없음')과 카운트 문구가
// 똑같은 "이력 없음"이라 그대로 이어붙이면 "이력 없음 · 이력 없음"으로 중복 표시되던
// 버그가 있었다 — new는 상태 라벨 하나만 보여주고 카운트 문구는 생략한다.
export function hotspotSummary(d: VehicleDomain): string {
  if (d.state === 'new') return stateLabel.new
  const detail = d.complaint_count > 0 ? `신고 ${d.complaint_count}건` : d.recall_count > 0 ? `리콜 ${d.recall_count}건` : null
  return detail ? `${stateLabel[d.state]} · ${detail}` : stateLabel[d.state]
}
