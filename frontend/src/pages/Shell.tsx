import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { FolderOpen, Share2, Settings, Trash2, LogOut, HardDrive } from 'lucide-react'
import { api, fmtSize, type Me } from '../api'
import { AuthCtx } from '../main'
import { useUploads } from '../uploader'
import { Avatar, Logo, Meter } from '../ui'

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
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-[var(--ld-line)] bg-[var(--ld-surface)] px-4 py-5 md:flex">
        <div className="mb-7 flex items-center gap-2.5 px-1">
          <Logo size={30} />
          <span className="text-[17px] font-bold tracking-tight">LocalDrop</span>
        </div>
        <nav aria-label="Main" className="flex flex-col gap-1">
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `app-press flex items-center gap-3 rounded-[10px] px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? 'bg-[var(--ld-accent-soft)] font-semibold text-[var(--ld-accent)]'
                    : 'text-[var(--ld-muted)] hover:bg-[var(--ld-accent-soft)]/50 hover:text-[var(--ld-text)]'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon size={18} aria-hidden strokeWidth={isActive ? 2.2 : 1.8} />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* storage meter */}
        {me && (
          <div className="mt-6 rounded-[var(--ld-radius)] border border-[var(--ld-line)] bg-[var(--ld-canvas)] p-3">
            <div className="flex items-center justify-between text-xs text-[var(--ld-muted)]">
              <span className="flex items-center gap-1.5"><HardDrive size={13} aria-hidden /> Storage</span>
              <span className="font-medium text-[var(--ld-text)]">{fmtSize(me.storage_used)}</span>
            </div>
            <Meter ratio={me.storage_quota ? me.storage_used / me.storage_quota : 0.1} className="mt-2" />
            {me.storage_quota ? (
              <p className="mt-1.5 text-[11px] text-[var(--ld-muted)]">of {fmtSize(me.storage_quota)} used</p>
            ) : (
              <p className="mt-1.5 text-[11px] text-[var(--ld-muted)]">No quota set</p>
            )}
          </div>
        )}

        {/* account */}
        <div className="mt-auto flex items-center gap-2.5 border-t border-[var(--ld-line)] pt-4">
          <Avatar name={me?.username || '?'} />
          <div className="min-w-0 flex-1 leading-tight">
            <p className="truncate text-sm font-semibold">{me?.username || '…'}</p>
            <p className="text-[11px] text-[var(--ld-muted)]">Owner</p>
          </div>
          <button
            onClick={logout}
            aria-label="Log out"
            title="Log out"
            className="app-press rounded-lg p-2 text-[var(--ld-muted)] hover:bg-[var(--ld-danger-soft)] hover:text-[var(--ld-danger)]"
          >
            <LogOut size={16} aria-hidden />
          </button>
        </div>
      </aside>

      {/* main */}
      <div className="flex min-w-0 flex-1 flex-col pb-16 md:pb-0">
        <Outlet />
        {activeUploads > 0 && (
          <div className="fixed bottom-16 left-1/2 z-40 -translate-x-1/2 rounded-full bg-[var(--ld-accent)] px-4 py-1.5 text-xs font-medium text-[var(--ld-accent-ink)] shadow-[var(--ld-shadow-md)] md:bottom-4" role="status">
            Uploading {activeUploads} file{activeUploads > 1 ? 's' : ''}…
          </div>
        )}
      </div>

      {/* bottom tabs (mobile) */}
      <nav aria-label="Main" className="pb-safe fixed inset-x-0 bottom-0 z-40 flex border-t border-[var(--ld-line)] bg-[var(--ld-surface)]/95 backdrop-blur md:hidden">
        {nav.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium ${
                isActive ? 'text-[var(--ld-accent)]' : 'text-[var(--ld-muted)]'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span className={`grid h-7 w-12 place-items-center rounded-full ${isActive ? 'bg-[var(--ld-accent-soft)]' : ''}`}>
                  <Icon size={20} aria-hidden />
                </span>
                {label}
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
