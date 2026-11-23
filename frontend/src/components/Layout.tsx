import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import type { Role } from '../api/types'
import { ROLE_LABELS } from '../api/types'
import { useLogout, useMe } from '../lib/auth'
import { cx } from '../lib/cx'
import { Button } from './ui'

interface NavItem {
  to: string
  label: string
  roles?: Role[]
}

const NAV: NavItem[] = [
  { to: '/', label: 'Dashboard' },
  { to: '/rates', label: "Today's rates" },
  { to: '/stock', label: 'Stock' },
  { to: '/purchases', label: 'Purchases', roles: ['owner', 'accountant', 'godown'] },
  { to: '/parties', label: 'Customers & suppliers' },
  { to: '/products', label: 'Products' },
  { to: '/settings', label: 'Settings' },
  { to: '/admin/users', label: 'Users', roles: ['owner'] },
  { to: '/admin/audit', label: 'Audit log', roles: ['owner'] },
]

export function Layout() {
  const { data: user } = useMe()
  const logout = useLogout()
  const navigate = useNavigate()

  const items = NAV.filter((n) => !n.roles || (user && n.roles.includes(user.role)))

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 shrink-0 flex-col border-r border-stone-200 bg-white print:hidden">
        <div className="border-b border-stone-200 px-4 py-4">
          <div className="text-lg font-bold text-brand-700">Cement ERP</div>
          <div className="text-xs text-stone-500">Stock · Billing · Credit</div>
        </div>
        <nav className="flex-1 space-y-0.5 p-2">
          {items.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === '/'}
              className={({ isActive }) =>
                cx(
                  'block rounded-md px-3 py-2 text-sm',
                  isActive ? 'bg-brand-50 font-medium text-brand-700' : 'text-stone-700 hover:bg-stone-100',
                )
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        {user && (
          <div className="border-t border-stone-200 p-3 text-sm">
            <div className="font-medium">{user.full_name}</div>
            <div className="mb-2 text-xs text-stone-500">{ROLE_LABELS[user.role]}</div>
            <Button
              variant="secondary"
              className="w-full"
              onClick={() => logout.mutate(undefined, { onSettled: () => navigate('/login') })}
            >
              Log out
            </Button>
          </div>
        )}
      </aside>
      <main className="min-w-0 flex-1 p-6 lg:p-8">
        <Outlet />
      </main>
    </div>
  )
}
