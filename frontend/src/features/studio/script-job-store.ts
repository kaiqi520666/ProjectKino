import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { apiErrorMessage, getProjectDetail, listProjects, watchJob } from './api'
import type { JobOut, ProjectDetailOut } from './api-types'
import {
  isScriptJobType,
  parseTargetEpisodeNumber,
  scriptJobSuccessMessage,
  shouldRefreshDetailOnProgress,
  type ScriptJobSnapshot,
} from './script-job-helpers'
import { useStudioStore } from './studio-store'

export interface TrackScriptJobOptions {
  targetEpisodeNumber?: number
  onCompleted?: (detail: ProjectDetailOut) => void | Promise<void>
}

function resolveStartedAt(job: JobOut): number {
  const raw = job.startedAt || job.createdAt
  const parsed = raw ? Date.parse(raw) : Number.NaN
  return Number.isFinite(parsed) ? parsed : Date.now()
}

export const useScriptJobStore = defineStore('script-jobs', () => {
  const jobsByProject = ref<Record<string, ScriptJobSnapshot>>({})
  const watchingJobIds = new Set<string>()
  const completionHandlers = new Map<string, Array<(detail: ProjectDetailOut) => void | Promise<void>>>()

  function getJob(projectId: string): ScriptJobSnapshot | undefined {
    return jobsByProject.value[projectId]
  }

  function isRunning(projectId: string): boolean {
    return jobsByProject.value[projectId]?.status === 'running'
  }

  function dismiss(projectId: string) {
    const current = jobsByProject.value[projectId]
    if (!current || current.status === 'running') return
    const next = { ...jobsByProject.value }
    delete next[projectId]
    jobsByProject.value = next
  }

  function clearProject(projectId: string) {
    if (!jobsByProject.value[projectId]) return
    const next = { ...jobsByProject.value }
    delete next[projectId]
    jobsByProject.value = next
  }

  function trackScriptJob(projectId: string, job: JobOut, options: TrackScriptJobOptions = {}) {
    if (!isScriptJobType(job.jobType)) return
    const jobType = job.jobType

    if (options.onCompleted) {
      const list = completionHandlers.get(job.id) ?? []
      list.push(options.onCompleted)
      completionHandlers.set(job.id, list)
    }

    const targetEpisodeNumber = options.targetEpisodeNumber ?? parseTargetEpisodeNumber(job)
    const existing = jobsByProject.value[projectId]
    if (watchingJobIds.has(job.id) && existing?.jobId === job.id) {
      return
    }

    watchingJobIds.add(job.id)
    const snapshot: ScriptJobSnapshot = {
      jobId: job.id,
      projectId,
      jobType,
      status: 'running',
      stepIndex: job.stepIndex,
      stepTotal: job.stepTotal,
      stepLabel: job.stepLabel || '正在排队等待后台开始生成',
      progress: Math.max(0, Math.min(100, job.progress || 0)),
      startedAt: resolveStartedAt(job),
      ...(targetEpisodeNumber ? { targetEpisodeNumber } : {}),
    }
    jobsByProject.value = { ...jobsByProject.value, [projectId]: snapshot }

    const studio = useStudioStore()
    const auth = useAuthStore()
    const ui = useUiStore()

    let refreshInFlight = false
    let refreshPending = false
    let lastLabel = snapshot.stepLabel

    const scheduleDetailRefresh = () => {
      if (refreshInFlight) {
        refreshPending = true
        return
      }
      refreshInFlight = true
      void getProjectDetail(projectId)
        .then((detail) => {
          studio.hydrateProjectDetail(detail)
        })
        .catch(() => {
          // 忽略中间态刷新波动，下一次进度推送或终态会重新同步。
        })
        .finally(() => {
          refreshInFlight = false
          if (refreshPending) {
            refreshPending = false
            scheduleDetailRefresh()
          }
        })
    }

    void watchJob(job.id, (updated) => {
      const current = jobsByProject.value[projectId]
      if (!current || current.jobId !== job.id) return

      const nextLabel = updated.stepLabel || current.stepLabel
      const shouldRefresh = shouldRefreshDetailOnProgress(lastLabel, nextLabel)
      lastLabel = nextLabel

      jobsByProject.value = {
        ...jobsByProject.value,
        [projectId]: {
          ...current,
          status: 'running',
          stepIndex: updated.stepIndex,
          stepTotal: updated.stepTotal,
          stepLabel: nextLabel,
          progress: Math.max(current.progress, Math.min(99, updated.progress || 0)),
          ...(current.targetEpisodeNumber ? { targetEpisodeNumber: current.targetEpisodeNumber } : {}),
        },
      }

      if (shouldRefresh) {
        scheduleDetailRefresh()
      }
    })
      .then(async () => {
        const detail = await getProjectDetail(projectId)
        studio.hydrateProjectDetail(detail)

        if (jobsByProject.value[projectId]?.jobId === job.id) {
          const next = { ...jobsByProject.value }
          delete next[projectId]
          jobsByProject.value = next
        }

        const handlers = completionHandlers.get(job.id) ?? []
        completionHandlers.delete(job.id)
        for (const handler of handlers) {
          await handler(detail)
        }

        ui.notify(
          scriptJobSuccessMessage(jobType, detail.name, detail.episodes.length, targetEpisodeNumber),
          'success',
        )
      })
      .catch(async (error: unknown) => {
        completionHandlers.delete(job.id)
        // 失败时仍拉取一次最新详情，把中断前已落库的大纲和前 k 集立即呈现给用户。
        try {
          const detail = await getProjectDetail(projectId)
          studio.hydrateProjectDetail(detail)
        } catch {
          // 忽略拉取异常，保留错误提示。
        }

        const message = apiErrorMessage(error)
        const current = jobsByProject.value[projectId]
        if (!current || current.jobId === job.id) {
          jobsByProject.value = {
            ...jobsByProject.value,
            [projectId]: {
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
        void listProjects().then((summaries) => studio.syncProjectSummaries(summaries)).catch(() => {})
      })
  }

  return {
    jobsByProject,
    getJob,
    isRunning,
    dismiss,
    clearProject,
    trackScriptJob,
  }
})
