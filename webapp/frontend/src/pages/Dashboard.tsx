import { api } from '../lib/api'
import { useFetch } from '../lib/useFetch'
import KpiStrip from '../components/KpiStrip'
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

      {summary.data ? <KpiStrip summary={summary.data} /> : <SkeletonBlock height={100} />}

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
