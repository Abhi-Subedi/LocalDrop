// Shared UI primitives: buttons, dialog, toasts, icons — accessible by default.

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import {
  File as FileIcon, FileText, FileArchive, Image as ImageIcon, Film, Music,
  FileQuestion, Folder as FolderIcon, X, CheckCircle2, AlertTriangle,
} from 'lucide-react'
import type { Entry } from './api'

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
  const base = 'inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none'
  const variants = {
    primary: 'bg-[var(--ld-accent)] text-white hover:bg-[var(--ld-accent-strong)]',
    secondary: 'border border-[var(--ld-line)] bg-[var(--ld-surface)] hover:bg-[var(--ld-accent-soft)]',
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
      className={`w-full rounded-lg border border-[var(--ld-line)] bg-[var(--ld-surface)] px-3 py-2 text-sm outline-none focus:border-[var(--ld-accent)] ${className}`}
    />
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-xl border border-[var(--ld-line)] bg-[var(--ld-surface)] p-5 shadow-xl"
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
      <div aria-live="polite" className="fixed bottom-4 right-4 z-[60] flex max-w-[90vw] flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.kind === 'error' ? 'alert' : 'status'}
            className={`pointer-events-auto flex items-start gap-2 rounded-lg border px-4 py-3 text-sm shadow-lg ${
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
