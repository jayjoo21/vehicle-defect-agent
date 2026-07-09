import Logo from '../components/Logo'

// 발표용 페이지. SVG 로고 애니메이션은 추후 별도 작업으로 이 이미지 태그를 대체할 예정.
export default function Brand() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 py-16">
      <div className="w-full max-w-2xl px-6">
        <Logo />
      </div>
    </div>
  )
}
