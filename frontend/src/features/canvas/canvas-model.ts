import type { Edge, Node, Viewport } from '@xyflow/vue'
import type { JobOut } from '@/features/studio/api-types'

export const canvasNodeKinds = ['text', 'image', 'video', 'audio', 'image-generation', 'video-generation'] as const
export type CanvasNodeKind = typeof canvasNodeKinds[number]
export type MediaKind = 'image' | 'video' | 'audio'
export type CanvasImageTier = 'web' | '1k' | '2k' | '4k'

export const canvasNodeLabels: Record<CanvasNodeKind, string> = {
  text: '文本',
  image: '图片素材',
  video: '视频素材',
  audio: '音频素材',
  'image-generation': '图片生成',
  'video-generation': '视频生成',
}

export interface CanvasMedia {
  url: string
  key?: string
  name: string
  jobId?: string
  modelId?: string
  createdAt?: string
  example?: boolean
}

export interface CanvasGenerationSettings {
  modelId?: string
  model?: string
  ratio?: string
  tier?: CanvasImageTier
  resolution?: string
  durationSeconds?: number
  duration?: string
}

export type CanvasNodeData = {
  title?: string
  text?: string
  prompt?: string
  draft?: string
  media?: CanvasMedia
  history?: CanvasMedia[]
  settings?: CanvasGenerationSettings
  referenceOrder?: string[]
  lastJobId?: string
  lastError?: string
}
export type CanvasNode = Node<CanvasNodeData, CanvasNodeKind>

export interface CanvasAsset {
  id: string
  title: string
  kind: MediaKind | 'text'
  media?: CanvasMedia
  text?: string
  sourceType?: 'canvas' | 'studio' | 'upload'
  sourceId?: string | null
  createdAt?: string
}

export interface CanvasDocument {
  id: string
  name: string
  description: string
  cover?: string
  coverKey?: string | null
  updatedAt: string
  createdAt?: string
  version: number
  nodeCount: number
  loaded: boolean
  nodes: CanvasNode[]
  edges: Edge[]
  viewport?: Viewport
  activeJobs?: JobOut[]
}

export interface PersistedCanvasMedia {
  url: string
  key?: string
  name: string
  jobId?: string
  modelId?: string
  createdAt?: string
}

export interface PersistedCanvasSettings {
  modelId?: string
  ratio?: string
  tier?: CanvasImageTier
  resolution?: string
  durationSeconds?: number
}

export interface PersistedCanvasNodeData {
  title?: string
  text?: string
  draft?: string
  prompt?: string
  media?: PersistedCanvasMedia
  history?: PersistedCanvasMedia[]
  settings?: PersistedCanvasSettings
  referenceOrder?: string[]
  lastJobId?: string
  lastError?: string
}

export interface PersistedCanvasNode {
  id: string
  type: CanvasNodeKind
  position: { x: number; y: number }
  data: PersistedCanvasNodeData
}

export interface PersistedCanvasEdge {
  id: string
  source: string
  target: string
}

export interface PersistedCanvasGraph {
  nodes: PersistedCanvasNode[]
  edges: PersistedCanvasEdge[]
}

export const MAX_CANVAS_NODE_HISTORY = 20

export function isGenerationNode(kind?: CanvasNodeKind) {
  return kind === 'image-generation' || kind === 'video-generation'
}

export function canvasRatio(value = '16:9') {
  const [width, height] = value.split(':').map(Number)
  return width && height ? width / height : 16 / 9
}

export function outputKind(kind?: CanvasNodeKind): CanvasAsset['kind'] {
  if (kind === 'video-generation') return 'video'
  if (kind === 'image-generation') return 'image'
  return kind ?? 'text'
}

export function canConnectCanvasKinds(source?: CanvasNodeKind, target?: CanvasNodeKind) {
  const output = outputKind(source)
  if (output === 'video') return target === 'video-generation'
  if (target === 'text') return true
  if (target === 'image-generation') return output === 'text' || output === 'image'
  return target === 'video-generation'
}

export function canConnectCanvasNodes(source: CanvasNode, target: CanvasNode) {
  return source.id !== target.id && canConnectCanvasKinds(source.type, target.type)
}

export function createCanvasNode(
  id: string,
  type: CanvasNodeKind,
  x: number,
  y: number,
  data: CanvasNodeData = {},
): CanvasNode {
  return { id, type, position: { x, y }, data }
}

export function isPersistedMediaUrl(url?: string | null): boolean {
  if (typeof url !== 'string') return false
  const cleaned = url.trim()
  if (!cleaned) return false
  const lower = cleaned.toLowerCase()
  if (lower.startsWith('blob:') || lower.startsWith('data:')) return false
  return lower.startsWith('https://') || lower.startsWith('http://') || cleaned.startsWith('/')
}

