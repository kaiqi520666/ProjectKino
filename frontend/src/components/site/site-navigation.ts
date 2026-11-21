export interface SiteNavItem {
  label: string
  to: string
}

export const siteNavigation: readonly SiteNavItem[] = [
  { label: '作品展示', to: '/#works' },
  { label: '创作能力', to: '/#features' },
  { label: '创作流程', to: '/#workflow' },
]
