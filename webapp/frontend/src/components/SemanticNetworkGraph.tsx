import { useCallback, useMemo, useRef, useState } from 'react'
import ForceGraph2D, { type NodeObject } from 'react-force-graph-2d'
import { useElementSize } from '../lib/useElementSize'
import { api } from '../lib/api'
import { GROUP_COLOR, GROUP_LABEL_KO, MOCK_SEMANTIC_GRAPH, type SemanticGraphData, type GraphLink, type GraphNode, type GraphNodeGroup } from '../lib/semanticGraph'

type Node = GraphNode & { expandedBy?: string }

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

// 시맨틱 분석 과정(증상->부품->리콜)을 물리 기반 그래프로 보여준다. data가 없거나 근거
// 노드가 없으면(sources에 부품/캠페인 정보가 없는 답변) 자리표시용 더미 그래프로 대체한다.
// 툴팁은 force-graph 내부 라이브러리(float-tooltip)가 주입하는 .float-tooltip-kap 클래스를
// index.css에서 전역 오버라이드해 다른 차트들과 동일한 글래스모피즘으로 통일했다.
//
// 부품(part) 노드는 실제 Part 573 부품번호(partNumbers)를 갖고 있으면 클릭해 확장할 수 있다 —
// GET /api/parts/{part_number}/related로 같은 부품 계열을 공유하는 다른 차종·리콜을 조회해
// 새 노드(공유 차종=보라, 공유 리콜=기존 recall 빨강 재사용)로 그래프에 덧붙인다. 다시 클릭하면
// 그 확장으로 추가된 노드만 접는다(다른 확장이 같은 노드를 공유하는 드문 경우는 남겨둔다).
export default function SemanticNetworkGraph({ data }: { data?: SemanticGraphData }) {
  const graph = data && data.nodes.length > 0 ? data : MOCK_SEMANTIC_GRAPH
  const [containerRef, { width, height }] = useElementSize<HTMLDivElement>()
  const [extraNodes, setExtraNodes] = useState<Node[]>([])
  const [extraLinks, setExtraLinks] = useState<GraphLink[]>([])
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const expansions = useRef<Map<string, string[]>>(new Map())

  const baseNodeIds = useMemo(() => new Set(graph.nodes.map((n) => n.id)), [graph])

  const allNodes: Node[] = useMemo(() => [...graph.nodes, ...extraNodes.filter((n) => !baseNodeIds.has(n.id))], [graph, extraNodes, baseNodeIds])
  const allLinks: GraphLink[] = useMemo(() => [...graph.links, ...extraLinks], [graph, extraLinks])

  const graphData = useMemo(
    () => ({
      nodes: allNodes.map((n) => ({ ...n })) as Node[],
      links: allLinks.map((l) => ({ ...l })),
    }),
    [allNodes, allLinks],
  )

  async function toggleExpand(node: Node) {
    if (expansions.current.has(node.id)) {
      // 접기: 이 노드가 만든 링크(source가 이 노드인 것)는 전부 제거하고, 이 노드가 새로
      // 만들었던 노드 중 다른 아직 펼쳐진 확장이 여전히 필요로 하지 않는 것만 제거한다.
      const addedIds = new Set(expansions.current.get(node.id))
      expansions.current.delete(node.id)
      const stillNeeded = new Set([...expansions.current.values()].flat())
      setExtraNodes((prev) => prev.filter((n) => !addedIds.has(n.id) || stillNeeded.has(n.id)))
      setExtraLinks((prev) => prev.filter((l) => l.source !== node.id))
      return
    }

    const partNumbers = node.partNumbers ?? []
    if (partNumbers.length === 0) {
      setNotice('실제 부품번호 정보가 없어 확장할 수 없습니다.')
      return
    }

    setLoadingId(node.id)
    setNotice(null)
    try {
      const results = await Promise.all(partNumbers.map((pn) => api.relatedParts(pn).catch(() => null)))
      const sharedModels = new Set<string>()
      const sharedRecalls = new Set<string>()
      for (const r of results) {
        if (!r) continue
        for (const item of r.shared) {
          sharedModels.add(item.model)
          sharedRecalls.add(item.campaign)
        }
      }

      if (sharedModels.size === 0) {
        setNotice('이 부품은 다른 차종·리콜과 공유되지 않습니다.')
        setLoadingId(null)
        return
      }

      const newNodes: Node[] = []
      const newLinks: GraphLink[] = []
      const addedIds: string[] = []
      const linkExists = (target: string) => graph.links.some((l) => l.source === node.id && l.target === target)

      for (const c of sharedRecalls) {
        const id = `recall:${c}`
        if (!baseNodeIds.has(id) && !extraNodes.some((n) => n.id === id)) {
          newNodes.push({ id, label: c, group: 'recall', expandedBy: node.id })
          addedIds.push(id)
        }
        if (!linkExists(id)) newLinks.push({ source: node.id, target: id })
      }
      for (const m of sharedModels) {
        const id = `model:${m}`
        if (!extraNodes.some((n) => n.id === id)) {
          newNodes.push({ id, label: m, group: 'shared_model', expandedBy: node.id })
          addedIds.push(id)
        }
        newLinks.push({ source: node.id, target: id })
      }

      expansions.current.set(node.id, addedIds)
      setExtraNodes((prev) => [...prev, ...newNodes])
      setExtraLinks((prev) => [...prev, ...newLinks])
    } finally {
      setLoadingId(null)
    }
  }

  const onNodeClick = useCallback(
    (node: NodeObject) => {
      const n = node as unknown as Node
      if (n.group !== 'part') return
      void toggleExpand(n)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [extraNodes, baseNodeIds],
  )

  const nodeCanvasObject = useCallback(
    (node: NodeObject, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const n = node as NodeObject & Node
      const radius = 5
      const x = node.x ?? 0
      const y = node.y ?? 0
      const expandable = n.group === 'part' && (n.partNumbers?.length ?? 0) > 0

      if (expandable) {
        ctx.beginPath()
        ctx.arc(x, y, radius + 3, 0, 2 * Math.PI)
        ctx.setLineDash([2 / globalScale, 2 / globalScale])
        ctx.lineWidth = 1.5 / globalScale
        ctx.strokeStyle = expansions.current.has(n.id) ? GROUP_COLOR.part : 'rgba(59,130,246,0.55)'
        ctx.stroke()
        ctx.setLineDash([])
      }

      ctx.beginPath()
      ctx.arc(x, y, radius, 0, 2 * Math.PI)
      ctx.fillStyle = GROUP_COLOR[n.group]
      ctx.fill()
      ctx.lineWidth = 1.5 / globalScale
      ctx.strokeStyle = '#ffffff'
      ctx.stroke()

      const fontSize = 11 / globalScale
      ctx.font = `500 ${fontSize}px sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      ctx.fillStyle = '#334155'
      ctx.fillText(n.label, x, y + radius + 2)
    },
    [],
  )

  const nodePointerAreaPaint = useCallback((node: NodeObject, color: string, ctx: CanvasRenderingContext2D) => {
    ctx.beginPath()
    ctx.arc(node.x ?? 0, node.y ?? 0, 9, 0, 2 * Math.PI)
    ctx.fillStyle = color
    ctx.fill()
  }, [])

  return (
    <div>
      <p className="mb-1.5 text-[11px]" style={{ color: 'var(--color-ink-muted)' }}>
        점선 테두리가 있는 부품 노드를 누르면 같은 부품 계열을 공유하는 다른 차종·리콜이 펼쳐집니다.
      </p>
      <div
        ref={containerRef}
        className="relative h-[320px] w-full overflow-hidden rounded-xl"
        style={{
          backgroundColor: '#F8FAFC',
          backgroundImage: 'radial-gradient(circle, #CBD5E1 1px, transparent 1px)',
          backgroundSize: '18px 18px',
        }}
      >
        {width > 0 && height > 0 && (
          <ForceGraph2D
            width={width}
            height={height}
            graphData={graphData}
            backgroundColor="rgba(0,0,0,0)"
            nodeLabel={(node) => {
              const n = node as unknown as Node
              const group = n.group as GraphNodeGroup
              const hint = n.group === 'part' && (n.partNumbers?.length ?? 0) > 0 ? '<div style="font-size:11px;opacity:.75">클릭해서 펼치기</div>' : ''
              return `<div style="font-weight:700;margin-bottom:2px">${escapeHtml(n.label)}</div><div style="font-size:11px;opacity:.75">${GROUP_LABEL_KO[group]}</div>${hint}`
            }}
            nodeCanvasObject={nodeCanvasObject}
            nodePointerAreaPaint={nodePointerAreaPaint}
            onNodeClick={onNodeClick}
            linkColor={() => 'rgba(100,116,139,0.35)'}
            linkWidth={1}
            enableZoomInteraction={false}
          />
        )}
      </div>
      {loadingId && (
        <p className="mt-1.5 text-[11px]" style={{ color: 'var(--color-ink-muted)' }}>
          관련 부품 조회 중...
        </p>
      )}
      {notice && !loadingId && (
        <p className="mt-1.5 text-[11px]" style={{ color: 'var(--color-ink-muted)' }}>
          {notice}
        </p>
      )}
    </div>
  )
}
