// Shared UI primitives: buttons, inputs, dialog, toasts, cards, icons —
// accessible by default. Exports are additive-only: existing names and
// props stay stable so pages keep working.

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import {
  File as FileIcon, FileText, FileArchive, Image as ImageIcon, Film, Music,
  FileQuestion, Folder as FolderIcon, X, CheckCircle2, AlertTriangle, Inbox,
  List, LayoutGrid,
} from 'lucide-react'
import type { Entry } from './api'

/** LocalDrop brand mark: leaf chip on near-black (works on both themes). */
export function Logo({ size = 28, className = '' }: { size?: number; className?: string }) {
  return (
    <img
      src="/brand-mark.png"
      width={size}
      height={size}
      alt="LocalDrop"
      className={`shrink-0 select-none ${className}`}
      style={{ width: size, height: size }}
      draggable={false}
    />
  )
}

/** Full "localdrop" wordmark, theme-aware (white on dark / near-black on light). */
export function LogoWordmark({ height = 30, className = '' }: { height?: number; className?: string }) {
  return (
    <span className={`inline-block ${className}`} style={{ height }}>
      <img src="/logo-on-light.png" alt="LocalDrop" className="only-light h-full w-auto select-none" draggable={false} />
      <img src="/logo-on-dark.png" alt="LocalDrop" className="only-dark h-full w-auto select-none" draggable={false} />
    </span>
  )
}

export function Button({
  children, onClick, variant = 'primary', type = 'button', disabled, className = '', ariaLabel,
}: {
  children: ReactNode
  onClick?: () => void
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  type?: 'button' | 'submit'
  disabled?: boolean
  className?: string
  ariaLabel?: string
}) {
  const base = 'app-press inline-flex min-h-[38px] items-center justify-center gap-2 rounded-[10px] px-3.5 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none'
  const variants = {
    primary: 'bg-[var(--ld-accent)] text-[var(--ld-accent-ink)] shadow-[var(--ld-shadow-sm)] hover:bg-[var(--ld-accent-strong)]',
    secondary: 'border border-[var(--ld-line)] bg-[var(--ld-surface)] shadow-[var(--ld-shadow-sm)] hover:bg-[var(--ld-accent-soft)]',
    ghost: 'hover:bg-[var(--ld-accent-soft)]',
    danger: 'bg-[var(--ld-danger)] text-white shadow-[var(--ld-shadow-sm)] hover:opacity-90',
  }
  return (
    <button type={type} onClick={onClick} disabled={disabled} aria-label={ariaLabel} className={`${base} ${variants[variant]} ${className}`}>
      {children}
    </button>
  )
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const { className = '', ...rest } = props
  return (
    <input
      {...rest}
      className={`w-full rounded-[10px] border border-[var(--ld-line)] bg-[var(--ld-surface)] px-3 py-2 text-sm text-[var(--ld-text)] shadow-[var(--ld-shadow-sm)] outline-none transition-colors placeholder:text-[var(--ld-muted)] focus:border-[var(--ld-accent)] ${className}`}
    />
  )
}

/** Card: the single surface container. One radius scale app-wide. */
export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <section
      className={`rounded-[var(--ld-radius)] border border-[var(--ld-line)] bg-[var(--ld-surface)] shadow-[var(--ld-shadow-sm)] ${className}`}
    >
      {children}
    </section>
  )
}

