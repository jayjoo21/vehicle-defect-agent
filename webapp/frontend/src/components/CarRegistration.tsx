import { useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { CAR_MODELS, YEAR_OPTIONS } from '../lib/carRegistry'

export default function CarRegistration({ onComplete }: { onComplete: (model: string, year: string) => void }) {
  const [step, setStep] = useState<1 | 2>(1)
  const [query, setQuery] = useState('')
  const [model, setModel] = useState<string | null>(null)

  const filtered = useMemo(() => {
    const q = query.trim().toUpperCase()
    return q ? CAR_MODELS.filter((m) => m.model.includes(q)) : CAR_MODELS
  }, [query])

  if (step === 1) {
    return (
      <div className="mx-auto max-w-[720px]">
        <h1 className="mb-1 text-2xl font-semibold" style={{ color: 'var(--color-navy)' }}>
          내 차 등록
        </h1>
        <p className="mb-6 text-sm" style={{ color: 'var(--color-ink-muted)' }}>
          1/2 · 차종을 선택하세요
        </p>

        <div className="relative mb-4">
          <Search size={16} strokeWidth={1.5} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--color-ink-muted)' }} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="차종 검색 (예: TUCSON)"
            className="w-full rounded-lg border py-2.5 pl-9 pr-3 text-sm outline-none"
            style={{ borderColor: 'var(--color-border)' }}
          />
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {filtered.map((m) => (
            <button
              key={m.model}
              onClick={() => {
                setModel(m.model)
                setStep(2)
              }}
              className="rounded-lg border p-4 text-left transition-colors hover:border-[var(--color-navy)]"
              style={{ borderColor: 'var(--color-border)' }}
            >
              <div className="text-[11px]" style={{ color: 'var(--color-ink-muted)' }}>
                {m.make === 'HYUNDAI' ? '현대' : '기아'}
              </div>
              <div className="text-sm font-medium" style={{ color: 'var(--color-ink)' }}>
                {m.model}
              </div>
            </button>
          ))}
          {filtered.length === 0 && (
            <p className="col-span-full text-sm" style={{ color: 'var(--color-ink-muted)' }}>
              검색 결과가 없습니다.
            </p>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-[480px]">
      <h1 className="mb-1 text-2xl font-semibold" style={{ color: 'var(--color-navy)' }}>
        내 차 등록
      </h1>
      <p className="mb-6 text-sm" style={{ color: 'var(--color-ink-muted)' }}>
        2/2 · {model}의 연식을 선택하세요
      </p>

      <div className="grid grid-cols-3 gap-3 sm:grid-cols-4">
        {YEAR_OPTIONS.map((y) => (
          <button
            key={y}
            onClick={() => model && onComplete(model, String(y))}
            className="rounded-lg border py-3 text-sm font-medium transition-colors hover:border-[var(--color-navy)]"
            style={{ borderColor: 'var(--color-border)', color: 'var(--color-ink)' }}
          >
            {y}
          </button>
        ))}
      </div>

      <button onClick={() => setStep(1)} className="mt-6 text-[13px]" style={{ color: 'var(--color-ink-muted)' }}>
        ← 차종 다시 선택
      </button>
    </div>
  )
}
