import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { motion, useReducedMotion } from 'framer-motion'
import { Send, Download, Loader2 } from 'lucide-react'
import html2pdf from 'html2pdf.js'
import { streamChat } from '../lib/sse'
import type { ChatAnswer, ChatStep } from '../lib/types'
import InvestigationTimeline from '../components/InvestigationTimeline'
import ChatAnswerCard from '../components/ChatAnswerCard'

interface Turn {
  question: string
  steps: ChatStep[]
  answer: ChatAnswer | null
  pending: boolean
  error: string | null
}

// 백엔드 detect_scenario()가 인식하는 키워드와 정확히 매칭 — 클릭하면 실제 데모 시나리오로 이어진다.
const SUGGESTED_QUESTIONS = [
  'EV6 계기판이 깜빡이다 꺼져요',
  '아이오닉5 배터리 리콜 있나요?',
  '아이오닉5 충전 중 12V 배터리 경고가 떠요',
  'EV6 계기판 블랙아웃 현상 있나요?',
]

function pdfFilename(): string {
  const d = new Date()
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `MOBISCOPE_조사리포트_${yyyy}${mm}${dd}.pdf`
}

// 마지막 turn만 갱신하는 헬퍼 — 스트리밍 콜백(onStep/onAnswer/...)이 배열 전체가 아니라
// 진행 중인 마지막 항목 하나만 바꿔야 해서 반복된다.
function updateLastTurn(turns: Turn[], patch: (t: Turn) => Turn): Turn[] {
  if (turns.length === 0) return turns
  const next = [...turns]
  next[next.length - 1] = patch(next[next.length - 1])
  return next
}

export default function Chat() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [input, setInput] = useState(() => searchParams.get('q') ?? '')
  const [turns, setTurns] = useState<Turn[]>([])
  const [exporting, setExporting] = useState(false)
  const reduceMotion = useReducedMotion()
  const printRef = useRef<HTMLDivElement>(null)
  const pending = turns.length > 0 && turns[turns.length - 1].pending

  useEffect(() => {
    // 내 차 페이지의 "이 증상 조사하기"에서 넘어온 프리필 — 자동 전송은 하지 않음
    const q = searchParams.get('q')
    if (q) {
      setInput(q)
      setSearchParams({}, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function ask(question: string) {
    if (!question.trim() || pending) return
    setInput('')
    const next: Turn = { question, steps: [], answer: null, pending: true, error: null }
    setTurns((ts) => [...ts, next])

    await streamChat(question, {
      onStep: (step) => setTurns((ts) => updateLastTurn(ts, (t) => ({ ...t, steps: [...t.steps, step] }))),
      onAnswer: (answer) => setTurns((ts) => updateLastTurn(ts, (t) => ({ ...t, answer }))),
      onDone: () => setTurns((ts) => updateLastTurn(ts, (t) => ({ ...t, pending: false }))),
      onError: (err) => setTurns((ts) => updateLastTurn(ts, (t) => ({ ...t, pending: false, error: err.message }))),
    })
  }

  async function exportPdf() {
    if (!printRef.current || exporting) return
    setExporting(true)
    try {
      await html2pdf()
        .set({
          filename: pdfFilename(),
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
    <div className="flex h-full flex-col">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold" style={{ color: 'var(--color-navy)' }}>
          조사 채팅
        </h1>
        {turns.length > 0 && (
          <button
            onClick={exportPdf}
            disabled={exporting}
            className="btn-tension inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-medium disabled:opacity-60"
            style={{ backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }}
          >
            {exporting ? <Loader2 size={14} strokeWidth={1.75} className="animate-spin" /> : <Download size={14} strokeWidth={1.75} />}
            {exporting ? '내보내는 중...' : 'PDF로 내보내기'}
          </button>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-4">
        {turns.length === 0 && (
          <p className="card p-6 text-sm" style={{ color: 'var(--color-ink-muted)' }}>
            차종명과 증상을 함께 입력해 보세요. 예: &ldquo;내 차 EV6인데 계기판이 깜빡여요&rdquo;, &ldquo;아이오닉5 충전 중에 12V 배터리
            경고가 떠요&rdquo; — 또는 아래 추천 질문을 눌러보세요.
          </p>
        )}

        {turns.length > 0 && (
          <div ref={printRef} className="flex flex-col gap-6 bg-white p-1">
            {turns.map((turn, i) => (
              <div key={i} className="flex flex-col gap-3">
                <div className="self-end rounded-xl px-4 py-2.5 text-sm text-white" style={{ backgroundColor: 'var(--color-navy)' }}>
                  {turn.question}
                </div>
                <InvestigationTimeline steps={turn.steps} pending={turn.pending} />
                {turn.error && <p className="text-sm text-red-600">오류: {turn.error}</p>}
                {turn.answer && <ChatAnswerCard answer={turn.answer} />}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 입력 영역 — 대화 캔버스(회색 배경)와 구분되는 흰색 독(top shadow) */}
      <div
        className="sticky bottom-0 mt-6 rounded-t-xl p-4"
        style={{ backgroundColor: 'var(--color-surface)', boxShadow: '0 -6px 16px rgba(15,23,42,.05)' }}
      >
        {turns.length === 0 && (
          <motion.div
            className="scrollbar-hide mb-3 flex gap-2 overflow-x-auto pb-1"
            initial="hidden"
            animate="show"
            variants={{ hidden: {}, show: { transition: { staggerChildren: reduceMotion ? 0 : 0.08 } } }}
          >
            {SUGGESTED_QUESTIONS.map((q) => (
              <motion.button
                key={q}
                type="button"
                onClick={() => ask(q)}
                className="btn-tension shrink-0 whitespace-nowrap rounded-full px-3.5 py-2 text-[13px] font-medium"
                style={{ backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }}
                variants={{ hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0 } }}
                transition={{ duration: 0.25 }}
              >
                {q}
              </motion.button>
            ))}
          </motion.div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault()
            ask(input)
          }}
          className="flex gap-2"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="내 차 EV6인데 계기판이 깜빡여요"
            className="flex-1 rounded-lg border px-4 py-2.5 text-sm outline-none"
            style={{ borderColor: 'var(--color-border)' }}
          />
          <button
            type="submit"
            disabled={pending}
            className="btn-tension flex items-center gap-1.5 rounded-lg px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
            style={{ backgroundColor: 'var(--color-navy)' }}
          >
            <Send size={15} strokeWidth={1.5} />
            전송
          </button>
        </form>
      </div>
    </div>
  )
}
