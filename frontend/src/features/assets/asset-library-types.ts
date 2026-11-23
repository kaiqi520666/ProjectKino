import type { UserAssetOut } from '@/features/canvas/api'
import type { StudioAsset } from '@/features/studio/studio-assets'

export type AssetMediaKind = 'image' | 'video' | 'audio' | 'text'
export type UploadableMediaKind = 'image' | 'video' | 'audio'
export type AssetLibrarySource = 'project' | 'personal'
export type AssetLibraryMode = 'single' | 'multiple' | 'manage'

export interface AssetLibraryItem {
  id: string
  key: string
  source: AssetLibrarySource
  kind: AssetMediaKind
  title: string
  mediaUrl?: string
  mediaKey?: string
  mediaName?: string
  text?: string
  tag?: string
  projectAsset?: StudioAsset
  userAsset?: UserAssetOut
  createdAt?: string
}

const IMAGE_EXTS = new Set(['jpg', 'jpeg', 'png', 'webp', 'gif', 'avif', 'bmp'])
const VIDEO_EXTS = new Set(['mp4', 'mov', 'webm', 'mkv', 'm4v'])
const AUDIO_EXTS = new Set(['mp3', 'wav', 'm4a', 'aac', 'ogg', 'flac'])

export function detectFileMediaKind(file: File): UploadableMediaKind | null {
  const mime = (file.type || '').toLowerCase()
  if (mime.startsWith('image/')) return 'image'
  if (mime.startsWith('video/')) return 'video'
  if (mime.startsWith('audio/')) return 'audio'

  const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
  if (IMAGE_EXTS.has(ext)) return 'image'
  if (VIDEO_EXTS.has(ext)) return 'video'
  if (AUDIO_EXTS.has(ext)) return 'audio'
  return null
}

export function buildAcceptAttribute(kinds: readonly AssetMediaKind[]): string {
  const tokens: string[] = []
  if (kinds.includes('image')) tokens.push('image/*')
  if (kinds.includes('video')) tokens.push('video/*')
  if (kinds.includes('audio')) tokens.push('audio/*')
  return tokens.join(',')
}

export function stripFileExtension(filename: string): string {
  const trimmed = filename.trim()
  if (!trimmed) return '未命名素材'
  const lastDot = trimmed.lastIndexOf('.')
  if (lastDot <= 0) return trimmed
  return trimmed.slice(0, lastDot).trim() || trimmed
}

export function isHttpMediaUrl(url?: string | null): url is string {
  return typeof url === 'string' && /^https?:\/\//i.test(url.trim())
}
