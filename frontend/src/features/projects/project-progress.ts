export interface ProjectProgressInput {
  scriptConfirmed: boolean
  episodeCount: number
  plannedEpisodeCount?: number
  assetCount: number
  assetImageReadyCount?: number
  storyboardEpisodeCount?: number
  clipCount?: number
  clipVideoReadyCount?: number
  composedEpisodeCount?: number
}

export type ProjectProgressTone = 'draft' | 'ready' | 'progress' | 'done'
export type ProjectTargetRoute = 'studio-script' | 'studio-assets' | 'studio-storyboard'

export interface ProjectProgressState {
  label: string
  tone: ProjectProgressTone
  targetRoute: ProjectTargetRoute
  percent: number
}

export interface ProjectCoverInput {
  coverUrl?: string | null
  autoCoverUrl?: string | null
  styleCoverUrl?: string | null
  visualStyle?: string | null
}

export function resolveProjectCoverUrl(project: ProjectCoverInput): {
  url: string
  isCustom: boolean
  isAuto: boolean
} {
  const custom = project.coverUrl?.trim()
  if (custom) {
    return { url: custom, isCustom: true, isAuto: false }
  }
  const auto = project.autoCoverUrl?.trim()
  if (auto) {
    return { url: auto, isCustom: false, isAuto: true }
  }
  const styleCover = project.styleCoverUrl?.trim() || ''
  return { url: styleCover, isCustom: false, isAuto: false }
}

export function resolveProjectProgress(input: ProjectProgressInput): ProjectProgressState {
  const epCount = Math.max(0, input.episodeCount || 0)
  const planned = Math.max(epCount, input.plannedEpisodeCount ?? epCount)
  const assetCount = Math.max(0, input.assetCount || 0)
  const assetReady = Math.max(0, Math.min(assetCount, input.assetImageReadyCount ?? 0))
  const sbEpisodes = Math.max(0, input.storyboardEpisodeCount ?? 0)
  const clipCount = Math.max(0, input.clipCount ?? 0)
  const clipReady = Math.max(0, Math.min(clipCount, input.clipVideoReadyCount ?? 0))
  const composed = Math.max(0, input.composedEpisodeCount ?? 0)

  if (!input.scriptConfirmed) {
    if (planned > 0 && epCount < planned) {
      const ratio = epCount / planned
      return {
        label: `剧本草稿 ${epCount}/${planned} 集`,
        tone: 'draft',
        targetRoute: 'studio-script',
        percent: Math.round(5 + ratio * 15),
      }
    }
    return {
      label: '剧本草稿',
      tone: 'draft',
      targetRoute: 'studio-script',
      percent: 15,
    }
  }

  if (planned > 0 && composed >= planned) {
    return {
      label: `全剧已合成 ${composed}/${planned} 集`,
      tone: 'done',
      targetRoute: 'studio-storyboard',
      percent: 100,
    }
  }

  if (composed > 0) {
    const denom = Math.max(planned, composed)
    return {
      label: `已合成 ${composed}/${denom} 集`,
      tone: 'done',
      targetRoute: 'studio-storyboard',
      percent: Math.min(98, Math.round(80 + (composed / denom) * 18)),
    }
  }

  if (clipReady > 0 && clipCount > 0) {
    return {
      label: `视频 ${clipReady}/${clipCount} 段`,
      tone: 'progress',
      targetRoute: 'studio-storyboard',
      percent: Math.round(60 + (clipReady / clipCount) * 20),
    }
  }

  if (sbEpisodes > 0) {
    const denom = Math.max(planned, sbEpisodes)
    return {
      label: `已拆分镜 ${sbEpisodes}/${denom} 集`,
      tone: 'progress',
      targetRoute: 'studio-storyboard',
      percent: Math.round(45 + (sbEpisodes / denom) * 15),
    }
  }

  if (assetCount > 0) {
    return {
      label: assetReady > 0 ? `资产出图 ${assetReady}/${assetCount}` : `已提资产 ${assetCount} 项`,
      tone: 'ready',
      targetRoute: 'studio-assets',
      percent: Math.round(25 + (assetReady / assetCount) * 20),
    }
  }

  return {
    label: '剧本已确认',
    tone: 'ready',
    targetRoute: 'studio-assets',
    percent: 25,
  }
}
