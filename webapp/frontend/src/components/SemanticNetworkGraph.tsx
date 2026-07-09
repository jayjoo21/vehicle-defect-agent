import { useCallback, useMemo } from 'react'
import ForceGraph2D, { type NodeObject } from 'react-force-graph-2d'
import { useElementSize } from '../lib/useElementSize'
import { GROUP_COLOR, GROUP_LABEL_KO, MOCK_SEMANTIC_GRAPH, type SemanticGraphData, type GraphNodeGroup } from '../lib/semanticGraph'

type Node = { id: string; label: string; group: GraphNodeGroup }

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

// 시맨틱 분석 과정(증상->부품->리콜)을 물리 기반 그래프로 보여준다. data가 없거나 근거
// 노드가 없으면(sources에 부품/캠페인 정보가 없는 답변) 자리표시용 더미 그래프로 대체한다.
// 툴팁은 force-graph 내부 라이브러리(float-tooltip)가 주입하는 .float-tooltip-kap 클래스를
// index.css에서 전역 오버라이드해 다른 차트들과 동일한 글래스모피즘으로 통일했다.
export default function SemanticNetworkGraph({ data }: { data?: SemanticGraphData }) {
  const graph = data && data.nodes.length > 0 ? data : MOCK_SEMANTIC_GRAPH
  const [containerRef, { width, height }] = useElementSize<HTMLDivElement>()

  const graphData = useMemo(
    () => ({
      nodes: graph.nodes.map((n) => ({ ...n })) as Node[],
      links: graph.links.map((l) => ({ ...l })),
    }),
    [graph],
  )

  const nodeCanvasObject = useCallback((node: NodeObject, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const n = node as NodeObject & Node
    const radius = 5
    const x = node.x ?? 0
    const y = node.y ?? 0

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
  }, [])

  const nodePointerAreaPaint = useCallback((node: NodeObject, color: string, ctx: CanvasRenderingContext2D) => {
    ctx.beginPath()
    ctx.arc(node.x ?? 0, node.y ?? 0, 9, 0, 2 * Math.PI)
    ctx.fillStyle = color
    ctx.fill()
  }, [])

  return (
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
            return `<div style="font-weight:700;margin-bottom:2px">${escapeHtml(n.label)}</div><div style="font-size:11px;opacity:.75">${GROUP_LABEL_KO[n.group]}</div>`
          }}
          nodeCanvasObject={nodeCanvasObject}
          nodePointerAreaPaint={nodePointerAreaPaint}
          linkColor={() => 'rgba(100,116,139,0.35)'}
          linkWidth={1}
          enableZoomInteraction={false}
        />
      )}
    </div>
  )
}
