export default function Skeleton({ height, className = '' }: { height: number; className?: string }) {
  return <div className={`skeleton ${className}`} style={{ height }} />
}