export function sanitizeCanvasMedia(media?: CanvasMedia | null): PersistedCanvasMedia | undefined {
  if (!media || !isPersistedMediaUrl(media.url)) return undefined
  const out: PersistedCanvasMedia = {
    url: media.url.trim(),
    name: (media.name ?? '').slice(0, 255),
  }
  if (media.key) out.key = media.key.slice(0, 512)
  if (media.jobId) out.jobId = media.jobId.slice(0, 64)
  if (media.modelId) out.modelId = media.modelId.slice(0, 48)
  if (media.createdAt) out.createdAt = media.createdAt.slice(0, 64)
  return out
}

function sanitizeCanvasSettings(settings?: CanvasGenerationSettings | null): PersistedCanvasSettings | undefined {
  if (!settings) return undefined
  const out: PersistedCanvasSettings = {}
  if (settings.modelId) out.modelId = settings.modelId.slice(0, 48)
  if (settings.ratio) out.ratio = settings.ratio.slice(0, 16)
  if (settings.tier && ['web', '1k', '2k', '4k'].includes(settings.tier)) {
    out.tier = settings.tier
  }
  if (settings.resolution) out.resolution = settings.resolution.slice(0, 16)
  if (
    typeof settings.durationSeconds === 'number'
    && Number.isFinite(settings.durationSeconds)
    && settings.durationSeconds >= 1
    && settings.durationSeconds <= 60
  ) {
    out.durationSeconds = Math.round(settings.durationSeconds)
  }
  return Object.keys(out).length ? out : undefined
}

function isCanvasNodeKind(value: unknown): value is CanvasNodeKind {
  return typeof value === 'string' && (canvasNodeKinds as readonly string[]).includes(value)
}

export function serializeCanvasGraph(nodes: readonly CanvasNode[], edges: readonly Edge[]): PersistedCanvasGraph {
  const validNodeIds = new Set<string>()
  const serializedNodes: PersistedCanvasNode[] = []

  for (const node of nodes) {
    if (!node.id || !isCanvasNodeKind(node.type)) continue
    validNodeIds.add(node.id)
    const raw = node.data ?? {}
    const data: PersistedCanvasNodeData = {}
    if (raw.title) data.title = raw.title.slice(0, 120)
    if (raw.text !== undefined) data.text = raw.text
    if (raw.draft !== undefined) data.draft = raw.draft
    if (raw.prompt !== undefined) data.prompt = raw.prompt

    const media = sanitizeCanvasMedia(raw.media)
    if (media) data.media = media

    if (Array.isArray(raw.history) && raw.history.length) {
      const cleaned = raw.history
        .map((item) => sanitizeCanvasMedia(item))
        .filter((item): item is PersistedCanvasMedia => Boolean(item))
        .slice(-MAX_CANVAS_NODE_HISTORY)
      if (cleaned.length) data.history = cleaned
    }

    const settings = sanitizeCanvasSettings(raw.settings)
    if (settings) data.settings = settings

    if (Array.isArray(raw.referenceOrder) && raw.referenceOrder.length) {
      data.referenceOrder = raw.referenceOrder.filter((id) => typeof id === 'string' && id.length > 0).slice(0, 64)
    }
    if (raw.lastJobId) data.lastJobId = raw.lastJobId.slice(0, 64)
    if (raw.lastError) data.lastError = raw.lastError.slice(0, 1000)

    const x = Number.isFinite(node.position?.x) ? Math.round(node.position.x * 100) / 100 : 0
    const y = Number.isFinite(node.position?.y) ? Math.round(node.position.y * 100) / 100 : 0
    serializedNodes.push({
      id: node.id,
      type: node.type,
      position: { x, y },
      data,
    })
  }

  const seenEdges = new Set<string>()
  const serializedEdges: PersistedCanvasEdge[] = []
  for (const edge of edges) {
    if (!edge.id || !validNodeIds.has(edge.source) || !validNodeIds.has(edge.target)) continue
    const dedupeKey = `${edge.source}->${edge.target}`
    if (seenEdges.has(dedupeKey)) continue
    seenEdges.add(dedupeKey)
    serializedEdges.push({
      id: edge.id,
      source: edge.source,
      target: edge.target,
    })
  }

  return {
    nodes: serializedNodes,
    edges: serializedEdges,
  }
}

export function hydrateCanvasGraph(graph: PersistedCanvasGraph | null | undefined): {
  nodes: CanvasNode[]
  edges: Edge[]
} {
  if (!graph) return { nodes: [], edges: [] }
  const nodes: CanvasNode[] = (graph.nodes ?? []).map((item) =>
    createCanvasNode(item.id, item.type, item.position?.x ?? 0, item.position?.y ?? 0, {
      ...item.data,
      media: item.data?.media ? { ...item.data.media } : undefined,
      history: item.data?.history ? item.data.history.map((h) => ({ ...h })) : undefined,
      settings: item.data?.settings ? { ...item.data.settings } : undefined,
      referenceOrder: item.data?.referenceOrder ? [...item.data.referenceOrder] : undefined,
    }),
  )
  const edges: Edge[] = (graph.edges ?? []).map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
  }))
  return { nodes, edges }
}
