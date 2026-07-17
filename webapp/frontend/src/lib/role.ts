// 목(mock) 로그인/역할 스위치 — 실제 세션 인증이 아니다(backend/auth.py의 데모 test 계정
// 2개와만 매칭). role='agent' 판정만 상담사 전용 화면(/agent-chat) 접근 여부·채팅 답변
// 표시 레이어를 바꾸고, role='user'는 차종 구독 기능을 활성화한다. 값 검증도 서버 세션도
// 없다 — 보안 기능으로 오해하지 말 것.
import { useSyncExternalStore } from 'react'

export type Role = 'consumer' | 'user' | 'agent'

const KEY = 'mobiscope:role'
const ACCOUNT_KEY = 'mobiscope:account'
const EVENT = 'mobiscope:role-changed'

export function getRole(): Role {
  const v = localStorage.getItem(KEY)
  return v === 'agent' || v === 'user' ? v : 'consumer'
}

export function getAccount(): string | null {
  return localStorage.getItem(ACCOUNT_KEY)
}

export function login(role: 'user' | 'agent', account: string) {
  localStorage.setItem(KEY, role)
  localStorage.setItem(ACCOUNT_KEY, account)
  window.dispatchEvent(new Event(EVENT))
}

export function logout() {
  localStorage.removeItem(KEY)
  localStorage.removeItem(ACCOUNT_KEY)
  window.dispatchEvent(new Event(EVENT))
}

function subscribe(callback: () => void) {
  window.addEventListener(EVENT, callback)
  window.addEventListener('storage', callback)
  return () => {
    window.removeEventListener(EVENT, callback)
    window.removeEventListener('storage', callback)
  }
}

// localStorage 변경(다른 탭 포함)과 로컬 login/logout 호출 양쪽에 반응하는 역할 상태 훅.
export function useRole(): Role {
  return useSyncExternalStore(subscribe, getRole)
}

export function useAccount(): string | null {
  return useSyncExternalStore(subscribe, getAccount)
}
