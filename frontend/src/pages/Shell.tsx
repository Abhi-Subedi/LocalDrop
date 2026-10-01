import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import {
  ChevronDown, FolderOpen, FolderPlus, HardDrive, LogOut, Moon, Plus,
  Search, Settings, Share2, Sun, Trash2, Upload,
} from 'lucide-react'
import { api, fmtSize, type Me } from '../api'
import { AuthCtx } from '../main'
import { useUploads } from '../uploader'
import { useUi, requestUpload, requestNewFolder } from '../ui-store'
import { useTheme } from '../theme'
import { Avatar, Logo, Meter } from '../ui'

const nav = [
  { to: '/', label: 'My Files', short: 'Files', icon: FolderOpen, end: true },
  { to: '/shares', label: 'Shared', short: 'Shared', icon: Share2 },
  { to: '/trash', label: 'Trash', short: 'Trash', icon: Trash2 },
  { to: '/settings', label: 'Settings', short: 'Settings', icon: Settings },
]

export function AppShell() {
  const [me, setMe] = useState<Me | null>(AuthCtx.current)
  const [accountOpen, setAccountOpen] = useState(false)
  const [newOpen, setNewOpen] = useState(false)
  const q = useUi((s) => s.q)
  const setQ = useUi((s) => s.setQ)
  const folderId = useUi((s) => s.folderId)
  const uploads = useUploads((s) => s.items)
  const activeUploads = uploads.filter((u) => ['uploading', 'queued', 'verifying'].includes(u.status)).length
  const { setMode } = useTheme()
  const accountRef = useRef<HTMLDivElement>(null)
  const newRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.get<Me>('/me').then(setMe).catch(() => {})
  }, [])

  // Click-outside for the two header/sidebar popovers.
  useEffect(() => {
    if (!accountOpen && !newOpen) return
    const onDown = (e: MouseEvent) => {
      if (accountOpen && !accountRef.current?.contains(e.target as Node)) setAccountOpen(false)
      if (newOpen && !newRef.current?.contains(e.target as Node)) setNewOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { setAccountOpen(false); setNewOpen(false) } }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [accountOpen, newOpen])

  const logout = async () => {
    try { await api.post('/auth/logout') } catch { /* session already gone */ }
    window.location.href = '/login'
  }

  // Effective theme (system mode resolves against the OS preference).
  const effectiveDark =
    document.documentElement.getAttribute('data-theme')
      ? document.documentElement.getAttribute('data-theme') === 'dark'
      : window.matchMedia('(prefers-color-scheme: dark)').matches
  const toggleTheme = () => setMode(effectiveDark ? 'light' : 'dark')

  return (
    <div className="flex min-h-screen flex-col">
      {/* top bar */}
      <header className="pt-safe sticky top-0 z-40 flex h-16 shrink-0 items-center gap-3 border-b border-[var(--ld-line)] bg-[var(--ld-surface)] px-4 md:px-6">
        <Link to="/" className="flex shrink-0 items-center gap-2.5" aria-label="LocalDrop home">
          <Logo size={30} />
          <span className="hidden text-[17px] font-bold tracking-tight sm:block">LocalDrop</span>
        </Link>

        {/* global search (desktop) */}
        <label className="relative mx-auto hidden w-full max-w-2xl md:block">
          <span className="sr-only">Search files</span>
          <Search size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[var(--ld-muted)]" aria-hidden />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search in LocalDrop"
            aria-label="Search files"
            className="h-11 w-full rounded-full border border-transparent bg-[var(--ld-surface-2)] pl-11 pr-4 text-sm outline-none transition-colors placeholder:text-[var(--ld-muted)] focus:border-[var(--ld-line-strong)] focus:bg-[var(--ld-surface)] focus:shadow-[var(--ld-shadow-sm)]"
          />
        </label>

        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          <button
            onClick={toggleTheme}
            aria-label={effectiveDark ? 'Switch to light theme' : 'Switch to dark theme'}
            title={effectiveDark ? 'Light theme' : 'Dark theme'}
            className="app-press grid h-10 w-10 place-items-center rounded-full text-[var(--ld-muted)] hover:bg-[var(--ld-accent-soft)] hover:text-[var(--ld-text)]"
          >
            {effectiveDark ? <Sun size={18} aria-hidden /> : <Moon size={18} aria-hidden />}
          </button>
          <div className="relative" ref={accountRef}>
            <button
              onClick={() => setAccountOpen(!accountOpen)}
              aria-label="Account menu"
              aria-expanded={accountOpen}
              className="app-press rounded-full ring-[var(--ld-line)] hover:ring-2"
            >
              <Avatar name={me?.username || '?'} size={34} />
            </button>
            {accountOpen && (
              <div
                role="menu"
                aria-label="Account"
                className="animate-rise absolute right-0 top-12 z-50 w-56 rounded-[var(--ld-radius)] border border-[var(--ld-line)] bg-[var(--ld-surface)] p-2 shadow-[var(--ld-shadow-lg)]"
              >
                <div className="px-3 py-2">
                  <p className="truncate text-sm font-semibold">{me?.username || '…'}</p>
                  <p className="text-xs capitalize text-[var(--ld-muted)]">{me?.role || ''}</p>
                </div>
                <div className="my-1 border-t border-[var(--ld-line)]" aria-hidden />
                <NavLink
                  to="/settings"
                  role="menuitem"
                  onClick={() => setAccountOpen(false)}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-[var(--ld-accent-soft)]"
                >
                  <Settings size={15} aria-hidden /> Settings
                </NavLink>
                <button
                  role="menuitem"
                  onClick={logout}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-[var(--ld-danger)] hover:bg-[var(--ld-danger-soft)]"
                >
                  <LogOut size={15} aria-hidden /> Log out
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="flex min-w-0 flex-1">
        {/* sidebar */}
        <aside className="sticky top-16 hidden h-[calc(100dvh-4rem)] w-60 shrink-0 flex-col overflow-y-auto px-3 py-4 md:flex">
          {/* New button (Drive-style) */}
          <div className="relative mb-4 px-1" ref={newRef}>
            <button
              onClick={() => setNewOpen(!newOpen)}
              aria-expanded={newOpen}
              aria-haspopup="menu"
              className="app-press flex h-11 w-full items-center gap-3 rounded-[10px] bg-[var(--ld-accent)] px-4 text-sm font-semibold text-[var(--ld-accent-ink)] hover:bg-[var(--ld-accent-strong)]"
            >
              <Plus size={20} aria-hidden /> New
              <ChevronDown size={16} className={`ml-auto transition-transform ${newOpen ? 'rotate-180' : ''}`} aria-hidden />
            </button>
            {newOpen && (
              <div
                role="menu"
                aria-label="Create new"
                className="animate-rise absolute left-1 top-14 z-50 w-56 rounded-[var(--ld-radius)] border border-[var(--ld-line)] bg-[var(--ld-surface)] p-2 shadow-[var(--ld-shadow-lg)]"
              >
                <button
                  role="menuitem"
                  disabled={!folderId}
                  onClick={() => { setNewOpen(false); requestUpload() }}
                  className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm hover:bg-[var(--ld-accent-soft)] disabled:opacity-40 disabled:hover:bg-transparent"
                >
                  <Upload size={16} aria-hidden /> Upload files
                </button>
                <button
                  role="menuitem"
                  disabled={!folderId}
                  onClick={() => { setNewOpen(false); requestNewFolder() }}
                  className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm hover:bg-[var(--ld-accent-soft)] disabled:opacity-40 disabled:hover:bg-transparent"
                >
                  <FolderPlus size={16} aria-hidden /> New folder
                </button>
                {!folderId && (
                  <p className="px-3 pb-1 pt-2 text-xs text-[var(--ld-muted)]">Open a folder first — uploads go into folders.</p>
                )}
              </div>
            )}
          </div>

          <nav aria-label="Main" className="flex flex-col gap-0.5">
            {nav.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  `app-press flex items-center gap-3 rounded-full px-4 py-2.5 text-sm transition-colors ${
                    isActive
                      ? 'bg-[var(--ld-accent-soft)] font-semibold text-[var(--ld-accent)]'
                      : 'text-[var(--ld-muted)] hover:bg-[var(--ld-surface-2)] hover:text-[var(--ld-text)]'
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

          {/* storage */}
          {me && (
            <div className="mt-auto px-2 pb-2">
              <div className="flex items-center gap-2 text-xs text-[var(--ld-muted)]">
                <HardDrive size={14} aria-hidden />
                <span className="font-medium text-[var(--ld-text)]">{fmtSize(me.storage_used)}</span>
                {me.storage_quota ? <span>of {fmtSize(me.storage_quota)} used</span> : <span>used</span>}
              </div>
              <Meter ratio={me.storage_quota ? me.storage_used / me.storage_quota : 0.1} className="mt-2" />
            </div>
          )}
        </aside>

        {/* main */}
        <div className="min-w-0 flex-1 pb-16 md:pb-0">
          <Outlet />
          {activeUploads > 0 && (
            <div className="fixed bottom-16 left-1/2 z-40 -translate-x-1/2 rounded-full bg-[var(--ld-accent)] px-4 py-1.5 text-xs font-medium text-[var(--ld-accent-ink)] shadow-[var(--ld-shadow-md)] md:bottom-4" role="status">
              Uploading {activeUploads} file{activeUploads > 1 ? 's' : ''}…
            </div>
          )}
        </div>
      </div>

      {/* bottom tabs (mobile) */}
      <nav aria-label="Main" className="pb-safe fixed inset-x-0 bottom-0 z-40 flex border-t border-[var(--ld-line)] bg-[var(--ld-surface)] md:hidden">
        {nav.map(({ to, label, short, icon: Icon, end }) => (
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
                {short || label}
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
