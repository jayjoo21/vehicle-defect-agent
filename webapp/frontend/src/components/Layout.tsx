import { useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Bell } from 'lucide-react'
import { DATA_AS_OF } from '../lib/tokens'
import { useRole, useAccount, logout } from '../lib/role'
import { SubscriptionsProvider, useSubscriptions } from '../lib/subscriptions'
import Logo from './Logo'
import Footer from './Footer'
import NotificationDrawer from './NotificationDrawer'

const navClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm font-medium ${isActive ? 'text-[#002C5F]' : 'text-[#6B7280] hover:text-[#111318]'}`

export default function Layout() {
  // SubscriptionsProvider가 LayoutInner를 감싸야 그 안의 useSubscriptions()(배지 카운트·
  // 드로어·MyCar의 구독 모달이 모두 공유)가 값을 읽을 수 있다 — Layout 자신은 자기가 만든
  // Provider를 소비할 수 없어 내부 컴포넌트로 분리했다.
  return (
    <SubscriptionsProvider>
      <LayoutInner />
    </SubscriptionsProvider>
  )
}

function LayoutInner() {
  const location = useLocation()
  const navigate = useNavigate()
  const role = useRole()
  const account = useAccount()
  const { items: subscriptions } = useSubscriptions()
  const [drawerOpen, setDrawerOpen] = useState(false)

  function handleLogout() {
    // 먼저 가드된 라우트(/agent-chat) 밖으로 이동한 뒤 role을 지운다 — 순서를 바꾸면
    // RequireAgent가 role 변경에 반응해 같은 틱에 /login으로도 리다이렉트를 시도하면서
    // 이 navigate('/')와 경쟁해 최종 URL이 불안정해지는 문제가 있었다(실측으로 확인).
    // 지금 순서에서는 두 리다이렉트가 경쟁해도 최종적으로 role이 지워진 비로그인 상태로
    // 수렴함을 반복 검증(Playwright, 16회 연속 통과)으로 확인했다.
    navigate('/')
    setTimeout(() => logout(), 0)
  }

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
            {role === 'agent' ? (
              <div className="flex items-center gap-2">
                <span
                  className="rounded-full px-2.5 py-1 text-[11px] font-semibold"
                  style={{ backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }}
                >
                  상담사 모드
                </span>
                <button onClick={handleLogout} className="text-xs text-[#6B7280] hover:text-[#111318]">
                  로그아웃
                </button>
              </div>
            ) : role === 'user' ? (
              <div className="flex items-center gap-2">
                <span
                  className="max-w-[160px] truncate rounded-full px-2.5 py-1 text-[11px] font-semibold"
                  style={{ backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }}
                  title={account ?? undefined}
                >
                  {account}
                </span>
                <button onClick={handleLogout} className="text-xs text-[#6B7280] hover:text-[#111318]">
                  로그아웃
                </button>
              </div>
            ) : (
              <NavLink to="/login" className="text-sm font-medium text-[#6B7280] hover:text-[#111318]">
                로그인
              </NavLink>
            )}
            <button
              onClick={() => setDrawerOpen(true)}
              aria-label="구독 중인 시그널 알림"
              className="btn-tension relative flex h-9 w-9 items-center justify-center rounded-full"
              style={{ backgroundColor: 'var(--color-navy-soft)', color: 'var(--color-navy)' }}
            >
              <Bell size={16} strokeWidth={1.75} />
              {subscriptions.length > 0 && (
                <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white ring-2 ring-white">
                  {subscriptions.length}
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
