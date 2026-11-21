import axios from 'axios'

import { http, readStoredToken, unwrap } from '@/lib/http'

import type { DramaSettings } from './components/drama-creation'
import type {
  BackendScene,
  BatchAssetImageAcceptedOut,
  BatchClipVideoAcceptedOut,
  JobOut,
  ModelCatalogOut,
  OssUploadPolicyOut,
  PersistedAssetOut,
  PersistedClipOut,
  PersistedEpisodeOut,
  ProjectDetailOut,
  ProjectJobAcceptedOut,
  ProjectSummaryOut,
} from './api-types'
import type { StudioAssetDraft, StudioAssetKind } from './studio-assets'

const TERMINAL_JOB_STATUSES = new Set<JobOut['status']>(['succeeded', 'failed', 'review'])

export interface ScriptRequest {
  settings: DramaSettings & { visualStyleLabel?: string }
  mode: 'story' | 'upload'
  text: string
  feedback?: string
}

export function listProjects() {
  return unwrap<ProjectSummaryOut[]>(http.get('/projects'))
}

export function getProjectDetail(projectId: string) {
  return unwrap<ProjectDetailOut>(http.get(`/projects/${projectId}`))
}

export function renameProjectApi(projectId: string, name: string) {
  return unwrap<{ id: string; name: string }>(http.patch(`/projects/${projectId}`, { name }))
}

export function archiveProjectApi(projectId: string) {
  return unwrap<{ id: string; archived: boolean }>(http.delete(`/projects/${projectId}`))
}

export function confirmScriptApi(projectId: string) {
  return unwrap<{ projectId: string; scriptConfirmed: boolean }>(
    http.post(`/projects/${projectId}/confirm-script`),
  )
}

export function startGenerateProject(body: ScriptRequest) {
  return unwrap<ProjectJobAcceptedOut>(http.post('/projects/generate', body))
}

export function startRegenerateStory(projectId: string, feedback = '') {
  return unwrap<ProjectJobAcceptedOut>(http.post(`/projects/${projectId}/regenerate`, { feedback }))
}

export function startRewriteEpisode(projectId: string, episodeNumber: number, feedback = '') {
  return unwrap<ProjectJobAcceptedOut>(
    http.post(`/projects/${projectId}/episodes/${episodeNumber}/rewrite`, { feedback }),
  )
}

export function startAppendEpisode(projectId: string, feedback = '') {
  return unwrap<ProjectJobAcceptedOut>(http.post(`/projects/${projectId}/episodes/append`, { feedback }))
}

export function saveStructuredEpisodeApi(
  projectId: string,
  episodeNumber: number,
  title: string,
  scenes: BackendScene[],
) {
  return unwrap<PersistedEpisodeOut>(
    http.put(`/projects/${projectId}/episodes/${episodeNumber}`, { title, scenes }),
  )
}

export function startExtractAssets(projectId: string, mode: 'full' | 'incremental' = 'incremental') {
  return unwrap<ProjectJobAcceptedOut>(http.post(`/projects/${projectId}/assets/extract`, { mode }))
}

export function createAssetApi(projectId: string, kind: StudioAssetKind, draft: StudioAssetDraft) {
  return unwrap<PersistedAssetOut>(
    http.post(`/projects/${projectId}/assets`, {
      kind,
      name: draft.name,
      description: draft.description,
      prompt: draft.prompt,
      voice: draft.voice ?? '',
      imageUrl: draft.imageUrl ?? null,
      imageKey: draft.imageKey ?? null,
    }),
  )
}

export function updateAssetApi(projectId: string, assetId: string, draft: StudioAssetDraft) {
  return unwrap<PersistedAssetOut>(
    http.patch(`/projects/${projectId}/assets/${assetId}`, {
      name: draft.name,
      description: draft.description,
      prompt: draft.prompt,
      voice: draft.voice ?? '',
      imageUrl: draft.imageUrl ?? null,
      imageKey: draft.imageKey ?? null,
      clearImage: !draft.imageUrl,
    }),
  )
}

export function deleteAssetApi(projectId: string, assetId: string) {
  return unwrap<{ deleted: boolean }>(http.delete(`/projects/${projectId}/assets/${assetId}`))
}

export function getModelCatalog() {
  return unwrap<ModelCatalogOut>(http.get('/models'))
}

export function requestOssUploadPolicy(body: {
  kind: 'image' | 'video' | 'audio'
  fileName: string
  mimeType: string
  size: number
}) {
  return unwrap<OssUploadPolicyOut>(http.post('/uploads/oss-policy', body))
}

export async function uploadFileToOss(
  file: File,
  kind: 'image' | 'video' | 'audio' = 'image',
): Promise<{ key: string; url: string }> {
  const policy = await requestOssUploadPolicy({
    kind,
    fileName: file.name || `upload.${kind === 'image' ? 'png' : 'mp4'}`,
    mimeType: file.type || (kind === 'image' ? 'image/png' : 'video/mp4'),
    size: file.size,
  })
  const form = new FormData()
  for (const [k, v] of Object.entries(policy.fields)) {
    form.append(k, v)
  }
  form.append('file', file)
  const response = await fetch(policy.host, { method: 'POST', body: form })
  if (!response.ok) {
    throw new Error(`阿里云 OSS 直传失败（HTTP ${response.status}）`)
  }
  return { key: policy.key, url: policy.url }
}

export function startGenerateAssetImage(
  projectId: string,
  assetId: string,
  body: { modelId: string; tier: 'web' | '1k' | '2k' | '4k'; ratio?: string },
) {
  return unwrap<ProjectJobAcceptedOut>(
    http.post(`/projects/${projectId}/assets/${assetId}/generate-image`, body),
  )
}

