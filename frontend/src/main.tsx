import { StrictMode, useEffect, useState, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import './index.css'
import { api, type Me } from './api'
import { ToastProvider } from './ui'
import { ThemeProvider } from './theme'
import { SetupPage } from './pages/Setup'
import { LoginPage } from './pages/Login'
import { AppShell } from './pages/Shell'
import { FilesPage } from './pages/Files'
import { TrashPage } from './pages/Trash'
import { SharesPage } from './pages/Shares'
import { SettingsPage } from './pages/Settings'
import { PublicSharePage } from './pages/PublicShare'

export const AuthCtx = { current: null as Me | null }

// Set when the server is running with LOCALDROP_DEMO_MODE. Read once at boot by
// DemoGate; the endpoint is a 404 on a normal deployment, so this stays null.
export const DemoCtx = { info: null as DemoInfo | null }

export interface DemoInfo {
  accepting_visitors: boolean
  max_upload_bytes: number
  ttl_minutes: number
  notice: string
}

/**
 * On a demo instance, hand the visitor a throwaway account automatically.
 *
 * The point of a demo is that the first click is *yours*, so the visitor must
 * not have to find a setup token, read a console log, or invent a password.
 * One request creates an isolated account and signs them in.
 */
function DemoGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<'loading' | 'ok' | 'no'>('loading')

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const info = await api.get<DemoInfo>('/demo/status')
        if (cancelled) return
        DemoCtx.info = info
        if (!info.accepting_visitors) { setState('no'); return }
        // Already signed in? Then we are a returning visitor on a live account.
        try {
          AuthCtx.current = await api.get<Me>('/me')
          setState('ok')
          return
        } catch { /* not signed in yet: ask for a demo account */ }
        await api.post('/demo/session')
        AuthCtx.current = await api.get<Me>('/me')
        setState('ok')
      } catch {
        if (!cancelled) setState('no')
      }
    })()
    return () => { cancelled = true }
  }, [])

  if (state === 'loading')
    return <div className="grid min-h-screen place-items-center text-sm text-[var(--ld-muted)]" role="status">Starting your private demo session…</div>
  return state === 'ok' ? <>{children}</> : <Navigate to="/login" replace />
}

function RequireAuth({ children }: { children: ReactNode }) {
  const [state, setState] = useState<'loading' | 'ok' | 'no'>('loading')
  useEffect(() => {
    api.get<Me>('/me')
      .then((me) => { AuthCtx.current = me; setState('ok') })
      .catch(() => setState('no'))
  }, [])
  if (state === 'loading')
    return <div className="grid min-h-screen place-items-center text-sm text-[var(--ld-muted)]" role="status">Loading…</div>
  return state === 'ok' ? <>{children}</> : <Navigate to="/login" replace />
}

function FilesPageWithId() {
  const { folderId } = useParams()
  return <FilesPage folderId={folderId || null} />
}

function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/s/:token" element={<PublicSharePage />} />
          <Route path="/setup" element={<SetupPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <DemoGate>
                <RequireAuth><AppShell /></RequireAuth>
              </DemoGate>
            }
          >
            <Route index element={<FilesPage folderId={null} />} />
            <Route path="files/:folderId" element={<FilesPageWithId />} />
            <Route path="trash" element={<TrashPage />} />
            <Route path="shares" element={<SharesPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      </ToastProvider>
    </ThemeProvider>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode><App /></StrictMode>,
)
