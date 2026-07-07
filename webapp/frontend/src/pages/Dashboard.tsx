import { api } from '../lib/api'
import { useFetch } from '../lib/useFetch'
import KpiStrip from '../components/KpiStrip'
import HeroSignalCard from '../components/HeroSignalCard'
import SignalCardGrid from '../components/SignalCardGrid'
import GapDumbbell from '../components/GapDumbbell'
import Heatmap from '../components/Heatmap'
import RecentReports from '../components/RecentReports'

export default function Dashboard() {
  const summary = useFetch(api.summary, [])
  const signals = useFetch(() => api.signals(), [])
  const gap = useFetch(api.gap, [])
  const heatmap = useFetch(api.heatmap, [])

  const error = summary.error || signals.error || gap.error || heatmap.error
  if (error) {
    return <p className="text-sm text-red-600">데이터를 불러오지 못했습니다: {error}</p>
  }

  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-2xl font-semibold" style={{ color: 'var(--color-navy)' }}>
        상황판
      </h1>

      {summary.data?.hero && <HeroSignalCard hero={summary.data.hero} />}

      {summary.data ? (
        <div>
          <KpiStrip summary={summary.data} />
          <p className="mt-2 text-[11px]" style={{ color: 'var(--color-ink-muted)' }}>
            * 한국 시정 개시일 미확인: 한국 발표는 확인됐으나 시정 개시 정보가 없는 건
          </p>
        </div>
      ) : (
        <SkeletonBlock height={100} />
      )}

      {signals.data ? <SignalCardGrid cards={signals.data.signals} /> : <SkeletonBlock height={200} />}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {gap.data ? <GapDumbbell data={gap.data} /> : <SkeletonBlock height={300} />}
        {heatmap.data ? <Heatmap data={heatmap.data} /> : <SkeletonBlock height={300} />}
      </div>

      {signals.data ? <RecentReports cards={signals.data.signals} /> : <SkeletonBlock height={150} />}
    </div>
  )
}

function SkeletonBlock({ height }: { height: number }) {
  return (
    <div
      className="animate-pulse rounded-xl"
      style={{ height, backgroundColor: 'var(--color-bg-subtle)' }}
    />
  )
}
