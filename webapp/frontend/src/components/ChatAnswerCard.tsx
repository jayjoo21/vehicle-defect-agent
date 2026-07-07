import { Link } from 'react-router-dom'
import { FileText } from 'lucide-react'
import type { ChatAnswer } from '../lib/types'
import { renderMarkdown } from '../lib/markdown'
import { DISCLAIMER } from '../lib/tokens'
import { koGloss } from '../lib/partCategory'

export default function ChatAnswerCard({ answer }: { answer: ChatAnswer }) {
  const quoted = answer.sources.filter((s) => s.text)

  return (
    <div className="rounded-xl border p-6" style={{ borderColor: 'var(--color-border)', boxShadow: 'var(--shadow-card)' }}>
      <div className="text-sm leading-relaxed">{renderMarkdown(answer.markdown)}</div>

      {quoted.length > 0 && (
        <div className="mt-4 border-t pt-4" style={{ borderColor: 'var(--color-border)' }}>
          <p className="mb-2 text-[12px] font-medium" style={{ color: 'var(--color-ink-muted)' }}>
            원문 인용 {quoted.length}건
          </p>
          <ul className="flex flex-col gap-2">
            {quoted.map((s) => {
              const gloss = koGloss(s.part_category, s.symptom)
              return (
                <li key={s.id} className="text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
                  <span
                    className="mr-1.5 rounded px-1.5 py-0.5 font-mono"
                    style={{ backgroundColor: 'var(--color-bg-subtle)' }}
                  >
                    ODINO {s.id}
                  </span>
                  &ldquo;{s.text}&rdquo;
                  {gloss && (
                    <span className="ml-1.5" style={{ color: 'var(--color-navy)' }}>
                      — {gloss}
                    </span>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      )}

      {answer.report_id != null && (
        <Link
          to={`/reports/${answer.report_id}`}
          className="mt-4 inline-flex items-center gap-1 text-[13px] font-medium"
          style={{ color: 'var(--color-navy)' }}
        >
          <FileText size={14} strokeWidth={1.5} />
          상세 리포트 보기
        </Link>
      )}

      <p className="mt-4 border-t pt-3 text-[11px]" style={{ borderColor: 'var(--color-border)', color: 'var(--color-ink-muted)' }}>
        {DISCLAIMER}
      </p>
    </div>
  )
}
