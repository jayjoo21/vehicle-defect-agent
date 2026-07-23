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
  id: number
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

export interface TimelinePoint {
  month: string
  count: number
  baseline: number | null
  state: SignalState
}

export interface SignalRecall {
  campaign: string
  report_date: string
  component: string | null
  summary: string | null
}

export interface SignalKrGap {
  campaign: string
  defect_summary: string | null
  date_basis: string | null
  us_date: string | null
  kr_date: string | null
  kr_start_date: string | null
  gap_days: number | null
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
  timeline: TimelinePoint[]
  recalls: SignalRecall[]
  kr_gap: SignalKrGap[]
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

export interface ReportMetrics {
  complaint_count: number | null
  concentration_pct: number | null
  lead_days: number | null
}

export interface Report {
  id: number
  signal_id: number | null
  title: string
  markdown: string
  created_at: string
  model: string | null
  campaign: string | null
  reference_month: string | null
  state: SignalState | null
  metrics: ReportMetrics | null
  parts: ChatPart[]
}

export interface VehicleDomain {
  domain: string
  state: SignalState
  evidence:
    | { type: 'recall'; campaign: string; report_date: string; part_number: string | null; supplier_canonical: string | null }
    | { type: 'complaint'; odino: string; text: string }
    | null
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

export interface ChatSection {
  title: string
  body: string
  badges: string[]
}

export interface ChatQuote {
  odino: string
  original: string
  summary_ko: string | null
}

export interface ChatPartLine {
  component_name: string | null
  part_number: string | null
  supplier_canonical: string | null
}

export interface ChatPart {
  campaign: string
  defect_cause: string | null
  remedy_type: string | null
  pdf_url: string | null
  parts: ChatPartLine[]
}

export interface ChatStructured {
  headline: string
  chips: string[]
  sections: ChatSection[]
  quotes: ChatQuote[]
  parts: ChatPart[]
  // role='agent'일 때만 백엔드가 채워 보내는 "고객 안내 요약"용 데이터(parts와 동일 소스,
  // remedy_type만 추가) — 소비자 채팅에서는 항상 null.
  agent_summary: ChatPart[] | null
}

export interface ChatAnswer {
  markdown: string
  structured: ChatStructured | null
  sources: ChatSource[]
  report_id: number | null
}

export interface RelatedPartItem {
  model: string
  campaign: string
  part_number: string
}

export interface RelatedPartsResponse {
  part_number: string
  part_family: string
  supplier_group: string | null
  shared: RelatedPartItem[]
}

export interface LoginResponse {
  account: string
  role: 'user' | 'agent'
}

export interface SubscriptionCard {
  id: number | null
  model: string
  state: SignalState
  top_symptom: string | null
  recent_count: number
  created_at: string
}

export interface SubscriptionsResponse {
  subscriptions: SubscriptionCard[]
}

export interface NotifyResponse {
  sent: boolean
  reason?: 'not_configured' | 'slack_error'
  status_code?: number
}
