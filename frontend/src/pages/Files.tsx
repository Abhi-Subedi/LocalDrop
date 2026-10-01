// File browser: the core screen. Breadcrumbs, grid/list, drag-drop upload,
// selection, context actions, rename/move/delete dialogs, search, sort,
// previews, empty/loading/error states. Mobile-first + keyboard accessible.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowUp, ChevronRight, Search, Upload, FolderPlus, MoreVertical,
  Pencil, FolderInput, Copy, Trash2, Share2, Download, X, FileText,
  List, LayoutGrid,
} from 'lucide-react'
import { api, downloadUrl, fmtDate, fmtSize, isImage, type Entry } from '../api'
import {
  Button, EmptyState, Input, Modal, Segmented, SkeletonGrid, SkeletonList,
  entryIcon, useToast,
} from '../ui'
import { useUi } from '../ui-store'
import { startUpload, useUploads, pauseUpload, resumeUpload, retryUpload, cancelUpload } from '../uploader'

type DialogState =
  | { kind: 'newFolder' } | { kind: 'rename'; entry: Entry }
  | { kind: 'delete'; entries: Entry[] } | { kind: 'move'; entries: Entry[] }
  | { kind: 'copy'; entry: Entry } | { kind: 'share'; entry: Entry }

const SORTS = [
  { v: 'name', label: 'Name' },
  { v: '-name', label: 'Name ↓' },
  { v: 'size', label: 'Size' },
  { v: '-size', label: 'Size ↓' },
  { v: '-created_at', label: 'Newest' },
  { v: 'created_at', label: 'Oldest' },
]

