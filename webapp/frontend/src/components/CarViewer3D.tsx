import { Suspense, useEffect, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, Html, useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import type { HotspotDef } from '../lib/hotspots'
import type { VehicleDomain } from '../lib/types'
import { stateColor } from '../lib/tokens'
import { hotspotSummary } from '../lib/hotspotSummary'
import StateIcon from './StateIcon'

const AUTO_ROTATE_RAD_PER_SEC = (6 * Math.PI) / 180 // 초당 6도

// hotspots.ts는 400x200 SVG 좌표계(x=370 전면~40 후면, y=60 상단~160 바닥)로 정의돼 있다.
// 실제 glb 모델의 정확한 스케일·원점을 알 수 없으므로(에이전트 환경에 브라우저가 없어
// 시각 확인 불가), 로드 후 계산한 바운딩 박스에 대한 상대 비율로 변환해 앵커를 배치한다.
// 실제 렌더링에서 위치가 어긋나면(예: 전후 반전) 아래 FRONT_AXIS_SIGN을 -1로 바꿔 보정할 것.
const FRONT_AXIS_SIGN = 1

function toRelative(x: number, y: number) {
  const frontBack = (x - 40) / (370 - 40)
  const upDown = 1 - (y - 60) / (160 - 60)
  return { frontBack, upDown }
}

// 카메라를 모델 바운딩박스에 맞춰 자동 프레이밍할 때, 화면에서 차지할 목표 비율 — 잘리지
// 않게 여유를 두기 위해 1보다 확실히 작게 잡는다.
const FRAME_FILL_RATIO = 0.82

function CarModel({
  path,
  hotspots,
  domains,
  selectedDomain,
  onSelect,
  onLoaded,
  onFramed,
}: {
  path: string
  hotspots: HotspotDef[]
  domains: VehicleDomain[]
  selectedDomain: string | null
  onSelect: (domain: string) => void
  onLoaded: () => void
  onFramed: (target: [number, number, number]) => void
}) {
  const { scene } = useGLTF(path)
  const { camera } = useThree()
  const group = useRef<THREE.Group>(null)
  const [box, setBox] = useState<THREE.Box3 | null>(null)

  useEffect(() => {
    // scene 참조가 아닌 path에 의존: useGLTF 캐시 때문에 같은 차체형태(suv 등)로 차종을
    // 바꾸면 scene 참조가 그대로라 [scene] 의존이면 onLoaded가 다시 호출되지 않아
    // 상위(CarViewer)의 3초 타임아웃 폴백이 잘못 발동하는 문제가 있었다.
    const b = new THREE.Box3().setFromObject(scene)
    setBox(b)

    // 카메라 자동 fit: 바운딩박스 8개 꼭짓점을 카메라의 실제 right/up 축에 투영해 가로·세로
    // 투영 폭을 각각 구하고, 가로 FOV(세로 FOV를 실제 캔버스 aspect로 넓힌 값)·세로 FOV 각각에
    // 대해 "이 축을 FRAME_FILL_RATIO로 채우는 데 필요한 거리"를 계산한 뒤 더 큰(더 빡빡한) 쪽을
    // 채택한다 — 차종마다 glb 스케일이 다르고 뷰어가 16:9로 넓어, 세로 기준만으로는 가로가
    // 목표보다 작게 남는 문제가 있었다.
    const center = new THREE.Vector3()
    b.getCenter(center)
    const persp = camera as THREE.PerspectiveCamera
    const fovVRad = (persp.fov * Math.PI) / 180
    const aspect = persp.aspect || 16 / 9
    const fovHRad = 2 * Math.atan(Math.tan(fovVRad / 2) * aspect)

    const dir = new THREE.Vector3(1, 0.35, 1).normalize()

    // 모델이 Y축으로 계속 자동 회전하므로(useFrame 아래), 정지 상태의 바운딩박스 꼭짓점을
    // 고정 카메라 방향에 투영해 프레이밍하면 회전하면서 그 각도에서만 맞고 다른 각도에선
    // 화면 밖으로 삐져나간다(잘림 버그). 바운딩 스피어 반지름은 회전에 불변이므로 이걸로
    // 가로·세로를 동시에 맞추면 어떤 회전각에서도 프레임을 벗어나지 않는다.
    const sphere = new THREE.Sphere()
    b.getBoundingSphere(sphere)
    const radius = sphere.radius

    const distanceForW = radius / (FRAME_FILL_RATIO * Math.tan(fovHRad / 2))
    const distanceForH = radius / (FRAME_FILL_RATIO * Math.tan(fovVRad / 2))
    const distance = Math.max(distanceForW, distanceForH, 0.1)

    camera.position.copy(center.clone().addScaledVector(dir, distance))
    camera.lookAt(center)
    persp.updateProjectionMatrix()
    onFramed([center.x, center.y, center.z])

    onLoaded()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path])

  useFrame((_, delta) => {
    if (group.current) group.current.rotation.y += AUTO_ROTATE_RAD_PER_SEC * delta
  })

  const domainByKey = Object.fromEntries(domains.map((d) => [d.domain, d]))

  return (
    <group ref={group}>
      <primitive object={scene} />
      {box &&
        hotspots.map((h) => {
          const d = domainByKey[h.domain]
          if (!d) return null
          const { frontBack, upDown } = toRelative(h.x, h.y)
          const z = box.min.z + (FRONT_AXIS_SIGN > 0 ? frontBack : 1 - frontBack) * (box.max.z - box.min.z)
          const position: [number, number, number] = [0, box.min.y + upDown * (box.max.y - box.min.y), z]
          const color = stateColor[d.state]
          const summary = hotspotSummary(d)
          return (
            <Html key={h.domain} position={position} center distanceFactor={10} zIndexRange={[10, 0]}>
              <button onClick={() => onSelect(h.domain)} className="group relative block">
                {/* 점 크기 1/3 축소 — SVG 버전(HotspotDot)과 동일하게 아이콘은 툴팁으로 옮김 */}
                <span
                  className="block rounded-full ring-2 ring-white"
                  style={{ width: 5, height: 5, backgroundColor: color, boxShadow: selectedDomain === h.domain ? `0 0 0 3px ${color}55` : undefined }}
                />
                <div
                  className="pointer-events-none absolute left-1/2 top-full z-10 mt-1.5 hidden -translate-x-1/2 items-center gap-1 whitespace-nowrap rounded-md px-2 py-1 text-[11px] text-white group-hover:flex"
                  style={{ backgroundColor: '#0B1220' }}
                >
                  <StateIcon state={d.state} size={10} color={color} />
                  <span>
                    {h.label} · {summary}
                  </span>
                </div>
              </button>
            </Html>
          )
        })}
    </group>
  )
}

export default function CarViewer3D({
  path,
  hotspots,
  domains,
  selectedDomain,
  onSelect,
  onLoaded,
}: {
  path: string
  hotspots: HotspotDef[]
  domains: VehicleDomain[]
  selectedDomain: string | null
  onSelect: (domain: string) => void
  onLoaded: () => void
}) {
  const [target, setTarget] = useState<[number, number, number]>([0, 0, 0])

  return (
    <Canvas camera={{ position: [4, 1.6, 4], fov: 40 }}>
      <ambientLight intensity={0.7} />
      <directionalLight position={[5, 8, 5]} intensity={1.2} />
      <Suspense fallback={null}>
        <CarModel
          path={path}
          hotspots={hotspots}
          domains={domains}
          selectedDomain={selectedDomain}
          onSelect={onSelect}
          onLoaded={onLoaded}
          onFramed={setTarget}
        />
      </Suspense>
      <OrbitControls target={target} enableZoom={false} enablePan={false} />
    </Canvas>
  )
}
