import { defineStore } from 'pinia'
import { reactive } from 'vue'
import {
  createCanvasNode, createSampleCanvases, outputKind, sampleImage, sampleVideo,
  type CanvasAsset, type CanvasDocument, type CanvasMedia, type CanvasNode, type CanvasNodeData, type CanvasNodeKind,
} from './canvas-model'

export const useCanvasStore = defineStore('canvases', {
  state: () => ({ canvases: createSampleCanvases(), assets: [] as CanvasAsset[], generatingText: {} as Record<string, boolean> }),
  actions: {
    createCanvas(name: string) {
      const id = crypto.randomUUID()
      this.canvases.unshift({
        id,
        name,
        description: '',
        updatedAt: '刚刚',
        nodes: [],
        edges: [],
      })
      return id
    },
    addNode(canvas: CanvasDocument, type: CanvasNodeKind, x: number, y: number, data?: CanvasNodeData) {
      const node = { ...createCanvasNode(crypto.randomUUID(), type, x, y, data), selected: true }
      canvas.nodes = [...canvas.nodes.map(item => item.selected ? { ...item, selected: false } : item), node]
      canvas.edges = canvas.edges.map(item => item.selected ? { ...item, selected: false } : item)
      canvas.updatedAt = '刚刚'
      return node
    },
    updateNode(canvas: CanvasDocument, id: string, changes: Partial<CanvasNodeData>) {
      const node = canvas.nodes.find(item => item.id === id)
      if (!node) return
      const oldMedia = [node.data.media, ...(node.data.history ?? [])]
      // Vue Flow keeps node objects raw. Update the reactive data without replacing the node.
      Object.assign(reactive(node.data), changes)
      canvas.updatedAt = '刚刚'
      for (const media of oldMedia) this.releaseMedia(media?.url)
    },
    replaceMedia(canvas: CanvasDocument, id: string, file: File) {
      const node = canvas.nodes.find(item => item.id === id)
      if (!node) return
      const media = { url: URL.createObjectURL(file), name: file.name }
      this.updateNode(canvas, id, node.type?.endsWith('-generation')
        ? { media, history: [...(node.data.history ?? []), media] }
        : { media })
    },
    async generateExample(canvas: CanvasDocument, id: string, prompt: string) {
      const node = canvas.nodes.find(item => item.id === id)
      if (!node) return
      if (node.type === 'text') {
        if (this.generatingText[id] || node.data.draft) return
        const original = node.data.text
        this.generatingText[id] = true
        try {
          await new Promise<void>(resolve => window.setTimeout(resolve, 350))
          const current = canvas.nodes.find(item => item.id === id)
          if (!current) return
          const result = `## 文本示例\n\n${prompt}\n\n- 补充背景与目标。\n- 用具体动作与细节展开。`
          this.updateNode(canvas, id, current.data.text === original ? { text: result } : { draft: result })
        } finally {
          delete this.generatingText[id]
        }
        return
      }
      if (node.type === 'image-generation') {
        const media = node.data.media?.url === sampleImage.url
          ? { url: '/images/workspace/banner-canvas.jpg', name: '画面示例.jpg', example: true }
          : sampleImage
        const history = node.data.history ?? []
        const entry = { ...media, name: media.name.replace(/(\.[^.]+)$/, ' · 结果 ' + (history.length + 1) + '$1') }
        this.updateNode(canvas, id, { media: entry, history: [...history, entry] })
      }
      if (node.type === 'video-generation') {
        const history = node.data.history ?? []
        const media = {
          ...sampleVideo,
          url: history.length % 2 ? '/media/canvas/street-preview.mp4' : sampleVideo.url,
          name: '城市档案 · 结果 ' + (history.length + 1) + '.mp4',
        }
        this.updateNode(canvas, id, { media, history: [...history, media] })
      }
    },
    collectAsset(node: CanvasNode, title: string) {
      const { media, text } = node.data
      if (!media && !text?.trim()) return
      if (this.assets.some(asset => asset.title === title && asset.media?.url === media?.url && asset.text === text)) return
      this.assets.unshift({ id: crypto.randomUUID(), kind: outputKind(node.type), title, media, text })
    },
    removeAsset(id: string) {
      const asset = this.assets.find(item => item.id === id)
      this.assets = this.assets.filter(item => item.id !== id)
      this.releaseMedia(asset?.media?.url)
    },
    setCover(canvas: CanvasDocument, media: CanvasMedia) {
      const oldCover = canvas.cover
      canvas.cover = media.url
      canvas.updatedAt = '刚刚'
      this.releaseMedia(oldCover)
    },
    replaceNodes(canvas: CanvasDocument, nodes: CanvasNode[]) {
      const keptIds = new Set(nodes.map(node => node.id))
      const removedNodes = canvas.nodes.filter(node => !keptIds.has(node.id))
      canvas.nodes = nodes
      if (!removedNodes.length) return

      canvas.edges = canvas.edges.filter(edge => keptIds.has(edge.source) && keptIds.has(edge.target))
      canvas.updatedAt = '刚刚'
      for (const node of removedNodes) {
        for (const media of [node.data.media, ...(node.data.history ?? [])]) this.releaseMedia(media?.url)
      }
    },
    releaseMedia(url?: string) {
      if (!url?.startsWith('blob:')) return
      const isReferenced = this.canvases.some(canvas =>
        canvas.cover === url || canvas.nodes.some(node =>
          node.data.media?.url === url || node.data.history?.some(media => media.url === url),
        ),
      ) || this.assets.some(asset => asset.media?.url === url)
      if (!isReferenced) URL.revokeObjectURL(url)
    },
  },
})
