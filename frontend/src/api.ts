// LocalDrop API client: fetch wrapper with CSRF header + problem+json errors.

export class ApiError extends Error {
  status: number
  title: string
  requestId?: string
  constructor(status: number, title: string, detail: string, requestId?: string) {
    super(detail || title)
    this.status = status
    this.title = title
    this.requestId = requestId
  }
}

async function request<T>(method: string, path: string, body?: unknown, extra?: HeadersInit): Promise<T> {
  const headers: Record<string, string> = { 'X-Requested-With': 'localdrop' }
  let payload: string | undefined
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  Object.assign(headers, extra || {})
  const res = await fetch(`/api/v1${path}`, { method, headers, body: payload, credentials: 'same-origin' })
  if (res.status === 204) return undefined as T
  const type = res.headers.get('content-type') || ''
  if (!res.ok) {
    if (type.includes('application/problem+json')) {
      const p = await res.json()
      throw new ApiError(res.status, p.title, p.detail, p.request_id)
    }
    throw new ApiError(res.status, res.statusText, `Request failed (${res.status})`)
  }
  if (type.includes('application/json')) return res.json() as Promise<T>
  return undefined as T
}

export const api = {
  get: <T,>(p: string) => request<T>('GET', p),
  post: <T,>(p: string, b?: unknown) => request<T>('POST', p, b),
  patch: <T,>(p: string, b?: unknown) => request<T>('PATCH', p, b),
  put: <T,>(p: string, b?: unknown) => request<T>('PUT', p, b),
  del: <T,>(p: string) => request<T>('DELETE', p),
}

// ---- types ----
export interface Entry {
  id: string
  kind: 'file' | 'folder'
  name: string
  size: number
  mime_type?: string | null
  hash_status?: string | null
  created_at: string
  updated_at?: string | null
  deleted_at?: string | null
}

export interface Share {
  id: string
  token: string
  file_id: string
  file_name?: string | null
  file_size: number
  url: string
  expires_at?: string | null
  max_downloads?: number | null
  download_count: number
  has_password: boolean
  revoked_at?: string | null
  created_at?: string
  qr_svg?: string
}

export interface Me {
  id: string
  username: string
  role: string
  storage_used: number
  storage_quota: number | null
}

// ---- helpers ----
export function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let v = n
  let u = -1
  do { v /= 1024; u++ } while (v >= 1024 && u < units.length - 1)
  return `${v.toFixed(v >= 100 ? 0 : 1)} ${units[u]}`
}

export function fmtDate(iso?: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

export function downloadUrl(id: string): string {
  return `/api/v1/files/${id}/content`
}

export function isPreviewable(e: Entry): boolean {
  const m = e.mime_type || ''
  return /^(image\/(jpeg|png|webp|gif|avif)|video\/|audio\/|application\/pdf|text\/)/.test(m)
}

export function isImage(e: Entry): boolean {
  return /^image\/(jpeg|png|webp|gif|avif)$/.test(e.mime_type || '')
}
