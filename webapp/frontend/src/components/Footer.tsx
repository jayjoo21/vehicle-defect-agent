import { Link } from 'react-router-dom'
import { ExternalLink, Mail } from 'lucide-react'
import { DISCLAIMER } from '../lib/tokens'

const QUICK_LINKS = [
  { label: '상황판', to: '/' },
  { label: '내 차', to: '/my-car' },
  { label: '시그널 리포트', to: '/reports' },
  { label: '조사 채팅', to: '/chat' },
]

const DATA_SOURCES = [
  { label: '한국교통안전공단', href: 'https://www.kotsa.or.kr' },
  { label: '국토교통부', href: 'https://www.molit.go.kr' },
  { label: 'NHTSA (미국 도로교통안전국)', href: 'https://www.nhtsa.gov' },
]

// 이용약관·개인정보처리방침은 아직 실제 문서가 없는 자리표시 링크(placeholder) — 클릭해도 이동하지 않는다.
function LegalPlaceholder({ label }: { label: string }) {
  return (
    <a href="#" onClick={(e) => e.preventDefault()} className="transition-colors hover:text-white">
      {label}
    </a>
  )
}

export default function Footer() {
  return (
    <footer className="bg-slate-900 text-slate-400">
      <div className="mx-auto grid max-w-[1200px] grid-cols-1 gap-10 px-6 py-12 sm:grid-cols-2 lg:grid-cols-4">
        <div className="flex flex-col gap-3">
          <span className="text-lg font-bold tracking-tight text-white">MOBISCOPE</span>
          <p className="text-[13px] leading-relaxed">
            NHTSA·국토부 공개 데이터에서 소프트웨어/전장 결함 시그널을 리콜 전에 조기 탐지하는 차량 결함 조사 Agent.
          </p>
          <a href="mailto:contact@mobiscope.app" className="inline-flex items-center gap-1.5 text-[13px] transition-colors hover:text-white">
            <Mail size={13} strokeWidth={1.75} />
            contact@mobiscope.app
          </a>
        </div>

        <div className="flex flex-col gap-3">
          <h4 className="text-[12px] font-semibold uppercase tracking-wide text-slate-300">바로가기</h4>
          <nav className="flex flex-col gap-2 text-[13px]">
            {QUICK_LINKS.map((l) => (
              <Link key={l.to} to={l.to} className="transition-colors hover:text-white">
                {l.label}
              </Link>
            ))}
          </nav>
        </div>

        <div className="flex flex-col gap-3">
          <h4 className="text-[12px] font-semibold uppercase tracking-wide text-slate-300">데이터 출처</h4>
          <nav className="flex flex-col gap-2 text-[13px]">
            {DATA_SOURCES.map((l) => (
              <a
                key={l.href}
                href={l.href}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 transition-colors hover:text-white"
              >
                {l.label}
                <ExternalLink size={11} strokeWidth={1.75} />
              </a>
            ))}
          </nav>
        </div>

        <div className="flex flex-col gap-3">
          <h4 className="text-[12px] font-semibold uppercase tracking-wide text-slate-300">법적 고지</h4>
          <nav className="flex flex-col gap-2 text-[13px]">
            <LegalPlaceholder label="이용약관" />
            <LegalPlaceholder label="개인정보처리방침" />
          </nav>
          <p className="text-[11px] leading-relaxed text-slate-500">{DISCLAIMER}</p>
        </div>
      </div>

      <div className="border-t border-slate-800">
        <div className="mx-auto max-w-[1200px] px-6 py-4 text-[11px] text-slate-500">
          Copyright © 2026 MOBISCOPE. All rights reserved.
        </div>
      </div>
    </footer>
  )
}
