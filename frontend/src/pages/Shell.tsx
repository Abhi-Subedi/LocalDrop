import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { FolderOpen, Share2, Settings, Trash2, LogOut, HardDrive } from 'lucide-react'
import { api, fmtSize, type Me } from '../api'
import { AuthCtx } from '../main'
import { useUploads } from '../uploader'

const nav = [
  { to: '/', label: 'Files', icon: FolderOpen, end: true },
  { to: '/shares', label: 'Shared', icon: Share2 },
  { to: '/trash', label: 'Trash', icon: Trash2 },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function AppShell() {
  const [me, setMe] = useState<Me | null>(AuthCtx.current)
  const uploads = useUploads((s) => s.items)
  const activeUploads = uploads.filter((u) => ['uploading', 'queued', 'verifying'].includes(u.status)).length

  useEffect(() => {
    api.get<Me>('/me').then(setMe).catch(() => {})
  }, [])

  const logout = async () => {
    try { await api.post('/auth/logout') } catch { /* session already gone */ }
    window.location.href = '/login'
  }

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      {/* sidebar (desktop) */}
      <aside className="hidden w-56 shrink-0 flex-col border-r border-[var(--ld-line)] bg-[var(--ld-surface)] p-4 md:flex">
        <div className="mb-6 px-2 text-lg font-bold">LocalDrop</div>
        <nav aria-label="Main" className="flex flex-col gap-1">
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm ${isActive ? 'bg-[var(--ld-accent-soft)] font-medium text-[var(--ld-accent)]' : 'hover:bg-[var(--ld-accent-soft)]'}`
              }
            >
              <Icon size={18} aria-hidden /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto flex flex-col gap-2 text-xs text-[var(--ld-muted)]">
          {me && (
            <div className="flex items-center gap-2 px-2" aria-label={`Storage used ${fmtSize(me.storage_used)}`}>
              <HardDrive size={14} aria-hidden />
              <span>{fmtSize(me.storage_used)} used</span>
            </div>
          )}
          <div className="flex items-center justify-between px-2">
            <span>{me?.username}</span>
            <button onClick={logout} className="flex items-center gap-1 hover:text-[var(--ld-danger)]" aria-label="Log out">
              <LogOut size={14} aria-hidden /> Log out
            </button>
          </div>
        </div>
      </aside>

      {/* main */}
      <div className="flex min-w-0 flex-1 flex-col pb-16 md:pb-0">
        <Outlet />
        {activeUploads > 0 && (
          <div className="fixed bottom-16 left-1/2 z-40 -translate-x-1/2 rounded-full bg-[var(--ld-accent)] px-4 py-1.5 text-xs font-medium text-white shadow-lg md:bottom-4" role="status">
            Uploading {activeUploads} file{activeUploads > 1 ? 's' : ''}…
          </div>
        )}
      </div>

      {/* bottom tabs (mobile) */}
      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-40 flex border-t border-[var(--ld-line)] bg-[var(--ld-surface)] md:hidden">
        {nav.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] ${isActive ? 'text-[var(--ld-accent)]' : 'text-[var(--ld-muted)]'}`
            }
          >
            <Icon size={20} aria-hidden /> {label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
