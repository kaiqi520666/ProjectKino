import type { ModelCatalogItemOut } from './api-types.ts'

export type ImageTier = 'web' | '1k' | '2k' | '4k'

export const IMAGE_TIER_OPTIONS: readonly { value: ImageTier; label: string }[] = [
  { value: 'web', label: 'Web' },
  { value: '1k', label: '1K' },
  { value: '2k', label: '2K' },
  { value: '4k', label: '4K' },
]

export function isImageTier(value: unknown): value is ImageTier {
  return value === 'web' || value === '1k' || value === '2k' || value === '4k'
}

export function modelMinDuration(model: ModelCatalogItemOut | null | undefined): number {
  const raw = Number(model?.capabilities?.minDuration)
  return Number.isFinite(raw) && raw > 0 ? raw : 4
}

export function modelMaxDuration(model: ModelCatalogItemOut | null | undefined): number {
  const raw = Number(model?.capabilities?.maxDuration)
  return Number.isFinite(raw) && raw > 0 ? raw : 15
}

export function resolveDefaultVideoModel(
  models: readonly ModelCatalogItemOut[],
  segmentCap: 15 | 30,
  preferredModelId?: string | null,
): ModelCatalogItemOut | null {
  if (!models.length) return null

  if (preferredModelId) {
    const preferred = models.find((m) => m.id === preferredModelId)
    if (preferred && (segmentCap < 30 || modelMaxDuration(preferred) >= 30)) {
      return preferred
    }
  }

  if (segmentCap >= 30) {
    return (
      models.find((m) => m.isDefaultLong && modelMaxDuration(m) >= 30)
      ?? models.find((m) => m.isDefault && modelMaxDuration(m) >= 30)
      ?? models.find((m) => modelMaxDuration(m) >= 30)
      ?? models.find((m) => m.isDefault)
      ?? models[0]
      ?? null
    )
  }

  return models.find((m) => m.isDefault) ?? models[0] ?? null
}

export function resolveDefaultImageModel(
  models: readonly ModelCatalogItemOut[],
  preferredModelId?: string | null,
): ModelCatalogItemOut | null {
  if (!models.length) return null
  if (preferredModelId) {
    const preferred = models.find((m) => m.id === preferredModelId)
    if (preferred) return preferred
  }
  return models.find((m) => m.isDefault) ?? models[0] ?? null
}

export function availableImageTiers(model: ModelCatalogItemOut | null | undefined): ImageTier[] {
  const priced = (model?.imagePrices ?? [])
    .map((item) => item.tier)
    .filter((tier): tier is ImageTier => isImageTier(tier))
  if (priced.length) {
    const order: readonly ImageTier[] = ['web', '1k', '2k', '4k']
    return order.filter((tier) => priced.includes(tier))
  }
  return ['web', '1k', '2k', '4k']
}

export function resolveImageTierForModel(
  model: ModelCatalogItemOut | null | undefined,
  preferredTier?: string | null,
): ImageTier {
  const tiers = availableImageTiers(model)
  if (isImageTier(preferredTier) && tiers.includes(preferredTier)) {
    return preferredTier
  }
  const modelDefaultTier = model?.defaults?.tier
  if (isImageTier(modelDefaultTier) && tiers.includes(modelDefaultTier)) {
    return modelDefaultTier
  }
  if (tiers.includes('1k')) return '1k'
  return tiers[0] ?? '1k'
}

export function isClipDurationExceededByModel(
  clipDuration: number | undefined,
  model: ModelCatalogItemOut | null | undefined,
): { exceeded: boolean; minDuration: number; maxDuration: number } {
  const minDuration = modelMinDuration(model)
  const maxDuration = modelMaxDuration(model)
  const exceeded = Boolean(
    model && clipDuration !== undefined && Number.isFinite(clipDuration) && clipDuration > maxDuration,
  )
  return { exceeded, minDuration, maxDuration }
}
