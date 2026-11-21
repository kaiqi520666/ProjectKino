import type { Edge, Node, Viewport } from '@xyflow/vue'

export const canvasNodeKinds = ['text', 'image', 'video', 'audio', 'image-generation', 'video-generation'] as const
export type CanvasNodeKind = typeof canvasNodeKinds[number]
export type MediaKind = 'image' | 'video' | 'audio'

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
  name: string
  example?: boolean
}

export interface CanvasGenerationSettings {
  model?: string
  ratio?: string
  resolution?: string
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
}
export type CanvasNode = Node<CanvasNodeData, CanvasNodeKind>

export interface CanvasAsset {
  id: string
  title: string
  kind: MediaKind | 'text'
  media?: CanvasMedia
  text?: string
}

export interface CanvasDocument {
  id: string
  name: string
  description: string
  cover?: string
  updatedAt: string
  nodes: CanvasNode[]
  edges: Edge[]
  viewport?: Viewport
}

export const sampleImage: CanvasMedia = {
  url: '/images/workspace/banner-story.jpg',
  name: '城市档案.jpg',
  example: true,
}

export const sampleVideo: CanvasMedia = {
  url: '/media/canvas/city-preview.mp4',
  name: '城市档案预览.mp4',
  example: true,
}

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

export function createSampleCanvases(): CanvasDocument[] {
  return [
    {
      id: '1',
      name: '都市悬疑分镜规划',
      description: '整理人物关系、关键场景和故事线索。',
      cover: '/images/workspace/banner-canvas.jpg',
      updatedAt: '今天 14:32',
      nodes: [
        createCanvasNode('story', 'text', 52, 52, { text: '凌晨的城市档案室。窗外刚下过雨，一沓旧案卷摊在桌灯下。' }),
        createCanvasNode('image', 'image', 0, 346, { media: sampleImage }),
        createCanvasNode('image-prompt', 'image-generation', 515, 10, { prompt: '冷调雨夜，写实电影摄影。' }),
        createCanvasNode('video-prompt', 'video-generation', 580, 276, { prompt: '镜头缓慢向前推进，保留原本的色调。' }),
      ],
      edges: [
        { id: 'story-image', source: 'story', target: 'image-prompt' },
        { id: 'image-video', source: 'image', target: 'video-prompt' },
      ],
    },
    {
      id: '2',
      name: '古风人物关系图',
      description: '记录角色设定、人物关系和情节走向。',
      cover: '/images/art-styles/historical-realism.webp',
      updatedAt: '昨天 20:15',
      nodes: [
        createCanvasNode('character', 'text', 0, 80, { text: '沈七在来京途中结识了文先生，两人各自保管一半旧信。' }),
      ],
      edges: [],
    },
    {
      id: '3',
      name: '场景灵感收集',
      description: '收集城市、室内和夜景的画面参考。',
      cover: '/images/workspace/banner-assets.jpg',
      updatedAt: '11 月 16 日',
      nodes: [createCanvasNode('scene', 'image', 0, 80, { media: sampleImage })],
      edges: [],
    },
    {
      id: '4',
      name: '未命名画布',
      description: '还没有添加内容。',
      updatedAt: '11 月 12 日',
      nodes: [],
      edges: [],
    },
  ]
}
