import type { SignalState } from './tokens'

export interface Summary {
  watched_models: number
  active_signals: number
  new_alarms_this_week: number
  us_recalled_kr_unremediated: number
  data_as_of_month: string
  hero: HeroCardData | null
  note: string
}

export interface SignalCardData {
  model: string
  state: SignalState
  top_symptom: string | null
  recent_count: number
  sparkline: number[]
  month: string
  report_id: number | null
  recall_recent: boolean
}

export interface HeroCardData extends SignalCardData {
  quote: { odino: string; text: string } | null
}

export interface SignalsResponse {
  signals: SignalCardData[]
  month: string
}

export interface LifecycleEntry {
  state: SignalState
  changed_at: string
}

export interface SignalDetail {
  id: number
  model: string
  month: string
  count: number
  baseline: number | null
  state: SignalState
  top_symptom: string | null
  report_id: number | null
  lifecycle: LifecycleEntry[]
}

export interface GapRow {
  id: number
  campaign: string
  model: string | null
  defect_summary: string | null
  date_basis: string | null
  us_date: string | null
  kr_date: string | null
  kr_start_date: string | null
  gap_days: number | null
  note: string
}

export interface GapResponse {
  gap: GapRow[]
  excluded_count: number
  excluded_note: string
}

export interface HeatmapCell {
  model: string
  month: string
  count: number
  alarm: boolean
}

export interface HeatmapResponse {
  models: string[]
  months: string[]
  cells: HeatmapCell[]
}

export interface Report {
  id: number
  signal_id: number | null
  title: string
  markdown: string
  created_at: string
}

export interface VehicleDomain {
  domain: string
  state: SignalState
  evidence: { type: 'recall'; campaign: string; report_date: string } | { type: 'complaint'; odino: string; text: string } | null
  recall_count: number
  complaint_count: number
  trend: { month: string; count: number }[]
  kr_gap: { kr_date: string | null; gap_days: number | null } | null
}

export interface VehicleMap {
  model: string
  year: string
  year_matched_complaints: boolean
  domains: VehicleDomain[]
  note: string
}

export interface VehicleHistoryPoint {
  month: string
  count: number
  state: SignalState
}

export interface VehicleHistory {
  model: string
  history: VehicleHistoryPoint[]
}

export interface ChatStep {
  id: number
  icon: string
  title: string
  result: string
  status: 'done' | 'active'
  tool: string
  duration_ms: number
}

export interface ChatSource {
  type: 'odino' | 'campaign'
  id: string
  text: string | null
  part_category: string | null
  symptom: string | null
}

export interface ChatAnswer {
  markdown: string
  sources: ChatSource[]
  report_id: number | null
}
