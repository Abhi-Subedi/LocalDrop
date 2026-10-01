import { useCallback, useEffect, useState } from 'react'
import { api, fmtDate, fmtSize, type Entry } from '../api'
import { Button, entryIcon, useToast } from '../ui'

export function TrashPage() {
  const [items, setItems] = useState<Entry[]>([])
  const [loading, setLoading] = useState(true)
  const toast = useToast()

  const load = useCallback(async () => {
    setLoading(true)
    try { setItems(await api.get<Entry[]>('/trash')) } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])

  const restore = async (e: Entry) => {
    try {
      if (e.kind === 'folder') await api.post(`/folders/${e.id}/restore`)
      else await api.post(`/files/${e.id}/restore`)
      toast(`Restored “${e.name}”`, 'success'); load()
    }
    catch (err) { toast(String(err), 'error') }
  }
  const purge = async () => {
    try {
      const r = await api.post<{ purged: number }>('/trash/purge')
      toast(`Purged ${r.purged} items.`, 'success'); load()
    } catch (err) { toast(String(err), 'error') }
  }

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Trash</h1>
        {items.length > 0 && <Button variant="danger" onClick={purge}>Empty trash</Button>}
      </div>
      {loading ? <p className="text-sm text-[var(--ld-muted)]" role="status">Loading…</p>
        : items.length === 0 ? <p className="py-16 text-center text-sm text-[var(--ld-muted)]">Trash is empty.</p>
        : (
          <ul className="divide-y divide-[var(--ld-line)] rounded-xl border border-[var(--ld-line)] bg-[var(--ld-surface)]">
            {items.map((e) => (
              <li key={e.id} className="flex items-center gap-3 px-4 py-3">
                {entryIcon(e, 18)}
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm">{e.name}</span>
                  <span className="text-xs text-[var(--ld-muted)]">{fmtSize(e.size)} · deleted {fmtDate(e.deleted_at)}</span>
                </span>
                <Button variant="secondary" onClick={() => restore(e)}>Restore</Button>
              </li>
            ))}
          </ul>
        )}
    </main>
  )
}
