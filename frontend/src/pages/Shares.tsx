import { useCallback, useEffect, useState } from 'react'
import { api, fmtDate, fmtSize, type Share } from '../api'
import { Badge, Button, EmptyState, Input, Modal, PageHeader, SkeletonList, useToast } from '../ui'
import { Copy, Ban, Share2 } from 'lucide-react'

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

  const status = (s: Share): { label: string; tone: 'ok' | 'danger' | 'neutral' } =>
    s.revoked_at ? { label: 'Revoked', tone: 'danger' }
    : s.expires_at && new Date(s.expires_at) < new Date() ? { label: 'Expired', tone: 'neutral' }
    : { label: 'Active', tone: 'ok' }

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-6">
      <PageHeader title="Shared links" hint="Public download pages for files on this server." />
      {loading ? <SkeletonList rows={3} />
        : shares.length === 0 ? (
          <EmptyState
            icon={<Share2 size={26} aria-hidden />}
            title="No share links yet"
            hint="Select a file in the browser and press Share to create one."
          />
        ) : (
          <ul className="flex flex-col gap-3">
            {shares.map((s) => {
              const st = status(s)
              return (
                <li key={s.id} className="rounded-[var(--ld-radius)] border border-[var(--ld-line)] bg-[var(--ld-surface)] p-4 shadow-[var(--ld-shadow-sm)]">
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
                    <Badge tone={st.tone}>{st.label}</Badge>
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
