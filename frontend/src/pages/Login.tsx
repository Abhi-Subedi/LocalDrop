import { useState, type FormEvent } from 'react'
import { api } from '../api'
import { Button, Input, useToast } from '../ui'
import { Link } from 'react-router-dom'
import { AuthCard } from './AuthCard'

export function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const toast = useToast()

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await api.post('/auth/login', { username, password })
      window.location.href = '/'
    } catch (err) {
      toast(String(err), 'error')
      setBusy(false)
    }
  }

  return (
    <AuthCard>
      <h2 className="mb-5 text-center text-base font-semibold">Welcome back</h2>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="text-sm font-medium">Username
          <Input value={username} onChange={(e) => setUsername(e.target.value)} required autoComplete="username" autoFocus className="mt-1.5" />
        </label>
        <label className="text-sm font-medium">Password
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" className="mt-1.5" />
        </label>
        <Button type="submit" disabled={busy} className="mt-1">{busy ? 'Logging in…' : 'Log in'}</Button>
      </form>
      <p className="mt-5 text-center text-sm text-[var(--ld-muted)]">
        First run?{' '}
        <Link to="/setup" className="font-medium text-[var(--ld-accent)] hover:underline">Create the owner account</Link>
      </p>
    </AuthCard>
  )
}