export function FilesPage({ folderId }: { folderId: string | null }) {
  const [entries, setEntries] = useState<Entry[]>([])
  const [crumbs, setCrumbs] = useState<{ id: string; name: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const q = useUi((s) => s.q)
  const setQ = useUi((s) => s.setQ)
  const [sort, setSort] = useState('name')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [dialog, setDialog] = useState<DialogState | null>(null) //

  const [view, setView] = useState<'list' | 'grid'>(
    () => (localStorage.getItem('localdrop-view') === 'grid' ? 'grid' : 'list'),
  )
  useEffect(() => { localStorage.setItem('localdrop-view', view) }, [view]) 

  const [preview, setPreview] = useState<Entry | null>(null)
  const [menuFor, setMenuFor] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const toast = useToast()
  const nav = useNavigate()
  const uploadItems = useUploads((s) => s.items)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const path = folderId ? `/folders/${folderId}/children` : '/folders/root/children'
      const params = new URLSearchParams({ sort })
      if (q) params.set('q', q)
      const page = await api.get<{ items: Entry[] }>(`${path}?${params}`)
      setEntries(page.items)
      if (folderId) {
        try {
          setCrumbs(await api.get<{ id: string; name: string }[]>(`/folders/${folderId}/path`))
        } catch { setCrumbs([]) }
      } else setCrumbs([])
    } catch (e) {
      setError(String(e))
    } finally { setLoading(false) }
  }, [folderId, q, sort])

  useEffect(() => { load() }, [load])

  // Report the current folder to the shell ("New" menu targets it) and
  // answer the shell's upload/new-folder requests.
  useEffect(() => {
    useUi.getState().setFolderId(folderId)
    const onUpload = () => pickFiles()
    const onNewFolder = () => setDialog({ kind: 'newFolder' })
    window.addEventListener('ld-upload', onUpload)
    window.addEventListener('ld-new-folder', onNewFolder)
    return () => {
      useUi.getState().setFolderId(null)
      window.removeEventListener('ld-upload', onUpload)
      window.removeEventListener('ld-new-folder', onNewFolder)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [folderId])

  const refresh = () => { load(); api.get('/me').catch(() => {}) }

  // ---- selection (click / ctrl / shift) ----
  const lastIndex = useRef(-1)
  function onRowClick(e: React.MouseEvent, entry: Entry, idx: number) {
    if (entry.kind === 'folder' && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
      nav(`/files/${entry.id}`)
      return
    }
    const sel = new Set(selected)
    if (e.shiftKey && lastIndex.current >= 0) {
      const [a, b] = [lastIndex.current, idx].sort((x, y) => x - y)
      entries.slice(a, b + 1).forEach((en) => sel.add(en.id))
    } else if (e.ctrlKey || e.metaKey) {
      sel.has(entry.id) ? sel.delete(entry.id) : sel.add(entry.id)
    } else {
      sel.clear(); sel.add(entry.id)
    }
    setSelected(sel)
    lastIndex.current = idx
  }

  const selectedEntries = useMemo(
    () => entries.filter((e) => selected.has(e.id)),
    [entries, selected],
  )

  // ---- actions ----
  async function doDelete(entries: Entry[]) {
    try {
      for (const en of entries) {
        if (en.kind === 'folder') await api.del(`/folders/${en.id}`)
        else await api.del(`/files/${en.id}`)
      }
      toast(entries.length === 1 ? `Deleted “${entries[0].name}”` : `Deleted ${entries.length} items`, 'success')
      setSelected(new Set())
      refresh()
    } catch (e) { toast(String(e), 'error') }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    const files = Array.from(e.dataTransfer.files)
    if (!files.length) return
    if (!folderId) { toast('Open a folder first — uploads go into folders.', 'error'); return }
    files.forEach((f) => startUpload(f, folderId, refresh))
  }

  function pickFiles() {
    if (!folderId) { toast('Open a folder first — uploads go into folders.', 'error'); return }
    fileInput.current?.click()
  }

  function onUploadChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files || [])
    files.forEach((f) => startUpload(f, folderId, refresh))
    e.target.value = ''
  }


  return (
    <div
      className="flex min-h-screen flex-col"
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
    >
      {/* title + toolbar (Drive-style: big title, filter chips below) */}
      <div className="mx-auto w-full max-w-6xl px-4 pt-5 md:px-8">
        {folderId && (
          <nav aria-label="Breadcrumb" className="mb-1 flex min-w-0 items-center gap-1 text-sm text-[var(--ld-muted)]">
            <Link to="/" className="rounded px-1 py-0.5 hover:bg-[var(--ld-accent-soft)] hover:text-[var(--ld-text)]" aria-label="Root folder">My Files</Link>
            {crumbs.map((c, i) => (
              <span key={c.id} className="flex min-w-0 items-center gap-1">
                <ChevronRight size={14} className="shrink-0" aria-hidden />
                {i === crumbs.length - 1
                  ? <span aria-current="location" className="truncate font-medium text-[var(--ld-text)]">{c.name}</span>
                  : <Link to={`/files/${c.id}`} className="truncate rounded px-1 py-0.5 hover:bg-[var(--ld-accent-soft)] hover:text-[var(--ld-text)]">{c.name}</Link>}
              </span>
            ))}
          </nav>
        )}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="truncate text-2xl font-bold tracking-tight">
            {folderId ? (crumbs[crumbs.length - 1]?.name ?? 'Folder') : 'My Files'}
          </h1>
          <Segmented
            ariaLabel="View mode"
            value={view}
            onChange={setView}
            options={[
              { v: 'list', label: 'List view', icon: <List size={15} aria-hidden /> },
              { v: 'grid', label: 'Grid view', icon: <LayoutGrid size={15} aria-hidden /> },
            ]}
          />
        </div>
        <div className="mb-5 mt-4 flex flex-wrap items-center gap-2">
          <label className="relative md:hidden">
            <span className="sr-only">Search files</span>
            <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--ld-muted)]" aria-hidden />
            <Input
              value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search…"
              className="!w-44 !py-1.5 pl-8" aria-label="Search files"
            />
          </label>
          <select
            value={sort} onChange={(e) => setSort(e.target.value)}
            aria-label="Sort files" className="h-9 rounded-full border border-[var(--ld-line)] bg-[var(--ld-surface)] px-3.5 text-sm shadow-[var(--ld-shadow-sm)]"
          >
            {SORTS.map((s) => <option key={s.v} value={s.v}>{s.label}</option>)}
          </select>
          <div className="ml-auto flex items-center gap-2">
            {folderId && (
              <>
                <Button variant="secondary" onClick={() => setDialog({ kind: 'newFolder' })} ariaLabel="Create folder" className="!rounded-full">
                  <FolderPlus size={16} aria-hidden /><span className="hidden sm:inline">Folder</span>
                </Button>
                <Button onClick={pickFiles} ariaLabel="Upload files" className="!rounded-full">
                  <Upload size={16} aria-hidden /><span className="hidden sm:inline">Upload</span>
                </Button>
              </>
            )}
          </div>
        </div>
      </div>

      <input ref={fileInput} type="file" multiple hidden onChange={onUploadChosen} aria-hidden />

      {/* selection action bar */}
      {selected.size > 0 && (
        <div className="fixed inset-x-0 bottom-16 z-30 mx-auto flex max-w-fit items-center gap-2 rounded-xl border border-[var(--ld-line)] bg-[var(--ld-surface)] px-3 py-2 shadow-lg md:bottom-4" role="toolbar" aria-label="Selected item actions">
          <span className="text-sm text-[var(--ld-muted)]">{selected.size} selected</span>
          {selectedEntries.length === 1 && (
            <>
              <Button variant="ghost" onClick={() => setDialog({ kind: 'rename', entry: selectedEntries[0] })} ariaLabel="Rename"><Pencil size={16} aria-hidden /></Button>
              <Button variant="ghost" onClick={() => setDialog({ kind: 'move', entries: selectedEntries })} ariaLabel="Move"><FolderInput size={16} aria-hidden /></Button>
              {selectedEntries[0].kind === 'file' && (
                <>
                  <Button variant="ghost" onClick={() => setDialog({ kind: 'copy', entry: selectedEntries[0] })} ariaLabel="Copy"><Copy size={16} aria-hidden /></Button>
                  <Button variant="ghost" onClick={() => setDialog({ kind: 'share', entry: selectedEntries[0] })} ariaLabel="Share"><Share2 size={16} aria-hidden /></Button>
                </>
              )}
            </>
          )}
          {selectedEntries.every((e) => e.kind === 'file') && (
            <a
              href={selected.size === 1 ? downloadUrl(selectedEntries[0].id) : undefined}
              className="rounded-lg p-2 hover:bg-[var(--ld-accent-soft)]"
              aria-label="Download"
              onClick={(e) => { if (selected.size > 1) { e.preventDefault(); toast('Multi-file download comes in v1.1 — download one at a time for now.') } }}
            ><Download size={16} aria-hidden /></a>
          )}
          <Button variant="ghost" onClick={() => setDialog({ kind: 'delete', entries: selectedEntries })} ariaLabel="Delete"><Trash2 size={16} className="text-[var(--ld-danger)]" aria-hidden /></Button>
          <Button variant="ghost" onClick={() => setSelected(new Set())} ariaLabel="Clear selection"><X size={16} aria-hidden /></Button>
        </div>
      )}

      {/* body */}
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 pb-10 md:px-8">
        {dragOver && (
          <div className="pointer-events-none fixed inset-0 z-20 m-4 grid place-items-center rounded-2xl border-2 border-dashed border-[var(--ld-accent)] bg-[var(--ld-accent-soft)]/80" role="status">
            <p className="text-lg font-medium text-[var(--ld-accent)]">Drop files to upload</p>
          </div>
        )}

        {loading ? (
          view === 'grid' ? <SkeletonGrid /> : <SkeletonList rows={7} />
        ) : error ? (
          <div className="rounded-[var(--ld-radius)] border border-[var(--ld-danger)] bg-[var(--ld-danger-soft)] p-4 text-sm text-[var(--ld-danger)]" role="alert">
            {error}
            <Button variant="secondary" className="ml-3" onClick={() => load()}>Retry</Button>
          </div>
        ) : entries.length === 0 ? (
          q ? (
            <EmptyState
              icon={<Search size={26} aria-hidden />}
              title={`No results for “${q}”`}
              hint="Try a different name, or check the spelling."
            />
          ) : folderId ? (
            <EmptyState
              icon={<Upload size={26} aria-hidden />}
              title="This folder is empty"
              hint="Drop files anywhere on this page, or use the Upload button."
              action={<Button onClick={pickFiles}><Upload size={16} aria-hidden /> Upload files</Button>}
            />
          ) : (
            <EmptyState
              icon={<FolderPlus size={26} aria-hidden />}
              title="No folders yet"
              hint="Folders hold your files. Create the first one to get started."
              action={<Button onClick={() => setDialog({ kind: 'newFolder' })}><FolderPlus size={16} aria-hidden /> Create folder</Button>}
            />
          )
        ) : view === 'grid' ? (
          <ul role="listbox" aria-label="Files and folders" aria-multiselectable="true" className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {entries.map((entry, idx) => (
              <li
                key={entry.id}
                role="option"
                aria-selected={selected.has(entry.id)}
                tabIndex={0}
                onClick={(e) => onRowClick(e, entry, idx)}
                onContextMenu={(e) => { e.preventDefault(); setMenuFor(entry.id) }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') { entry.kind === 'folder' ? nav(`/files/${entry.id}`) : setPreview(entry) }
                  if (e.key === ' ') { e.preventDefault(); onRowClick({ ctrlKey: true } as React.MouseEvent, entry, idx) }
                  if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) setMenuFor(entry.id)
                }}
                className={`app-press relative cursor-pointer rounded-[var(--ld-radius)] border bg-[var(--ld-surface)] p-2.5 shadow-[var(--ld-shadow-sm)] transition-colors ${
                  selected.has(entry.id)
                    ? 'border-[var(--ld-accent)] ring-2 ring-[var(--ld-accent)]'
                    : 'border-[var(--ld-line)] hover:border-[var(--ld-line-strong)]'
                }`}
              >
                <div className="relative grid aspect-square place-items-center overflow-hidden rounded-xl bg-[var(--ld-canvas)]">
                  {isImage(entry) && entry.hash_status === 'verified'
                    ? <img src={`/api/v1/files/${entry.id}/thumbnail`} alt="" loading="lazy" className="h-full w-full object-cover" />
                    : entryIcon(entry, 34)}
                  {entry.kind === 'folder' && (
                    <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/25 to-transparent p-1.5 text-[11px] font-medium text-white">
                      Folder
                    </span>
                  )}
                </div>
                <p className="mt-2 truncate text-sm font-medium" title={entry.name}>{entry.name}</p>
                <p className="text-xs text-[var(--ld-muted)]">
                  {entry.kind === 'file' ? fmtSize(entry.size) : 'Folder'}
                  {entry.hash_status === 'pending' && ' · verifying…'}
                </p>
                <div className="absolute right-1.5 top-1.5" onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={() => setMenuFor(menuFor === entry.id ? null : entry.id)}
                    aria-label={`Actions for ${entry.name}`}
                    aria-expanded={menuFor === entry.id}
                    className="app-press grid h-8 w-8 place-items-center rounded-lg bg-[var(--ld-surface)]/90 text-[var(--ld-muted)] shadow-[var(--ld-shadow-sm)] backdrop-blur hover:text-[var(--ld-text)]"
                  >
                    <MoreVertical size={15} aria-hidden />
                  </button>
                  {menuFor === entry.id && <EntryMenu entry={entry} close={() => setMenuFor(null)} setDialog={setDialog} setPreview={setPreview} />}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="overflow-hidden rounded-[var(--ld-radius)] border border-[var(--ld-line)] bg-[var(--ld-surface)] shadow-[var(--ld-shadow-sm)]">
            {/* column headers (desktop, Drive-style table) */}
            <div
              aria-hidden
              className="hidden md:grid md:grid-cols-[minmax(0,1fr)_110px_170px_48px] md:items-center md:gap-3 md:border-b md:border-[var(--ld-line)] md:px-4 md:py-2.5 md:text-xs md:font-semibold md:text-[var(--ld-muted)]"
            >
              <span>Name</span>
              <span className="text-right md:text-left">Size</span>
              <span>Modified</span>
              <span />
            </div>
            <ul role="listbox" aria-label="Files and folders" aria-multiselectable="true" className="divide-y divide-[var(--ld-line)]">
              {entries.map((entry, idx) => (
                <li
                  key={entry.id}
                  role="option"
                  aria-selected={selected.has(entry.id)}
                  tabIndex={0}
                  onClick={(e) => onRowClick(e, entry, idx)}
                  onContextMenu={(e) => { e.preventDefault(); setMenuFor(entry.id) }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') { entry.kind === 'folder' ? nav(`/files/${entry.id}`) : setPreview(entry) }
                    if (e.key === ' ') { e.preventDefault(); onRowClick({ ctrlKey: true } as React.MouseEvent, entry, idx) }
                    if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) setMenuFor(entry.id)
                  }}
                  className={`flex cursor-pointer items-center gap-3 px-4 py-2.5 transition-colors md:grid md:grid-cols-[minmax(0,1fr)_110px_170px_48px] md:items-center ${
                    selected.has(entry.id) ? 'bg-[var(--ld-accent-soft)]' : 'hover:bg-[var(--ld-surface-2)]'
                  }`}
                >
                  <span className="flex min-w-0 items-center gap-3">
                    {isImage(entry) && entry.hash_status === 'verified'
                      ? <img src={`/api/v1/files/${entry.id}/thumbnail`} alt="" loading="lazy" className="h-10 w-10 shrink-0 rounded-lg object-cover" />
                      : <span className="grid h-10 w-10 shrink-0 place-items-center">{entryIcon(entry, 22)}</span>}
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium" title={entry.name}>{entry.name}</span>
                      <span className="block text-xs text-[var(--ld-muted)] md:hidden">
                        {entry.kind === 'file' ? fmtSize(entry.size) : 'Folder'}
                        {' · '}{fmtDate(entry.created_at)}
                        {entry.hash_status === 'pending' && ' · verifying…'}
                      </span>
                      <span className="hidden text-xs text-[var(--ld-muted)] md:block">
                        {entry.kind === 'folder' ? 'Folder' : (entry.mime_type || '').split('/')[1] || 'File'}
                        {entry.hash_status === 'pending' && ' · verifying…'}
                      </span>
                    </span>
                  </span>
                  <span className="hidden text-sm tabular-nums text-[var(--ld-muted)] md:block">
                    {entry.kind === 'file' ? fmtSize(entry.size) : '—'}
                  </span>
                  <span className="hidden text-sm text-[var(--ld-muted)] md:block">{fmtDate(entry.created_at)}</span>
                  <div className="relative" onClick={(e) => e.stopPropagation()}>
                    <Button variant="ghost" onClick={() => setMenuFor(menuFor === entry.id ? null : entry.id)} ariaLabel={`Actions for ${entry.name}`} aria-expanded={menuFor === entry.id}>
                      <MoreVertical size={16} aria-hidden />
                    </Button>
                    {menuFor === entry.id && <EntryMenu entry={entry} close={() => setMenuFor(null)} setDialog={setDialog} setPreview={setPreview} />}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </main>

      {/* upload manager (bottom sheet, only when items exist) */}
      {uploadItems.length > 0 && <UploadSheet />}

      {/* dialogs */}
      {dialog?.kind === 'newFolder' && (
        <NameDialog title="Create folder" initial="" submitLabel="Create"
          onClose={() => setDialog(null)}
          onSubmit={async (name) => {
            try {
              if (!folderId) { toast('Pick a folder to create it in.', 'error'); return }
              await api.post('/folders', { parent_id: folderId, name })
              setDialog(null); refresh()
            } catch (e) { toast(String(e), 'error') }
          }} />
      )}
      {dialog?.kind === 'rename' && (
        <NameDialog title="Rename" initial={dialog.entry.name} submitLabel="Rename"
          onClose={() => setDialog(null)}
          onSubmit={async (name) => {
            try {
              if (dialog.entry.kind === 'folder') await api.patch(`/folders/${dialog.entry.id}`, { name })
              else await api.patch(`/files/${dialog.entry.id}`, { name })
              setDialog(null); refresh()
            } catch (e) { toast(String(e), 'error') }
          }} />
      )}
      {dialog?.kind === 'delete' && (
        <Modal open onClose={() => setDialog(null)} title={dialog.entries.length === 1 ? `Delete “${dialog.entries[0].name}”?` : `Delete ${dialog.entries.length} items?`} danger>
          <p className="mb-4 text-sm text-[var(--ld-muted)]">Items move to the trash and are purged after 30 days.</p>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setDialog(null)}>Cancel</Button>
            <Button variant="danger" onClick={async () => { const d = dialog.entries; setDialog(null); await doDelete(d) }}>Delete</Button>
          </div>
        </Modal>
      )}
      {dialog?.kind === 'move' && (
        <MoveDialog entries={dialog.entries} onClose={() => { setDialog(null); refresh() }} />
      )}
      {dialog?.kind === 'copy' && (
        <MoveDialog entries={[dialog.entry]} copy onClose={() => { setDialog(null); refresh() }} />
      )}
      {dialog?.kind === 'share' && (
        <ShareDialog entry={dialog.entry} onClose={() => { setDialog(null) }} />
      )}

      {/* preview */}
      {preview && <PreviewModal entry={preview} onClose={() => setPreview(null)} />}

      {/* upload FAB (mobile-visible, folder-only) */}
      {folderId && selected.size === 0 && (
        <button
          onClick={pickFiles}
          aria-label="Upload files"
          className="fixed bottom-20 right-4 z-30 grid h-14 w-14 place-items-center rounded-full bg-[var(--ld-accent)] text-white shadow-xl hover:bg-[var(--ld-accent-strong)] md:hidden"
        ><Upload size={22} aria-hidden /></button>
      )}
    </div>
  )
}

// ---- sub-components ----

function EntryMenu({ entry, close, setDialog, setPreview }: {
  entry: Entry
  close: () => void
  setDialog: (d: DialogState) => void
  setPreview: (e: Entry) => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) close() }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    setTimeout(() => ref.current?.querySelector<HTMLButtonElement>('button')?.focus(), 0)
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [close])
  const act = (fn: () => void) => () => { close(); fn() }
  return (
    <div ref={ref} role="menu" aria-label={`Actions for ${entry.name}`} className="absolute right-0 top-9 z-40 w-48 rounded-xl border border-[var(--ld-line)] bg-[var(--ld-surface)] py-1 shadow-xl">
      {entry.kind === 'folder' ? (
        <button role="menuitem" className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-[var(--ld-accent-soft)]" onClick={act(() => setDialog({ kind: 'rename', entry }))}><Pencil size={14} aria-hidden /> Rename</button>
      ) : (
        <>
          <button role="menuitem" className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-[var(--ld-accent-soft)]" onClick={act(() => setPreview(entry))}><FileText size={14} aria-hidden /> Preview</button>
          <a role="menuitem" href={downloadUrl(entry.id)} className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-[var(--ld-accent-soft)]" onClick={close}><Download size={14} aria-hidden /> Download</a>
          <button role="menuitem" className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-[var(--ld-accent-soft)]" onClick={act(() => setDialog({ kind: 'rename', entry }))}><Pencil size={14} aria-hidden /> Rename</button>
          <button role="menuitem" className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-[var(--ld-accent-soft)]" onClick={act(() => setDialog({ kind: 'copy', entry }))}><Copy size={14} aria-hidden /> Copy</button>
          <button role="menuitem" className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-[var(--ld-accent-soft)]" onClick={act(() => setDialog({ kind: 'share', entry }))}><Share2 size={14} aria-hidden /> Share</button>
        </>
      )}
      <button role="menuitem" className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-[var(--ld-accent-soft)]" onClick={act(() => setDialog({ kind: 'move', entries: [entry] }))}><FolderInput size={14} aria-hidden /> Move</button>
      <div className="my-1 border-t border-[var(--ld-line)]" aria-hidden />
      <button role="menuitem" className="flex w-full items-center gap-2 px-3 py-2 text-sm text-[var(--ld-danger)] hover:bg-[var(--ld-danger-soft)]" onClick={act(() => setDialog({ kind: 'delete', entries: [entry] }))}><Trash2 size={14} aria-hidden /> Delete</button>
    </div>
  )
}

