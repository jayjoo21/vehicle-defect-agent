// 목(mock) 로그인/역할 스위치 — 실제 인증이 아니다. 상담사 전용 화면(/agent-chat) 접근
// 여부와 채팅 답변 표시 레이어(고객 안내 요약 블록)만 바꾸는 로컬 스위치일 뿐, 값 검증도
// 서버 세션도 없다. 보안 기능으로 오해하지 말 것.
import { useSyncExternalStore } from 'react'

export type Role = 'consumer' | 'agent'

const KEY = 'mobiscope:role'
const EVENT = 'mobiscope:role-changed'

export function getRole(): Role {
  return localStorage.getItem(KEY) === 'agent' ? 'agent' : 'consumer'
}

export function loginAsAgent() {
  localStorage.setItem(KEY, 'agent')
  window.dispatchEvent(new Event(EVENT))
}

export function logout() {
  localStorage.removeItem(KEY)
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
