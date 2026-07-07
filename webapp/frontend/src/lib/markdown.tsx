import type { ReactNode } from 'react'

// 이 리포트 마크다운(h1~h3, **bold**, `code`, -/숫자 목록, 문단)만 지원하는 최소 렌더러.
// 출처 배지 클릭→원문 팝오버는 6단계(폴리시)에서 구현 예정 — 여기서는 배지 스타일만 적용.
const BADGE_SPLIT_RE = /(ODINO \d+|\d{2}[A-Z]\d{6})/g
const BADGE_TOKEN_RE = /^(ODINO \d+|\d{2}[A-Z]\d{6})$/

function renderBadges(text: string, keyPrefix: string): ReactNode[] {
  return text.split(BADGE_SPLIT_RE).map((seg, i) =>
    BADGE_TOKEN_RE.test(seg) ? (
      <span
        key={`${keyPrefix}-badge-${i}`}
        className="rounded px-1.5 py-0.5 font-mono text-[11px]"
        style={{ backgroundColor: 'var(--color-bg-subtle)', color: 'var(--color-ink-muted)' }}
      >
        {seg}
      </span>
    ) : (
      seg
    ),
  )
}

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  return text
    .split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
    .filter((p) => p.length > 0)
    .map((part, i) => {
      const key = `${keyPrefix}-${i}`
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={key}>{renderBadges(part.slice(2, -2), key)}</strong>
      }
      if (part.startsWith('`') && part.endsWith('`')) {
        return (
          <code
            key={key}
            className="rounded px-1 py-0.5 font-mono text-[0.9em]"
            style={{ backgroundColor: 'var(--color-bg-subtle)' }}
          >
            {part.slice(1, -1)}
          </code>
        )
      }
      return <span key={key}>{renderBadges(part, key)}</span>
    })
}

export function renderMarkdown(md: string): ReactNode {
  const blocks = md.trim().split(/\n{2,}/)

  return blocks.map((block, bi) => {
    const lines = block.split('\n')
    const heading = lines[0].match(/^(#{1,3})\s+(.*)/)

    if (heading && lines.length === 1) {
      const level = heading[1].length
      const text = heading[2]
      if (level === 1) {
        return (
          <h1 key={bi} className="mt-8 mb-3 text-2xl font-semibold first:mt-0" style={{ color: 'var(--color-navy)' }}>
            {renderInline(text, `h-${bi}`)}
          </h1>
        )
      }
      if (level === 2) {
        return (
          <h2
            key={bi}
            className="mt-6 mb-2 border-b pb-1 text-lg font-semibold"
            style={{ color: 'var(--color-navy)', borderColor: 'var(--color-border)' }}
          >
            {renderInline(text, `h-${bi}`)}
          </h2>
        )
      }
      return (
        <h3 key={bi} className="mt-4 mb-1 text-base font-semibold" style={{ color: 'var(--color-ink)' }}>
          {renderInline(text, `h-${bi}`)}
        </h3>
      )
    }

    if (lines.every((l) => /^-\s+/.test(l))) {
      return (
        <ul key={bi} className="my-2 list-disc space-y-1 pl-5 text-sm" style={{ color: 'var(--color-ink)' }}>
          {lines.map((l, li) => (
            <li key={li}>{renderInline(l.replace(/^-\s+/, ''), `li-${bi}-${li}`)}</li>
          ))}
        </ul>
      )
    }

    if (lines.every((l) => /^\d+\.\s+/.test(l))) {
      return (
        <ol key={bi} className="my-2 list-decimal space-y-1 pl-5 text-sm" style={{ color: 'var(--color-ink)' }}>
          {lines.map((l, li) => (
            <li key={li}>{renderInline(l.replace(/^\d+\.\s+/, ''), `li-${bi}-${li}`)}</li>
          ))}
        </ol>
      )
    }

    return (
      <p key={bi} className="my-2 text-sm leading-relaxed" style={{ color: 'var(--color-ink)' }}>
        {renderInline(lines.join(' '), `p-${bi}`)}
      </p>
    )
  })
}
