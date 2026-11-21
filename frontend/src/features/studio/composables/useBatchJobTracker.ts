import { computed, onUnmounted, ref, watch, type Ref } from 'vue'
import type { JobOut, ProjectDetailOut } from '../api-types'

export interface BatchTrackerState<TMeta> {
  meta: TMeta
  jobToTarget: Record<string, string>
  succeededIds: string[]
  failedById: Record<string, string>
  dismissed: boolean
}

export interface BatchSummaryView<TMeta> {
  visible: boolean
  total: number
  succeeded: number
  failed: number
  failedIds: string[]
  running: number
  percent: number
  finished: boolean
  meta: TMeta | null
}

export interface TrackableJobRef {
  id: string
  targetId?: string | null
}

/** 纯函数：将新提交的一批任务合并（若当前同作用域批次仍在运行）或开启新批次。 */
export function mergeTrackedJobs<TMeta>(
  existing: BatchTrackerState<TMeta> | null,
  jobs: TrackableJobRef[],
  meta: TMeta,
  shouldMerge: boolean,
  checkedTerminals: Set<string>,
): BatchTrackerState<TMeta> {
  const tracker: BatchTrackerState<TMeta> = shouldMerge && existing
    ? {
        meta,
        jobToTarget: { ...existing.jobToTarget },
        succeededIds: [...existing.succeededIds],
        failedById: { ...existing.failedById },
        dismissed: false,
      }
    : {
        meta,
        jobToTarget: {},
        succeededIds: [],
        failedById: {},
        dismissed: false,
      }

  for (const job of jobs) {
    if (!job.targetId) continue
    tracker.jobToTarget[job.id] = job.targetId
    checkedTerminals.delete(job.id)
    delete tracker.failedById[job.targetId]
    tracker.succeededIds = tracker.succeededIds.filter((id) => id !== job.targetId)
  }
  return tracker
}

/** 纯函数：根据单个终态 Job 结果收敛批次统计。返回是否已进入终态。 */
export function applyTerminalJobStatus<TMeta>(
  tracker: BatchTrackerState<TMeta>,
  jobId: string,
  status: string,
  errorMessage: string | null | undefined,
  fallbackError: string,
): boolean {
  const targetId = tracker.jobToTarget[jobId]
  if (!targetId) return true
  if (status === 'succeeded') {
    if (!tracker.succeededIds.includes(targetId)) tracker.succeededIds.push(targetId)
    delete tracker.failedById[targetId]
    return true
  }
  if (status === 'failed' || status === 'review') {
    tracker.failedById[targetId] = errorMessage || fallbackError
    return true
  }
  return false
}

/** 纯函数：计算批次进度条摘要（兼顾页面刷新后从后端 activeCount 恢复展示）。 */
export function computeBatchSummary<TMeta>(
  tracker: BatchTrackerState<TMeta> | null,
  activeCount: number,
  inScope: boolean,
): BatchSummaryView<TMeta> | null {
  if (tracker && inScope && !tracker.dismissed) {
    const total = Object.keys(tracker.jobToTarget).length
    const succeeded = tracker.succeededIds.length
    const failedIds = Object.keys(tracker.failedById)
    const failed = failedIds.length
    const running = Math.max(0, total - succeeded - failed)
    const done = succeeded + failed
    const percent = total > 0 ? Math.round((done / total) * 100) : 0
    return {
      visible: true,
      total,
      succeeded,
      failed,
      failedIds,
      running,
      percent,
      finished: running === 0 && activeCount === 0,
      meta: tracker.meta,
    }
  }
  if (activeCount > 0) {
    return {
      visible: true,
      total: activeCount,
      succeeded: 0,
      failed: 0,
      failedIds: [],
      running: activeCount,
      percent: 15,
      finished: false,
      meta: null,
    }
  }
  return null
}

