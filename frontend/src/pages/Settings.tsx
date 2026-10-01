import { useEffect, useState, type FormEvent } from 'react'
import { api, fmtSize, type Me } from '../api'
import { AuthCtx } from '../main'
import { Button, Input, useToast } from '../ui'

export function SettingsPage() {
  const toast = useToast()
  const [me, setMe] = useState<Me | null>(AuthCtx.current)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')

  useEffect(() => { api.get<Me>('/me').then(setMe).catch(() => {}) }, [])

  const changePassword = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await api.put('/me/password', { current, new: next })
      toast('Password changed. Other sessions were logged out.', 'success')
      setCurrent(''); setNext('')
    } catch (err) { toast(String(err), 'error') }
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
          <h2 className="mb-1 text-sm font-semibold">About</h2>
          <p className="text-sm text-[var(--ld-muted)]">
            LocalDrop v1.0.0 — self-hosted, local-network-first file sharing. Licensed AGPL-3.0.
          </p>
        </section>
      </div>
    </main>
  )
}
