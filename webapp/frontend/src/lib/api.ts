import type {
  GapResponse,
  LoginResponse,
  NotifyResponse,
  RelatedPartsResponse,
  Report,
  SignalDetail,
  SignalsResponse,
  SubscriptionsResponse,
  Summary,
  VehicleHistory,
  VehicleMap,
  HeatmapResponse,
} from './types'

const BASE = '/api'

async function request<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status}`)
  }
  return res.json() as Promise<T>
}

async function requestJson<T>(path: string, method: 'POST' | 'DELETE', body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).detail ?? ''
    } catch {
      // 응답이 JSON이 아니면 무시
    }
    throw new Error(detail || `API ${path} failed: ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string }>('/health'),
  summary: () => request<Summary>('/summary'),
  signals: (params?: { state?: string; model?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString()
    return request<SignalsResponse>(`/signals${qs ? `?${qs}` : ''}`)
  },
  signal: (id: number) => request<SignalDetail>(`/signals/${id}`),
  vehicleMap: (model: string, year: string) => request<VehicleMap>(`/vehicles/${model}/${year}/map`),
  vehicleHistory: (model: string) => request<VehicleHistory>(`/vehicles/${model}/history`),
  gap: () => request<GapResponse>('/gap'),
  heatmap: () => request<HeatmapResponse>('/heatmap'),
  report: (id: number) => request<Report>(`/reports/${id}`),
  relatedParts: (partNumber: string) => request<RelatedPartsResponse>(`/parts/${encodeURIComponent(partNumber)}/related`),
  login: (email: string, password: string) => requestJson<LoginResponse>('/auth/login', 'POST', { email, password }),
  subscriptions: (account: string) =>
    request<SubscriptionsResponse>(`/subscriptions?account=${encodeURIComponent(account)}`),
  subscribe: (account: string, baseModel: string) =>
    requestJson<{ subscribed: boolean; model: string }>('/subscriptions', 'POST', { account, base_model: baseModel }),
  unsubscribe: (account: string, baseModel: string) =>
    requestJson<{ subscribed: boolean; model: string }>('/subscriptions', 'DELETE', { account, base_model: baseModel }),
  notify: (baseModel: string) => requestJson<NotifyResponse>(`/notify/${encodeURIComponent(baseModel)}`, 'POST'),
}
