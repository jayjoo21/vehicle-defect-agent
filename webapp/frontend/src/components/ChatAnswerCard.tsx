import { useState } from 'react'
import { Link } from 'react-router-dom'
import { FileText, ChevronDown } from 'lucide-react'
import type { ChatAnswer } from '../lib/types'
import { renderMarkdown } from '../lib/markdown'
import { DISCLAIMER } from '../lib/tokens'

function Badge({ text }: { text: string }) {
  return (
    <span
      className="rounded px-1.5 py-0.5 font-mono text-[11px]"
      style={{ backgroundColor: 'var(--color-bg-subtle)', color: 'var(--color-ink-muted)' }}
    >
      {text}
    </span>
  )
}

// 6.6단계: 답변을 결론 한 줄 -> 상태 칩 행 -> 섹션 카드 -> 원문 인용 접이식 -> 고지문 순으로 구조화 렌더링.
// structured가 없는 경우(과거 캐시 등 방어적 상황)는 기존 markdown 렌더러로 폴백한다.
export default function ChatAnswerCard({ answer }: { answer: ChatAnswer }) {
  const [quotesOpen, setQuotesOpen] = useState(false)
  const s = answer.structured

  if (!s) {
    return (
      <div className="rounded-xl border p-6" style={{ borderColor: 'var(--color-border)', boxShadow: 'var(--shadow-card)' }}>
        <div className="text-sm leading-relaxed">{renderMarkdown(answer.markdown)}</div>
        <p className="mt-4 border-t pt-3 text-[11px]" style={{ borderColor: 'var(--color-border)', color: 'var(--color-ink-muted)' }}>
          {DISCLAIMER}
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border p-6" style={{ borderColor: 'var(--color-border)', boxShadow: 'var(--shadow-card)' }}>
      <p className="text-[16px] font-semibold leading-snug" style={{ color: 'var(--color-navy)' }}>
        {s.headline}
      </p>

      {s.chips.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {s.chips.map((chip, i) => (
            <span
              key={i}
              className="rounded-full px-2.5 py-1 text-[12px] font-medium"
              style={{ backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }}
            >
              {chip}
            </span>
          ))}
        </div>
      )}

      <div className="mt-4 flex flex-col gap-3">
        {s.sections.map((sec, i) => (
          <div key={i} className="rounded-lg p-3" style={{ backgroundColor: 'var(--color-bg-subtle)' }}>
            <p className="mb-1 text-[13px] font-semibold" style={{ color: 'var(--color-ink)' }}>
              {sec.title}
            </p>
            <p className="text-[13px] leading-relaxed" style={{ color: 'var(--color-ink)' }}>
              {sec.body}
            </p>
            {sec.badges.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {sec.badges.flatMap((b) => b.split('·')).map((b, bi) => (
                  <Badge key={bi} text={b} />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {s.quotes.length > 0 && (
        <div className="mt-4 border-t pt-3" style={{ borderColor: 'var(--color-border)' }}>
          <button
            onClick={() => setQuotesOpen((v) => !v)}
            className="flex items-center gap-1 text-[12px] font-medium"
            style={{ color: 'var(--color-ink-muted)' }}
          >
            <ChevronDown size={13} strokeWidth={1.5} className={quotesOpen ? 'rotate-180 transition-transform' : 'transition-transform'} />
            원문 인용 {s.quotes.length}건 {quotesOpen ? '접기' : '펼치기'}
          </button>
          {quotesOpen && (
            <ul className="mt-2 flex flex-col gap-2">
              {s.quotes.map((q) => (
                <li key={q.odino} className="text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
                  <span
                    className="mr-1.5 rounded px-1.5 py-0.5 font-mono"
                    style={{ backgroundColor: 'var(--color-bg-subtle)' }}
                  >
                    ODINO {q.odino}
                  </span>
                  &ldquo;{q.original}&rdquo;
                  {q.summary_ko && (
                    <span className="ml-1.5" style={{ color: 'var(--color-navy)' }}>
                      — {q.summary_ko}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
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
