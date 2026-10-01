import { StrictMode, useEffect, useState, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import { api, type Me } from './api'
import { ToastProvider } from './ui'
import { SetupPage } from './pages/Setup'
import { LoginPage } from './pages/Login'
import { AppShell } from './pages/Shell'
import { FilesPage } from './pages/Files'
import { TrashPage } from './pages/Trash'
import { SharesPage } from './pages/Shares'
import { SettingsPage } from './pages/Settings'
import { PublicSharePage } from './pages/PublicShare'

export const AuthCtx = { current: null as Me | null }

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
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/s/:token" element={<PublicSharePage />} />
          <Route path="/setup" element={<SetupPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<RequireAuth><AppShell /></RequireAuth>}>
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
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode><App /></StrictMode>,
)
