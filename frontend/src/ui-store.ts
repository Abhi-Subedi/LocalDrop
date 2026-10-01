// Small shared UI state: the app-shell top bar owns search, the file page
// owns the current folder context (the sidebar "New" button targets it).

import { create } from 'zustand'

interface UiState {
  folderId: string | null
  q: string
  setFolderId: (id: string | null) => void
  setQ: (q: string) => void
}

export const useUi = create<UiState>((set) => ({
  folderId: null,
  q: '',
  setFolderId: (folderId) => set({ folderId }),
  setQ: (q) => set({ q }),
}))

/** Sidebar/header → Files page action requests. */
export const requestUpload = () => window.dispatchEvent(new CustomEvent('ld-upload'))
export const requestNewFolder = () => window.dispatchEvent(new CustomEvent('ld-new-folder'))
