import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { loginAsAgent } from '../lib/role'

// 목(mock) 로그인 화면 — 회사용 상담 지원 콘솔 데모 진입점. 아이디·비밀번호는 어떤 값을
// 입력해도(빈 값 포함) 통과한다. 실제 계정 인증·비밀번호 검증은 연결돼 있지 않다.
export default function Login() {
  const [id, setId] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()

  function submit(e: FormEvent) {
    e.preventDefault()
    loginAsAgent()
    navigate('/agent-chat')
  }

  return (
    <div className="mx-auto max-w-sm">
      <div className="card p-6">
        <h1 className="text-xl font-semibold" style={{ color: 'var(--color-navy)' }}>
          회사용 상담 지원 콘솔
        </h1>
        <p className="mt-1.5 text-[13px] leading-relaxed" style={{ color: 'var(--color-ink-muted)' }}>
          상담사 전용 데모 로그인입니다. 실제 계정 인증은 연결되어 있지 않으며, 어떤 값을
          입력해도 통과합니다.
        </p>
        <form onSubmit={submit} className="mt-5 flex flex-col gap-3">
          <input
            value={id}
            onChange={(e) => setId(e.target.value)}
            placeholder="아이디"
            autoComplete="username"
            className="rounded-lg border px-4 py-2.5 text-sm outline-none"
            style={{ borderColor: 'var(--color-border)' }}
          />
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            placeholder="비밀번호"
            autoComplete="current-password"
            className="rounded-lg border px-4 py-2.5 text-sm outline-none"
            style={{ borderColor: 'var(--color-border)' }}
          />
          <button
            type="submit"
            className="btn-tension rounded-lg px-4 py-2.5 text-sm font-medium text-white"
            style={{ backgroundColor: 'var(--color-navy)' }}
          >
            상담사 로그인
          </button>
        </form>
      </div>
    </div>
  )
}
