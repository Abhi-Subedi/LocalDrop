import { useState, type FormEvent } from 'react'
import { api } from '../api'
import { Button, Input, useToast } from '../ui'
import { Link } from 'react-router-dom'

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
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center p-6">
      <h1 className="mb-6 text-center text-2xl font-bold">LocalDrop</h1>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="text-sm font-medium">Username
          <Input value={username} onChange={(e) => setUsername(e.target.value)} required autoComplete="username" autoFocus />
        </label>
        <label className="text-sm font-medium">Password
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
        </label>
        <Button type="submit" disabled={busy}>{busy ? 'Logging in…' : 'Log in'}</Button>
      </form>
      <p className="mt-4 text-center text-sm">
        <Link to="/setup" className="text-[var(--ld-accent)] underline">First run? Create the owner account</Link>
      </p>
    </main>
  )
}
