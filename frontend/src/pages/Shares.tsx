import { useCallback, useEffect, useState } from 'react'
import { api, fmtDate, fmtSize, type Share } from '../api'
import { Button, Input, Modal, useToast } from '../ui'
import { Copy, Ban } from 'lucide-react'

export function SharesPage() {
  const [shares, setShares] = useState<Share[]>([])
  const [loading, setLoading] = useState(true)
  const [revoke, setRevoke] = useState<Share | null>(null)
  const toast = useToast()

  const load = useCallback(async () => {
    setLoading(true)
    try { setShares(await api.get<Share[]>('/shares')) } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])

  const status = (s: Share): { label: string; cls: string } =>
    s.revoked_at ? { label: 'Revoked', cls: 'text-[var(--ld-danger)]' }
    : s.expires_at && new Date(s.expires_at) < new Date() ? { label: 'Expired', cls: 'text-[var(--ld-muted)]' }
    : { label: 'Active', cls: 'text-[var(--ld-ok)]' }

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-6">
      <h1 className="mb-4 text-lg font-semibold">Shared links</h1>
      {loading ? <p className="text-sm text-[var(--ld-muted)]" role="status">Loading…</p>
        : shares.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-sm text-[var(--ld-muted)]">No share links yet.</p>
            <p className="mt-1 text-sm text-[var(--ld-muted)]">Select a file and press Share to create one.</p>
          </div>
        ) : (
          <ul className="flex flex-col gap-3">
            {shares.map((s) => {
              const st = status(s)
              return (
                <li key={s.id} className="rounded-xl border border-[var(--ld-line)] bg-[var(--ld-surface)] p-4">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{s.file_name || 'file'}</p>
                      <p className="text-xs text-[var(--ld-muted)]">
                        {fmtSize(s.file_size)} · created {fmtDate(s.created_at)}
                        {s.expires_at ? ` · expires ${fmtDate(s.expires_at)}` : ' · never expires'}
                      </p>
                      <p className="text-xs text-[var(--ld-muted)]">
                        {s.download_count}{s.max_downloads ? ` / ${s.max_downloads}` : ''} downloads
                        {s.has_password ? ' · password' : ''}
                      </p>
                    </div>
                    <span className={`text-xs font-medium ${st.cls}`} role="status">{st.label}</span>
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <Input readOnly value={s.url} onFocus={(e) => e.target.select()} aria-label={`Link for ${s.file_name}`} className="!py-1.5 text-xs" />
                    <Button variant="ghost" onClick={async () => { await navigator.clipboard.writeText(s.url); toast('Link copied.', 'success') }} ariaLabel="Copy link"><Copy size={14} aria-hidden /></Button>
                    {!s.revoked_at && (
                      <Button variant="ghost" onClick={() => setRevoke(s)} ariaLabel={`Revoke link for ${s.file_name}`}><Ban size={14} className="text-[var(--ld-danger)]" aria-hidden /></Button>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      {revoke && (
        <Modal open onClose={() => setRevoke(null)} title={`Revoke link for “${revoke.file_name}”?`} danger>
          <p className="mb-4 text-sm text-[var(--ld-muted)]">Anyone with this link will immediately lose access.</p>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setRevoke(null)}>Cancel</Button>
            <Button variant="danger" onClick={async () => {
              try { await api.del(`/shares/${revoke.id}`); toast('Link revoked.', 'success'); setRevoke(null); load() }
              catch (e) { toast(String(e), 'error') }
            }}>Revoke</Button>
          </div>
        </Modal>
      )}
    </main>
  )
}
