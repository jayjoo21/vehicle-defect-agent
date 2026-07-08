import { useParams, Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, MessageCircle, FileText } from 'lucide-react'
import { api } from '../lib/api'
import { useFetch } from '../lib/useFetch'
import { stateColor, stateLabel, type SignalState } from '../lib/tokens'
import LifecycleTimeline from '../components/LifecycleTimeline'

// 6.6단계: 타임라인 제목을 데이터에 맞는 헤드라인으로 — "한 시그널의 일생" 유형은 이미 리콜로
// 이어진(recalls 존재) 시그널에만 쓰고, 그 외엔 현재 상태를 정직하게 반영한다.
function timelineHeadline(model: string, state: SignalState, hasRecall: boolean): string {
  if (hasRecall) return `${model}의 일생 — 신고에서 리콜까지`
  if (state === 'active') return `${model}, 지금 활성 시그널이 발화 중`
  if (state === 'rising') return `${model}, 신고가 늘고 있는 시그널`
  return `${model}, 아직 뚜렷한 시그널 없음`
}

export default function SignalDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data, loading, error } = useFetch(() => api.signal(Number(id)), [id])

  return (
    <div className="mx-auto max-w-[900px]">
      <Link to="/" className="mb-4 inline-flex items-center gap-1 text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
        <ArrowLeft size={14} strokeWidth={1.5} />
        상황판으로
      </Link>

      {loading && <div className="h-64 animate-pulse rounded-xl" style={{ backgroundColor: 'var(--color-bg-subtle)' }} />}
      {error && <p className="text-sm text-red-600">시그널 정보를 불러오지 못했습니다: {error}</p>}

      {data && (
        <div className="flex flex-col gap-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold" style={{ color: 'var(--color-navy)' }}>
                {data.model}
              </h1>
              <div className="mt-2 flex items-center gap-2">
                <span
                  className="rounded-full px-2.5 py-1 text-[12px] font-medium"
                  style={{ color: stateColor[data.state], backgroundColor: `${stateColor[data.state]}1A` }}
                >
                  {stateLabel[data.state]}
                </span>
                {data.top_symptom && (
                  <span className="text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
                    {data.top_symptom}
                  </span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-3">
              {data.report_id != null && (
                <Link
                  to={`/reports/${data.report_id}`}
                  className="inline-flex items-center gap-1.5 text-[13px] font-medium"
                  style={{ color: 'var(--color-navy)' }}
                >
                  <FileText size={14} strokeWidth={1.5} />
                  연결 리포트 보기
                </Link>
              )}
              <button
                onClick={() => navigate(`/chat?q=${encodeURIComponent(`내 차 ${data.model}인데 관련 증상이 있어요`)}`)}
                className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-[13px] font-medium text-white"
                style={{ backgroundColor: 'var(--color-navy)' }}
              >
                <MessageCircle size={14} strokeWidth={1.5} />
                조사하기
              </button>
            </div>
          </div>

          <LifecycleTimeline
            timeline={data.timeline}
            recalls={data.recalls}
            title={timelineHeadline(data.model, data.state, data.recalls.length > 0)}
          />

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="rounded-xl border p-6" style={{ borderColor: 'var(--color-border)', boxShadow: 'var(--shadow-card)' }}>
              <h3 className="mb-3 text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
                관련 US 리콜 {data.recalls.length}건
              </h3>
              {data.recalls.length === 0 ? (
                <p className="text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
                  이 차종에 매칭된 US 리콜이 없습니다.
                </p>
              ) : (
                <ul className="flex flex-col gap-3">
                  {data.recalls.map((r) => (
                    <li key={r.campaign} className="text-[13px]">
                      <div className="flex items-center gap-2">
                        <span
                          className="rounded px-1.5 py-0.5 font-mono text-[11px]"
                          style={{ backgroundColor: 'var(--color-bg-subtle)', color: 'var(--color-ink-muted)' }}
                        >
                          {r.campaign}
                        </span>
                        <span style={{ color: 'var(--color-ink-muted)' }}>접수 {r.report_date}</span>
                      </div>
                      {r.component && (
                        <p className="mt-0.5" style={{ color: 'var(--color-ink)' }}>
                          {r.component}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="rounded-xl border p-6" style={{ borderColor: 'var(--color-border)', boxShadow: 'var(--shadow-card)' }}>
              <h3 className="mb-3 text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
                한·미 시차 {data.kr_gap.length}건
              </h3>
              {data.kr_gap.length === 0 ? (
                <p className="text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
                  이 차종에 매칭된 한·미 시차 데이터가 없습니다.
                </p>
              ) : (
                <ul className="flex flex-col gap-3">
                  {data.kr_gap.map((g) => (
                    <li key={g.campaign} className="text-[13px]">
                      <div className="flex items-center gap-2">
                        <span
                          className="rounded px-1.5 py-0.5 font-mono text-[11px]"
                          style={{ backgroundColor: 'var(--color-bg-subtle)', color: 'var(--color-ink-muted)' }}
                        >
                          {g.campaign}
                        </span>
                        <span
                          className="font-medium"
                          style={{ color: g.gap_days != null && g.gap_days < 0 ? '#DC2626' : 'var(--color-navy)' }}
                        >
                          {g.gap_days != null ? `${g.gap_days > 0 ? '+' : ''}${g.gap_days}일` : '-'}
                        </span>
                        {g.date_basis && (
                          <span className="text-[11px]" style={{ color: 'var(--color-ink-muted)' }}>
                            ({g.date_basis})
                          </span>
                        )}
                      </div>
                      {g.defect_summary && (
                        <p className="mt-0.5" style={{ color: 'var(--color-ink)' }}>
                          {g.defect_summary}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
