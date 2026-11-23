export type PromptReferenceKind = 'image' | 'video' | 'audio' | 'text'
export type PromptTokenSyntax = 'canvas' | 'studio'

export interface PromptReferenceOption {
  /** Key serialized inside the token: nodeId in canvas ('node-1'), slotLabel in studio ('图片1') */
  tokenKey: string
  /** Display label in the inline chip and @ mention popup */
  label: string
  kind: PromptReferenceKind
  thumbnailUrl?: string
}

export type PromptSegment =
  | { type: 'text'; text: string }
  | { type: 'ref'; tokenKey: string; removedLabel?: string }

const CANVAS_SPLIT_RE = /(\{\{ref:[\w-]+\}\})/g
const CANVAS_TOKEN_RE = /^\{\{ref:([\w-]+)\}\}$/

const STUDIO_SPLIT_RE = /(@\[(?:(?:图片|视频|音频)\d+|已移除:[^\]]+)\])/g
const STUDIO_SLOT_TOKEN_RE = /^@\[((?:图片|视频|音频)\d+)\]$/
const STUDIO_REMOVED_TOKEN_RE = /^@\[已移除:([^\]]+)\]$/

const STUDIO_PREFIX_BY_KIND: Record<'image' | 'video' | 'audio', string> = {
  image: '图片',
  video: '视频',
  audio: '音频',
}

export function formatPromptToken(
  tokenKey: string,
  syntax: PromptTokenSyntax,
  removedLabel?: string,
): string {
  if (syntax === 'studio') {
    if (removedLabel) {
      const clean = removedLabel.replace(/[\]]/g, '').trim() || tokenKey
      return `@[已移除:${clean}]`
    }
    return `@[${tokenKey}]`
  }
  return `{{ref:${tokenKey}}}`
}

export function parsePromptLine(line: string, syntax: PromptTokenSyntax): PromptSegment[] {
  if (!line) return []
  const splitter = syntax === 'studio' ? STUDIO_SPLIT_RE : CANVAS_SPLIT_RE
  const parts = line.split(splitter)
  const segments: PromptSegment[] = []

  for (const part of parts) {
    if (!part) continue
    if (syntax === 'studio') {
      const slotMatch = STUDIO_SLOT_TOKEN_RE.exec(part)
      if (slotMatch) {
        segments.push({ type: 'ref', tokenKey: slotMatch[1]! })
        continue
      }
      const removedMatch = STUDIO_REMOVED_TOKEN_RE.exec(part)
      if (removedMatch) {
        segments.push({ type: 'ref', tokenKey: '', removedLabel: removedMatch[1]! })
        continue
      }
    } else {
      const canvasMatch = CANVAS_TOKEN_RE.exec(part)
      if (canvasMatch) {
        segments.push({ type: 'ref', tokenKey: canvasMatch[1]! })
        continue
      }
    }
    segments.push({ type: 'text', text: part })
  }

  return segments
}

export function hasPromptToken(value: string, syntax: PromptTokenSyntax): boolean {
  if (!value) return false
  if (syntax === 'studio') {
    return /@\[(?:(?:图片|视频|音频)\d+|已移除:[^\]]+)\]/.test(value)
  }
  return /\{\{ref:[\w-]+\}\}/.test(value)
}

export interface StudioPromptRemapResult {
  prompt: string
  changed: boolean
  removedCount: number
  shiftedCount: number
}

/**
 * Remap `@[图片N]` / `@[视频N]` / `@[音频N]` tokens in a Studio clip prompt when a
 * reference slot of `removedKind` at 1-based `removedIndex` is deleted:
 * - Matching kind & index === removedIndex -> replaced with `@[已移除:<label>]` (prevents collision with shifted slot)
 * - Matching kind & index > removedIndex -> decremented by 1 (`@[图片2]` -> `@[图片1]`)
 * - Other modalities and indices < removedIndex -> untouched
 */
export function remapStudioPromptOnSlotRemove(
  prompt: string,
  removedKind: 'image' | 'video' | 'audio',
  removedIndex: number,
  removedLabel?: string,
): StudioPromptRemapResult {
  if (!prompt || removedIndex < 1) {
    return { prompt, changed: false, removedCount: 0, shiftedCount: 0 }
  }
  const targetPrefix = STUDIO_PREFIX_BY_KIND[removedKind]
  const safeLabel = (removedLabel || `${targetPrefix}${removedIndex}`).replace(/[\]]/g, '').trim()
    || `${targetPrefix}${removedIndex}`

  let removedCount = 0
  let shiftedCount = 0

  const next = prompt.replace(/@\[(图片|视频|音频)(\d+)\]/g, (full, prefix: string, numStr: string) => {
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
  })

  return {
    prompt: next,
    changed: next !== prompt,
    removedCount,
    shiftedCount,
  }
}
