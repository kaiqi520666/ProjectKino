import { Clapperboard, Images, LayoutDashboard, UserRound } from 'lucide-vue-next'

export const workspaceNavigation = [
  { key: 'studio', label: '短剧', to: '/workspace', icon: Clapperboard },
  { key: 'canvas', label: '画布', to: '/canvas', icon: LayoutDashboard },
  { key: 'assets', label: '素材', to: '/assets', icon: Images },
] as const

export const workspaceAccountNavigation = {
  key: 'account', label: '我的', to: '/account', icon: UserRound,
} as const

export interface WorkspaceUser {
  name: string
  avatarUrl?: string
}

export interface WorkspaceBreadcrumb {
  label: string
  to?: string
}
