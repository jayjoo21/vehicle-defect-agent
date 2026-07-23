import { FileText } from 'lucide-react'
import type { ChatPart } from '../lib/types'

// 실제 NHTSA Part 573 리콜 문서 원문 링크(parts.pdf_url, chat.py/reports.py가 조회)로만 연결한다.
// pdf_url이 없는 캠페인은 그 항목만 자연히 빠짐(지어낸 링크 금지 — 이 프로젝트 전역 원칙).
// 국토교통부 보도자료는 파이프라인 어디에도 원문 URL 데이터가 없어 버튼 자체를 두지 않는다.
export default function SourceChips({ parts }: { parts: ChatPart[] }) {
  const links = parts.filter((p): p is ChatPart & { pdf_url: string } => Boolean(p.pdf_url))
  if (links.length === 0) return null

  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {links.map((p) => (
        <a
          key={p.campaign}
          href={p.pdf_url}
          target="_blank"
          rel="noreferrer"
          className="btn-tension inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-medium"
          style={{ backgroundColor: 'var(--color-bg-subtle)', color: 'var(--color-ink-muted)' }}
        >
          <FileText size={12} strokeWidth={1.75} />
          NHTSA 리포트 원문 보기 ({p.campaign})
        </a>
      ))}
    </div>
  )
}
