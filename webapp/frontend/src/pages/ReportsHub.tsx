import { useMemo, useRef, useState } from 'react'
import { Download, FileText, Loader2 } from 'lucide-react'
import html2pdf from 'html2pdf.js'
import { api } from '../lib/api'
import { useFetch } from '../lib/useFetch'
import { stateColor, stateLabel } from '../lib/tokens'
import ReportPaper from '../components/ReportPaper'
import Skeleton from '../components/Skeleton'

// PDF 다운로드: Chat.tsx의 조사 채팅 PDF 내보내기와 동일한 html2pdf 로직을 재사용(새 구현 아님).
// 공유 기능은 실제 구현이 없어(단축 URL·권한 등 백엔드 지원 전무) 버튼 자체를 두지 않는다 —
// "준비 중" 토스트로 있는 척하지 않고, 안 되는 건 숨긴다는 이 작업의 원칙을 그대로 따름.
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
  const printRef = useRef<HTMLDivElement>(null)
  const [exporting, setExporting] = useState(false)

  async function exportPdf() {
    if (!printRef.current || exporting || !report.data) return
    setExporting(true)
    try {
      await html2pdf()
        .set({
          filename: `MOBISCOPE_${report.data.title.replace(/[^\w가-힣-]+/g, '_')}.pdf`,
          margin: 10,
          image: { type: 'jpeg', quality: 0.95 },
          html2canvas: { scale: 2, useCORS: true, backgroundColor: '#FFFFFF' },
          jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
        })
        .from(printRef.current)
        .save()
    } finally {
      setExporting(false)
    }
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
          {activeId != null && report.data && (
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={exportPdf}
                disabled={exporting}
                className="btn-tension inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium disabled:opacity-60"
                style={{ backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }}
              >
                {exporting ? <Loader2 size={14} strokeWidth={1.75} className="animate-spin" /> : <Download size={14} strokeWidth={1.75} />}
                {exporting ? '내보내는 중...' : 'PDF 다운로드'}
              </button>
            </div>
          )}

          <div className="mx-auto w-full" style={{ maxWidth: 720 }}>
            <div
              ref={printRef}
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
