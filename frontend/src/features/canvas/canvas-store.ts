import axios from 'axios'
import { defineStore } from 'pinia'
import { reactive } from 'vue'
import type { JobOut } from '@/features/studio/api-types'
import {
  apiErrorMessage,
  archiveCanvasApi,
  createCanvasApi,
  createUserAssetApi,
  deleteUserAssetApi,
  generateCanvasNodeApi,
  getCanvasDetailApi,
  JobFailureError,
  listCanvasesApi,
  listUserAssetsApi,
  updateCanvasApi,
  uploadFileToOss,
  watchJob,
  type CanvasDetailOut,
  type CanvasGenerateBody,
  type CanvasGenerateReference,
  type CanvasSummaryOut,
  type UserAssetOut,
} from './api'
import {
  canvasNodeLabels,
  createCanvasNode,
  hydrateCanvasGraph,
  isPersistedMediaUrl,
  MAX_CANVAS_NODE_HISTORY,
  outputKind,
  serializeCanvasGraph,
  type CanvasAsset,
  type CanvasDocument,
  type CanvasMedia,
  type CanvasNode,
  type CanvasNodeData,
  type CanvasNodeKind,
  type MediaKind,
} from './canvas-model'

export type CanvasSaveStatus = 'idle' | 'saving' | 'saved' | 'error'

export interface CanvasNodeGenerationState {
  jobId: string
  jobType: string
  status: JobOut['status']
  progress: number
  stepLabel: string
}

export interface CanvasJobWatchHooks {
  onSuccess?: (job: JobOut) => void
  onError?: (message: string) => void
  onSettled?: () => void
}

const saveTimers = new Map<string, ReturnType<typeof setTimeout>>()
const pendingSaves = new Map<string, Promise<void>>()
const watchedJobIds = new Set<string>()

function buildGenerateReferences(nodes: readonly CanvasNode[]): CanvasGenerateReference[] {
  return nodes.map((refNode) => {
    const kind = outputKind(refNode.type)
    const rawUrl = refNode.data.media?.url
    return {
      nodeId: refNode.id,
      kind,
      title: refNode.data.title || canvasNodeLabels[refNode.type ?? 'text'],
      text: refNode.data.text ?? null,
      mediaUrl: isPersistedMediaUrl(rawUrl) ? rawUrl! : null,
    }
  })
}

function defaultStepLabel(status: JobOut['status'], stepLabel?: string | null): string {
  if (stepLabel && stepLabel.trim()) return stepLabel.trim()
  if (status === 'queued') return '排队中...'
  if (status === 'polling') return '等待生成结果...'
  return '正在生成...'
}

function mapUserAsset(item: UserAssetOut): CanvasAsset {
  return {
    id: item.id,
    kind: item.kind,
    title: item.title,
    text: item.textContent ?? undefined,
    media: item.mediaUrl
      ? {
          url: item.mediaUrl,
          key: item.mediaKey ?? undefined,
          name: item.mediaName || item.title,
        }
      : undefined,
    sourceType: item.sourceType,
    sourceId: item.sourceId ?? null,
    createdAt: item.createdAt,
  }
}

function mapSummaryToDocument(summary: CanvasSummaryOut, existing?: CanvasDocument): CanvasDocument {
  if (existing && existing.loaded) {
    return {
      ...existing,
      name: summary.name,
      description: summary.description,
      cover: summary.coverUrl ?? existing.cover,
      updatedAt: summary.updatedAt,
      createdAt: summary.createdAt,
      version: Math.max(existing.version, summary.version),
      nodeCount: existing.nodes.length,
    }
  }
  return {
    id: summary.id,
    name: summary.name,
    description: summary.description,
    cover: summary.coverUrl ?? undefined,
    coverKey: null,
    updatedAt: summary.updatedAt,
    createdAt: summary.createdAt,
    version: summary.version,
    nodeCount: summary.nodeCount,
    loaded: false,
    nodes: [],
    edges: [],
  }
}

