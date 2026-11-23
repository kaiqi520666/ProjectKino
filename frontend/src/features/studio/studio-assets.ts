import type { JobOut, MediaHistoryItemOut } from './api-types.ts'

export const assetKindOptions = [
  { value: 'character', label: '角色' },
  { value: 'scene', label: '场景' },
  { value: 'prop', label: '物品' },
] as const

export type StudioAssetKind = (typeof assetKindOptions)[number]['value']

export interface StudioAsset {
  id: string
  backendId?: string
  parentAssetId?: string
  variantLabel?: string
  kind: StudioAssetKind
  name: string
  description: string
  prompt: string
  imageUrl?: string
  imageKey?: string
  voice?: string
  imageModelId?: string
  imageTier?: string
  imageStatus?: string
  imageHistory?: MediaHistoryItemOut[]
  lastJobId?: string
  lastJobStatus?: JobOut['status']
  lastJobError?: string
}

export type StudioAssetDraft = Pick<
  StudioAsset,
  'name' | 'description' | 'prompt' | 'imageUrl' | 'imageKey' | 'voice' | 'parentAssetId' | 'variantLabel'
>

export interface StudioAssetGroup {
  root: StudioAsset
  items: StudioAsset[]
}

export const variantLabelSuggestions: Record<StudioAssetKind, readonly string[]> = {
  character: ['晚宴礼服', '便装', '受伤战损', '雨中湿身', '回忆/年轻'],
  scene: ['深夜', '黄昏', '雨夜', '灯火通明', '损毁/凌乱'],
  prop: ['碎裂', '拆封', '沾血', '启动/发光', '陈旧破损'],
}

export function assetStateLabel(asset: Pick<StudioAsset, 'variantLabel'>): string {
  return asset.variantLabel?.trim() || '默认'
}

export function assetDisplayName(asset: Pick<StudioAsset, 'name' | 'variantLabel'>): string {
  const label = asset.variantLabel?.trim()
  return label ? `${asset.name} · ${label}` : asset.name
}

export function groupStudioAssets(assets: readonly StudioAsset[]): StudioAssetGroup[] {
  const roots = new Map<string, StudioAssetGroup>()
  const ordered: StudioAssetGroup[] = []
  const variants: StudioAsset[] = []

  for (const asset of assets) {
    if (asset.parentAssetId) {
      variants.push(asset)
      continue
    }
    const group: StudioAssetGroup = { root: asset, items: [asset] }
    if (asset.backendId) roots.set(asset.backendId, group)
    ordered.push(group)
  }

  for (const variant of variants) {
    const parentGroup = variant.parentAssetId ? roots.get(variant.parentAssetId) : undefined
    if (parentGroup) {
      parentGroup.items.push(variant)
    } else {
      ordered.push({ root: variant, items: [variant] })
    }
  }

  return ordered
}

export function findParentAsset(
  assets: readonly StudioAsset[],
  asset: StudioAsset,
): StudioAsset | undefined {
  if (!asset.parentAssetId) return undefined
  return assets.find((item) => item.backendId === asset.parentAssetId)
}

export function findAssetSiblings(
  assets: readonly StudioAsset[],
  target: StudioAsset,
): StudioAsset[] {
  const rootId = target.parentAssetId ?? target.backendId
  if (!rootId) return [target]
  const root = assets.find((item) => item.backendId === rootId)
  const variants = assets.filter((item) => item.parentAssetId === rootId)
  if (!root) return variants.length ? variants : [target]
  return [root, ...variants]
}

export const exampleAssetLibrary = {
  character: [
    { name: '城市街头的短发女孩', imageUrl: '/images/home/cover-city.jpg' },
    { name: '观景窗边的宇航员', imageUrl: '/images/home/scene-scifi.jpg' },
  ],
  scene: [
    { name: '老城巷口', imageUrl: '/images/art-styles/republican-era.webp' },
    { name: '夜间走廊', imageUrl: '/images/art-styles/suspense-horror.webp' },
  ],
  prop: [
    { name: '桌上的纸质剧本', imageUrl: '/images/workspace/banner-story.jpg' },
    { name: '桌面分镜卡片', imageUrl: '/images/workspace/entry-canvas.jpg' },
  ],
} satisfies Record<StudioAssetKind, { name: string; imageUrl: string }[]>

export function createExampleAssets(): StudioAsset[] {
  return [
    {
      id: 'reporter', kind: 'character', name: '林夏', description: '追查一封旧信来历的记者，常穿浅色外套。',
      prompt: '写实电影风，短发青年女记者，浅色夹克，神情专注，柔和自然光，正面半身肖像。',
      imageUrl: exampleAssetLibrary.character[0].imageUrl,
    },
    {
      id: 'caretaker', kind: 'character', name: '周伯', description: '照看旧档案楼的管理员，随身带着一串钥匙。',
      prompt: '写实半身肖像，年长的档案管理员，深灰外套，面容平静，室内侧光，朴素背景。',
    },
    {
      id: 'alley', kind: 'scene', name: '老城巷口', description: '连接街道和档案楼后门的窄巷。',
      prompt: '老城石板巷，刚下过雨，两侧旧砖墙，傍晚自然光，平视广角，写实电影质感。',
      imageUrl: exampleAssetLibrary.scene[0].imageUrl,
    },
    {
      id: 'archive', kind: 'scene', name: '旧档案室', description: '一间布满金属文件柜的档案室，窗边只亮着一盏台灯。',
      prompt: '旧档案室全景，成排金属柜，窗边暖光台灯，夜晚，轻微颗粒感，无人物。',
    },
    {
      id: 'documents', kind: 'prop', name: '纸质档案', description: '夹在书桌资料里的一叠旧纸张。',
      prompt: '木桌上的旧纸质档案，纸张略发黄，有折痕和细微磨损，侧上方柔光，无可读文字。',
      imageUrl: exampleAssetLibrary.prop[0].imageUrl,
    },
    {
      id: 'key', kind: 'prop', name: '铜钥匙', description: '挂在管理员钥匙串上的一枚旧铜钥匙。',
      prompt: '单枚暗黄铜钥匙，表面有划痕，平放于中性深灰背景，写实近景，无其他物品。',
    },
  ]
}