export interface UseBatchJobTrackerOptions<TMeta> {
  jobType: 'asset_image' | 'clip_video'
  pollIntervalMs: number
  fallbackErrorMessage: string
  canPoll: () => boolean
  activeCount: Ref<number>
  hasActiveJobs: Ref<boolean>
  isInScope?: (meta: TMeta) => boolean
  fetchProjectDetail: () => Promise<ProjectDetailOut>
  fetchJob: (jobId: string) => Promise<JobOut>
  onDetail: (detail: ProjectDetailOut) => void
  isStillRunning: (detail: ProjectDetailOut) => boolean
  onBatchComplete?: (result: { okCount: number; failCount: number; meta: TMeta }) => void
}

export function useBatchJobTracker<TMeta>(options: UseBatchJobTrackerOptions<TMeta>) {
  const tracker = ref<BatchTrackerState<TMeta> | null>(null) as Ref<BatchTrackerState<TMeta> | null>
  const checkedJobTerminals = new Set<string>()
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let pollingInFlight = false

  const inScope = (meta: TMeta) => (options.isInScope ? options.isInScope(meta) : true)

  const summary = computed<BatchSummaryView<TMeta> | null>(() => {
    const current = tracker.value
    return computeBatchSummary(
      current,
      options.activeCount.value,
      current ? inScope(current.meta) : true,
    )
  })

  function stopPolling() {
    if (pollTimer !== null) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function startPolling() {
    if (pollTimer !== null || !options.canPoll()) return
    pollTimer = setInterval(() => {
      void pollProgress()
    }, options.pollIntervalMs)
  }

  async function pollProgress() {
    if (pollingInFlight || !options.canPoll()) return
    pollingInFlight = true
    try {
      const detail = await options.fetchProjectDetail()
      options.onDetail(detail)

      const activeIds = new Set(
        (detail.activeJobs ?? [])
          .filter((j) => j.jobType === options.jobType)
          .map((j) => j.id),
      )

      const current = tracker.value
      if (current) {
        const newlyFinished = Object.keys(current.jobToTarget).filter(
          (jid) => !activeIds.has(jid) && !checkedJobTerminals.has(jid),
        )
        for (const jid of newlyFinished) {
          checkedJobTerminals.add(jid)
          try {
            const job = await options.fetchJob(jid)
            const terminal = applyTerminalJobStatus(
              current,
              jid,
              job.status,
              job.errorMessage,
              options.fallbackErrorMessage,
            )
            if (!terminal) checkedJobTerminals.delete(jid)
          } catch {
            checkedJobTerminals.delete(jid)
          }
        }
      }

      if (!options.isStillRunning(detail)) {
        stopPolling()
        if (current && inScope(current.meta) && !current.dismissed) {
          const okCount = current.succeededIds.length
          const failCount = Object.keys(current.failedById).length
          if (okCount > 0 || failCount > 0) {
            options.onBatchComplete?.({ okCount, failCount, meta: current.meta })
          }
        }
      }
    } catch {
      // 忽略单次轮询网络波动，下个周期重试。
    } finally {
      pollingInFlight = false
    }
  }

  function trackJobs(jobs: TrackableJobRef[], meta: TMeta) {
    const existing = tracker.value
    const shouldMerge =
      !!existing
      && inScope(existing.meta)
      && !existing.dismissed
      && !!summary.value
      && !summary.value.finished
    tracker.value = mergeTrackedJobs(existing, jobs, meta, shouldMerge, checkedJobTerminals)
  }

  function failedReason(targetId?: string | null): string {
    if (!targetId) return ''
    return tracker.value?.failedById[targetId] ?? ''
  }

  function dismiss() {
    if (tracker.value) tracker.value.dismissed = true
  }

  watch(
    options.hasActiveJobs,
    (active) => {
      if (active) startPolling()
      else if (!summary.value || summary.value.finished) stopPolling()
    },
    { immediate: true },
  )

  onUnmounted(stopPolling)

  return {
    tracker,
    summary,
    trackJobs,
    startPolling,
    stopPolling,
    pollProgress,
    failedReason,
    dismiss,
  }
}
