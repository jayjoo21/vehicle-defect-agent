import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Send } from 'lucide-react'
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

export default function Chat() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [input, setInput] = useState(() => searchParams.get('q') ?? '')
  const [turn, setTurn] = useState<Turn | null>(null)

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
    if (!question.trim() || turn?.pending) return
    setInput('')
    const next: Turn = { question, steps: [], answer: null, pending: true, error: null }
    setTurn(next)

    await streamChat(question, {
      onStep: (step) => setTurn((t) => (t ? { ...t, steps: [...t.steps, step] } : t)),
      onAnswer: (answer) => setTurn((t) => (t ? { ...t, answer } : t)),
      onDone: () => setTurn((t) => (t ? { ...t, pending: false } : t)),
      onError: (err) => setTurn((t) => (t ? { ...t, pending: false, error: err.message } : t)),
    })
  }

  return (
    <div className="flex h-full flex-col">
      <h1 className="mb-6 text-2xl font-semibold" style={{ color: 'var(--color-navy)' }}>
        조사 채팅
      </h1>

      <div className="flex flex-1 flex-col gap-4">
        {!turn && (
          <p className="rounded-xl border p-6 text-sm" style={{ borderColor: 'var(--color-border)', color: 'var(--color-ink-muted)' }}>
            차종명과 증상을 함께 입력해 보세요. 예: &ldquo;내 차 EV6인데 계기판이 깜빡여요&rdquo;, &ldquo;아이오닉5 충전 중에 12V 배터리
            경고가 떠요&rdquo;
          </p>
        )}

        {turn && (
          <div className="flex flex-col gap-3">
            <div className="self-end rounded-xl px-4 py-2.5 text-sm text-white" style={{ backgroundColor: 'var(--color-navy)' }}>
              {turn.question}
            </div>
            <InvestigationTimeline steps={turn.steps} pending={turn.pending} />
            {turn.error && <p className="text-sm text-red-600">오류: {turn.error}</p>}
            {turn.answer && <ChatAnswerCard answer={turn.answer} />}
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          ask(input)
        }}
        className="sticky bottom-0 mt-6 flex gap-2 border-t pt-4"
        style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-bg)' }}
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
          disabled={turn?.pending}
          className="flex items-center gap-1.5 rounded-lg px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
          style={{ backgroundColor: 'var(--color-navy)' }}
        >
          <Send size={15} strokeWidth={1.5} />
          전송
        </button>
      </form>
    </div>
  )
}
