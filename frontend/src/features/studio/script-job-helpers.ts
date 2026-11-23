import type { JobOut } from './api-types.ts'

export const SCRIPT_JOB_TYPES = [
  'script_generate',
  'script_regenerate',
  'episode_rewrite',
  'episode_append',
] as const

export type ScriptJobType = (typeof SCRIPT_JOB_TYPES)[number]

export type EpisodeGenerationStatus = 'completed' | 'warning' | 'writing' | 'pending'

export interface ScriptJobSnapshot {
  jobId: string
  projectId: string
  jobType: ScriptJobType
  status: 'running' | 'failed'
  stepIndex: number
  stepTotal: number
  stepLabel: string
  progress: number
  startedAt: number
  targetEpisodeNumber?: number
  errorMessage?: string
}

export function isScriptJobType(jobType: string): jobType is ScriptJobType {
  return (SCRIPT_JOB_TYPES as readonly string[]).includes(jobType)
}

export function parseTargetEpisodeNumber(job: Pick<JobOut, 'jobType' | 'targetId' | 'stepLabel'>): number | undefined {
  if (job.jobType === 'episode_rewrite') {
    const raw = Number(job.targetId)
    if (Number.isInteger(raw) && raw > 0) return raw
    const match = /第\s*(\d+)/u.exec(job.stepLabel || '')
    if (match) {
      const parsed = Number(match[1])
      if (Number.isInteger(parsed) && parsed > 0) return parsed
    }
  }
  return undefined
}

export function parseWritingEpisodeNumber(
  job: Pick<ScriptJobSnapshot, 'jobType' | 'status' | 'stepLabel' | 'targetEpisodeNumber'> | null | undefined,
  totalEpisodes: number,
): number | null {
  if (!job || job.status !== 'running') return null

  if (job.jobType === 'episode_rewrite') {
    if (job.targetEpisodeNumber && job.targetEpisodeNumber > 0) {
      return job.targetEpisodeNumber
    }
    const match = /第\s*(\d+)/u.exec(job.stepLabel || '')
    return match ? Number(match[1]) : null
  }

  if (job.jobType === 'episode_append') {
    const match = /第\s*(\d+)/u.exec(job.stepLabel || '')
    return match ? Number(match[1]) : Math.max(1, totalEpisodes + 1)
  }

  const writingMatch = /正在(?:撰写|补写|重写)第\s*(\d+)/u.exec(job.stepLabel || '')
  if (writingMatch) {
    const parsed = Number(writingMatch[1])
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null
  }
  return null
}

export function shouldRefreshDetailOnProgress(prevLabel: string, nextLabel: string): boolean {
  const cleanNext = nextLabel.trim()
  if (!cleanNext || cleanNext === prevLabel.trim()) return false
  if (cleanNext.includes('已保存')) return true
  if (cleanNext.includes('正在撰写第') && !prevLabel.includes('已保存')) return true
  return false
}

export function resolveEpisodeGenerationStatus(params: {
  episodeNumber: number
  writingEpisodeNumber: number | null
  hasWrittenScript: boolean
  warningCount: number
}): EpisodeGenerationStatus {
  if (params.writingEpisodeNumber === params.episodeNumber) return 'writing'
  if (params.hasWrittenScript) {
    return params.warningCount > 0 ? 'warning' : 'completed'
  }
  return 'pending'
}

export function formatElapsedSeconds(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds))
  const minutes = Math.floor(safe / 60)
  const seconds = safe % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

export function scriptJobTitle(jobType: ScriptJobType, targetEpisodeNumber?: number): string {
  switch (jobType) {
    case 'episode_rewrite':
      return targetEpisodeNumber ? `正在重写第 ${targetEpisodeNumber} 集` : '正在重写单集剧本'
    case 'episode_append':
      return '正在续写新增分集'
    case 'script_regenerate':
      return '正在重生成全剧剧本'
    case 'script_generate':
    default:
      return '正在生成全剧剧本'
  }
}

export function scriptJobSuccessMessage(
  jobType: ScriptJobType,
  detailName: string,
  episodeCount: number,
  targetEpisodeNumber?: number,
): string {
  switch (jobType) {
    case 'episode_rewrite':
      return targetEpisodeNumber ? `第 ${targetEpisodeNumber} 集已重写完成` : '本集剧本已重写完成'
    case 'episode_append':
      return `第 ${episodeCount} 集已续写完成`
    case 'script_regenerate':
      return `《${detailName}》全剧 ${episodeCount} 集已重新生成`
    case 'script_generate':
    default:
      return `《${detailName}》已生成 ${episodeCount} 集剧本`
  }
}
