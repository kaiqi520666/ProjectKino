import { acceptHMRUpdate, defineStore } from 'pinia'
import { computed, ref } from 'vue'

export type GenerationStatus = 'running' | 'success' | 'error'

export interface GenerationTaskControls {
  setStep: (index: number, description?: string) => void
  setDescription: (description: string) => void
  setProgress: (progress: number | undefined) => void
  setJobId: (jobId: string) => void
}

export interface GenerationTaskOptions<T = unknown> {
  title: string
  subtitle?: string
  description?: string
  steps?: readonly string[]
  hint?: string
  successDelayMs?: number
  formatError?: (error: unknown) => string
  canRetryError?: (error: unknown) => boolean
  successMessage?: (result: T) => string
}

export interface GenerationTaskState {
  id: string
  jobId?: string
  status: GenerationStatus
  title: string
  subtitle?: string
  description?: string
  steps: string[]
  /** -1 indicates steps are shown as an overview list without faking exact step progress. */
  activeStep: number
  progress?: number
  hint: string
  startedAt: number
  finishedAt?: number
  error?: string
  errorHint?: string
  canRetry: boolean
}

export function formatElapsedSeconds(totalSeconds: number): string {
  const safe = Number.isFinite(totalSeconds) && totalSeconds > 0 ? Math.floor(totalSeconds) : 0
  const minutes = Math.floor(safe / 60)
  const seconds = safe % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

function clampProgress(value: number | undefined): number | undefined {
  if (value === undefined || !Number.isFinite(value)) return undefined
  return Math.min(100, Math.max(0, value))
}

function defaultErrorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim() ? error.message : '生成失败，请稍后重试'
}

export const useGenerationStore = defineStore('generation', () => {
  const task = ref<GenerationTaskState | null>(null)
  let retryHandler: (() => Promise<unknown>) | null = null
  let closeTimer: ReturnType<typeof setTimeout> | null = null

  const isOpen = computed(() => task.value !== null)
  const isRunning = computed(() => task.value?.status === 'running')

  function clearCloseTimer() {
    if (closeTimer !== null) {
      clearTimeout(closeTimer)
      closeTimer = null
    }
  }

  async function runTask<T>(
    options: GenerationTaskOptions<T>,
    executor: (controls: GenerationTaskControls) => Promise<T>,
  ): Promise<T | undefined> {
    if (task.value?.status === 'running') return undefined

    clearCloseTimer()
    const runId = crypto.randomUUID()
    const steps = [...(options.steps ?? [])]
    retryHandler = () => runTask(options, executor)

    task.value = {
      id: runId,
      status: 'running',
      title: options.title,
      subtitle: options.subtitle,
      description: options.description,
      steps,
      activeStep: -1,
      progress: undefined,
      hint: options.hint ?? '正在生成中，请勿刷新或关闭页面',
      startedAt: Date.now(),
      canRetry: false,
    }

    const controls: GenerationTaskControls = {
      setStep(index, description) {
        if (task.value?.id !== runId || task.value.status !== 'running') return
        task.value.activeStep = Math.max(-1, Math.min(index, task.value.steps.length))
        if (description !== undefined) task.value.description = description
      },
      setDescription(description) {
        if (task.value?.id !== runId || task.value.status !== 'running') return
        task.value.description = description
      },
      setProgress(progress) {
        if (task.value?.id !== runId || task.value.status !== 'running') return
        task.value.progress = clampProgress(progress)
      },
      setJobId(jobId) {
        if (task.value?.id !== runId) return
        task.value.jobId = jobId
      },
    }

    try {
      const result = await executor(controls)
      if (task.value?.id !== runId) return result

      task.value.status = 'success'
      task.value.progress = 100
      task.value.activeStep = task.value.steps.length
      task.value.finishedAt = Date.now()
      task.value.description = options.successMessage ? options.successMessage(result) : '生成完成'
      retryHandler = null

      const delay = options.successDelayMs ?? 450
      if (delay <= 0) {
        task.value = null
      } else {
        await new Promise<void>((resolve) => {
          closeTimer = setTimeout(() => {
            closeTimer = null
            if (task.value?.id === runId) task.value = null
            resolve()
          }, delay)
        })
      }
      return result
    } catch (error) {
      if (task.value?.id !== runId) return undefined

      const canRetry = options.canRetryError ? options.canRetryError(error) : true
      task.value.status = 'error'
      task.value.finishedAt = Date.now()
      task.value.error = options.formatError ? options.formatError(error) : defaultErrorMessage(error)
      task.value.canRetry = canRetry
      task.value.errorHint = canRetry ? undefined : '当前报错属于输入或参数校验问题，请先关闭返回修改后再提交。'
      return undefined
    }
  }

  async function retry() {
    if (!task.value || task.value.status !== 'error' || !task.value.canRetry || !retryHandler) return undefined
    const runner = retryHandler
    return await runner()
  }

  function dismiss() {
    if (task.value?.status === 'running') return false
    clearCloseTimer()
    task.value = null
    retryHandler = null
    return true
  }

  return {
    task,
    isOpen,
    isRunning,
    runTask,
    retry,
    dismiss,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useGenerationStore, import.meta.hot))
}
