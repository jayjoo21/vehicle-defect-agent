import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { DATA_AS_OF } from '../lib/tokens'
import Logo from './Logo'
import Footer from './Footer'

const navClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm font-medium ${isActive ? 'text-[#002C5F]' : 'text-[#6B7280] hover:text-[#111318]'}`

export default function Layout() {
  const location = useLocation()

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-[#111318]">
      <header className="sticky top-0 z-20 bg-white shadow-sm">
        <div className="mx-auto flex max-w-[1200px] items-center justify-between px-6 py-4">
          <NavLink to="/" className="flex items-center">
            <Logo compact />
          </NavLink>
          <div className="flex items-center gap-6">
            <span className="text-xs text-[#6B7280]">데이터 기준: {DATA_AS_OF}</span>
            <nav className="flex items-center gap-4">
              <NavLink to="/my-car" className={navClass}>내 차</NavLink>
              <NavLink to="/reports" className={navClass}>시그널 리포트</NavLink>
              <NavLink to="/chat" className={navClass}>조사 채팅</NavLink>
            </nav>
          </div>
        </div>
      </header>

      <main key={location.pathname} className="page-fade-in mx-auto w-full max-w-[1200px] flex-1 px-6 py-8">
        <Outlet />
      </main>

      <Footer />
    </div>
  )
}
