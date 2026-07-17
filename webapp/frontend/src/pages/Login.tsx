import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { login } from '../lib/role'

// 로그인 화면 — backend/auth.py의 test 계정 2개(user@test.com·agent@test.com, 비밀번호 둘
// 다 "test")와만 매칭하는 데모 인증이지만, 화면에는 데모 흔적(계정/비번 안내)을 노출하지
// 않는다. 진짜 회원가입/세션 시스템이 아니다(비밀번호 해싱·서버 세션 없음). user 계정은
// 차종 구독 기능을, agent 계정은 기존 상담사 콘솔(/agent-chat)을 연다.
type AccountType = 'user' | 'agent'

const TAB_LABEL: Record<AccountType, string> = { user: 'Personal', agent: 'Business' }
const MISMATCH_MESSAGE: Record<AccountType, string> = {
  user: 'Personal 계정으로 로그인해 주세요',
  agent: 'Business 계정으로 로그인해 주세요',
}

export default function Login() {
  const [tab, setTab] = useState<AccountType>('user')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()

  function selectTab(next: AccountType) {
    setTab(next)
    setError(null)
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const res = await api.login(email, password)
      if (res.role !== tab) {
        setError(MISMATCH_MESSAGE[tab])
        return
      }
      login(res.role, res.account)
      navigate(res.role === 'agent' ? '/agent-chat' : '/')
    } catch {
      setError('계정을 확인하세요')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <div className="card p-6">
        <h1 className="text-xl font-semibold" style={{ color: 'var(--color-navy)' }}>
          로그인
        </h1>

        <div className="mt-4 flex gap-1 rounded-lg p-1" style={{ backgroundColor: 'var(--color-bg-subtle)' }}>
          {(['user', 'agent'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => selectTab(t)}
              className="flex-1 rounded-md py-2 text-sm font-medium transition-colors"
              style={
                tab === t
                  ? { backgroundColor: 'var(--color-navy)', color: '#fff' }
                  : { color: 'var(--color-ink-muted)' }
              }
            >
              {TAB_LABEL[t]}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="mt-5 flex flex-col gap-3">
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="아이디 (이메일)"
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
          {error && <p className="text-[13px] text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="btn-tension rounded-lg px-4 py-2.5 text-sm font-medium text-white disabled:opacity-60"
            style={{ backgroundColor: 'var(--color-navy)' }}
          >
            {submitting ? '확인 중...' : '로그인'}
          </button>
        </form>
      </div>
    </div>
  )
}
