import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, ChevronDown } from 'lucide-react'
import { api } from '../lib/api'
import { useFetch } from '../lib/useFetch'
import { renderMarkdown, splitConfidenceSection } from '../lib/markdown'
import { DISCLAIMER, stateColor, stateLabel } from '../lib/tokens'

function MetricCell({ label, value, suffix }: { label: string; value: number | null; suffix: string }) {
  return (
    <div className="rounded-lg p-3 text-center" style={{ backgroundColor: 'var(--color-bg-subtle)' }}>
      <div className="text-2xl font-semibold" style={{ color: 'var(--color-navy)' }}>
        {value != null ? `${value.toLocaleString('ko-KR')}${suffix}` : '—'}
      </div>
      <div className="mt-1 text-[11px]" style={{ color: 'var(--color-ink-muted)' }}>
        {label}
      </div>
    </div>
  )
}

export default function ReportView() {
  const { id } = useParams<{ id: string }>()
  const { data, loading, error } = useFetch(() => api.report(Number(id)), [id])
  const [confidenceOpen, setConfidenceOpen] = useState(false)

  const { body, confidence } = data ? splitConfidenceSection(data.markdown) : { body: '', confidence: null }
  const color = data?.state ? stateColor[data.state] : 'var(--color-ink-muted)'

  return (
    <div className="mx-auto max-w-[760px]">
      <Link to="/" className="mb-4 inline-flex items-center gap-1 text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
        <ArrowLeft size={14} strokeWidth={1.5} />
        상황판으로
      </Link>

      {loading && <div className="h-40 animate-pulse rounded-xl" style={{ backgroundColor: 'var(--color-bg-subtle)' }} />}
      {error && <p className="text-sm text-red-600">리포트를 불러오지 못했습니다: {error}</p>}

      {data && (
        <div className="flex flex-col gap-4">
          <div className="rounded-xl border p-5" style={{ borderColor: 'var(--color-border)', boxShadow: 'var(--shadow-card)' }}>
            <p className="text-[13px] font-semibold" style={{ color: 'var(--color-ink)' }}>
              {data.title}
            </p>
            <div className="mt-3 grid grid-cols-2 gap-3 text-[12px] sm:grid-cols-4">
              <div>
                <div style={{ color: 'var(--color-ink-muted)' }}>차종</div>
                <div className="font-medium" style={{ color: 'var(--color-ink)' }}>{data.model ?? '—'}</div>
              </div>
              <div>
                <div style={{ color: 'var(--color-ink-muted)' }}>캠페인</div>
                <div className="truncate font-mono font-medium" style={{ color: 'var(--color-ink)' }} title={data.campaign ?? undefined}>
                  {data.campaign ?? '—'}
                </div>
              </div>
              <div>
                <div style={{ color: 'var(--color-ink-muted)' }}>기준월</div>
                <div className="font-medium" style={{ color: 'var(--color-ink)' }}>{data.reference_month ?? '—'}</div>
              </div>
              <div>
                <div style={{ color: 'var(--color-ink-muted)' }}>상태</div>
                <div className="font-medium" style={{ color }}>{data.state ? stateLabel[data.state] : '—'}</div>
              </div>
            </div>
          </div>

          {data.metrics && (
            <div className="grid grid-cols-3 gap-3">
              <MetricCell label="신고 수" value={data.metrics.complaint_count} suffix="건" />
              <MetricCell label="증상 집중도" value={data.metrics.concentration_pct} suffix="%" />
              <MetricCell label="리콜 대비 선행일" value={data.metrics.lead_days} suffix="일" />
            </div>
          )}

          <article className="rounded-xl border p-8" style={{ borderColor: 'var(--color-border)', boxShadow: 'var(--shadow-card)' }}>
            <p className="mb-4 text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
              생성일 {data.created_at}
            </p>
            {renderMarkdown(body)}

            {confidence && (
              <div className="mt-6 border-t pt-4" style={{ borderColor: 'var(--color-border)' }}>
                <button
                  onClick={() => setConfidenceOpen((v) => !v)}
                  className="flex items-center gap-1 text-[13px] font-semibold"
                  style={{ color: 'var(--color-navy)' }}
                >
                  <ChevronDown size={14} strokeWidth={1.5} className={confidenceOpen ? 'rotate-180 transition-transform' : 'transition-transform'} />
                  확신도와 한계 {confidenceOpen ? '접기' : '펼치기'}
                </button>
                {confidenceOpen && <div className="mt-2">{renderMarkdown(confidence)}</div>}
              </div>
            )}

            <p className="mt-8 border-t pt-4 text-[12px]" style={{ borderColor: 'var(--color-border)', color: 'var(--color-ink-muted)' }}>
              {DISCLAIMER}
            </p>
          </article>
        </div>
      )}
    </div>
  )
}