function NameDialog({ title, initial, submitLabel, onSubmit, onClose }: {
  title: string; initial: string; submitLabel: string
  onSubmit: (name: string) => Promise<void>; onClose: () => void
}) {
  const [name, setName] = useState(initial)
  return (
    <Modal open onClose={onClose} title={title}>
      <form onSubmit={async (e) => { e.preventDefault(); await onSubmit(name) }} className="flex flex-col gap-4">
        <label className="text-sm font-medium">Name
          <Input value={name} onChange={(e) => setName(e.target.value)} required maxLength={255} autoFocus onFocus={(e) => e.target.select()} />
        </label>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit">{submitLabel}</Button>
        </div>
      </form>
    </Modal>
  )
}

export function FolderPicker({ onPick, exclude, allowRoot }: { onPick: (id: string | null, name: string) => void; exclude?: string; allowRoot?: boolean }) {
  const [folders, setFolders] = useState<Entry[]>([])
  const [stack, setStack] = useState<{ id: string; name: string }[]>([])
  useEffect(() => {
    const path = stack.length ? `/folders/${stack[stack.length - 1].id}/children` : '/folders/root/children'
    api.get<{ items: Entry[] }>(`${path}?type=folder`).then((p) => setFolders(p.items.filter((f) => f.id !== exclude)))
  }, [stack, exclude])
  return (
    <div className="max-h-64 overflow-y-auto rounded-lg border border-[var(--ld-line)]">
      <button type="button" disabled={!stack.length} onClick={() => setStack((s) => s.slice(0, -1))}
        className="flex w-full items-center gap-2 border-b border-[var(--ld-line)] px-3 py-2 text-sm disabled:opacity-40">
        <ArrowUp size={14} aria-hidden /> Up{stack.length ? ` (from ${stack[stack.length - 1].name})` : ''}
      </button>
      {allowRoot && stack.length === 0 && (
        <button type="button" onClick={() => onPick(null, 'Top level')}
          className="w-full bg-[var(--ld-accent-soft)] px-3 py-2 text-left text-sm font-medium">
          <span className="text-[var(--ld-accent)]">⤴ Move to top level</span>
        </button>
      )}
      {folders.map((f) => (
        <button key={f.id} type="button"
          onClick={() => setStack((s) => [...s, { id: f.id, name: f.name }])}
          className="flex w-full items-center gap-2 border-b border-[var(--ld-line)] px-3 py-2 text-sm last:border-0 hover:bg-[var(--ld-accent-soft)]">
          {entryIcon(f, 16)} {f.name}
        </button>
      ))}
      {stack.length > 0 && (
        <button type="button" onClick={() => onPick(stack[stack.length - 1].id, stack[stack.length - 1].name)}
          className="w-full bg-[var(--ld-accent-soft)] px-3 py-2 text-sm font-medium text-[var(--ld-accent)]">
          Move here
        </button>
      )}
    </div>
  )
}

