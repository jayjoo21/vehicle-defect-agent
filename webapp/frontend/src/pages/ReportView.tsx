import { useParams, Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { api } from '../lib/api'
import { useFetch } from '../lib/useFetch'
import Skeleton from '../components/Skeleton'
import ReportPaper from '../components/ReportPaper'

export default function ReportView() {
  const { id } = useParams<{ id: string }>()
  const { data, loading, error } = useFetch(() => api.report(Number(id)), [id])

  return (
    <div className="mx-auto max-w-[760px]">
      <Link to="/" className="mb-4 inline-flex items-center gap-1 text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
        <ArrowLeft size={14} strokeWidth={1.5} />
        상황판으로
      </Link>

      {loading && <Skeleton height={160} />}
      {error && <p className="text-sm text-red-600">리포트를 불러오지 못했습니다: {error}</p>}

      {data && <ReportPaper data={data} />}
    </div>
  )
}
