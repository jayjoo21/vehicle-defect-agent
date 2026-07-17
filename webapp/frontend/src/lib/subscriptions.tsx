import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from './api'
import { useAccount, useRole } from './role'
import type { SubscriptionCard } from './types'

interface SubscriptionsState {
  items: SubscriptionCard[]
  loading: boolean
  refresh: () => void
}

const SubscriptionsContext = createContext<SubscriptionsState>({ items: [], loading: false, refresh: () => {} })

// 헤더 종 배지·구독 드로어·내 차의 구독 모달이 모두 같은 목록을 공유한다 — 어느 화면에서
// 구독/해제하든 다른 화면이 별도 새로고침 없이 즉시 반영되도록 Context 하나로 묶는다.
export function SubscriptionsProvider({ children }: { children: ReactNode }) {
  const role = useRole()
  const account = useAccount()
  const [items, setItems] = useState<SubscriptionCard[]>([])
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(() => {
    if (role !== 'user' || !account) {
      setItems([])
      return
    }
    setLoading(true)
    api
      .subscriptions(account)
      .then((res) => setItems(res.subscriptions))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [role, account])

  useEffect(() => {
    refresh()
  }, [refresh])

  return <SubscriptionsContext.Provider value={{ items, loading, refresh }}>{children}</SubscriptionsContext.Provider>
}

export function useSubscriptions() {
  return useContext(SubscriptionsContext)
}