function MoveDialog({ entries, copy = false, onClose }: { entries: Entry[]; copy?: boolean; onClose: () => void }) {
  const toast = useToast()
  const [done, setDone] = useState(false)
  return (
    <Modal open onClose={onClose} title={copy ? `Copy “${entries[0].name}” to…` : `Move ${entries.length} item${entries.length > 1 ? 's' : ''} to…`}>
      {!done ? (
        <FolderPicker
          allowRoot={!copy && entries.every((e) => e.kind === 'folder')}
          onPick={async (id) => {
          try {
            for (const en of entries) {
              if (copy && en.kind === 'file') await api.post(`/files/${en.id}/copy`, { folder_id: id })
              else if (en.kind === 'folder') await api.post(`/folders/${en.id}/move`, { new_parent_id: id })
              else await api.post(`/files/${en.id}/move`, { folder_id: id, overwrite: false })
            }
            toast(copy ? 'Copied.' : 'Moved.', 'success')
            setDone(true); onClose()
          } catch (e) { toast(String(e), 'error'); onClose() }
        }} />
      ) : <div />}
    </Modal>
  )
}

function ShareDialog({ entry, onClose }: { entry: Entry; onClose: () => void }) {
  const [password, setPassword] = useState('')
  const [usePassword, setUsePassword] = useState(false)
  const [days, setDays] = useState(7)
  const [limit, setLimit] = useState('')
  const [result, setResult] = useState<{ url: string; qr_svg: string } | null>(null)
  const toast = useToast()

  const create = async () => {
    try {
      const body: Record<string, unknown> = { file_id: entry.id }
      if (days > 0) body.expires_at = new Date(Date.now() + days * 86400000).toISOString()
      if (limit) body.max_downloads = parseInt(limit, 10)
      if (usePassword && password) body.password = password
      const share = await api.post<{ url: string; qr_svg: string }>('/shares', body)
      setResult(share)
    } catch (e) { toast(String(e), 'error') }
  }

  return (
    <Modal open onClose={onClose} title={`Share “${entry.name}”`}>
      {!result ? (
        <div className="flex flex-col gap-4">
          <label className="flex items-center justify-between text-sm font-medium">
            Expires after
            <select value={days} onChange={(e) => setDays(+e.target.value)} className="rounded-lg border border-[var(--ld-line)] bg-[var(--ld-surface)] px-2 py-1.5 text-sm" aria-label="Link expiry">
              <option value={7}>7 days</option>
              <option value={30}>30 days</option>
              <option value={0}>Never</option>
            </select>
          </label>
          <label className="flex items-center justify-between text-sm font-medium">
            Download limit
            <Input value={limit} onChange={(e) => setLimit(e.target.value.replace(/\D/g, ''))} placeholder="unlimited" className="!w-32" aria-label="Maximum downloads" />
          </label>
          <label className="flex items-center gap-2 text-sm font-medium">
            <input type="checkbox" checked={usePassword} onChange={(e) => setUsePassword(e.target.checked)} className="h-4 w-4" />
            Password protect
          </label>
          {usePassword && (
            <label className="text-sm font-medium">Password
              <Input value={password} onChange={(e) => setPassword(e.target.value)} minLength={1} required autoFocus />
            </label>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button onClick={create}>Create link</Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3">
          <div className="rounded-lg bg-white p-3" aria-hidden dangerouslySetInnerHTML={{ __html: result.qr_svg }} />
          <div className="flex w-full items-center gap-2">
            <Input readOnly value={result.url} onFocus={(e) => e.target.select()} aria-label="Share link" />
            <Button variant="secondary" onClick={async () => { await navigator.clipboard.writeText(result.url); toast('Link copied.', 'success') }} ariaLabel="Copy link">Copy</Button>
          </div>
          <Button onClick={onClose}>Done</Button>
        </div>
      )}
    </Modal>
  )
}

export function PreviewModal({ entry, onClose }: { entry: Entry; onClose: () => void }) {
  const m = entry.mime_type || ''
  return (
    <Modal open onClose={onClose} title={entry.name}>
      <div className="max-h-[70vh] overflow-auto">
        {m.startsWith('image/') ? (
          <img src={downloadUrl(entry.id)} alt={entry.name} className="mx-auto max-h-[60vh] rounded" />
        ) : m === 'application/pdf' ? (
          <iframe src={downloadUrl(entry.id)} title={`PDF preview of ${entry.name}`} className="h-[60vh] w-full rounded" />
        ) : m.startsWith('video/') ? (
          <video controls className="w-full rounded" src={downloadUrl(entry.id)} />
        ) : m.startsWith('audio/') ? (
          <audio controls className="w-full" src={downloadUrl(entry.id)} />
        ) : m.startsWith('text/') || m === 'application/json' ? (
          <TextPreview entry={entry} />
        ) : (
          <div className="py-8 text-center text-sm text-[var(--ld-muted)]">
            No preview available for this file type.
            <div className="mt-3"><a href={downloadUrl(entry.id)} download className="text-[var(--ld-accent)] underline">Download instead</a></div>
          </div>
        )}
      </div>
    </Modal>
  )
}

function TextPreview({ entry }: { entry: Entry }) {
  const [text, setText] = useState<string | null>(null)
  useEffect(() => {
    fetch(`/api/v1/files/${entry.id}/preview`, { headers: { 'X-Requested-With': 'localdrop' } })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.statusText))))
      .then((p) => setText(p.text + (p.truncated ? '\n\n… (truncated)' : '')))
      .catch((e) => setText(`Could not load preview: ${e}`))
  }, [entry.id])
  return (
    <pre className="whitespace-pre-wrap rounded-lg bg-[var(--ld-canvas)] p-3 text-xs leading-relaxed">{text ?? 'Loading…'}</pre>
  )
}

