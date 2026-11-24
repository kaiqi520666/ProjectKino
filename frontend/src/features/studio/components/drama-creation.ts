import type { ImageAspectRatio } from '../../../components/ui/image-types'
import { artStyles, defaultArtStyle } from './art-styles.ts'

export const videoRatios: readonly ImageAspectRatio[] = ['16:9', '9:16', '1:1', '4:3', '3:4']
export const segmentDurations = [15, 30] as const
export type SegmentDuration = typeof segmentDurations[number]
export const defaultSegmentDuration: SegmentDuration = 15
export const episodeDurationPresets = [120, 180, 300, 480, 600] as const
export const minEpisodeDuration = 120
export const maxEpisodeDuration = 600
export const defaultEpisodeDuration = 120
export const maxInitialTotalSeconds = 3600
export const maxScriptUploadMb = 2
export const contentLanguages = [
  { value: 'zh-CN', label: '简体中文' },
  { value: 'zh-TW', label: '繁體中文' },
  { value: 'en', label: 'English' },
]
export type DramaImageTier = 'web' | '1k' | '2k' | '4k'

export interface DramaSettings {
  name: string
  ratio: ImageAspectRatio
  language: string
  visualStyle: string
  episodeCount: number
  maxSegmentDuration: SegmentDuration
  secondsPerEpisode?: number
  backgroundMusic: boolean
  imageModelId?: string
  imageTier?: DramaImageTier
  videoModelId?: string
}

export type DramaCreation =
  | { mode: 'story'; settings: DramaSettings; story: string }
  | { mode: 'upload'; settings: DramaSettings; file: File }

type DramaSettingsDraft = Omit<DramaSettings, 'episodeCount' | 'secondsPerEpisode'> & {
  episodeCount: number | ''
  secondsPerEpisode: number | ''
}

export function maxEpisodesForDuration(secondsPerEpisode: number | ''): number {
  if (
    typeof secondsPerEpisode !== 'number' ||
    !Number.isFinite(secondsPerEpisode) ||
    secondsPerEpisode < minEpisodeDuration
  ) {
    return Math.floor(maxInitialTotalSeconds / minEpisodeDuration)
  }
  const clamped = Math.min(maxEpisodeDuration, Math.round(secondsPerEpisode))
  return Math.max(1, Math.floor(maxInitialTotalSeconds / clamped))
}

export function formatDurationLabel(seconds: number): string {
  const safe = Math.max(0, Math.round(seconds))
  const mins = Math.floor(safe / 60)
  const rem = safe % 60
  if (mins === 0) return `${rem} 秒`
  if (rem === 0) return `${mins} 分钟`
  return `${mins} 分 ${rem} 秒`
}

export function initialDramaSettings(): DramaSettingsDraft {
  return {
    name: '',
    ratio: '16:9',
    language: 'zh-CN',
    visualStyle: defaultArtStyle,
    episodeCount: 5,
    maxSegmentDuration: defaultSegmentDuration,
    secondsPerEpisode: defaultEpisodeDuration,
    backgroundMusic: true,
    imageModelId: undefined,
    imageTier: '1k',
    videoModelId: undefined,
  }
}

export function resolveDramaSettings(draft: DramaSettingsDraft): DramaSettings | null {
  const name = draft.name.trim()
  const { episodeCount, secondsPerEpisode } = draft
  if (
    !name ||
    !videoRatios.includes(draft.ratio) ||
    !contentLanguages.some(({ value }) => value === draft.language) ||
    !artStyles.some(({ value }) => value === draft.visualStyle) ||
    !segmentDurations.includes(draft.maxSegmentDuration) ||
    typeof draft.backgroundMusic !== 'boolean' ||
    typeof episodeCount !== 'number' ||
    !Number.isSafeInteger(episodeCount) ||
    episodeCount < 1 ||
    typeof secondsPerEpisode !== 'number' ||
    !Number.isSafeInteger(secondsPerEpisode) ||
    secondsPerEpisode < minEpisodeDuration ||
    secondsPerEpisode > maxEpisodeDuration ||
    episodeCount * secondsPerEpisode > maxInitialTotalSeconds
  ) {
    return null
  }
  return { ...draft, name, episodeCount, secondsPerEpisode }
}
