// 3D/SVG 뷰어 뒤에 깔리는 은은한 스캐닝 그리드 — 중앙에서 가장자리로 갈수록 마스크로 자연스럽게 흐려진다.
export default function GridOverlay() {
  return (
    <div
      className="pointer-events-none absolute inset-0"
      style={{
        backgroundImage:
          'linear-gradient(to right, rgba(148,163,184,0.18) 1px, transparent 1px), linear-gradient(to bottom, rgba(148,163,184,0.18) 1px, transparent 1px)',
        backgroundSize: '28px 28px',
        maskImage: 'radial-gradient(ellipse at center, black 35%, transparent 80%)',
        WebkitMaskImage: 'radial-gradient(ellipse at center, black 35%, transparent 80%)',
      }}
    />
  )
}
