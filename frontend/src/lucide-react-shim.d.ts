// Fallback types for lucide-react: the installed 1.49.0 publish ships
// JavaScript only (no dist/lucide-react.d.ts), so TS7016 fires on every
// icon import. This ambient declaration keeps `npm run build` green
// without touching deps. If you import a new icon, add its name below.

declare module 'lucide-react' {
  import type { FC, SVGProps } from 'react'
  export type LucideProps = SVGProps<SVGSVGElement> & {
    size?: number | string
  }
  export const File: FC<LucideProps>
  export const FileText: FC<LucideProps>
  export const FileArchive: FC<LucideProps>
  export const FileQuestion: FC<LucideProps>
  export const Image: FC<LucideProps>
  export const Film: FC<LucideProps>
  export const Music: FC<LucideProps>
  export const Folder: FC<LucideProps>
  export const FolderOpen: FC<LucideProps>
  export const FolderPlus: FC<LucideProps>
  export const FolderInput: FC<LucideProps>
  export const X: FC<LucideProps>
  export const CheckCircle2: FC<LucideProps>
  export const AlertTriangle: FC<LucideProps>
  export const Inbox: FC<LucideProps>
  export const ArrowUp: FC<LucideProps>
  export const ChevronDown: FC<LucideProps>
  export const ChevronRight: FC<LucideProps>
  export const Search: FC<LucideProps>
  export const Upload: FC<LucideProps>
  export const Download: FC<LucideProps>
  export const MoreVertical: FC<LucideProps>
  export const Pencil: FC<LucideProps>
  export const Copy: FC<LucideProps>
  export const Trash2: FC<LucideProps>
  export const Share2: FC<LucideProps>
  export const Settings: FC<LucideProps>
  export const LogOut: FC<LucideProps>
  export const HardDrive: FC<LucideProps>
  export const Ban: FC<LucideProps>
  export const Sun: FC<LucideProps>
  export const Moon: FC<LucideProps>
  export const Monitor: FC<LucideProps>
  export const MonitorSmartphone: FC<LucideProps>
  export const Smartphone: FC<LucideProps>
  export const LayoutGrid: FC<LucideProps>
  export const List: FC<LucideProps>
  export const RefreshCw: FC<LucideProps>
  export const QrCode: FC<LucideProps>
  export const Plus: FC<LucideProps>
  export const RotateCcw: FC<LucideProps>
  export const ShieldCheck: FC<LucideProps>
  export const KeyRound: FC<LucideProps>
  export const CircleUserRound: FC<LucideProps>
}
