import type { AssetResult, JobOut, ScriptResult } from './api-types'
import type { DramaCreation } from './components/drama-creation.ts'
import type { StudioAsset } from './studio-assets.ts'
import type { EpisodeStoryboard } from './studio-storyboard.ts'

export interface StudioEpisode {
  number: number
  title: string
  summary: string
  script: string
  example?: boolean
  composedVideoUrl?: string
  composedDuration?: number
}

export interface StudioProject {
  id: string
  persisted?: boolean
  loadedDetail?: boolean
  creation: DramaCreation
  episodes: Partial<Record<number, StudioEpisode>>
  assets?: StudioAsset[]
  storyboards?: Partial<Record<number, EpisodeStoryboard>>
  scriptConfirmed: boolean
  scriptResult?: ScriptResult
  assetResult?: AssetResult
  sourceText?: string
  scriptEdited?: boolean
  activeJobs?: JobOut[]
}

export function isEpisodeNumber(number: number, total: number) {
  return Number.isSafeInteger(number) && number >= 1 && number <= total
}

export function readEpisode(project: StudioProject, number: number): StudioEpisode {
  return project.episodes[number] ?? { number, title: `第 ${number} 集`, summary: '', script: '' }
}

export function episodeLabel({ number, title }: StudioEpisode) {
  const label = `第 ${number} 集`
  const name = title.trim()
  return !name || name === label ? label : `${label} · ${name}`
}

export const episodePageSize = 12

export function episodePage(total: number, page: number) {
  const offset = (page - 1) * episodePageSize
  return Array.from({ length: Math.max(0, Math.min(episodePageSize, total - offset)) }, (_, index) => offset + index + 1)
}
