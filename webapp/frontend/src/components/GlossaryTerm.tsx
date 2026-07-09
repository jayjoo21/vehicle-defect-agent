import type { ReactNode } from 'react'

export default function GlossaryTerm({ term, description, children }: { term: string; description: string; children: ReactNode }) {
  return (
    <span className="group relative inline-block">
      <span
        className="cursor-help underline decoration-dashed underline-offset-[3px]"
        style={{ textDecorationColor: 'var(--color-ink-muted)' }}
      >
        {children}
      </span>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-full z-30 mt-2 w-64 -translate-x-1/2 translate-y-1 rounded-lg px-3 py-2 text-[12px] leading-relaxed text-white opacity-0 shadow-lg transition-all duration-200 group-hover:translate-y-0 group-hover:opacity-100"
        style={{ backgroundColor: '#0B1220' }}
      >
        <span className="mb-0.5 block font-semibold text-white">{term}</span>
        {description}
      </span>
    </span>
  )
}
