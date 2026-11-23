import { ref } from 'vue'
import { defineStore } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { apiErrorMessage, getProjectDetail, watchJob } from './api'
import type { JobOut, ProjectDetailOut } from './api-types'
import { useStudioStore } from './studio-store'

export type AssetExtractMode = 'full' | 'incremental'

export interface AssetExtractJobSnapshot {
  jobId: string
  projectId: string
  mode: AssetExtractMode
  status: 'running' | 'failed'
  stepIndex: number
  stepTotal: number
  stepLabel: string
  progress: number
  startedAt: number
  errorMessage?: string
}

export interface TrackAssetExtractOptions {
  mode?: AssetExtractMode
  onCompleted?: (detail: ProjectDetailOut) => void | Promise<void>
}

function resolveStartedAt(job: JobOut): number {
  const raw = job.startedAt || job.createdAt
  const parsed = raw ? Date.parse(raw) : Number.NaN
  return Number.isFinite(parsed) ? parsed : Date.now()
}

export function shouldRefreshAssetsOnProgress(prevLabel: string, nextLabel: string): boolean {
  const cleanNext = nextLabel.trim()
  if (!cleanNext || cleanNext === prevLabel.trim()) return false
  return cleanNext.includes('已保存')
}

export const useAssetExtractStore = defineStore('asset-extract-jobs', () => {
  const jobsByProject = ref<Record<string, AssetExtractJobSnapshot>>({})
  const watchingJobIds = new Set<string>()
  const completionHandlers = new Map<string, Array<(detail: ProjectDetailOut) => void | Promise<void>>>()

  function getJob(projectId: string): AssetExtractJobSnapshot | undefined {
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

  function trackExtractJob(projectId: string, job: JobOut, options: TrackAssetExtractOptions = {}) {
    if (job.jobType !== 'assets_extract') return

    if (options.onCompleted) {
      const list = completionHandlers.get(job.id) ?? []
      list.push(options.onCompleted)
      completionHandlers.set(job.id, list)
    }

    const mode: AssetExtractMode = options.mode ?? 'full'
    const existing = jobsByProject.value[projectId]
    if (watchingJobIds.has(job.id) && existing?.jobId === job.id) {
      return
    }

    watchingJobIds.add(job.id)
    const snapshot: AssetExtractJobSnapshot = {
      jobId: job.id,
      projectId,
      mode,
      status: 'running',
      stepIndex: job.stepIndex,
      stepTotal: job.stepTotal,
      stepLabel: job.stepLabel || '正在排队等待后台识别角色、场景与道具',
      progress: Math.max(0, Math.min(100, job.progress || 0)),
      startedAt: resolveStartedAt(job),
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
      const shouldRefresh = shouldRefreshAssetsOnProgress(lastLabel, nextLabel)
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
          mode === 'incremental'
            ? `已完成增量资产补充，当前共 ${detail.assets.length} 项资产`
            : `已识别并生成 ${detail.assets.length} 项项目资产`,
          'success',
        )
      })
      .catch(async (error: unknown) => {
        completionHandlers.delete(job.id)
        try {
          const detail = await getProjectDetail(projectId)
          studio.hydrateProjectDetail(detail)
        } catch {
          // 保留错误提示。
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
      })
  }

  return {
    jobsByProject,
    getJob,
    isRunning,
    dismiss,
    trackExtractJob,
  }
})
