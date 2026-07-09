import { useState, type CSSProperties } from 'react'
import { Building2, Calendar, Download } from 'lucide-react'

const MAKES = ['전체', '현대', '기아'] as const
const RANGES = ['최근 3개월', '최근 6개월', '최근 1년'] as const

const pillStyle = (active: boolean): CSSProperties =>
  active
    ? { backgroundColor: 'var(--color-navy)', color: '#fff' }
    : { backgroundColor: 'var(--color-bg-subtle)', color: 'var(--color-ink-muted)' }

// 제조사/기간 토글과 내보내기 버튼은 아직 실제 필터링·내보내기에 연결되지 않은 더미 컨트롤이다
// (백엔드가 이 축의 필터를 지원하지 않음) — 클릭 시 선택 상태만 바뀌고, 내보내기는 준비 중 안내만 띄운다.
export default function FilterBar() {
  const [make, setMake] = useState<(typeof MAKES)[number]>('전체')
  const [range, setRange] = useState<(typeof RANGES)[number]>('최근 6개월')
  const [hint, setHint] = useState(false)

  function exportClick() {
    setHint(true)
    setTimeout(() => setHint(false), 2200)
  }

  return (
    <div className="card flex flex-wrap items-center gap-3 p-4">
      <div className="flex items-center gap-1.5 text-[12px] font-medium" style={{ color: 'var(--color-ink-muted)' }}>
        <Building2 size={14} strokeWidth={1.75} />
        제조사
      </div>
      <div className="flex gap-1.5">
        {MAKES.map((m) => (
          <button
            key={m}
            onClick={() => setMake(m)}
            className="btn-tension rounded-full px-3 py-1.5 text-[12px] font-medium"
            style={pillStyle(make === m)}
          >
            {m}
          </button>
        ))}
      </div>

      <div className="mx-1 hidden h-5 w-px sm:block" style={{ backgroundColor: 'var(--color-border)' }} />

      <div className="flex items-center gap-1.5 text-[12px] font-medium" style={{ color: 'var(--color-ink-muted)' }}>
        <Calendar size={14} strokeWidth={1.75} />
        기간
      </div>
      <div className="flex gap-1.5">
        {RANGES.map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
            className="btn-tension rounded-full px-3 py-1.5 text-[12px] font-medium"
            style={pillStyle(range === r)}
          >
            {r}
          </button>
        ))}
      </div>

      <div className="ml-auto flex items-center gap-2">
        {hint && (
          <span className="text-[11px]" style={{ color: 'var(--color-ink-muted)' }}>
            내보내기 기능은 준비 중입니다
          </span>
        )}
        <button
          onClick={exportClick}
          className="btn-tension inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[12px] font-medium"
          style={{ backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }}
        >
          <Download size={14} strokeWidth={1.75} />
          데이터 내보내기
        </button>
      </div>
    </div>
  )
}
