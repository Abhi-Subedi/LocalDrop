import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../api'
import { Button, Input, useToast } from '../ui'
import { Link, useNavigate } from 'react-router-dom'
import { AuthCard } from './AuthCard'

export function SetupPage() {
  const [token, setToken] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const nav = useNavigate()

  useEffect(() => {
    // First-run convenience: the server issues a setup token on demand.
    api.get<{ token?: string; token_available: boolean }>('/setup/token')
      .then((r) => { if (r.token) { setToken(r.token); toast('Setup token filled in automatically.') } })
      .catch(() => {})
  }, [])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await api.post('/setup/owner', { username, password, setup_token: token })
      toast('Account created — please log in.', 'success')
      nav('/login')
    } catch (err) {
      toast(String(err), 'error')
    } finally { setBusy(false) }
  }

  return (
    <AuthCard wide>
      <h2 className="mb-1 text-center text-base font-semibold">Create the owner account</h2>
      <p className="mb-5 text-center text-sm text-[var(--ld-muted)]">
        The setup token is printed in the server console on first start.
      </p>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="text-sm font-medium">Setup token
          <Input value={token} onChange={(e) => setToken(e.target.value)} required minLength={8} autoComplete="off" className="mt-1.5 font-mono text-xs" />
        </label>
        <label className="text-sm font-medium">Username
          <Input value={username} onChange={(e) => setUsername(e.target.value)} required minLength={3} maxLength={32} pattern="[a-z0-9_.\-]+" autoComplete="username" className="mt-1.5" />
        </label>
        <label className="text-sm font-medium">Password (min 8 chars)
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} autoComplete="new-password" className="mt-1.5" />
        </label>
        <Button type="submit" disabled={busy} className="mt-1">{busy ? 'Creating…' : 'Create account'}</Button>
      </form>
      <p className="mt-5 text-center text-sm text-[var(--ld-muted)]">
        Already have an account?{' '}
        <Link to="/login" className="font-medium text-[var(--ld-accent)] hover:underline">Log in</Link>
      </p>
    </AuthCard>
  )
}