export function startBatchGenerateAssetImages(
  projectId: string,
  body: { assetIds: string[]; modelId: string; tier: 'web' | '1k' | '2k' | '4k'; ratio?: string },
) {
  return unwrap<BatchAssetImageAcceptedOut>(
    http.post(`/projects/${projectId}/assets/batch-generate-image`, body),
  )
}

export function startGenerateStoryboard(projectId: string, episodeNumber: number) {
  return unwrap<ProjectJobAcceptedOut>(
    http.post(`/projects/${projectId}/episodes/${episodeNumber}/storyboard/generate`),
  )
}

export function startGenerateClipVideo(
  projectId: string,
  clipId: string,
  body: {
    modelId: string
    resolution: '480p' | '720p' | '1080p'
    ratio?: string
    durationSeconds?: number
  },
) {
  return unwrap<ProjectJobAcceptedOut>(
    http.post(`/projects/${projectId}/clips/${clipId}/generate-video`, body),
  )
}

export function startBatchGenerateClipVideos(
  projectId: string,
  episodeNumber: number,
  body: {
    clipIds: string[]
    modelId: string
    resolution: '480p' | '720p' | '1080p'
    ratio?: string
    durationSeconds?: number
  },
) {
  return unwrap<BatchClipVideoAcceptedOut>(
    http.post(`/projects/${projectId}/episodes/${episodeNumber}/clips/batch-generate-video`, body),
  )
}

export function startComposeEpisode(projectId: string, episodeNumber: number) {
  return unwrap<ProjectJobAcceptedOut>(
    http.post(`/projects/${projectId}/episodes/${episodeNumber}/compose`),
  )
}

export function createClipApi(projectId: string, episodeNumber: number, durationSeconds: number, prompt = '') {
  return unwrap<PersistedClipOut>(
    http.post(`/projects/${projectId}/episodes/${episodeNumber}/clips`, { durationSeconds, prompt }),
  )
}

export function updateClipApi(
  projectId: string,
  clipId: string,
  patch: {
    durationSeconds?: number
    prompt?: string
    references?: Array<{
      index: number
      assetId: string
      assetCode?: string
      name: string
      kind: StudioAssetKind
    }>
  },
) {
  return unwrap<PersistedClipOut>(http.patch(`/projects/${projectId}/clips/${clipId}`, patch))
}

export function deleteClipApi(projectId: string, clipId: string) {
  return unwrap<{ deleted: boolean }>(http.delete(`/projects/${projectId}/clips/${clipId}`))
}

export function reorderClipsApi(projectId: string, episodeNumber: number, clipIds: string[]) {
  return unwrap<PersistedClipOut[]>(
    http.put(`/projects/${projectId}/episodes/${episodeNumber}/clips/reorder`, { clipIds }),
  )
}

export function getJob(jobId: string) {
  return unwrap<JobOut>(http.get(`/jobs/${jobId}`))
}

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

function finalizeJob(job: JobOut): JobOut {
  if (job.status === 'succeeded') return job
  const nonRetryable = new Set([
    'insufficient_credits',
    'validation_error',
    'assets_required',
    'provider_not_configured',
    'oss_not_configured',
    'duration_exceeds_model_limit',
    'reference_image_missing',
  ])
  const retryable = !job.errorCode || !nonRetryable.has(job.errorCode)
  throw new JobFailureError(job.errorMessage || '生成任务失败，请稍后重试', job.errorCode ?? undefined, retryable)
}

export async function watchJob(
  jobId: string,
  onProgress?: (job: JobOut) => void,
): Promise<JobOut> {
  const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/u, '')
  const token = readStoredToken()

  try {
    const response = await fetch(`${baseUrl}/jobs/${jobId}/events`, {
      headers: {
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })
    if (response.ok && response.body) {
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let latest: JobOut | undefined

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let splitIdx = buffer.indexOf('\n\n')
        while (splitIdx >= 0) {
          const chunk = buffer.slice(0, splitIdx)
          buffer = buffer.slice(splitIdx + 2)
          for (const line of chunk.split('\n')) {
            if (!line.startsWith('data:')) continue
            const raw = line.slice(5).trim()
            if (!raw) continue
            try {
              const job = JSON.parse(raw) as JobOut
              latest = job
              onProgress?.(job)
              if (TERMINAL_JOB_STATUSES.has(job.status)) {
                await reader.cancel().catch(() => {})
                return finalizeJob(job)
              }
            } catch {
              // Ignore malformed keepalive fragments.
            }
          }
          splitIdx = buffer.indexOf('\n\n')
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
    const job = await getJob(jobId)
    onProgress?.(job)
    if (TERMINAL_JOB_STATUSES.has(job.status)) {
      return finalizeJob(job)
    }
    await new Promise((resolve) => setTimeout(resolve, 2000))
  }
}

export function apiErrorMessage(error: unknown): string {
  if (error instanceof JobFailureError) return error.message
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as { message?: unknown; detail?: unknown } | undefined
    if (typeof data?.message === 'string' && data.message.trim()) return data.message
    if (typeof data?.detail === 'string' && data.detail.trim()) return data.detail
    if (error.code === 'ECONNABORTED') return '请求超时，请稍后重试'
    if (!error.response) return '无法连接后端服务，请确认正式后端与 Worker 已启动'
  }
  return error instanceof Error ? error.message : '请求失败'
}

export function isRetryableApiError(error: unknown): boolean {
  if (error instanceof JobFailureError) return error.retryable
  if (axios.isAxiosError(error)) {
    const status = error.response?.status
    if (!status) return true
    if (status === 402 || status === 401 || status === 403 || status === 400 || status === 422) return false
    if (status === 408 || status === 429 || status >= 500) return true
    return false
  }
  return true
}
