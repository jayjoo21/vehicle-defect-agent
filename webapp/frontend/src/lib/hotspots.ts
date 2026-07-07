// 6개 핫스팟 도메인의 표시 순서·라벨·SVG 배치 좌표(400x200 viewBox 기준, 차는 우측을 정면으로 함).
// 3D(R3F) 버전에서도 같은 순서·라벨을 재사용하고 좌표만 3D 앵커로 바꾼다.
export interface HotspotDef {
  domain: string
  label: string
  x: number
  y: number
}

export const HOTSPOTS: HotspotDef[] = [
  { domain: 'ADAS_카메라', label: 'ADAS 카메라', x: 250, y: 65 },
  { domain: '계기판', label: '계기판', x: 230, y: 92 },
  { domain: '인포테인먼트', label: '인포테인먼트', x: 185, y: 92 },
  { domain: '제동SW', label: '제동 SW', x: 300, y: 150 },
  { domain: '구동배터리', label: '구동배터리', x: 200, y: 162 },
  { domain: 'ICCU_충전제어', label: 'ICCU·충전제어', x: 100, y: 140 },
]
