// lucide-react ships without bundled types in some installs; the icons are
// used purely as presentational components (size, className, aria-*).
declare module 'lucide-react' {
  import type { ComponentType, SVGProps } from 'react'
  export type LucideProps = SVGProps<SVGSVGElement> & { size?: number | string }
  type Icon = ComponentType<LucideProps>
  export const AlertTriangle: Icon
  export const ArrowUp: Icon
  export const Ban: Icon
  export const CheckCircle2: Icon
  export const ChevronDown: Icon
  export const ChevronRight: Icon
  export const Copy: Icon
  export const Download: Icon
  export const File: Icon
  export const FileArchive: Icon
  export const FileQuestion: Icon
  export const FileText: Icon
  export const Film: Icon
  export const Folder: Icon
  export const FolderInput: Icon
  export const FolderOpen: Icon
  export const FolderPlus: Icon
  export const HardDrive: Icon
  export const Image: Icon
  export const LogOut: Icon
  export const MoreVertical: Icon
  export const Music: Icon
  export const Pencil: Icon
  export const Search: Icon
  export const Settings: Icon
  export const Share2: Icon
  export const Trash2: Icon
  export const Upload: Icon
  export const X: Icon
}
