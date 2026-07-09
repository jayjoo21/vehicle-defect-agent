import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { Bell } from 'lucide-react'
import { DATA_AS_OF } from '../lib/tokens'
import Logo from './Logo'
import Footer from './Footer'
import NotificationDrawer, { MOCK_SUBSCRIPTIONS } from './NotificationDrawer'

const navClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm font-medium ${isActive ? 'text-[#002C5F]' : 'text-[#6B7280] hover:text-[#111318]'}`

export default function Layout() {
  const location = useLocation()
  const [drawerOpen, setDrawerOpen] = useState(false)

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
            <button
              onClick={() => setDrawerOpen(true)}
              aria-label="구독 중인 시그널 알림"
              className="btn-tension relative flex h-9 w-9 items-center justify-center rounded-full"
              style={{ backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }}
            >
              <Bell size={16} strokeWidth={1.75} />
              {MOCK_SUBSCRIPTIONS.length > 0 && (
                <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white ring-2 ring-white">
                  {MOCK_SUBSCRIPTIONS.length}
                </span>
              )}
            </button>
          </div>
        </div>
      </header>

      <main key={location.pathname} className="page-fade-in mx-auto w-full max-w-[1200px] flex-1 px-6 py-8">
        <Outlet />
      </main>

      <Footer />

      <NotificationDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </div>
  )
}
