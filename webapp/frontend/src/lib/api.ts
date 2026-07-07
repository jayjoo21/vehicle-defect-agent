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
  summary: () => request('/summary'),
  signals: (params?: { state?: string; model?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString()
    return request(`/signals${qs ? `?${qs}` : ''}`)
  },
  signal: (id: number) => request(`/signals/${id}`),
  vehicleMap: (model: string, year: string) => request(`/vehicles/${model}/${year}/map`),
  vehicleHistory: (model: string) => request(`/vehicles/${model}/history`),
  gap: () => request('/gap'),
  heatmap: () => request('/heatmap'),
  report: (id: number) => request(`/reports/${id}`),
}
