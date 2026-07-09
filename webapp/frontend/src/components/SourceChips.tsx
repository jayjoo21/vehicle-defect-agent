import { FileText } from 'lucide-react'

export const SOURCE_LABELS = ['NHTSA 리포트 원문 보기', '국토교통부 보도자료'] as const

// 신뢰도를 보여주는 출처 뱃지 — 클릭하면 부모가 전달한 onSelect로 라벨을 넘겨 더미 모달을 띄운다.
export default function SourceChips({ onSelect }: { onSelect: (label: string) => void }) {
  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {SOURCE_LABELS.map((label) => (
        <button
          key={label}
          type="button"
          onClick={() => onSelect(label)}
          className="btn-tension inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-medium"
          style={{ backgroundColor: 'var(--color-bg-subtle)', color: 'var(--color-ink-muted)' }}
        >
          <FileText size={12} strokeWidth={1.75} />
          {label}
        </button>
      ))}
    </div>
  )
}
