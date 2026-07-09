import logoSrc from '../assets/logo_mobiscope.png'

interface LogoProps {
  /** 헤더용 — 높이 32px로 고정. false면 원본 비율 그대로(발표용 /brand 페이지). */
  compact?: boolean
  className?: string
}

export default function Logo({ compact = false, className = '' }: LogoProps) {
  return (
    <img
      src={logoSrc}
      alt="MOBISCOPE"
      className={className}
      style={compact ? { height: 32, width: 'auto' } : { width: '100%', height: 'auto' }}
    />
  )
}
