import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, fmtDate, fmtSize, type Me } from '../api'
import { AuthCtx } from '../main'
import { Button, Input, Modal, useToast } from '../ui'

interface Session {
  id: string
  created_at: string
  last_seen_at: string
  ip?: string | null
  user_agent?: string | null
  current: boolean
}

interface Pat {
  id: string
  name: string
  scopes: string
  created_at: string
  last_used_at?: string | null
}

export function SettingsPage() {
  const toast = useToast()
  const [me, setMe] = useState<Me | null>(AuthCtx.current)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [sessions, setSessions] = useState<Session[]>([])
  const [pats, setPats] = useState<Pat[]>([])
  const [newToken, setNewToken] = useState<string | null>(null)
  const [patName, setPatName] = useState('')
  const [patWrite, setPatWrite] = useState(true)

  const load = useCallback(async () => {
    try {
      const [m, s, p] = await Promise.all([
        api.get<Me>('/me'),
        api.get<Session[]>('/auth/sessions'),
        api.get<Pat[]>('/me/tokens'),
      ])
      setMe(m); setSessions(s); setPats(p)
    } catch { /* stays on cached AuthCtx */ }
  }, [])
  useEffect(() => { load() }, [load])

  const changePassword = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await api.put('/me/password', { current, new: next })
      toast('Password changed. Other sessions were logged out.', 'success')
      setCurrent(''); setNext(''); load()
    } catch (err) { toast(String(err), 'error') }
  }

  const revokeSession = async (id: string) => {
    try {
      await api.del(`/auth/sessions/${id}`)
      toast('Session revoked.', 'success'); load()
    } catch (e) { toast(String(e), 'error') }
  }

  const createPat = async (e: FormEvent) => {
    e.preventDefault()
    try {
      const pat = await api.post<{ token: string }>('/me/tokens', {
        name: patName, scopes: patWrite ? 'read,write' : 'read',
      })
      setNewToken(pat.token)
      setPatName(''); load()
    } catch (err) { toast(String(err), 'error') }
  }

  const revokePat = async (id: string) => {
    try {
      await api.del(`/me/tokens/${id}`)
      toast('Token revoked.', 'success'); load()
    } catch (e) { toast(String(e), 'error') }
  }

  const logout = async () => {
    try { await api.post('/auth/logout') } catch { /* already gone */ }
    window.location.href = '/login'
  }

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-6">
      <h1 className="mb-4 text-lg font-semibold">Settings</h1>
      <div className="flex flex-col gap-4">
        <section className="rounded-xl border border-[var(--ld-line)] bg-[var(--ld-surface)] p-4">
          <h2 className="mb-1 text-sm font-semibold">Account</h2>
          <p className="text-sm text-[var(--ld-muted)]">
            Signed in as <strong>{me?.username}</strong> ({me?.role}).
            Storage used: {me ? fmtSize(me.storage_used) : '…'}
          </p>
        </section>

        <section className="rounded-xl border border-[var(--ld-line)] bg-[var(--ld-surface)] p-4">
          <h2 className="mb-3 text-sm font-semibold">Change password</h2>
          <form onSubmit={changePassword} className="flex max-w-md flex-col gap-3">
            <label className="text-sm font-medium">Current password
              <Input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} required autoComplete="current-password" />
            </label>
            <label className="text-sm font-medium">New password (min 8 chars)
              <Input type="password" value={next} onChange={(e) => setNext(e.target.value)} required minLength={8} autoComplete="new-password" />
            </label>
            <Button type="submit" variant="secondary">Update password</Button>
          </form>
        </section>

        <section className="rounded-xl border border-[var(--ld-line)] bg-[var(--ld-surface)] p-4">
          <h2 className="mb-1 text-sm font-semibold">Sessions</h2>
          <p className="mb-3 text-sm text-[var(--ld-muted)]">Every device signed in to this server. Revoke any you don&apos;t recognize.</p>
          {sessions.length === 0 ? (
            <p className="text-sm text-[var(--ld-muted)]" role="status">Loading…</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {sessions.map((s) => (
                <li key={s.id} className="flex items-center justify-between gap-2 rounded-lg border border-[var(--ld-line)] px-3 py-2 text-sm">
                  <span className="min-w-0">
                    <span className="block truncate font-medium">
                      {s.current ? 'This device' : (s.user_agent || 'Unknown device')}
                    </span>
                    <span className="block text-xs text-[var(--ld-muted)]">
                      {s.ip || ''} · last seen {fmtDate(s.last_seen_at)}
                    </span>
                  </span>
                  {!s.current && (
                    <Button variant="ghost" onClick={() => revokeSession(s.id)} ariaLabel="Revoke session">Revoke</Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-xl border border-[var(--ld-line)] bg-[var(--ld-surface)] p-4">
          <h2 className="mb-1 text-sm font-semibold">API tokens</h2>
          <p className="mb-3 text-sm text-[var(--ld-muted)]">For scripts and integrations. Tokens are shown once — copy it now.</p>
          <form onSubmit={createPat} className="mb-3 flex max-w-md flex-wrap items-end gap-2">
            <label className="flex-1 text-sm font-medium">Name
              <Input value={patName} onChange={(e) => setPatName(e.target.value)} required maxLength={100} placeholder="backup-script" />
            </label>
            <label className="flex items-center gap-2 pb-2 text-sm">
              <input type="checkbox" checked={patWrite} onChange={(e) => setPatWrite(e.target.checked)} className="h-4 w-4" />
              Can write
            </label>
            <Button type="submit" variant="secondary">Create</Button>
          </form>
          {pats.length > 0 && (
            <ul className="flex flex-col gap-2">
              {pats.map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-2 rounded-lg border border-[var(--ld-line)] px-3 py-2 text-sm">
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{p.name}</span>
                    <span className="block text-xs text-[var(--ld-muted)]">
                      {p.scopes} · created {fmtDate(p.created_at)}
                      {p.last_used_at ? ` · used ${fmtDate(p.last_used_at)}` : ' · never used'}
                    </span>
                  </span>
                  <Button variant="ghost" onClick={() => revokePat(p.id)} ariaLabel={`Revoke token ${p.name}`}>Revoke</Button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-xl border border-[var(--ld-line)] bg-[var(--ld-surface)] p-4 md:hidden">
          <Button variant="secondary" onClick={logout}>Log out</Button>
        </section>

        <section className="rounded-xl border border-[var(--ld-line)] bg-[var(--ld-surface)] p-4">
          <h2 className="mb-1 text-sm font-semibold">About</h2>
          <p className="text-sm text-[var(--ld-muted)]">
            LocalDrop v1.0.0 — self-hosted, local-network-first file sharing. Licensed AGPL-3.0.
          </p>
        </section>
      </div>

      {newToken && (
        <Modal open onClose={() => setNewToken(null)} title="Token created — copy it now">
          <p className="mb-3 text-sm text-[var(--ld-muted)]">It will never be shown again.</p>
          <div className="mb-4 flex items-center gap-2">
            <Input readOnly value={newToken} onFocus={(e) => e.target.select()} aria-label="New API token" />
            <Button variant="secondary" onClick={async () => { await navigator.clipboard.writeText(newToken); toast('Copied.', 'success') }} ariaLabel="Copy token">Copy</Button>
          </div>
          <div className="flex justify-end"><Button onClick={() => setNewToken(null)}>Done</Button></div>
        </Modal>
      )}
    </main>
  )
}
