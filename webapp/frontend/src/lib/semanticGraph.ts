import type { ChatSource } from './types'
import { PART_CATEGORY_KO } from './partCategory'

export type GraphNodeGroup = 'symptom' | 'part' | 'recall'

export interface GraphNode {
  id: string
  label: string
  group: GraphNodeGroup
}

export interface GraphLink {
  source: string
  target: string
}

export interface SemanticGraphData {
  nodes: GraphNode[]
  links: GraphLink[]
}

// 답변에 실제로 실린 sources(odino=신고, campaign=리콜)로부터 그래프를 구성한다 — 지어낸 관계가
// 아니라 이미 화면에 인용문·뱃지로 표시 중인 것과 같은 근거를 노드/엣지로 재배열한 것이다.
// symptom 필드는 DB에 거의 비어 있어(구조화 LLM 테스트 표본 20건 외엔 전부 null) 대신 사용자가
// 실제로 입력한 질문 원문을 증상 노드로 쓴다.
export function buildSemanticGraph(question: string, sources: ChatSource[]): SemanticGraphData {
  const parts = [...new Set(sources.filter((s) => s.type === 'odino' && s.part_category).map((s) => s.part_category as string))]
  const campaigns = [...new Set(sources.filter((s) => s.type === 'campaign').map((s) => s.id))]

  if (parts.length === 0 && campaigns.length === 0) {
    return { nodes: [], links: [] }
  }

  const nodes: GraphNode[] = [{ id: 'q', label: question, group: 'symptom' }]
  const links: GraphLink[] = []

  for (const p of parts) {
    const partId = `part:${p}`
    nodes.push({ id: partId, label: PART_CATEGORY_KO[p] ?? p, group: 'part' })
    links.push({ source: 'q', target: partId })
    for (const c of campaigns) {
      links.push({ source: partId, target: `recall:${c}` })
    }
  }
  for (const c of campaigns) {
    nodes.push({ id: `recall:${c}`, label: c, group: 'recall' })
  }

  return { nodes, links }
}

// 실제 sources가 없는 맥락(컴포넌트 단독 미리보기 등)을 위한 더미 데이터.
export const MOCK_SEMANTIC_GRAPH: SemanticGraphData = {
  nodes: [
    { id: 'q', label: '계기판이 깜빡이다 꺼져요', group: 'symptom' },
    { id: 'part:ICCU', label: 'ICCU', group: 'part' },
    { id: 'part:ADAS', label: 'ADAS', group: 'part' },
    { id: 'recall:24V757000', label: '24V757000', group: 'recall' },
    { id: 'recall:24V200000', label: '24V200000', group: 'recall' },
  ],
  links: [
    { source: 'q', target: 'part:ICCU' },
    { source: 'q', target: 'part:ADAS' },
    { source: 'part:ICCU', target: 'recall:24V757000' },
    { source: 'part:ICCU', target: 'recall:24V200000' },
  ],
}

export const GROUP_LABEL_KO: Record<GraphNodeGroup, string> = {
  symptom: '증상',
  part: '부품',
  recall: '리콜 캠페인',
}

export const GROUP_COLOR: Record<GraphNodeGroup, string> = {
  symptom: '#F97316', // orange-500
  part: '#3B82F6', // blue-500
  recall: '#EF4444', // red-500
}
