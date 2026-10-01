import { useCallback, useEffect, useState } from 'react'
import { api, fmtDate, fmtSize, type Entry } from '../api'
import { Button, EmptyState, PageHeader, SkeletonList, entryIcon, useToast } from '../ui'
import { Trash2 } from 'lucide-react'

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
      <PageHeader
        title="Trash"
        hint="Deleted items are purged automatically after 30 days."
        actions={items.length > 0 ? <Button variant="danger" onClick={purge}>Empty trash</Button> : undefined}
      />
      {loading ? <SkeletonList rows={4} />
        : items.length === 0 ? (
          <EmptyState
            icon={<Trash2 size={26} aria-hidden />}
            title="Trash is empty"
            hint="Deleted files and folders land here first — nothing to clean up right now."
          />
        ) : (
          <ul className="divide-y divide-[var(--ld-line)] rounded-[var(--ld-radius)] border border-[var(--ld-line)] bg-[var(--ld-surface)] shadow-[var(--ld-shadow-sm)]">
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
