import { Link } from 'react-router-dom'
import type { SignalCardData } from '../lib/types'

export default function RecentReports({ cards }: { cards: SignalCardData[] }) {
  const withReports = cards.filter((c) => c.report_id !== null)

  return (
    <section className="rounded-xl border p-6" style={{ borderColor: 'var(--color-border)', boxShadow: 'var(--shadow-card)' }}>
      <h3 className="mb-4 text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
        최근 리포트
      </h3>
      {withReports.length === 0 ? (
        <p className="text-sm" style={{ color: 'var(--color-ink-muted)' }}>
          아직 생성된 리포트가 없습니다.
        </p>
      ) : (
        <ul className="divide-y" style={{ borderColor: 'var(--color-border)' }}>
          {withReports.map((c) => (
            <li key={c.model} className="flex items-center justify-between py-3">
              <div>
                <Link to={`/reports/${c.report_id}`} className="font-medium hover:underline" style={{ color: 'var(--color-navy)' }}>
                  {c.model} 시그널 리포트
                </Link>
                <p className="text-[12px]" style={{ color: 'var(--color-ink-muted)' }}>
                  기준월 {c.month}
                </p>
              </div>
              <Link to={`/reports/${c.report_id}`} className="text-[13px]" style={{ color: 'var(--color-navy)' }}>
                보기 →
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
