import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { apiErrorMessage, getProjectDetail, watchJob } from './api'
import type { JobOut, ProjectDetailOut } from './api-types'
import {
  episodeStoryboardKey,
  extractStoryboardJobMeta,
  isStoryboardOrComposeJobType,
  shouldRefreshStoryboardOnProgress,
  type EpisodeStoryboardJobSnapshot,
} from './storyboard-job-helpers'
import { useStudioStore } from './studio-store'

export type { EpisodeStoryboardJobSnapshot } from './storyboard-job-helpers'

export interface TrackStoryboardJobOptions {
  episodeNumber?: number
  onCompleted?: (detail: ProjectDetailOut, finalJob: JobOut) => void | Promise<void>
}

interface CoalescedRefreshState {
  inFlight: boolean
  pending: boolean
}

function resolveStartedAt(job: JobOut): number {
  const raw = job.startedAt || job.createdAt
  const parsed = raw ? Date.parse(raw) : Number.NaN
  return Number.isFinite(parsed) ? parsed : Date.now()
}

export const useStoryboardJobStore = defineStore('storyboard-jobs', () => {
  const jobsByKey = ref<Record<string, EpisodeStoryboardJobSnapshot>>({})
  const watchingJobIds = new Set<string>()
  const completionHandlers = new Map<
    string,
    Array<(detail: ProjectDetailOut, finalJob: JobOut) => void | Promise<void>>
  >()
  const projectRefreshMap = new Map<string, CoalescedRefreshState>()

  function getEpisodeJob(
    projectId: string,
    episodeNumber: number,
  ): EpisodeStoryboardJobSnapshot | undefined {
    return jobsByKey.value[episodeStoryboardKey(projectId, episodeNumber)]
  }

  function isEpisodeRunning(projectId: string, episodeNumber: number): boolean {
    return getEpisodeJob(projectId, episodeNumber)?.status === 'running'
  }

  function dismissEpisodeJob(projectId: string, episodeNumber: number) {
    const key = episodeStoryboardKey(projectId, episodeNumber)
    const current = jobsByKey.value[key]
    if (!current || current.status === 'running') return
    const next = { ...jobsByKey.value }
    delete next[key]
    jobsByKey.value = next
  }

  function scheduleDetailRefresh(projectId: string) {
    const studio = useStudioStore()
    let state = projectRefreshMap.get(projectId)
    if (!state) {
      state = { inFlight: false, pending: false }
      projectRefreshMap.set(projectId, state)
    }
    if (state.inFlight) {
      state.pending = true
      return
    }
    state.inFlight = true
    void getProjectDetail(projectId)
      .then((detail) => {
        studio.hydrateProjectDetail(detail)
      })
      .catch(() => {
        // 忽略中间态轮询波动，后续批次或终态刷新会重新对齐。
      })
      .finally(() => {
        const latest = projectRefreshMap.get(projectId)
        if (!latest) return
        latest.inFlight = false
        if (latest.pending) {
          latest.pending = false
          scheduleDetailRefresh(projectId)
        }
      })
  }

  function resolveEpisodeNumberForDetail(detail: ProjectDetailOut, job: JobOut): number | undefined {
    const parsed = extractStoryboardJobMeta(job)
    if (parsed.episodeNumber) return parsed.episodeNumber
    if (parsed.clipId) {
      for (const [epKey, clips] of Object.entries(detail.storyboards ?? {})) {
        if (clips.some((clip) => clip.id === parsed.clipId)) {
          const epNumber = Number(epKey)
          if (Number.isInteger(epNumber) && epNumber > 0) return epNumber
        }
      }
    }
    if (job.jobType === 'episode_compose' && job.targetId) {
      const ep = detail.episodes.find((item) => item.id === job.targetId)
      if (ep) return ep.number
    }
    return undefined
  }

  function trackFromProjectDetail(detail: ProjectDetailOut) {
    const activeByKey = new Map<string, JobOut>()
    for (const activeJob of detail.activeJobs ?? []) {
      if (!isStoryboardOrComposeJobType(activeJob.jobType)) continue
      const epNum = resolveEpisodeNumberForDetail(detail, activeJob)
      if (!epNum) continue
      const key = episodeStoryboardKey(detail.id, epNum)
      activeByKey.set(key, activeJob)
      trackStoryboardJob(detail.id, activeJob, { episodeNumber: epNum })
    }

    // 仅清理当前详情页中确认已结束但仍停留在 running 状态的旧快照。
    const prefix = `${detail.id}:ep:`
    let changed = false
    const next = { ...jobsByKey.value }
    for (const [key, snap] of Object.entries(next)) {
      if (!key.startsWith(prefix)) continue
      if (snap.status === 'running' && !activeByKey.has(key) && !watchingJobIds.has(snap.jobId)) {
        delete next[key]
        changed = true
      }
    }
    if (changed) {
      jobsByKey.value = next
    }
  }

  function trackStoryboardJob(
    projectId: string,
    job: JobOut,
    options: TrackStoryboardJobOptions = {},
  ) {
    if (!isStoryboardOrComposeJobType(job.jobType)) return

    const meta = extractStoryboardJobMeta(job)
    const episodeNumber = options.episodeNumber ?? meta.episodeNumber
    if (!episodeNumber) return

    if (options.onCompleted) {
      const list = completionHandlers.get(job.id) ?? []
      list.push(options.onCompleted)
      completionHandlers.set(job.id, list)
    }

    const key = episodeStoryboardKey(projectId, episodeNumber)
    const existing = jobsByKey.value[key]
    if (watchingJobIds.has(job.id) && existing?.jobId === job.id) {
      return
    }

    watchingJobIds.add(job.id)
    const defaultLabel =
      job.jobType === 'episode_compose'
        ? `第 ${episodeNumber} 集视频合成任务已排队`
        : meta.action === 'clip_regenerate'
          ? '片段分镜重生成已排队'
          : meta.action === 'clip_create'
            ? `第 ${episodeNumber} 集新增片段已排队`
            : `第 ${episodeNumber} 集分镜任务已排队`

    const snapshot: EpisodeStoryboardJobSnapshot = {
      jobId: job.id,
      projectId,
      episodeNumber,
      jobType: job.jobType,
      action: meta.action,
      targetClipId: meta.clipId,
      insertAfterClipId: meta.insertAfterClipId,
      completedBatches: meta.completedBatches,
      totalBatches: meta.totalBatches,
      segmentCount: meta.segmentCount,
      status: 'running',
      stepIndex: job.stepIndex,
      stepTotal: job.stepTotal,
      stepLabel: job.stepLabel || defaultLabel,
      progress: Math.max(0, Math.min(100, job.progress || 0)),
      startedAt: resolveStartedAt(job),
    }
    jobsByKey.value = { ...jobsByKey.value, [key]: snapshot }

    const studio = useStudioStore()
    const auth = useAuthStore()
    const ui = useUiStore()

    let lastLabel = snapshot.stepLabel
    let lastBatches = snapshot.completedBatches

    void watchJob(job.id, (updated) => {
      const current = jobsByKey.value[key]
      if (!current || current.jobId !== job.id) return

      const nextMeta = extractStoryboardJobMeta(updated)
      const nextLabel = updated.stepLabel || current.stepLabel
      const nextBatches = nextMeta.completedBatches ?? current.completedBatches
      const shouldRefresh = shouldRefreshStoryboardOnProgress(
        lastLabel,
        nextLabel,
        lastBatches,
        nextBatches,
      )
      lastLabel = nextLabel
      lastBatches = nextBatches

      jobsByKey.value = {
        ...jobsByKey.value,
        [key]: {
          ...current,
          status: 'running',
          completedBatches: nextBatches,
          totalBatches: nextMeta.totalBatches ?? current.totalBatches,
          segmentCount: nextMeta.segmentCount ?? current.segmentCount,
          targetClipId: nextMeta.clipId ?? current.targetClipId,
          stepIndex: updated.stepIndex,
          stepTotal: updated.stepTotal,
          stepLabel: nextLabel,
          progress: Math.max(current.progress, Math.min(99, updated.progress || 0)),
        },
      }

      if (shouldRefresh) {
        scheduleDetailRefresh(projectId)
      }
    })
      .then(async (finalJob) => {
        const detail = await getProjectDetail(projectId)
        studio.hydrateProjectDetail(detail)

        if (jobsByKey.value[key]?.jobId === job.id) {
          const next = { ...jobsByKey.value }
          delete next[key]
          jobsByKey.value = next
        }

        const handlers = completionHandlers.get(job.id) ?? []
        completionHandlers.delete(job.id)
        for (const handler of handlers) {
          await handler(detail, finalJob)
        }

        if (job.jobType === 'episode_compose') {
          ui.notify(`第 ${episodeNumber} 集成片已合成，可点击播放或下载`, 'success')
        } else if (meta.action === 'clip_regenerate') {
          ui.notify(`第 ${episodeNumber} 集片段分镜已更新，可继续生成视频`, 'success')
        } else if (meta.action === 'clip_create') {
          ui.notify(`第 ${episodeNumber} 集已新增 AI 片段`, 'success')
        } else {
          const clipCount = detail.storyboards?.[String(episodeNumber)]?.length ?? 0
          ui.notify(`第 ${episodeNumber} 集已拆分出 ${clipCount} 个分镜片段`, 'success')
        }
      })
      .catch(async (error: unknown) => {
        completionHandlers.delete(job.id)
        try {
          const detail = await getProjectDetail(projectId)
          studio.hydrateProjectDetail(detail)
        } catch {
          // 保留失败条提示，便于用户确认或重试。
        }

        const message = apiErrorMessage(error)
        const current = jobsByKey.value[key]
        if (!current || current.jobId === job.id) {
          jobsByKey.value = {
            ...jobsByKey.value,
            [key]: {
              ...(current ?? snapshot),
              status: 'failed',
              errorMessage: message,
            },
          }
        }
        ui.notify(message, 'error')
      })
      .finally(() => {
        watchingJobIds.delete(job.id)
        void auth.refreshBalance()
      })
  }

  return {
    jobsByKey,
    getEpisodeJob,
    isEpisodeRunning,
    dismissEpisodeJob,
    trackFromProjectDetail,
    trackStoryboardJob,
  }
})
