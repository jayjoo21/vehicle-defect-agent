import { useParams, Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { api } from '../lib/api'
import { useFetch } from '../lib/useFetch'
import { renderMarkdown } from '../lib/markdown'
import { DISCLAIMER } from '../lib/tokens'

export default function ReportView() {
  const { id } = useParams<{ id: string }>()
  const { data, loading, error } = useFetch(() => api.report(Number(id)), [id])

  return (
    <div className="mx-auto max-w-[760px]">
      <Link to="/" className="mb-4 inline-flex items-center gap-1 text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
        <ArrowLeft size={14} strokeWidth={1.5} />
        상황판으로
      </Link>

      {loading && <div className="h-40 animate-pulse rounded-xl" style={{ backgroundColor: 'var(--color-bg-subtle)' }} />}
      {error && <p className="text-sm text-red-600">리포트를 불러오지 못했습니다: {error}</p>}

      {data && (
        <article className="rounded-xl border p-8" style={{ borderColor: 'var(--color-border)', boxShadow: 'var(--shadow-card)' }}>
          <p className="mb-4 text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
            생성일 {data.created_at}
          </p>
          {renderMarkdown(data.markdown)}
          <p className="mt-8 border-t pt-4 text-[12px]" style={{ borderColor: 'var(--color-border)', color: 'var(--color-ink-muted)' }}>
            {DISCLAIMER}
          </p>
        </article>
      )}
    </div>
  )
}
