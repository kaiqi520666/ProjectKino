import type { JobOut } from './api-types'

export const TERMINAL_JOB_STATUSES = new Set(['succeeded', 'failed', 'canceled', 'review'])

const NON_RETRYABLE_CODES = new Set([
  'insufficient_credits',
  'validation_error',
  'assets_required',
  'provider_not_configured',
  'oss_not_configured',
  'duration_exceeds_model_limit',
  'reference_image_missing',
])

export class JobFailureError extends Error {
  code?: string
  retryable: boolean

  constructor(message: string, code?: string, retryable = true) {
    super(message)
    this.name = 'JobFailureError'
    this.code = code
    this.retryable = retryable
  }
}

export function finalizeJob(job: JobOut): JobOut {
  if (job.status === 'succeeded') return job
  const retryable = !job.errorCode || !NON_RETRYABLE_CODES.has(job.errorCode)
  throw new JobFailureError(job.errorMessage || '生成任务失败，请稍后重试', job.errorCode ?? undefined, retryable)
}

/**
 * 从累积的 SSE 文本缓冲中切分完整事件帧（兼容 \n\n 与 \r\n\r\n），解析合法的 JobOut JSON，
 * 忽略注释心跳与损坏片段，并返回尚未闭合的尾部缓冲。
 */
export function consumeSseBuffer(buffer: string): { events: JobOut[]; rest: string } {
  const normalized = buffer.replace(/\r\n/gu, '\n')
  const events: JobOut[] = []
  let rest = normalized
  let splitIdx = rest.indexOf('\n\n')

  while (splitIdx >= 0) {
    const frame = rest.slice(0, splitIdx)
    rest = rest.slice(splitIdx + 2)
    for (const line of frame.split('\n')) {
      if (!line.startsWith('data:')) continue
      const raw = line.slice(5).trim()
      if (!raw) continue
      try {
        events.push(JSON.parse(raw) as JobOut)
      } catch {
        // Ignore malformed keepalive fragments.
      }
    }
    splitIdx = rest.indexOf('\n\n')
  }

  return { events, rest }
}

export interface WatchJobStreamOptions {
  fetchEvents: () => Promise<Response>
  fetchJob: () => Promise<JobOut>
  onProgress?: (job: JobOut) => void
  pollIntervalMs?: number
}

export async function watchJobStream(options: WatchJobStreamOptions): Promise<JobOut> {
  const { fetchEvents, fetchJob, onProgress, pollIntervalMs = 2000 } = options

  try {
    const response = await fetchEvents()
    if (response.ok && response.body) {
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let latest: JobOut | undefined

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parsed = consumeSseBuffer(buffer)
        buffer = parsed.rest
        for (const job of parsed.events) {
          latest = job
          onProgress?.(job)
          if (TERMINAL_JOB_STATUSES.has(job.status)) {
            await reader.cancel().catch(() => {})
            return finalizeJob(job)
          }
        }
      }
      if (buffer.trim()) {
        const tail = consumeSseBuffer(`${buffer}\n\n`)
        for (const job of tail.events) {
          latest = job
          onProgress?.(job)
          if (TERMINAL_JOB_STATUSES.has(job.status)) {
            return finalizeJob(job)
          }
        }
      }
      if (latest && TERMINAL_JOB_STATUSES.has(latest.status)) {
        return finalizeJob(latest)
      }
    }
  } catch {
    // Fall back to polling if SSE stream is interrupted.
  }

  while (true) {
    const job = await fetchJob()
    onProgress?.(job)
    if (TERMINAL_JOB_STATUSES.has(job.status)) {
      return finalizeJob(job)
    }
    await new Promise((resolve) => setTimeout(resolve, pollIntervalMs))
  }
}
