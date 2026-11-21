import type { ImageAspectRatio } from '../../../components/ui/image-types'
import { artStyles, defaultArtStyle } from './art-styles.ts'

export const videoRatios: readonly ImageAspectRatio[] = ['16:9', '9:16', '1:1', '4:3', '3:4']
export const segmentDurations = [15, 30] as const
export type SegmentDuration = typeof segmentDurations[number]
export const defaultSegmentDuration: SegmentDuration = 15
export const contentLanguages = [
  { value: 'zh-CN', label: '简体中文' },
  { value: 'zh-TW', label: '繁體中文' },
  { value: 'en', label: 'English' },
]
export interface DramaSettings {
  name: string
  ratio: ImageAspectRatio
  language: string
  visualStyle: string
  episodeCount: number
  maxSegmentDuration: SegmentDuration
  backgroundMusic: boolean
}

export type DramaCreation =
  | { mode: 'story'; settings: DramaSettings; story: string }
  | { mode: 'upload'; settings: DramaSettings; file: File }

type DramaSettingsDraft = Omit<DramaSettings, 'episodeCount'> & { episodeCount: number | '' }

export function initialDramaSettings(): DramaSettingsDraft {
  return {
    name: '', ratio: '16:9', language: 'zh-CN', visualStyle: defaultArtStyle,
    episodeCount: 5, maxSegmentDuration: defaultSegmentDuration, backgroundMusic: true,
  }
}

export function resolveDramaSettings(draft: DramaSettingsDraft): DramaSettings | null {
  const name = draft.name.trim()
  const { episodeCount } = draft
  if (!name || !videoRatios.includes(draft.ratio) ||
      !contentLanguages.some(({ value }) => value === draft.language) ||
      !artStyles.some(({ value }) => value === draft.visualStyle) ||
      !segmentDurations.includes(draft.maxSegmentDuration) ||
      typeof draft.backgroundMusic !== 'boolean' ||
      typeof episodeCount !== 'number' || !Number.isSafeInteger(episodeCount) || episodeCount < 1) {
    return null
  }
  return { ...draft, name, episodeCount }
}
