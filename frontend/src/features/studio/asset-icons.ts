import { MapPin, Package, UserRound } from 'lucide-vue-next'
import type { StudioAssetKind } from './studio-assets'

export const assetKindIcons = {
  character: UserRound,
  scene: MapPin,
  prop: Package,
} as const satisfies Record<StudioAssetKind, typeof UserRound>

export const assetCategoryItems = [
  { kind: 'character' as const, label: '角色', icon: UserRound },
  { kind: 'scene' as const, label: '场景', icon: MapPin },
  { kind: 'prop' as const, label: '物品', icon: Package },
] as const
