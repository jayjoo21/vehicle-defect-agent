import type { ChatPart, ChatSource } from './types'
import { PART_CATEGORY_KO } from './partCategory'

export type GraphNodeGroup = 'symptom' | 'part' | 'recall' | 'shared_model'

export interface GraphNode {
  id: string
  label: string
  group: GraphNodeGroup
  // 이 노드를 클릭했을 때 GET /api/parts/{part_number}/related 확장에 쓸 실제 Part 573
  // 부품번호 목록(카테고리 노드 하나가 여러 캠페인과 교차 연결되므로, 그래프에 걸린 모든
  // 캠페인의 실제 부품번호를 합쳐 둔다 — 이미 존재하는 카테고리<->캠페인 전수 연결과
  // 동일한 근사 수준). 비어 있으면 확장 불가(단독 부품 또는 실제 부품번호 정보 없음).
  partNumbers?: string[]
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
export function buildSemanticGraph(question: string, sources: ChatSource[], parts: ChatPart[] = []): SemanticGraphData {
  const categories = [...new Set(sources.filter((s) => s.type === 'odino' && s.part_category).map((s) => s.part_category as string))]
  const campaigns = [...new Set(sources.filter((s) => s.type === 'campaign').map((s) => s.id))]

  if (categories.length === 0 && campaigns.length === 0) {
    return { nodes: [], links: [] }
  }

  // structured.parts(캠페인 기준으로 묶인 실제 Part 573 부품번호)에서 이 답변에 등장한
  // 모든 부품번호를 모아, 카테고리 노드 확장에 쓴다 — 새 값을 만들지 않고 이미 답변에 실린
  // 실측 부품번호만 사용.
  const allPartNumbers = [...new Set(parts.flatMap((p) => p.parts.map((line) => line.part_number).filter((x): x is string => !!x)))]

  const nodes: GraphNode[] = [{ id: 'q', label: question, group: 'symptom' }]
  const links: GraphLink[] = []

  for (const p of categories) {
    const partId = `part:${p}`
    nodes.push({
      id: partId,
      label: PART_CATEGORY_KO[p] ?? p,
      group: 'part',
      partNumbers: allPartNumbers.length > 0 ? allPartNumbers : undefined,
    })
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
  shared_model: '공유 차종',
}

export const GROUP_COLOR: Record<GraphNodeGroup, string> = {
  symptom: '#F97316', // orange-500
  part: '#3B82F6', // blue-500
  recall: '#EF4444', // red-500
  shared_model: '#A855F7', // purple-500 — 부품 노드 확장으로 드러난 공유 차종
}