/** Badge: compact status pill (Active / Revoked / Expired, scopes, counts). */
export function Badge({
  children, tone = 'neutral',
}: {
  children: ReactNode
  tone?: 'neutral' | 'ok' | 'danger' | 'warn' | 'accent'
}) {
  const tones = {
    neutral: 'bg-[var(--ld-surface-2)] text-[var(--ld-muted)]',
    ok: 'bg-[var(--ld-ok-soft)] text-[var(--ld-ok)]',
    danger: 'bg-[var(--ld-danger-soft)] text-[var(--ld-danger)]',
    warn: 'bg-[var(--ld-warn-soft)] text-[var(--ld-warn)]',
    accent: 'bg-[var(--ld-accent-soft)] text-[var(--ld-accent)]',
  }
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold leading-5 ${tones[tone]}`}>
      {children}
    </span>
  )
}

/** Segmented: compact icon toggle group (e.g. list/grid view switch). */
export function Segmented<T extends string>({
  value, onChange, options, ariaLabel,
}: {
  value: T
  onChange: (v: T) => void
  options: { v: T; label: string; icon?: ReactNode }[]
  ariaLabel: string
}) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className="flex rounded-[10px] border border-[var(--ld-line)] bg-[var(--ld-surface)] p-0.5 shadow-[var(--ld-shadow-sm)]">
      {options.map(({ v, label, icon }) => (
        <button
          key={v}
          role="radio"
          aria-checked={value === v}
          aria-label={label}
          title={label}
          onClick={() => onChange(v)}
          className={`app-press grid h-8 w-9 place-items-center rounded-lg ${
            value === v
              ? 'bg-[var(--ld-accent-soft)] text-[var(--ld-accent)]'
              : 'text-[var(--ld-muted)] hover:text-[var(--ld-text)]'
          }`}
        >
          {icon ?? label}
        </button>
      ))}
    </div>
  )
}

export const ViewIcons = { list: List, grid: LayoutGrid }

/** Avatar: user-initial chip for the sidebar account block. */
export function Avatar({ name, size = 30 }: { name: string; size?: number }) {
  const initial = (name.trim()[0] || '?').toUpperCase()
  return (
    <span
      aria-hidden
      className="grid shrink-0 place-items-center rounded-full bg-[var(--ld-accent)] font-bold text-[var(--ld-accent-ink)]"
      style={{ width: size, height: size, fontSize: size * 0.42 }}
    >
      {initial}
    </span>
  )
}

/** Meter: thin storage/progress bar. */
export function Meter({ ratio, tone = 'accent', className = '' }: { ratio: number; tone?: 'accent' | 'ok' | 'danger'; className?: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(ratio * 100)))
  const bg = { accent: 'bg-[var(--ld-accent)]', ok: 'bg-[var(--ld-ok)]', danger: 'bg-[var(--ld-danger)]' }[tone]
  return (
    <div className={`h-1.5 overflow-hidden rounded-full bg-[var(--ld-surface-2)] ${className}`} role="presentation">
      <div className={`h-full rounded-full transition-all ${bg}`} style={{ width: `${pct}%` }} />
    </div>
  )
}

/** PageHeader: title + supporting line + optional actions. */
export function PageHeader({
  title,
  hint,
  actions,
}: {
  title: string
  hint?: string
  actions?: ReactNode
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-bold tracking-tight">{title}</h1>
        {hint && <p className="mt-0.5 text-sm text-[var(--ld-muted)]">{hint}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

/** EmptyState: composed zero-data moment with a next step. */
export function EmptyState({
  title,
  hint,
  action,
  icon,
}: {
  title: string
  hint?: string
  action?: ReactNode
  icon?: ReactNode
}) {
  return (
    <div className="grid place-items-center px-6 py-16 text-center">
      <span className="grid h-14 w-14 place-items-center rounded-2xl bg-[var(--ld-accent-soft)] text-[var(--ld-accent)]">
        {icon ?? <Inbox size={26} aria-hidden />}
      </span>
      <p className="mt-4 text-sm font-semibold">{title}</p>
      {hint && <p className="mt-1 max-w-xs text-sm text-[var(--ld-muted)]">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

/** SkeletonList: shape-matched loading rows (no generic spinners). */
export function SkeletonList({ rows = 5 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2" role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-2 py-2.5">
          <div className="skeleton h-10 w-10 shrink-0 rounded-xl" aria-hidden />
          <div className="flex min-w-0 flex-1 flex-col gap-1.5" aria-hidden>
            <div className="skeleton h-3.5 w-2/5 rounded" />
            <div className="skeleton h-3 w-1/4 rounded" />
          </div>
        </div>
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  )
}

/** SkeletonGrid: loading state for the folder grid view. */
export function SkeletonGrid({ tiles = 8 }: { tiles?: number }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4" role="status" aria-label="Loading">
      {Array.from({ length: tiles }).map((_, i) => (
        <div key={i} className="rounded-[var(--ld-radius)] border border-[var(--ld-line)] bg-[var(--ld-surface)] p-3" aria-hidden>
          <div className="skeleton aspect-square w-full rounded-xl" />
          <div className="skeleton mt-3 h-3.5 w-3/4 rounded" />
          <div className="skeleton mt-2 h-3 w-1/3 rounded" />
        </div>
      ))}
      <span className="sr-only">Loading…</span>
    </div>
  )
}

export function Modal({
  open, onClose, title, children, danger, wide,
}: { open: boolean; onClose: () => void; title: string; children: ReactNode; danger?: boolean; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    ref.current?.querySelector<HTMLElement>('input, button, [tabindex]')?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])
  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [open])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/45 p-4 pb-safe backdrop-blur-[2px] sm:items-center" onClick={onClose}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        className={`animate-rise max-h-[88dvh] w-full overflow-y-auto rounded-t-[var(--ld-radius)] border border-[var(--ld-line)] bg-[var(--ld-surface)] p-5 shadow-[var(--ld-shadow-lg)] sm:rounded-[var(--ld-radius)] ${wide ? 'max-w-lg' : 'max-w-md'}`}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className={`text-base font-semibold ${danger ? 'text-[var(--ld-danger)]' : ''}`}>{title}</h2>
          <button onClick={onClose} aria-label="Close dialog" className="app-press rounded p-1.5 hover:bg-[var(--ld-accent-soft)]">
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

// ---- toasts ----
interface Toast { id: number; message: string; kind: 'info' | 'error' | 'success' }
const ToastCtx = createContext<(message: string, kind?: Toast['kind']) => void>(() => {})
export const useToast = () => useContext(ToastCtx)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const push = (message: string, kind: Toast['kind'] = 'info') => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, message, kind }])
    if (kind !== 'error') setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000)
  }
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div aria-live="polite" className="fixed bottom-4 right-4 z-[60] flex max-w-[90vw] flex-col gap-2 pb-safe">
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.kind === 'error' ? 'alert' : 'status'}
            className={`animate-rise pointer-events-auto flex items-start gap-2 rounded-[var(--ld-radius)] border px-4 py-3 text-sm shadow-[var(--ld-shadow-lg)] ${
              t.kind === 'error'
                ? 'border-[var(--ld-danger)] bg-[var(--ld-danger-soft)] text-[var(--ld-danger)]'
                : t.kind === 'success'
                ? 'border-[var(--ld-line)] bg-[var(--ld-surface)]'
                : 'border-[var(--ld-line)] bg-[var(--ld-surface)]'
            }`}
          >
            {t.kind === 'error'
              ? <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden />
              : <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-[var(--ld-ok)]" aria-hidden />}
            <span className="whitespace-pre-wrap">{t.message}</span>
            {t.kind === 'error' && (
              <button onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))} aria-label="Dismiss error" className="ml-2">
                <X size={14} />
              </button>
            )}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

// ---- file icons ----
export function entryIcon(e: Pick<Entry, 'kind' | 'mime_type' | 'name'>, size = 20) {
  if (e.kind === 'folder') return <FolderIcon size={size} className="text-[var(--ld-accent)]" aria-hidden />
  const m = e.mime_type || ''
  const cls = 'text-[var(--ld-muted)]'
  if (m.startsWith('image/')) return <ImageIcon size={size} className={cls} aria-hidden />
  if (m.startsWith('video/')) return <Film size={size} className={cls} aria-hidden />
  if (m.startsWith('audio/')) return <Music size={size} className={cls} aria-hidden />
  if (m === 'application/pdf' || m.startsWith('text/')) return <FileText size={size} className={cls} aria-hidden />
  if (m === 'application/zip') return <FileArchive size={size} className={cls} aria-hidden />
  if (m === 'application/octet-stream' && /\.(zip|tar|gz|7z|rar)$/i.test(e.name)) return <FileArchive size={size} className={cls} aria-hidden />
  if (m === 'application/octet-stream') return <FileQuestion size={size} className={cls} aria-hidden />
  return <FileIcon size={size} className={cls} aria-hidden />
}
