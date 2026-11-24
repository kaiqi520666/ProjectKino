import type { JobOut } from './api-types.ts'
import { formatElapsedSeconds } from './script-job-helpers.ts'

export { formatElapsedSeconds }

export const STORYBOARD_JOB_TYPES = ['storyboard_generate', 'episode_compose'] as const

export type StoryboardJobType = (typeof STORYBOARD_JOB_TYPES)[number]

export type EpisodeBoardJobKind = 'episode' | 'clip_regenerate' | 'clip_create' | 'compose'

export interface EpisodeStoryboardJobSnapshot {
  jobId: string
  projectId: string
  episodeNumber: number
  jobType: StoryboardJobType
  action: EpisodeBoardJobKind
  targetClipId?: string
  insertAfterClipId?: string
  completedBatches?: number
  totalBatches?: number
  segmentCount?: number
  status: 'running' | 'failed'
  stepIndex: number
  stepTotal: number
  stepLabel: string
  progress: number
  startedAt: number
  errorMessage?: string
}

export interface ParsedStoryboardJobMeta {
  episodeNumber?: number
  action: EpisodeBoardJobKind
  clipId?: string
  insertAfterClipId?: string
  completedBatches?: number
  totalBatches?: number
  segmentCount?: number
}

function parsePositiveInt(value: unknown): number | undefined {
  const num = Number(value)
  return Number.isInteger(num) && num > 0 ? num : undefined
}

function parseNonNegativeInt(value: unknown): number | undefined {
  const num = Number(value)
  return Number.isInteger(num) && num >= 0 ? num : undefined
}

export function episodeStoryboardKey(projectId: string, episodeNumber: number): string {
  return `${projectId}:ep:${episodeNumber}`
}

export function isStoryboardOrComposeJobType(jobType: string): jobType is StoryboardJobType {
  return (STORYBOARD_JOB_TYPES as readonly string[]).includes(jobType)
}

export function extractStoryboardJobMeta(
  job: Pick<JobOut, 'jobType' | 'targetId' | 'stepLabel' | 'jobMeta' | 'resultPayload'>,
): ParsedStoryboardJobMeta {
  const meta = (job.jobMeta ?? {}) as Record<string, unknown>
  const result = (job.resultPayload ?? {}) as Record<string, unknown>

  const action: EpisodeBoardJobKind =
    job.jobType === 'episode_compose'
      ? 'compose'
      : meta.action === 'clip_regenerate' || meta.action === 'clip_create' || meta.action === 'episode'
        ? meta.action
        : 'episode'

  let episodeNumber =
    parsePositiveInt(meta.episodeNumber) ?? parsePositiveInt(result.episodeNumber)

  if (!episodeNumber && job.jobType === 'storyboard_generate' && action !== 'clip_regenerate') {
    episodeNumber = parsePositiveInt(job.targetId)
  }

  if (!episodeNumber && Array.isArray(result.episodes) && result.episodes.length === 1) {
    episodeNumber = parsePositiveInt(result.episodes[0])
  }

  if (!episodeNumber) {
    const match = /第\s*(\d+)\s*集/u.exec(job.stepLabel || '')
    if (match) {
      episodeNumber = parsePositiveInt(match[1])
    }
  }

  const clipId =
    typeof meta.clipId === 'string' && meta.clipId
      ? meta.clipId
      : typeof result.clipId === 'string' && result.clipId
        ? result.clipId
        : action === 'clip_regenerate' && job.targetId
          ? job.targetId
          : undefined

  const insertAfterClipId =
    typeof meta.insertAfterClipId === 'string' && meta.insertAfterClipId
      ? meta.insertAfterClipId
      : undefined

  return {
    episodeNumber,
    action,
    clipId,
    insertAfterClipId,
    completedBatches: parseNonNegativeInt(meta.completedBatches),
    totalBatches: parsePositiveInt(meta.totalBatches),
    segmentCount: parseNonNegativeInt(meta.segmentCount),
  }
}

export function shouldRefreshStoryboardOnProgress(
  prevLabel: string,
  nextLabel: string,
  prevCompletedBatches?: number,
  nextCompletedBatches?: number,
): boolean {
  if (
    nextCompletedBatches !== undefined &&
    nextCompletedBatches > (prevCompletedBatches ?? 0)
  ) {
    return true
  }
  const cleanNext = nextLabel.trim()
  if (!cleanNext || cleanNext === prevLabel.trim()) return false
  return cleanNext.includes('已落库')
}

