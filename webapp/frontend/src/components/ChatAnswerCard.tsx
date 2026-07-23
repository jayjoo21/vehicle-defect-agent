import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { FileText, ChevronDown } from 'lucide-react'
import type { ChatAnswer } from '../lib/types'
import { renderMarkdown } from '../lib/markdown'
import { linkifyGlossary } from '../lib/glossary'
import { buildSemanticGraph } from '../lib/semanticGraph'
import { DISCLAIMER } from '../lib/tokens'
import SourceChips from './SourceChips'
import SemanticNetworkGraph from './SemanticNetworkGraph'

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
export default function ChatAnswerCard({ question, answer }: { question: string; answer: ChatAnswer }) {
  const [quotesOpen, setQuotesOpen] = useState(false)
  const [partsOpen, setPartsOpen] = useState(false)
  const s = answer.structured
  // sources(odino/campaign)에 실린 실제 부품·캠페인 정보로부터 그래프를 구성 — 근거가 없으면
  // 빈 그래프를 반환하고 SemanticNetworkGraph가 자체 더미 데이터로 대체한다.
  const graph = useMemo(
    () => buildSemanticGraph(question, answer.sources, answer.structured?.parts ?? []),
    [question, answer.sources, answer.structured],
  )

  if (!s) {
    return (
      <div className="card p-6">
        <div className="text-sm leading-relaxed">{renderMarkdown(answer.markdown)}</div>
        <SemanticGraphSection graph={graph} />
        <SourceChips parts={[]} />
        <p className="mt-4 border-t pt-3 text-[11px]" style={{ borderColor: 'var(--color-border)', color: 'var(--color-ink-muted)' }}>
          {DISCLAIMER}
        </p>
      </div>
    )
  }

  return (
    <div className="card p-6">
      {s.agent_summary && s.agent_summary.length > 0 && <AgentSummaryBlock groups={s.agent_summary} />}

      <p className="text-[16px] font-semibold leading-snug" style={{ color: 'var(--color-navy)' }}>
        {linkifyGlossary(s.headline)}
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
              {linkifyGlossary(sec.body)}
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

      {s.parts.length > 0 && (
        <div className="mt-4 border-t pt-3" style={{ borderColor: 'var(--color-border)' }}>
          <button
            onClick={() => setPartsOpen((v) => !v)}
            className="flex items-center gap-1 text-[12px] font-medium"
            style={{ color: 'var(--color-ink-muted)' }}
          >
            <ChevronDown size={13} strokeWidth={1.5} className={partsOpen ? 'rotate-180 transition-transform' : 'transition-transform'} />
            결함 부품 정보 {s.parts.length}건 {partsOpen ? '접기' : '펼치기'}
          </button>
          {partsOpen && (
            <ul className="mt-2 flex flex-col gap-3">
              {s.parts.map((p, i) => {
                const suppliers = new Set(p.parts.map((line) => line.supplier_canonical).filter(Boolean))
                const singleSupplier = suppliers.size === 1 ? [...suppliers][0] : null
                return (
                  <li key={i} className="text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge text={p.campaign} />
                      {singleSupplier && (
                        <span className="text-[11px]" style={{ color: 'var(--color-navy)' }}>
                          공급사: {singleSupplier}
                        </span>
                      )}
                    </div>
                    {p.defect_cause && (
                      <p className="mt-1 rounded p-2 text-[11px] leading-relaxed" style={{ backgroundColor: 'var(--color-bg-subtle)' }}>
                        &ldquo;{p.defect_cause}&rdquo;
                      </p>
                    )}
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {p.parts.map((line, li) => (
                        <span key={li} className="inline-flex items-center gap-1">
                          {line.component_name && <Badge text={line.component_name} />}
                          {line.part_number && <Badge text={line.part_number} />}
                          {!singleSupplier && line.supplier_canonical && (
                            <span className="text-[10px]" style={{ color: 'var(--color-navy)' }}>
                              ({line.supplier_canonical})
                            </span>
                          )}
                        </span>
                      ))}
                    </div>
                    <p className="mt-1 text-[10px]" style={{ color: 'var(--color-ink-muted)' }}>
                      출처: NHTSA Part 573 공식 리콜 문서 원문 기준
                    </p>
                  </li>
                )
              })}
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

      <SemanticGraphSection graph={graph} />

      <SourceChips parts={s.parts} />

      <p className="mt-4 border-t pt-3 text-[11px]" style={{ borderColor: 'var(--color-border)', color: 'var(--color-ink-muted)' }}>
        {DISCLAIMER}
      </p>
    </div>
  )
}

// 상담사 모드(role='agent') 전용 — 통화 중 즉시 읽을 수 있는 요약을 답변 맨 위에 둔다.
// groups는 백엔드가 parts와 동일 소스(parts 테이블)에서 캠페인 단위로 묶어 보낸 데이터로,
// 여기서 새 문구를 만들지 않고 defect_cause·remedy_type 원문과 부품 식별 정보만 나열한다.
function AgentSummaryBlock({ groups }: { groups: NonNullable<ChatAnswer['structured']>['agent_summary'] }) {
  if (!groups) return null
  return (
    <div
      className="mb-4 rounded-lg border-2 p-4"
      style={{ borderColor: 'var(--color-navy)', backgroundColor: 'var(--color-navy-soft)' }}
    >
      <p className="mb-3 text-[11px] font-bold uppercase tracking-wide" style={{ color: 'var(--color-navy)' }}>
        고객 안내 요약 (상담사용)
      </p>
      <div className="flex flex-col gap-3">
        {groups.map((g, i) => (
          <div key={i} className="rounded-md bg-white/70 p-3 text-[13px]" style={{ color: 'var(--color-ink)' }}>
            <Badge text={g.campaign} />
            {g.defect_cause && (
              <p className="mt-1.5 leading-relaxed">
                <span className="font-semibold">결함원인 </span>
                {g.defect_cause}
              </p>
            )}
            {g.remedy_type && (
              <p className="mt-1.5 leading-relaxed">
                <span className="font-semibold">시정 방식 </span>
                {g.remedy_type}
              </p>
            )}
            {g.parts.length > 0 && (
              <p className="mt-1.5 text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
                <span className="font-semibold">대상 부품 </span>
                {g.parts
                  .map((line) => [line.component_name, line.part_number, line.supplier_canonical].filter(Boolean).join(' '))
                  .join(' / ')}
              </p>
            )}
          </div>
        ))}
      </div>
      <p className="mt-3 text-[11px]" style={{ color: 'var(--color-ink-muted)' }}>
        * 고객에게 안내 시 참고용입니다 — NHTSA 공식 리콜 문서 기준이며, 개별 차량 진단을 대체하지 않습니다.
      </p>
    </div>
  )
}

function SemanticGraphSection({ graph }: { graph: ReturnType<typeof buildSemanticGraph> }) {
  return (
    <div className="mt-4 border-t pt-3" style={{ borderColor: 'var(--color-border)' }}>
      <p className="mb-2 text-[12px] font-medium" style={{ color: 'var(--color-ink-muted)' }}>
        시맨틱 분석 그래프 — 증상 · 부품 · 리콜 캠페인 연결
      </p>
      <SemanticNetworkGraph data={graph} />
    </div>
  )
}
