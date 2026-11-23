export type PromptReferenceKind = 'image' | 'video' | 'audio' | 'text'

export interface PromptReferenceOption {
  /** Unified slot key serialized inside `@[...]` (e.g. `图片1`, `视频1`, `音频1`, `文本1`) */
  tokenKey: string
  /** Display label inside the inline chip and @ mention popup */
  label: string
  kind: PromptReferenceKind
  thumbnailUrl?: string
}

export type PromptSegment =
  | { type: 'text'; text: string }
  | { type: 'ref'; tokenKey: string; removedLabel?: string }

const TOKEN_SPLIT_RE = /(@\[(?:(?:图片|视频|音频|文本)\d+|已移除:[^\]]+)\])/g
const SLOT_TOKEN_RE = /^@\[((?:图片|视频|音频|文本)\d+)\]$/
const REMOVED_TOKEN_RE = /^@\[已移除:([^\]]+)\]$/
const LEGACY_CANVAS_REF_RE = /\{\{ref:([\w-]+)\}\}/g

export const SLOT_PREFIX_BY_KIND: Record<PromptReferenceKind, string> = {
  image: '图片',
  video: '视频',
  audio: '音频',
  text: '文本',
}

export interface ModalitySlotEntry {
  id: string
  kind: PromptReferenceKind
  modalityIndex: number
  slotLabel: string
}

export function buildModalitySlotLabels(
  items: readonly { id: string; kind: PromptReferenceKind }[],
): ModalitySlotEntry[] {
  const counts: Record<PromptReferenceKind, number> = {
    image: 0,
    video: 0,
    audio: 0,
    text: 0,
  }
  return items.map((item) => {
    const modalityIndex = ++counts[item.kind]
    return {
      id: item.id,
      kind: item.kind,
      modalityIndex,
      slotLabel: `${SLOT_PREFIX_BY_KIND[item.kind]}${modalityIndex}`,
    }
  })
}

export function formatPromptToken(tokenKey: string, removedLabel?: string): string {
  if (removedLabel) {
    const clean = removedLabel.replace(/[\]]/g, '').trim() || tokenKey
    return `@[已移除:${clean}]`
  }
  return `@[${tokenKey}]`
}

export function parsePromptLine(line: string): PromptSegment[] {
  if (!line) return []
  const parts = line.split(TOKEN_SPLIT_RE)
  const segments: PromptSegment[] = []

  for (const part of parts) {
    if (!part) continue
    const slotMatch = SLOT_TOKEN_RE.exec(part)
    if (slotMatch) {
      segments.push({ type: 'ref', tokenKey: slotMatch[1]! })
      continue
    }
    const removedMatch = REMOVED_TOKEN_RE.exec(part)
    if (removedMatch) {
      segments.push({ type: 'ref', tokenKey: '', removedLabel: removedMatch[1]! })
      continue
    }
    segments.push({ type: 'text', text: part })
  }

  return segments
}

export function hasPromptToken(value: string): boolean {
  if (!value) return false
  return /@\[(?:(?:图片|视频|音频|文本)\d+|已移除:[^\]]+)\]/.test(value)
}

/**
 * Convert legacy Canvas `{{ref:nodeId}}` tokens into unified `@[图片N] / @[视频N] / @[音频N] / @[文本N]`.
 */
export function migrateLegacyCanvasRefs(
  prompt: string,
  slotByNodeId: ReadonlyMap<string, string>,
): string {
  if (!prompt || !prompt.includes('{{ref:')) return prompt
  return prompt.replace(LEGACY_CANVAS_REF_RE, (_full, nodeId: string) => {
    const slot = slotByNodeId.get(nodeId)
    return slot ? `@[${slot}]` : '@[已移除:节点]'
  })
}

export interface PromptRemapResult {
  prompt: string
  changed: boolean
  removedCount: number
  shiftedCount: number
}

/**
 * Remap `@[图片N]` / `@[视频N]` / `@[音频N]` / `@[文本N]` tokens when a slot of
 * `removedKind` at 1-based `removedIndex` is removed:
 * - Matching kind & index === removedIndex -> replaced with `@[已移除:<label>]`
 * - Matching kind & index > removedIndex -> decremented by 1
 * - Other modalities and indices < removedIndex -> untouched
 */
export function remapPromptOnSlotRemove(
  prompt: string,
  removedKind: PromptReferenceKind,
  removedIndex: number,
  removedLabel?: string,
): PromptRemapResult {
  if (!prompt || removedIndex < 1) {
    return { prompt, changed: false, removedCount: 0, shiftedCount: 0 }
  }
  const targetPrefix = SLOT_PREFIX_BY_KIND[removedKind]
  const safeLabel = (removedLabel || `${targetPrefix}${removedIndex}`).replace(/[\]]/g, '').trim()
    || `${targetPrefix}${removedIndex}`

  let removedCount = 0
  let shiftedCount = 0

  const next = prompt.replace(
    /@\[(图片|视频|音频|文本)(\d+)\]/g,
    (full, prefix: string, numStr: string) => {
      if (prefix !== targetPrefix) return full
      const num = Number(numStr)
      if (!Number.isSafeInteger(num) || num < 1) return full
      if (num === removedIndex) {
        removedCount += 1
        return `@[已移除:${safeLabel}]`
      }
      if (num > removedIndex) {
        shiftedCount += 1
        return `@[${prefix}${num - 1}]`
      }
      return full
    },
  )

  return {
    prompt: next,
    changed: next !== prompt,
    removedCount,
    shiftedCount,
  }
}

/**
 * Atomically remap `@[图片N]` / `@[视频N]` / `@[音频N]` / `@[文本N]` tokens when
 * reference items are reordered (single regex pass so swaps like 图片1 <-> 图片2 never double-replace).
 */
export function remapPromptOnReferenceReorder(
  prompt: string,
  prevItems: readonly { id: string; kind: PromptReferenceKind }[],
  nextItems: readonly { id: string; kind: PromptReferenceKind }[],
): { prompt: string; changed: boolean } {
  if (!prompt || !hasPromptToken(prompt)) return { prompt, changed: false }
  const prevSlots = buildModalitySlotLabels(prevItems)
  const nextSlots = buildModalitySlotLabels(nextItems)
  const nextById = new Map(nextSlots.map((entry) => [entry.id, entry.slotLabel]))

  const remap = new Map<string, string>()
  for (const prev of prevSlots) {
    const nextLabel = nextById.get(prev.id)
    if (nextLabel && nextLabel !== prev.slotLabel) {
      remap.set(prev.slotLabel, nextLabel)
    }
  }
  if (!remap.size) return { prompt, changed: false }

  const next = prompt.replace(/@\[((?:图片|视频|音频|文本)\d+)\]/g, (full, slot: string) => {
    const target = remap.get(slot)
    return target ? `@[${target}]` : full
  })
  return { prompt: next, changed: next !== prompt }
}