export interface StoryboardOverviewBadge {
  tone: 'pending' | 'running' | 'failed' | 'done'
  complete: boolean
  label: string
  detail: string
}

export function resolveStoryboardOverviewBadge(params: {
  hasPersistedStoryboard: boolean
  clipCount: number
  job?: EpisodeStoryboardJobSnapshot | null
  isComposingFallback?: boolean
}): StoryboardOverviewBadge {
  const { hasPersistedStoryboard, clipCount, job, isComposingFallback } = params

  if (job?.status === 'running') {
    const detail =
      job.action === 'episode' && job.totalBatches
        ? `已完成 ${job.completedBatches ?? 0}/${job.totalBatches} 批 · ${job.progress}%`
        : job.jobType === 'episode_compose'
          ? `合成进度 ${job.progress}%`
          : job.action === 'clip_create'
            ? 'AI 新增片段中'
            : job.action === 'clip_regenerate'
              ? '重生成片段中'
              : `${job.progress}%`
    return {
      tone: 'running',
      complete: false,
      label: job.jobType === 'episode_compose' ? '合成视频中' : '拆分镜中',
      detail,
    }
  }

  if (isComposingFallback) {
    return {
      tone: 'running',
      complete: false,
      label: '合成视频中',
      detail: '后台正在合成成片视频…',
    }
  }

  if (job?.status === 'failed') {
    return {
      tone: 'failed',
      complete: false,
      label: job.jobType === 'episode_compose' ? '合成失败' : '拆镜失败',
      detail: job.errorMessage || job.stepLabel || '任务执行失败，请进入分集查看详情',
    }
  }

  if (hasPersistedStoryboard && clipCount > 0) {
    return {
      tone: 'done',
      complete: true,
      label: `已拆 · ${clipCount} 段`,
      detail: `共 ${clipCount} 个分镜片段，点击继续编辑提示词与生视频`,
    }
  }

  return {
    tone: 'pending',
    complete: false,
    label: '待拆分镜',
    detail: '尚未生成分镜片段，点击进入拆镜',
  }
}

export interface StoryboardLockState {
  isAnyJobRunning: boolean
  isEpisodeSplitRunning: boolean
  isClipCreateRunning: boolean
  isClipRegenRunning: boolean
  isComposeRunning: boolean
  regeneratingClipId?: string
  episodeActionsLocked: boolean
  structureLocked: boolean
  isClipLocked: (clipBackendId?: string) => boolean
}

export function computeStoryboardLocks(params: {
  episodeNumber: number
  job?: EpisodeStoryboardJobSnapshot | null
  clipGenerating?: boolean
  syncing?: boolean
  reordering?: boolean
}): StoryboardLockState {
  const running =
    params.job?.status === 'running' && params.job.episodeNumber === params.episodeNumber
      ? params.job
      : undefined

  const isEpisodeSplitRunning = running?.action === 'episode'
  const isClipCreateRunning = running?.action === 'clip_create'
  const isClipRegenRunning = running?.action === 'clip_regenerate'
  const isComposeRunning = running?.action === 'compose'
  const isAnyJobRunning = Boolean(running)
  const regeneratingClipId = isClipRegenRunning ? running?.targetClipId : undefined

  const episodeActionsLocked = Boolean(
    isAnyJobRunning || params.clipGenerating || params.syncing,
  )
  const structureLocked = Boolean(
    isAnyJobRunning || params.clipGenerating || params.syncing || params.reordering,
  )

  return {
    isAnyJobRunning,
    isEpisodeSplitRunning,
    isClipCreateRunning,
    isClipRegenRunning,
    isComposeRunning,
    regeneratingClipId,
    episodeActionsLocked,
    structureLocked,
    isClipLocked: (clipBackendId?: string) => {
      if (isEpisodeSplitRunning || isClipCreateRunning || isComposeRunning) return true
      if (params.clipGenerating || params.syncing) return true
      if (regeneratingClipId && clipBackendId === regeneratingClipId) return true
      return false
    },
  }
}
