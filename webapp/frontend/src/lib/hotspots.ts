// 6개 핫스팟 도메인의 라벨(공통)과 차체형태별(suv/sedan/sports) 배치 좌표(400x200 viewBox 기준,
// 차는 우측을 정면으로 함). 좌표를 차체형태별로 분리하는 이유: SUV용 좌표(높은 루프라인 기준)를
// 세단 실루엣(낮고 긴 루프라인)에 그대로 쓰면 계기판/인포테인먼트 핫스팟이 세단 지붕 위 허공에서
// 서로 겹쳐 보이는 버그가 있었다(5.5단계에서 발견). 3D(R3F) 버전도 같은 좌표를 상대 비율로 재사용한다.
import type { BodyType } from './bodyType'

export interface HotspotDef {
  domain: string
  label: string
  x: number
  y: number
}

const LABELS: Record<string, string> = {
  ADAS_카메라: 'ADAS 카메라',
  계기판: '계기판',
  인포테인먼트: '인포테인먼트',
  제동SW: '제동 SW',
  구동배터리: '구동배터리',
  ICCU_충전제어: 'ICCU·충전제어',
}

const COORDS: Record<BodyType, Record<string, { x: number; y: number }>> = {
  // 루프라인이 높고 짧은 박스형 실루엣(roof 60~95) 기준.
  suv: {
    ADAS_카메라: { x: 250, y: 65 },
    계기판: { x: 230, y: 92 },
    인포테인먼트: { x: 185, y: 92 },
    제동SW: { x: 300, y: 150 },
    구동배터리: { x: 200, y: 162 },
    ICCU_충전제어: { x: 100, y: 140 },
  },
  // 루프라인이 낮고 긴 실루엣(roof 75~105) 기준 — suv 좌표를 그대로 쓰면 지붕 위에서 뭉쳤던 것을 보정.
  sedan: {
    ADAS_카메라: { x: 250, y: 80 },
    계기판: { x: 225, y: 102 },
    인포테인먼트: { x: 180, y: 102 },
    제동SW: { x: 300, y: 150 },
    구동배터리: { x: 200, y: 162 },
    ICCU_충전제어: { x: 100, y: 140 },
  },
  // 루프라인이 가장 낮고 캐빈이 짧은 실루엣(roof 88~118) 기준.
  sports: {
    ADAS_카메라: { x: 230, y: 95 },
    계기판: { x: 210, y: 115 },
    인포테인먼트: { x: 175, y: 115 },
    제동SW: { x: 290, y: 150 },
    구동배터리: { x: 200, y: 162 },
    ICCU_충전제어: { x: 110, y: 140 },
  },
}

const DOMAIN_ORDER = Object.keys(LABELS)

export const HOTSPOT_LABELS = LABELS

export const HOTSPOTS_BY_BODY_TYPE: Record<BodyType, HotspotDef[]> = {
  suv: DOMAIN_ORDER.map((domain) => ({ domain, label: LABELS[domain], ...COORDS.suv[domain] })),
  sedan: DOMAIN_ORDER.map((domain) => ({ domain, label: LABELS[domain], ...COORDS.sedan[domain] })),
  sports: DOMAIN_ORDER.map((domain) => ({ domain, label: LABELS[domain], ...COORDS.sports[domain] })),
}