function mapDetailToDocument(detail: CanvasDetailOut): CanvasDocument {
  const { nodes, edges } = hydrateCanvasGraph(detail.graphData)
  return {
    id: detail.id,
    name: detail.name,
    description: detail.description,
    cover: detail.coverUrl ?? undefined,
    coverKey: detail.coverKey ?? null,
    updatedAt: detail.updatedAt,
    createdAt: detail.createdAt,
    version: detail.version,
    nodeCount: detail.nodeCount,
    loaded: true,
    nodes,
    edges,
    viewport: detail.viewport ?? undefined,
    activeJobs: detail.activeJobs ?? [],
  }
}

function isVersionConflict(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return false
  return error.response?.status === 409
}

export const useCanvasStore = defineStore('canvases', {
  state: () => ({
    canvases: [] as CanvasDocument[],
    canvasesLoading: false,
    canvasesLoaded: false,
    assets: [] as CanvasAsset[],
    assetsLoaded: false,
    saveStatus: {} as Record<string, CanvasSaveStatus>,
    uploadingNodes: {} as Record<string, boolean>,
    generatingNodes: {} as Record<string, CanvasNodeGenerationState>,
  }),
  actions: {
    getCanvas(id: string): CanvasDocument | undefined {
      return this.canvases.find((item) => item.id === id)
    },

    async fetchCanvases() {
      this.canvasesLoading = true
      try {
        const summaries = await listCanvasesApi()
        const existingMap = new Map(this.canvases.map((c) => [c.id, c]))
        this.canvases = summaries.map((summary) =>
          mapSummaryToDocument(summary, existingMap.get(summary.id)),
        )
        this.canvasesLoaded = true
      } finally {
        this.canvasesLoading = false
      }
    },

    async fetchCanvasDetail(id: string): Promise<CanvasDocument> {
      const detail = await getCanvasDetailApi(id)
      const doc = mapDetailToDocument(detail)
      const idx = this.canvases.findIndex((c) => c.id === id)
      if (idx >= 0) {
        this.canvases[idx] = doc
      } else {
        this.canvases.unshift(doc)
      }
      this.saveStatus[id] = 'saved'
      return this.canvases.find((c) => c.id === id) ?? doc
    },

    async createCanvas(name: string, description = ''): Promise<CanvasDocument> {
      const detail = await createCanvasApi({ name: name.trim(), description: description.trim() })
      const doc = mapDetailToDocument(detail)
      this.canvases.unshift(doc)
      this.saveStatus[doc.id] = 'saved'
      return this.canvases[0] ?? doc
    },

    async renameCanvas(canvas: CanvasDocument, name: string) {
      const trimmed = name.trim()
      if (!trimmed || trimmed === canvas.name) return
      canvas.name = trimmed
      await this.flushSave(canvas)
    },

    async deleteCanvas(id: string) {
      this.cancelScheduledSave(id)
      await archiveCanvasApi(id)
      this.canvases = this.canvases.filter((item) => item.id !== id)
      delete this.saveStatus[id]
    },

    cancelScheduledSave(id: string) {
      const timer = saveTimers.get(id)
      if (timer !== undefined) {
        clearTimeout(timer)
        saveTimers.delete(id)
      }
    },

    scheduleSave(canvas: CanvasDocument, delayMs = 800) {
      this.cancelScheduledSave(canvas.id)
      const timer = setTimeout(() => {
        saveTimers.delete(canvas.id)
        void this.flushSave(canvas)
      }, delayMs)
      saveTimers.set(canvas.id, timer)
    },

    async flushSave(canvas: CanvasDocument): Promise<void> {
      this.cancelScheduledSave(canvas.id)
      const existing = pendingSaves.get(canvas.id)
      if (existing) {
        await existing
      }

      const run = async (attempt = 0): Promise<void> => {
        this.saveStatus[canvas.id] = 'saving'
        const graphData = serializeCanvasGraph(canvas.nodes, canvas.edges)
        const coverUrl = isPersistedMediaUrl(canvas.cover) ? canvas.cover : null
        try {
          const updated = await updateCanvasApi(canvas.id, {
            expectedVersion: canvas.version,
            name: canvas.name,
            description: canvas.description,
            coverKey: canvas.coverKey ?? null,
            coverUrl,
            viewport: canvas.viewport ?? null,
            graphData,
          })
          canvas.version = updated.version
          canvas.nodeCount = updated.nodeCount
          canvas.updatedAt = updated.updatedAt
          this.saveStatus[canvas.id] = 'saved'
        } catch (error) {
          if (isVersionConflict(error) && attempt === 0) {
            const latest = await getCanvasDetailApi(canvas.id)
            // Merge worker-produced media/history/text updates from server into local nodes before retrying once.
            const serverNodes = new Map(latest.graphData.nodes.map((n) => [n.id, n]))
            for (const localNode of canvas.nodes) {
              const srv = serverNodes.get(localNode.id)
              if (!srv) continue
              const localData = reactive(localNode.data)
              const srvHistory = srv.data.history ?? []
              if (srvHistory.length > (localData.history?.length ?? 0)) {
                localData.history = srvHistory.map((item) => ({ ...item }))
                if (srv.data.media) localData.media = { ...srv.data.media }
              }
              if (srv.data.draft && !localData.draft) {
                localData.draft = srv.data.draft
              }
              if (srv.data.text && !localData.text) {
                localData.text = srv.data.text
              }
              if (srv.data.lastJobId && !localData.lastJobId) {
                localData.lastJobId = srv.data.lastJobId
              }
            }
            canvas.version = latest.version
            await run(1)
            return
          }
          this.saveStatus[canvas.id] = 'error'
          throw error
        }
      }

      const promise = run().finally(() => {
        if (pendingSaves.get(canvas.id) === promise) {
          pendingSaves.delete(canvas.id)
        }
      })
      pendingSaves.set(canvas.id, promise)
      await promise
    },

    addNode(canvas: CanvasDocument, type: CanvasNodeKind, x: number, y: number, data?: CanvasNodeData) {
      const node = { ...createCanvasNode(crypto.randomUUID(), type, x, y, data), selected: true }
      canvas.nodes = [...canvas.nodes.map((item) => (item.selected ? { ...item, selected: false } : item)), node]
      canvas.edges = canvas.edges.map((item) => (item.selected ? { ...item, selected: false } : item))
      canvas.nodeCount = canvas.nodes.length
      canvas.updatedAt = new Date().toISOString()
      this.scheduleSave(canvas)
      return node
    },

    updateNode(canvas: CanvasDocument, id: string, changes: Partial<CanvasNodeData>) {
      const node = canvas.nodes.find((item) => item.id === id)
      if (!node) return
      // Vue Flow keeps node objects raw. Update the reactive data without replacing the node.
      Object.assign(reactive(node.data), changes)
      canvas.updatedAt = new Date().toISOString()
      this.scheduleSave(canvas)
    },

    async replaceMedia(canvas: CanvasDocument, id: string, file: File) {
      const node = canvas.nodes.find((item) => item.id === id)
      if (!node) return
      const kind = outputKind(node.type)
      const uploadKind: MediaKind = kind === 'video' || kind === 'audio' ? kind : 'image'
      this.uploadingNodes[id] = true
      try {
        const uploaded = await uploadFileToOss(file, uploadKind)
        const media: CanvasMedia = {
          url: uploaded.url,
          key: uploaded.key,
          name: file.name,
          createdAt: new Date().toISOString(),
        }
        const current = canvas.nodes.find((item) => item.id === id)
        if (!current) return
        this.updateNode(
          canvas,
          id,
          current.type?.endsWith('-generation')
            ? { media, history: [...(current.data.history ?? []), media] }
            : { media },
        )
        await this.flushSave(canvas)
      } finally {
        delete this.uploadingNodes[id]
      }
    },

    async setCover(canvas: CanvasDocument, media: CanvasMedia) {
      if (!isPersistedMediaUrl(media.url)) return
      canvas.cover = media.url
      canvas.coverKey = media.key ?? null
      canvas.updatedAt = new Date().toISOString()
      await this.flushSave(canvas)
    },

    replaceNodes(canvas: CanvasDocument, nodes: CanvasNode[]) {
      const keptIds = new Set(nodes.map((node) => node.id))
      const removedNodes = canvas.nodes.filter((node) => !keptIds.has(node.id))
      canvas.nodes = nodes
      canvas.nodeCount = nodes.length
      if (!removedNodes.length) return

      canvas.edges = canvas.edges.filter((edge) => keptIds.has(edge.source) && keptIds.has(edge.target))
      canvas.updatedAt = new Date().toISOString()
      this.scheduleSave(canvas)
    },

    async fetchAssets() {
      const items = await listUserAssetsApi()
      this.assets = items.map(mapUserAsset)
      this.assetsLoaded = true
    },

    async collectAsset(canvasId: string, node: CanvasNode, title: string) {
      const { media, text } = node.data
      const kind = outputKind(node.type)
      if (kind === 'text') {
        if (!text?.trim()) return
        if (this.assets.some((a) => a.kind === 'text' && a.title === title && a.text === text.trim())) return
        const created = await createUserAssetApi({
          kind: 'text',
          title,
          textContent: text.trim(),
          sourceType: 'canvas',
          sourceId: canvasId,
        })
        this.assets.unshift(mapUserAsset(created))
        return
      }
      if (!media || !isPersistedMediaUrl(media.url)) return
      if (this.assets.some((a) => a.title === title && a.media?.url === media.url)) return
      const created = await createUserAssetApi({
        kind,
        title,
        mediaKey: media.key ?? null,
        mediaUrl: media.url,
        mediaName: media.name,
        sourceType: 'canvas',
        sourceId: canvasId,
      })
      this.assets.unshift(mapUserAsset(created))
    },

    async removeAsset(id: string) {
      await deleteUserAssetApi(id)
      this.assets = this.assets.filter((item) => item.id !== id)
    },

    async generateNode(
      canvas: CanvasDocument,
      nodeId: string,
      references: readonly CanvasNode[],
      hooks?: CanvasJobWatchHooks,
    ): Promise<JobOut | null> {
      const node = canvas.nodes.find((item) => item.id === nodeId)
      if (!node) return null

      let kind: CanvasGenerateBody['kind']
      if (node.type === 'text') kind = 'text'
      else if (node.type === 'image-generation') kind = 'image'
      else if (node.type === 'video-generation') kind = 'video'
      else return null

      if (this.generatingNodes[nodeId]) return null

      // Persist latest node / prompt / settings before dispatching worker writeback.
      await this.flushSave(canvas)

      const current = (this.getCanvas(canvas.id) ?? canvas).nodes.find((item) => item.id === nodeId)
      if (!current) return null

      const settings = current.data.settings
      const baseText = current.data.text ?? ''
      const body: CanvasGenerateBody = {
        kind,
        prompt: current.data.prompt ?? '',
        currentText: kind === 'text' ? baseText : null,
        modelId: settings?.modelId ?? null,
        ratio: kind !== 'text' ? (settings?.ratio ?? '16:9') : null,
        tier: kind === 'image' ? (settings?.tier ?? '1k') : null,
        resolution: kind === 'video' ? (settings?.resolution ?? '720p') : null,
        durationSeconds: kind === 'video' ? (settings?.durationSeconds ?? null) : null,
        references: buildGenerateReferences(references),
      }

      const accepted = await generateCanvasNodeApi(canvas.id, nodeId, body)
      const currentData = reactive(current.data)
      currentData.lastJobId = accepted.job.id
      currentData.lastError = undefined
      if (canvas.activeJobs) {
        canvas.activeJobs = [
          ...canvas.activeJobs.filter((item) => item.id !== accepted.job.id),
          accepted.job,
        ]
      } else {
        canvas.activeJobs = [accepted.job]
      }
      hooks?.onSettled?.()
      void this.watchCanvasJob(canvas, nodeId, accepted.job, { ...hooks, baseText })
      return accepted.job
    },

    resumeActiveJobs(canvas: CanvasDocument, hooks?: CanvasJobWatchHooks) {
      const activeJobs = canvas.activeJobs ?? []
      for (const job of activeJobs) {
        if (!job.targetId || watchedJobIds.has(job.id)) continue
        const node = canvas.nodes.find((item) => item.id === job.targetId)
        if (!node) continue
        void this.watchCanvasJob(canvas, job.targetId, job, {
          ...hooks,
          baseText: node.data.text ?? '',
        })
      }
    },

    async watchCanvasJob(
      canvas: CanvasDocument,
      nodeId: string,
      initialJob: JobOut,
      options?: CanvasJobWatchHooks & { baseText?: string },
    ): Promise<void> {
      if (watchedJobIds.has(initialJob.id)) return
      watchedJobIds.add(initialJob.id)

      this.generatingNodes[nodeId] = {
        jobId: initialJob.id,
        jobType: initialJob.jobType,
        status: initialJob.status,
        progress: initialJob.progress,
        stepLabel: defaultStepLabel(initialJob.status, initialJob.stepLabel),
      }

      try {
        const finalJob = await watchJob(initialJob.id, (snapshot) => {
          if (this.generatingNodes[nodeId]?.jobId === initialJob.id) {
            this.generatingNodes[nodeId] = {
              jobId: snapshot.id,
              jobType: snapshot.jobType,
              status: snapshot.status,
              progress: snapshot.progress,
              stepLabel: defaultStepLabel(snapshot.status, snapshot.stepLabel),
            }
          }
        })

        const doc = this.getCanvas(canvas.id) ?? canvas
        const target = doc.nodes.find((item) => item.id === nodeId)
        if (target) {
          const targetData = reactive(target.data)
          const res = finalJob.resultPayload ?? {}
          if (finalJob.jobType === 'canvas_text') {
            const generatedText = typeof res.text === 'string' ? res.text : ''
            if (generatedText) {
              const currentText = targetData.text ?? ''
              const expectedBase = options?.baseText ?? ''
              if (currentText === expectedBase) {
                targetData.text = generatedText
                targetData.draft = undefined
              } else {
                targetData.draft = generatedText
              }
            }
          } else if (finalJob.jobType === 'canvas_image' || finalJob.jobType === 'canvas_video') {
            const url =
              typeof res.imageUrl === 'string'
                ? res.imageUrl
                : typeof res.videoUrl === 'string'
                  ? res.videoUrl
                  : ''
            const key =
              typeof res.imageKey === 'string'
                ? res.imageKey
                : typeof res.videoKey === 'string'
                  ? res.videoKey
                  : undefined
            const modelId = typeof res.modelId === 'string' ? res.modelId : undefined
            if (url) {
              const ext = finalJob.jobType === 'canvas_video' ? 'mp4' : 'png'
              const media: CanvasMedia = {
                url,
                key,
                name: modelId ? `${modelId}.${ext}` : `generated.${ext}`,
                jobId: finalJob.id,
                modelId,
                createdAt: finalJob.finishedAt || new Date().toISOString(),
              }
              targetData.media = media
              const prevHistory = targetData.history ?? []
              if (!prevHistory.some((item) => item.jobId === finalJob.id)) {
                targetData.history = [...prevHistory, media].slice(-MAX_CANVAS_NODE_HISTORY)
              }
            }
          }
          targetData.lastJobId = finalJob.id
          targetData.lastError = undefined
        }

        // Worker bumped canvases.version inside FOR UPDATE; advance locally to avoid unnecessary 409.
        doc.version += 1
        doc.updatedAt = finalJob.finishedAt || new Date().toISOString()
        if (doc.activeJobs) {
          doc.activeJobs = doc.activeJobs.filter((item) => item.id !== finalJob.id)
        }
        options?.onSuccess?.(finalJob)
      } catch (error) {
        const message = apiErrorMessage(error)
        const doc = this.getCanvas(canvas.id) ?? canvas
        const target = doc.nodes.find((item) => item.id === nodeId)
        if (target) {
          const targetData = reactive(target.data)
          targetData.lastJobId = initialJob.id
          targetData.lastError = message
        }
        if (doc.activeJobs) {
          doc.activeJobs = doc.activeJobs.filter((item) => item.id !== initialJob.id)
        }
        if (error instanceof JobFailureError) {
          doc.version += 1
        }
        options?.onError?.(message)
      } finally {
        watchedJobIds.delete(initialJob.id)
        if (this.generatingNodes[nodeId]?.jobId === initialJob.id) {
          delete this.generatingNodes[nodeId]
        }
        options?.onSettled?.()
      }
    },

    clearAll() {
      for (const timer of saveTimers.values()) clearTimeout(timer)
      saveTimers.clear()
      pendingSaves.clear()
      watchedJobIds.clear()
      this.canvases = []
      this.canvasesLoading = false
      this.canvasesLoaded = false
      this.assets = []
      this.assetsLoaded = false
      this.saveStatus = {}
      this.uploadingNodes = {}
      this.generatingNodes = {}
    },
  },
})
