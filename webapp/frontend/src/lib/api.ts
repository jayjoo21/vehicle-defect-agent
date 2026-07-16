import type {
  GapResponse,
  RelatedPartsResponse,
  Report,
  SignalDetail,
  SignalsResponse,
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
}
