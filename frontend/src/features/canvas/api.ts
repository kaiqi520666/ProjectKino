import type { Viewport } from '@xyflow/vue'
import { http, unwrap } from '@/lib/http'
import type { JobOut } from '@/features/studio/api-types'
import { apiErrorMessage, JobFailureError, uploadFileToOss, watchJob } from '@/features/studio/api'
import type { CanvasAsset, CanvasImageTier, PersistedCanvasGraph } from './canvas-model'

export { apiErrorMessage, JobFailureError, uploadFileToOss, watchJob }

export interface CanvasSummaryOut {
  id: string
  name: string
  description: string
  coverUrl?: string | null
  status: string
  version: number
  nodeCount: number
  createdAt: string
  updatedAt: string
}

export interface CanvasDetailOut extends CanvasSummaryOut {
  coverKey?: string | null
  schemaVersion: number
  viewport?: Viewport | null
  graphData: PersistedCanvasGraph
  activeJobs: JobOut[]
}

export interface CanvasUpdateBody {
  expectedVersion?: number
  name?: string
  description?: string
  coverKey?: string | null
  coverUrl?: string | null
  viewport?: Viewport | null
  graphData?: PersistedCanvasGraph
}

export interface UserAssetOut {
  id: string
  kind: CanvasAsset['kind']
  title: string
  textContent?: string | null
  mediaKey?: string | null
  mediaUrl?: string | null
  mediaName?: string | null
  sourceType: 'canvas' | 'studio' | 'upload'
  sourceId?: string | null
  createdAt: string
  updatedAt: string
}

export function listCanvasesApi() {
  return unwrap<{ items: CanvasSummaryOut[] }>(http.get('/canvases')).then((res) => res.items)
}

export function createCanvasApi(body: { name: string; description?: string }) {
  return unwrap<CanvasDetailOut>(http.post('/canvases', body))
}

export function getCanvasDetailApi(canvasId: string) {
  return unwrap<CanvasDetailOut>(http.get(`/canvases/${canvasId}`))
}

export function updateCanvasApi(canvasId: string, body: CanvasUpdateBody) {
  return unwrap<CanvasDetailOut>(http.patch(`/canvases/${canvasId}`, body))
}

export function archiveCanvasApi(canvasId: string) {
  return unwrap<{ id: string; archived: boolean }>(http.delete(`/canvases/${canvasId}`))
}

export function listUserAssetsApi(kind?: CanvasAsset['kind']) {
  return unwrap<{ items: UserAssetOut[] }>(
    http.get('/assets', { params: kind ? { kind } : undefined }),
  ).then((res) => res.items)
}

export function createUserAssetApi(body: {
  kind: CanvasAsset['kind']
  title: string
  textContent?: string | null
  mediaKey?: string | null
  mediaUrl?: string | null
  mediaName?: string | null
  sourceType?: 'canvas' | 'studio' | 'upload'
  sourceId?: string | null
}) {
  return unwrap<UserAssetOut>(http.post('/assets', body))
}

export interface CanvasGenerateReference {
  nodeId: string
  kind: CanvasAsset['kind']
  title: string
  text?: string | null
  mediaUrl?: string | null
}

export interface CanvasGenerateBody {
  kind: 'text' | 'image' | 'video'
  prompt: string
  currentText?: string | null
  modelId?: string | null
  ratio?: string | null
  tier?: CanvasImageTier | null
  resolution?: string | null
  durationSeconds?: number | null
  references: CanvasGenerateReference[]
}

export interface CanvasJobAcceptedOut {
  canvasId: string
  nodeId: string
  job: JobOut
}

export function generateCanvasNodeApi(canvasId: string, nodeId: string, body: CanvasGenerateBody) {
  return unwrap<CanvasJobAcceptedOut>(http.post(`/canvases/${canvasId}/nodes/${nodeId}/generate`, body))
}

export function deleteUserAssetApi(assetId: string) {
  return unwrap<{ id: string; deleted: boolean }>(http.delete(`/assets/${assetId}`))
}
