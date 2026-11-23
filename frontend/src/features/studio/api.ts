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
  PersistedClipReference,
  PersistedEpisodeOut,
  ProjectDetailOut,
  ProjectJobAcceptedOut,
  ProjectSummaryOut,
} from './api-types'
import type { StudioAssetDraft, StudioAssetKind } from './studio-assets'

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
      parentAssetId: draft.parentAssetId ?? null,
      variantLabel: draft.variantLabel ?? '',
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
      ...(draft.variantLabel !== undefined ? { variantLabel: draft.variantLabel } : {}),
    }),
  )
}

export function deleteAssetApi(projectId: string, assetId: string) {
  return unwrap<{ deleted: boolean }>(http.delete(`/projects/${projectId}/assets/${assetId}`))
}

export function selectAssetImageHistoryApi(projectId: string, assetId: string, historyId: string) {
  return unwrap<PersistedAssetOut>(
    http.post(`/projects/${projectId}/assets/${assetId}/history/select`, { historyId }),
  )
}

export function deleteAssetImageHistoryApi(projectId: string, assetId: string, historyId: string) {
  return unwrap<PersistedAssetOut>(
    http.delete(`/projects/${projectId}/assets/${assetId}/history/${encodeURIComponent(historyId)}`),
  )
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
  const defaultExt = kind === 'image' ? 'png' : kind === 'audio' ? 'mp3' : 'mp4'
  const defaultMime = kind === 'image' ? 'image/png' : kind === 'audio' ? 'audio/mpeg' : 'video/mp4'
  const policy = await requestOssUploadPolicy({
    kind,
    fileName: file.name || `upload.${defaultExt}`,
    mimeType: file.type || defaultMime,
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
  body: {
    modelId: string
    tier: 'web' | '1k' | '2k' | '4k'
    ratio?: string
    referenceUrls?: string[]
  },
) {
  return unwrap<ProjectJobAcceptedOut>(
    http.post(`/projects/${projectId}/assets/${assetId}/generate-image`, body),
  )
}

export function startBatchGenerateAssetImages(
  projectId: string,
  body: {
    assetIds: string[]
    modelId: string
    tier: 'web' | '1k' | '2k' | '4k'
    ratio?: string
    useParentReference?: boolean
  },
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
    references?: PersistedClipReference[]
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

export function selectClipVideoHistoryApi(
  projectId: string,
  episodeNumber: number,
  clipId: string,
  historyId: string,
) {
  return unwrap<PersistedClipOut>(
    http.post(`/projects/${projectId}/episodes/${episodeNumber}/clips/${clipId}/history/select`, {
      historyId,
    }),
  )
}

export function deleteClipVideoHistoryApi(
  projectId: string,
  episodeNumber: number,
  clipId: string,
  historyId: string,
) {
  return unwrap<PersistedClipOut>(
    http.delete(
      `/projects/${projectId}/episodes/${episodeNumber}/clips/${clipId}/history/${encodeURIComponent(historyId)}`,
    ),
  )
}

export function getJob(jobId: string) {
  return unwrap<JobOut>(http.get(`/jobs/${jobId}`))
}

import { JobFailureError, watchJobStream } from './job-stream'

export { JobFailureError }

export async function watchJob(
  jobId: string,
  onProgress?: (job: JobOut) => void,
): Promise<JobOut> {
  const baseUrl = (import.meta.env?.VITE_API_BASE_URL || '/api/v1').replace(/\/$/u, '')
  const token = readStoredToken()

  return watchJobStream({
    fetchEvents: () =>
      fetch(`${baseUrl}/jobs/${jobId}/events`, {
        headers: {
          Accept: 'text/event-stream',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      }),
    fetchJob: () => getJob(jobId),
    onProgress,
  })
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
