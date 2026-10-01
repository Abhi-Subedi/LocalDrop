// Public share page: zero-chrome download for anonymous visitors.

import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Button, Input, useToast } from '../ui'
import { fmtSize } from '../api'

interface Info {
  file_id: string
  token: string
  file_name: string
  file_size: number
  requires_password: boolean
  unlocked: boolean
}

export function PublicSharePage() {
  const { token } = useParams()
  const [info, setInfo] = useState<Info | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [password, setPassword] = useState('')
  const toast = useToast()

  useEffect(() => {
    if (!token) return
    fetch(`/api/v1/shares/${token}`)
      .then(async (r) => {
        if (r.status === 404) throw new Error('This link is invalid, expired, or has been revoked.')
        if (!r.ok) throw new Error(`Error ${r.status}`)
        return r.json()
      })
      .then(setInfo)
      .catch((e) => setError(String(e.message || e)))
  }, [token])

  const unlock = async () => {
    try {
      const r = await fetch(`/api/v1/shares/${token}/unlock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })
      if (r.status === 204) {
        setInfo((i) => (i ? { ...i, unlocked: true } : i))
        toast('Unlocked.', 'success')
      } else if (r.status === 403) {
        toast('Incorrect password.', 'error')
      } else if (r.status === 404) {
        setError('This link is invalid, expired, or has been revoked.')
      }
    } catch { toast('Could not unlock.', 'error') }
  }

  return (
    <main className="grid min-h-screen place-items-center p-6">
      <div className="w-full max-w-sm rounded-2xl border border-[var(--ld-line)] bg-[var(--ld-surface)] p-6 text-center shadow-sm">
        <h1 className="mb-1 text-lg font-bold">LocalDrop</h1>
        {error ? (
          <p className="mt-6 text-sm text-[var(--ld-danger)]" role="alert">{error}</p>
        ) : !info ? (
          <p className="mt-6 text-sm text-[var(--ld-muted)]" role="status">Loading…</p>
        ) : (
          <>
            <p className="mt-4 truncate text-sm font-medium" title={info.file_name}>{info.file_name}</p>
            <p className="mb-5 text-xs text-[var(--ld-muted)]">{fmtSize(info.file_size)}</p>
            {info.requires_password && !info.unlocked ? (
              <form
                onSubmit={(e) => { e.preventDefault(); unlock() }}
                className="flex flex-col gap-3"
              >
                <label className="text-sm font-medium">Password
                  <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoFocus autoComplete="off" />
                </label>
                <Button type="submit">Unlock & download</Button>
              </form>
            ) : (
              <Button
                onClick={() => {
                  const a = document.createElement('a')
                  a.href = `/api/v1/shares/${token}/files/${info.file_id}/content`
                  a.rel = 'noopener'
                  document.body.appendChild(a)
                  a.click()
                  a.remove()
                }}
              >Download</Button>
            )}
          </>
        )}
      </div>
    </main>
  )
}
