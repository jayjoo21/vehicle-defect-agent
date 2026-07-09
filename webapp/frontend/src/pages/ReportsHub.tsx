import { useMemo, useState } from 'react'
import { Download, Share2, FileText } from 'lucide-react'
import { api } from '../lib/api'
import { useFetch } from '../lib/useFetch'
import { stateColor, stateLabel } from '../lib/tokens'
import ReportPaper from '../components/ReportPaper'
import Skeleton from '../components/Skeleton'

// PDF 다운로드·공유는 아직 실제 구현이 없는 더미 버튼 — 클릭하면 준비 중 안내만 잠깐 보여준다.
export default function ReportsHub() {
  const signals = useFetch(() => api.signals(), [])
  const reportsList = useMemo(
    () => (signals.data?.signals ?? []).filter((c) => c.report_id != null),
    [signals.data],
  )
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const activeId = selectedId ?? reportsList[0]?.report_id ?? null
  const report = useFetch(
    () => (activeId != null ? api.report(activeId) : Promise.reject(new Error('선택된 리포트 없음'))),
    [activeId],
  )
  const [hint, setHint] = useState<string | null>(null)

  function dummyAction(label: string) {
    setHint(label)
    setTimeout(() => setHint(null), 2200)
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold" style={{ color: 'var(--color-navy)' }}>
        시그널 리포트
      </h1>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[300px_1fr]">
        {/* 좌측: 리포트 목록 */}
        <div className="card flex flex-col gap-1 p-3">
          {signals.loading && <Skeleton height={280} />}
          {!signals.loading && reportsList.length === 0 && (
            <p className="p-3 text-sm" style={{ color: 'var(--color-ink-muted)' }}>
              아직 생성된 리포트가 없습니다.
            </p>
          )}
          {reportsList.map((c) => {
            const isActive = c.report_id === activeId
            const color = stateColor[c.state]
            return (
              <button
                key={c.report_id}
                onClick={() => setSelectedId(c.report_id)}
                className="btn-tension flex flex-col items-start gap-1 rounded-lg px-3 py-2.5 text-left"
                style={{ backgroundColor: isActive ? 'var(--color-navy-soft)' : undefined }}
              >
                <span className="flex items-center gap-1.5 text-[13px] font-medium" style={{ color: 'var(--color-ink)' }}>
                  <FileText size={13} strokeWidth={1.5} style={{ color: isActive ? 'var(--color-navy)' : 'var(--color-ink-muted)' }} />
                  {c.model}
                </span>
                <span className="flex items-center gap-1.5 text-[11px]" style={{ color: 'var(--color-ink-muted)' }}>
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
                  {stateLabel[c.state]} · {c.month}
                </span>
              </button>
            )
          })}
        </div>

        {/* 우측: A4 비율 흰색 페이퍼 */}
        <div className="flex flex-col gap-3">
          {activeId != null && (
            <div className="flex items-center justify-end gap-2">
              {hint && (
                <span className="text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
                  {hint}
                </span>
              )}
              <button
                onClick={() => dummyAction('PDF 다운로드 기능은 준비 중입니다')}
                className="btn-tension inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium"
                style={{ backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }}
              >
                <Download size={14} strokeWidth={1.75} />
                PDF 다운로드
              </button>
              <button
                onClick={() => dummyAction('공유 링크 기능은 준비 중입니다')}
                className="btn-tension inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium"
                style={{ backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }}
              >
                <Share2 size={14} strokeWidth={1.75} />
                공유
              </button>
            </div>
          )}

          <div className="mx-auto w-full" style={{ maxWidth: 720 }}>
            <div
              className="rounded-sm p-8 sm:p-12"
              style={{ backgroundColor: 'var(--color-surface)', boxShadow: '0 8px 30px rgba(15,23,42,.14), 0 2px 8px rgba(15,23,42,.08)', minHeight: 400 }}
            >
              {activeId != null && report.loading && <Skeleton height={400} />}
              {activeId != null && report.error && (
                <p className="text-sm text-red-600">리포트를 불러오지 못했습니다: {report.error}</p>
              )}
              {activeId == null && !signals.loading && (
                <p className="text-sm" style={{ color: 'var(--color-ink-muted)' }}>
                  왼쪽 목록에서 리포트를 선택하세요.
                </p>
              )}
              {report.data && <ReportPaper data={report.data} variant="flat" />}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
