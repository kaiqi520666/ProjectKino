export type CollectableMediaKind = 'image' | 'video' | 'audio'

export interface UserAssetMediaRecord {
  id: string
  kind: string
  mediaUrl?: string | null
  mediaKey?: string | null
}

export interface MediaCollectCandidate {
  kind: CollectableMediaKind
  title: string
  mediaUrl?: string | null
  mediaKey?: string | null
  mediaName?: string | null
  sourceType?: 'canvas' | 'studio' | 'upload'
  sourceId?: string | null
}

export interface PlannedMediaCollectCandidate extends MediaCollectCandidate {
  mediaUrl: string
}

export interface BatchLibraryCollectPlan {
  toAdd: PlannedMediaCollectCandidate[]
  skippedExisting: number
  skippedEmpty: number
}

function normalizeUrl(url?: string | null): string {
  return typeof url === 'string' ? url.trim() : ''
}

function normalizeKey(key?: string | null): string {
  return typeof key === 'string' ? key.trim() : ''
}

export function isCollectableMediaUrl(url?: string | null): url is string {
  if (typeof url !== 'string') return false
  const trimmed = url.trim()
  if (!trimmed) return false
  return /^https?:\/\//i.test(trimmed) || (trimmed.startsWith('/') && !trimmed.startsWith('//'))
}

export function matchesUserAssetMedia(
  item: UserAssetMediaRecord,
  target: { kind: CollectableMediaKind; mediaUrl?: string | null; mediaKey?: string | null },
): boolean {
  if (item.kind !== target.kind) return false
  const targetKey = normalizeKey(target.mediaKey)
  const itemKey = normalizeKey(item.mediaKey)
  if (targetKey && itemKey && targetKey === itemKey) return true
  const targetUrl = normalizeUrl(target.mediaUrl)
  const itemUrl = normalizeUrl(item.mediaUrl)
  return Boolean(targetUrl && itemUrl && targetUrl === itemUrl)
}

export function findMatchingUserAssets<T extends UserAssetMediaRecord>(
  items: readonly T[],
  target: { kind: CollectableMediaKind; mediaUrl?: string | null; mediaKey?: string | null },
): T[] {
  const targetUrl = normalizeUrl(target.mediaUrl)
  const targetKey = normalizeKey(target.mediaKey)
  if (!targetUrl && !targetKey) return []
  return items.filter((item) => matchesUserAssetMedia(item, target))
}

export function planBatchLibraryCollect(
  candidates: readonly MediaCollectCandidate[],
  existingItems: readonly UserAssetMediaRecord[],
): BatchLibraryCollectPlan {
  const toAdd: PlannedMediaCollectCandidate[] = []
  const seenUrls = new Set<string>()
  const seenKeys = new Set<string>()
  let skippedExisting = 0
  let skippedEmpty = 0

  for (const candidate of candidates) {
    if (!isCollectableMediaUrl(candidate.mediaUrl)) {
      skippedEmpty += 1
      continue
    }
    const url = candidate.mediaUrl.trim()
    const key = normalizeKey(candidate.mediaKey)
    const alreadySaved = findMatchingUserAssets(existingItems, {
      kind: candidate.kind,
      mediaUrl: url,
      mediaKey: key || null,
    }).length > 0
    const dupKey = key ? `${candidate.kind}:key:${key}` : ''
    const dupUrl = `${candidate.kind}:url:${url}`
    if (alreadySaved || seenUrls.has(dupUrl) || (dupKey && seenKeys.has(dupKey))) {
      skippedExisting += 1
      continue
    }
    seenUrls.add(dupUrl)
    if (dupKey) seenKeys.add(dupKey)
    toAdd.push({
      ...candidate,
      mediaUrl: url,
      mediaKey: key || null,
    })
  }

  return { toAdd, skippedExisting, skippedEmpty }
}

export function formatBatchCollectSummary(result: {
  added: number
  skippedExisting: number
  skippedEmpty: number
  failed: number
}): { message: string; tone: 'success' | 'info' | 'error' } {
  if (result.added === 0 && result.failed > 0) {
    return { message: `加入素材库失败（${result.failed} 项）`, tone: 'error' }
  }
  if (result.added === 0 && result.skippedExisting > 0) {
    return { message: '所选项均已在素材库中', tone: 'info' }
  }
  if (result.added === 0) {
    return { message: '没有可加入素材库的已生成内容', tone: 'info' }
  }
  const parts = [`已加入 ${result.added} 项到素材库`]
  if (result.skippedExisting > 0) parts.push(`${result.skippedExisting} 项已存在`)
  if (result.failed > 0) parts.push(`${result.failed} 项失败`)
  return { message: parts.join('，'), tone: result.failed > 0 ? 'info' : 'success' }
}
