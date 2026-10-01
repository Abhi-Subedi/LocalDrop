// Shared auth-screen frame: branded card on a calm gradient canvas.
import type { ReactNode } from 'react'
import { Logo } from '../ui'

export function AuthCard({ children, wide }: { children: ReactNode; wide?: boolean }) {
  return (
    <main className="grid min-h-screen place-items-center p-4 pb-safe pt-safe">
      <div className={`animate-rise w-full ${wide ? 'max-w-md' : 'max-w-sm'}`}>
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <Logo size={52} />
          <div>
            <h1 className="text-2xl font-bold tracking-tight">LocalDrop</h1>
            <p className="mt-0.5 text-sm text-[var(--ld-muted)]">Your files, your server.</p>
          </div>
        </div>
        <div className="rounded-[var(--ld-radius)] border border-[var(--ld-line)] bg-[var(--ld-surface)] p-6 shadow-[var(--ld-shadow-md)]">
          {children}
        </div>
      </div>
    </main>
  )
}
