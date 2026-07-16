// POST /api/chat SSE 클라이언트. EventSource는 POST 바디를 지원하지 않아 fetch+스트림으로 직접 파싱한다.
import type { ChatAnswer, ChatStep } from './types'

interface StreamChatHandlers {
  onStep: (step: ChatStep) => void
  onAnswer: (answer: ChatAnswer) => void
  onDone: () => void
  onError: (err: Error) => void
}

function parseEvent(raw: string, handlers: StreamChatHandlers) {
  let event = 'message'
  let data = ''
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data += line.slice(5).trim()
  }
  if (!data) return
  const parsed = JSON.parse(data)
  if (event === 'step') handlers.onStep(parsed as ChatStep)
  else if (event === 'answer') handlers.onAnswer(parsed as ChatAnswer)
  else if (event === 'done') handlers.onDone()
}

export async function streamChat(
  message: string,
  handlers: StreamChatHandlers,
  role: 'consumer' | 'agent' = 'consumer',
): Promise<void> {
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, role }),
    })
    if (!res.ok || !res.body) {
      throw new Error(`채팅 요청 실패: ${res.status}`)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let sepIndex: number
      while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
        const rawEvent = buffer.slice(0, sepIndex)
        buffer = buffer.slice(sepIndex + 2)
        parseEvent(rawEvent, handlers)
      }
    }
  } catch (err) {
    handlers.onError(err instanceof Error ? err : new Error(String(err)))
  }
}
