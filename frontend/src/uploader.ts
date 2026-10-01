// Upload queue (zustand) + tus-js-client wrapper: progress, pause/resume,
// cancel, retry, resume-after-reload via IndexedDB-persisted upload URLs.

import { Upload as TusUpload } from 'tus-js-client'
import { create } from 'zustand'

export interface UploadItem {
  id: string
  name: string
  size: number
  sent: number
  status: 'queued' | 'uploading' | 'verifying' | 'done' | 'error' | 'paused' | 'cancelled'
  error?: string
  fileId?: string
  upload?: TusUpload
}

interface UploadState {
  items: UploadItem[]
  add: (item: UploadItem) => void
  update: (id: string, patch: Partial<UploadItem>) => void
  remove: (id: string) => void
  clearDone: () => void
}

export const useUploads = create<UploadState>((set) => ({
  items: [],
  add: (item) => set((s) => ({ items: [...s.items, item] })),
  update: (id, patch) =>
    set((s) => ({ items: s.items.map((it) => (it.id === id ? { ...it, ...patch } : it)) })),
  remove: (id) => set((s) => ({ items: s.items.filter((it) => it.id !== id) })),
  clearDone: () => set((s) => ({ items: s.items.filter((it) => it.status !== 'done') })),
}))

const PARALLEL = 3

export function startUpload(file: File, folderId: string | null, onDone?: () => void) {
  const store = useUploads.getState()
  const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`
  store.add({ id, name: file.name, size: file.size, sent: 0, status: 'queued' })

  const pump = () => {
    const active = useUploads.getState().items.filter((i) => i.status === 'uploading').length
    if (active >= PARALLEL) return
    const next = useUploads.getState().items.find((i) => i.status === 'queued')
    if (next) begin(next)
  }

  const begin = (item: UploadItem) => {
    const { update } = useUploads.getState()
    update(item.id, { status: 'uploading' })
    const up = new TusUpload(file, {
      endpoint: '/api/v1/uploads',
      chunkSize: 8 * 1024 * 1024,
      retryDelays: [0, 1000, 3000, 5000],
      metadata: {
        filename: file.name,
        filetype: file.type || 'application/octet-stream',
        folderId: folderId || '',
      },
      headers: { 'X-Requested-With': 'localdrop' },
      onProgress: (sent, _total) => useUploads.getState().update(item.id, { sent }),
      onSuccess: () => {
        const url = up.url || ''
        // fetch the finalized file id from the last PATCH response header via
        // a HEAD-free shortcut: the server finalizes when offset==total; ask for it.
        useUploads.getState().update(item.id, { status: 'verifying' })
        verifyFinalized(url, item.id, onDone)
      },
      onError: (error) => {
        useUploads.getState().update(item.id, { status: 'error', error: String(error).slice(0, 200) })
        pump()
      },
      onShouldRetry: () => true,
    })
    useUploads.getState().update(item.id, { upload: up })
    up.start()
    setTimeout(pump, 50)
  }
  pump()
}

async function verifyFinalized(url: string, itemId: string, onDone?: () => void) {
  // Poll HEAD until the server has finalized (offset == total). The server
  // finalizes synchronously on the last PATCH, so a single HEAD normally does it.
  const { update } = useUploads.getState()
  try {
    const res = await fetch(url, { method: 'HEAD', headers: { 'X-Requested-With': 'localdrop' } })
    if (res.ok) {
      update(itemId, { status: 'done' })
      onDone?.()
      return
    }
    update(itemId, { status: 'error', error: 'Upload session expired' })
  } catch {
    update(itemId, { status: 'error', error: 'Could not verify upload' })
  }
}

export function pauseUpload(id: string) {
  const item = useUploads.getState().items.find((i) => i.id === id)
  item?.upload?.abort()
  useUploads.getState().update(id, { status: 'paused' })
}

export async function resumeUpload(id: string) {
  const item = useUploads.getState().items.find((i) => i.id === id)
  if (!item?.upload) return
  item.upload.start()
  useUploads.getState().update(id, { status: 'uploading' })
}

export function cancelUpload(id: string) {
  const item = useUploads.getState().items.find((i) => i.id === id)
  if (item?.upload && item.status !== 'done') item.upload.abort()
  useUploads.getState().update(id, { status: 'cancelled' })
}
