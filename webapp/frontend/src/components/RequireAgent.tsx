import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useRole } from '../lib/role'

// 상담사 전용 라우트 가드 — role='agent'(목 로그인)가 아니면 /login으로 되돌린다.
// 실제 인증이 아니라 로컬 스위치 확인일 뿐이다(lib/role.ts 참조).
export default function RequireAgent({ children }: { children: ReactNode }) {
  const role = useRole()
  if (role !== 'agent') return <Navigate to="/login" replace />
  return <>{children}</>
}
