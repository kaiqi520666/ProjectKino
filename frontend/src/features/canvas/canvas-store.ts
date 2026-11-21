import axios from 'axios'
import { defineStore } from 'pinia'
import { reactive } from 'vue'
import {
  archiveCanvasApi,
  createCanvasApi,
  createUserAssetApi,
  deleteUserAssetApi,
  getCanvasDetailApi,
  listCanvasesApi,
  listUserAssetsApi,
  updateCanvasApi,
  uploadFileToOss,
  type CanvasDetailOut,
  type CanvasSummaryOut,
  type UserAssetOut,
} from './api'
import {
  createCanvasNode,
  hydrateCanvasGraph,
  isPersistedMediaUrl,
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

const saveTimers = new Map<string, ReturnType<typeof setTimeout>>()
const pendingSaves = new Map<string, Promise<void>>()

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
    generatingText: {} as Record<string, boolean>,
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

    clearAll() {
      for (const timer of saveTimers.values()) clearTimeout(timer)
      saveTimers.clear()
      pendingSaves.clear()
      this.canvases = []
      this.canvasesLoading = false
      this.canvasesLoaded = false
      this.assets = []
      this.assetsLoaded = false
      this.saveStatus = {}
      this.uploadingNodes = {}
      this.generatingText = {}
    },
  },
})
