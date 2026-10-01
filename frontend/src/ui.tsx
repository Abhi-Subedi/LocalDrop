// Shared UI primitives: buttons, inputs, dialog, toasts, cards, icons —
// accessible by default. Exports are additive-only: existing names and
// props stay stable so pages keep working.

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import {
  File as FileIcon, FileText, FileArchive, Image as ImageIcon, Film, Music,
  FileQuestion, Folder as FolderIcon, X, CheckCircle2, AlertTriangle, Inbox,
} from 'lucide-react'
import type { Entry } from './api'

/** LocalDrop brand mark: teal rounded square + white drop/arrow. */
export function Logo({ size = 28, className = '' }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 512 512"
      role="img"
      aria-label="LocalDrop"
      className={className}
    >
      <rect width="512" height="512" rx="115" fill="var(--ld-accent)" />
      <circle cx="256" cy="215" r="95" fill="var(--ld-accent-ink)" />
      <rect x="235" y="155" width="42" height="105" fill="var(--ld-accent)" />
      <path d="M203 255h106l-53 55z" fill="var(--ld-accent)" />
      <rect x="171" y="352" width="170" height="32" rx="16" fill="var(--ld-accent-ink)" />
    </svg>
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
    danger: 'bg-[var(--ld-danger)] text-white hover:opacity-90',
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
      className={`w-full rounded-[10px] border border-[var(--ld-line)] bg-[var(--ld-surface)] px-3 py-2 text-sm text-[var(--ld-text)] shadow-[var(--ld-shadow-sm)] outline-none placeholder:text-[var(--ld-muted)] focus:border-[var(--ld-accent)] ${className}`}
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
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
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
}: {
  title: string
  hint?: string
  action?: ReactNode
}) {
  return (
    <div className="grid place-items-center px-6 py-16 text-center">
      <span className="grid h-14 w-14 place-items-center rounded-2xl bg-[var(--ld-accent-soft)] text-[var(--ld-accent)]">
        <Inbox size={26} aria-hidden />
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

export function Modal({
  open, onClose, title, children, danger,
}: { open: boolean; onClose: () => void; title: string; children: ReactNode; danger?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    ref.current?.querySelector<HTMLElement>('input, button, [tabindex]')?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4 pb-safe" onClick={onClose}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        className="animate-rise w-full max-w-md rounded-[var(--ld-radius)] border border-[var(--ld-line)] bg-[var(--ld-surface)] p-5 shadow-[var(--ld-shadow-lg)]"
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className={`text-base font-semibold ${danger ? 'text-[var(--ld-danger)]' : ''}`}>{title}</h2>
          <button onClick={onClose} aria-label="Close dialog" className="rounded p-1 hover:bg-[var(--ld-accent-soft)]">
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
                : 'border-[var(--ld-line)] bg-[var(--ld-surface)]'
            }`}
          >
            {t.kind === 'error' ? <AlertTriangle size={16} className="mt-0.5 shrink-0" /> : <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-[var(--ld-ok)]" />}
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
