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

export interface StudioProjectProgressStats {
  episodeCount: number
  plannedEpisodeCount: number
  assetCount: number
  assetImageReadyCount: number
  storyboardEpisodeCount: number
  clipCount: number
  clipVideoReadyCount: number
  composedEpisodeCount: number
}

export interface StudioProject {
  id: string
  persisted?: boolean
  loadedDetail?: boolean
  creation: DramaCreation
  episodes: Partial<Record<number, StudioEpisode>>
  assets?: StudioAsset[]
  storyboards?: Partial<Record<number, EpisodeStoryboard>>
  coverUrl?: string | null
  coverKey?: string | null
  autoCoverUrl?: string | null
  updatedAt?: string
  progressStats?: StudioProjectProgressStats
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

export interface EpisodeNavSummary {
  number: number
  title: string
  statusTone: 'composed' | 'video' | 'storyboard' | 'pending'
  statusText: string
}

export function resolveNeighborEpisodes(current: number, total: number): {
  prev: number | null
  next: number | null
} {
  if (!isEpisodeNumber(current, total)) {
    return { prev: null, next: null }
  }
  return {
    prev: current > 1 ? current - 1 : null,
    next: current < total ? current + 1 : null,
  }
}

export function buildEpisodeNavItems(project: StudioProject): EpisodeNavSummary[] {
  const total = Math.max(0, project.creation.settings.episodeCount || 0)
  const items: EpisodeNavSummary[] = []
  for (let epNum = 1; epNum <= total; epNum += 1) {
    const ep = readEpisode(project, epNum)
    const board = project.storyboards?.[epNum]
    const clipCount = board?.clips.length ?? 0
    const readyCount = board?.clips.filter((clip) => Boolean(clip.videoUrl)).length ?? 0
    const rawTitle = ep.title.trim()
    const cleanTitle = rawTitle === `第 ${epNum} 集` ? '' : rawTitle

    if (ep.composedVideoUrl) {
      items.push({ number: epNum, title: cleanTitle, statusTone: 'composed', statusText: '已合成' })
    } else if (clipCount > 0 && readyCount > 0) {
      items.push({
        number: epNum,
        title: cleanTitle,
        statusTone: 'video',
        statusText: `${readyCount}/${clipCount} 视频`,
      })
    } else if (clipCount > 0) {
      items.push({
        number: epNum,
        title: cleanTitle,
        statusTone: 'storyboard',
        statusText: `${clipCount} 段分镜`,
      })
    } else {
      items.push({ number: epNum, title: cleanTitle, statusTone: 'pending', statusText: '待拆分镜' })
    }
  }
  return items
}
