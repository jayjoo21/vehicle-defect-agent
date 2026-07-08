import { NavLink, Outlet } from 'react-router-dom'
import { DATA_AS_OF, DISCLAIMER } from '../lib/tokens'

const navClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm font-medium ${isActive ? 'text-[#002C5F]' : 'text-[#6B7280] hover:text-[#111318]'}`

export default function Layout() {
  return (
    <div className="min-h-screen bg-white text-[#111318]">
      <header className="border-b border-[#E5E7EB]">
        <div className="mx-auto flex max-w-[1200px] items-center justify-between px-6 py-4">
          <NavLink to="/" className="flex flex-col leading-none">
            <span className="text-lg font-semibold tracking-tight text-[#002C5F]">PRECALL</span>
            <span className="text-[10px] font-medium tracking-wide text-[#6B7280]">리콜보다 먼저 아는</span>
          </NavLink>
          <div className="flex items-center gap-6">
            <span className="text-xs text-[#6B7280]">데이터 기준: {DATA_AS_OF}</span>
            <nav className="flex items-center gap-4">
              <NavLink to="/my-car" className={navClass}>내 차</NavLink>
              <NavLink to="/chat" className={navClass}>조사 채팅</NavLink>
            </nav>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1200px] px-6 py-8">
        <Outlet />
      </main>

      <footer className="mx-auto max-w-[1200px] px-6 py-6 text-xs text-[#6B7280]">
        {DISCLAIMER}
      </footer>
    </div>
  )
}