function UploadSheet() {
  const items = useUploads((s) => s.items)
  const clearDone = useUploads((s) => s.clearDone)
  const [open, setOpen] = useState(true)
  const [speeds, setSpeeds] = useState<Record<string, number>>({})
  const active = items.filter((i) => !['done', 'cancelled'].includes(i.status))

  // Transfer speed: sample each uploading item's `sent` once per second.
  const sentRef = useRef<Record<string, number>>({})
  useEffect(() => {
    const t = setInterval(() => {
      const uploading = items.filter((i) => i.status === 'uploading')
      setSpeeds(() => {
        const next: Record<string, number> = {}
        for (const it of uploading) {
          const before = sentRef.current[it.id]
          if (before !== undefined && it.sent >= before) next[it.id] = it.sent - before
          sentRef.current[it.id] = it.sent
        }
        return next
      })
    }, 1000)
    return () => clearInterval(t)
  }, [items])

  if (!items.length) return null
  return (
    <div className="fixed inset-x-0 bottom-16 z-40 mx-auto max-w-md md:bottom-4 md:left-auto md:right-4 md:mx-0" role="region" aria-label="Upload progress">
      <div className="animate-rise overflow-hidden rounded-[var(--ld-radius)] border border-[var(--ld-line)] bg-[var(--ld-surface)] shadow-[var(--ld-shadow-lg)]">
        <button onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center justify-between px-4 py-3 text-sm font-semibold">
          <span>Uploads{active.length > 0 ? ` — ${active.length} active` : ''}</span>
          <span className="flex items-center gap-3 text-xs font-normal text-[var(--ld-muted)]">
            {items.some((i) => i.status === 'done' || i.status === 'cancelled') && (
              <button onClick={(e) => { e.stopPropagation(); clearDone() }} className="font-medium underline hover:text-[var(--ld-text)]">Clear done</button>
            )}
            {open ? 'Hide' : 'Show'}
          </span>
        </button>
        {open && (
          <ul className="max-h-72 divide-y divide-[var(--ld-line)] overflow-y-auto border-t border-[var(--ld-line)]" aria-label="Upload items">
            {items.map((it) => {
              const pct = it.status === 'done' ? 100 : Math.round((it.sent / Math.max(it.size, 1)) * 100)
              const speed = speeds[it.id]
              return (
                <li key={it.id} className="px-4 py-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="min-w-0 flex-1 truncate font-medium" title={it.name}>{it.name}</span>
                    <span className={`shrink-0 text-xs font-medium ${it.status === 'error' ? 'text-[var(--ld-danger)]' : it.status === 'done' ? 'text-[var(--ld-ok)]' : 'text-[var(--ld-muted)]'}`}>
                      {it.status === 'uploading' ? `${pct}%`
                        : it.status === 'verifying' ? 'verifying…'
                        : it.status === 'done' ? 'Done ✓'
                        : it.status === 'error' ? 'Failed'
                        : it.status === 'paused' ? 'Paused'
                        : it.status}
                    </span>
                    {(it.status === 'uploading' || it.status === 'paused' || it.status === 'error') && (
                      <span className="flex shrink-0 items-center gap-1">
                        {it.status === 'uploading' ? (
                          <button onClick={() => pauseUpload(it.id)} aria-label={`Pause ${it.name}`}
                            className="rounded-md px-1.5 py-0.5 text-xs text-[var(--ld-muted)] hover:bg-[var(--ld-surface-2)]">Pause</button>
                        ) : (
                          <button onClick={() => (it.status === 'error' ? retryUpload(it.id) : resumeUpload(it.id))}
                            aria-label={`${it.status === 'error' ? 'Retry' : 'Resume'} ${it.name}`}
                            className="rounded-md px-1.5 py-0.5 text-xs font-medium text-[var(--ld-accent)] hover:bg-[var(--ld-accent-soft)]">
                            {it.status === 'error' ? 'Retry' : 'Resume'}
                          </button>
                        )}
                        <button onClick={() => cancelUpload(it.id)} aria-label={`Cancel ${it.name}`}
                          className="rounded-md px-1.5 py-0.5 text-xs text-[var(--ld-muted)] hover:bg-[var(--ld-surface-2)]">Cancel</button>
                      </span>
                    )}
                  </div>
                  <div className="mt-1.5 flex items-center gap-2" aria-hidden>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--ld-surface-2)]">
                      <div
                        className={`h-full rounded-full transition-all ${it.status === 'error' ? 'bg-[var(--ld-danger)]' : it.status === 'done' ? 'bg-[var(--ld-ok)]' : 'bg-[var(--ld-accent)]'}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="w-28 shrink-0 text-right text-[11px] tabular-nums text-[var(--ld-muted)]">
                      {it.status === 'uploading' && speed !== undefined && speed > 0
                        ? `${fmtSize(speed)}/s`
                        : it.status === 'done' ? '' : `${fmtSize(it.sent)} / ${fmtSize(it.size)}`}
                    </span>
                  </div>
                  {it.error && <p className="mt-1 text-xs text-[var(--ld-danger)]" role="alert">{it.error}</p>}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
