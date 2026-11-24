import type { ImageAspectRatio } from '@/components/ui/image-types'

import type { StudioAssetKind } from './studio-assets'

export type ScriptLanguage = 'zh-CN' | 'zh-TW' | 'en'

export interface BackendSettings {
  name: string
  ratio: ImageAspectRatio
  language: ScriptLanguage
  visualStyle: string
  visualStyleLabel?: string
  episodeCount: number
  maxSegmentDuration: 15 | 30
  secondsPerEpisode?: number
  backgroundMusic?: boolean
}

export interface BackendBeat {
  action?: string | null
  speaker?: string | null
  line?: string | null
  delivery?: string | null
}

export interface BackendScene {
  sceneId: string
  lighting: string
  characters: string[]
  props: string[]
  flow: BackendBeat[]
}

export interface BackendEpisode {
  number: number
  title: string
  summary: string
  targetSeconds: number
  hook: string
  cliff: string
  hookBeat: [number, number]
  seconds: number
  scenes: BackendScene[]
  script: string
  warnings?: string[]
}

export interface BackendWorld {
  kind: 'historical' | 'modern' | 'scifi' | 'fantasy'
  era: string
  baseline: string
}

export interface BackendOutlineCharacter {
  id: string
  name: string
  role?: string
  voice?: string
}

export interface BackendOutlineScene {
  id: string
  name: string
  kind: string
  time: string
  note?: string
}

export interface BackendOutlineProp {
  id: string
  name: string
  role?: string
}

export interface BackendOutlineEpisode {
  number: number
  title?: string
  summary?: string
  hook?: string
  suspense?: string
  ending?: string
  characterIds?: string[]
  sceneIds?: string[]
  propIds?: string[]
}

export interface BackendOutline {
  continuity?: string
  world?: BackendWorld
  characters?: BackendOutlineCharacter[]
  scenes?: BackendOutlineScene[]
  props?: BackendOutlineProp[]
  episodes?: BackendOutlineEpisode[]
  [key: string]: unknown
}

export interface ScriptResult {
  settings: BackendSettings
  outline: BackendOutline
  episodes: BackendEpisode[]
}

export interface BackendAsset {
  id: string
  kind: StudioAssetKind
  name: string
  description: string
  prompt: string
  episodeNumbers: number[]
  voice?: string
}

export interface AssetResult {
  settings: BackendSettings
  assets: BackendAsset[]
}

export interface BackendCut {
  index: number
  seconds: number
  shotSize: '特写' | '近景' | '中景' | '全景' | '远景'
  camera: string
  framePrompt: string
  beats: [number, number]
}

export interface BackendReference {
  index: number
  assetId: string
  name: string
  kind: StudioAssetKind
}

export interface BackendClip {
  id: number
  durationSeconds: number
  prompt: string
  assetIds: string[]
  references?: BackendReference[]
  beats?: [number, number]
  blocking?: string
  cuts?: BackendCut[]
}

export interface BackendStoryboardAsset {
  id: string
  kind: StudioAssetKind
  name: string
}

export interface BackendEpisodeStoryboard {
  number: number
  assets: BackendStoryboardAsset[]
  clips: BackendClip[]
}

export interface StoryboardResult {
  settings: BackendSettings
  episodes: BackendEpisodeStoryboard[]
}

export interface JobOut {
  id: string
  projectId?: string | null
  jobType: string
  targetId?: string | null
  status: 'queued' | 'running' | 'polling' | 'succeeded' | 'failed' | 'review'
  stepIndex: number
  stepTotal: number
  stepLabel: string
  progress: number
  resultPayload?: Record<string, unknown> | null
  jobMeta?: Record<string, unknown> | null
  errorCode?: string | null
  errorMessage?: string | null
  usageSummary?: Record<string, unknown> | null
  createdAt: string
  startedAt?: string | null
  finishedAt?: string | null
}

export interface ProjectJobAcceptedOut {
  projectId: string
  job: JobOut
}

export interface BatchSkippedAssetOut {
  assetId: string
  name: string
  reason: string
}

export interface BatchAssetImageAcceptedOut {
  projectId: string
  batchId: string
  acceptedCount: number
  totalFrozenCredits: string
  jobs: JobOut[]
  skipped: BatchSkippedAssetOut[]
}

export interface BatchSkippedClipOut {
  clipId: string
  clipIndex?: number | null
  reason: string
}

export interface BatchClipVideoAcceptedOut {
  projectId: string
  episodeNumber: number
  batchId: string
  acceptedCount: number
  totalDurationSeconds: number
  totalFrozenCredits: string
  jobs: JobOut[]
  skipped: BatchSkippedClipOut[]
}

export interface ProjectSummaryOut {
  id: string
  name: string
  mode: 'story' | 'upload'
  settings: BackendSettings
  scriptConfirmed: boolean
  episodeCount: number
  assetCount: number
  createdAt: string
  updatedAt: string
}

export interface PersistedEpisodeOut {
  id: string
  number: number
  title: string
  summary: string
  targetSeconds: number
  seconds: number
  hook: string
  cliff: string
  hookBeat: [number, number]
  scenes: BackendScene[]
  script: string
  warnings: string[]
  composedVideoUrl?: string | null
  composedDuration?: number | null
}

export interface MediaHistoryItemOut {
  id: string
  url: string
  key?: string | null
  source: 'ai' | 'upload' | 'rescue'
  jobId?: string | null
  modelId?: string | null
  tier?: string | null
  resolution?: string | null
  ratio?: string | null
  duration?: number | null
  createdAt: string
}

export interface PersistedAssetOut {
  id: string
  assetCode: string
  kind: StudioAssetKind
  name: string
  description: string
  prompt: string
  voice: string
  episodeNumbers: number[]
  parentAssetId?: string | null
  variantLabel?: string
  imageUrl?: string | null
  imageModelId?: string | null
  imageTier?: string | null
  imageStatus: string
  imageHistory: MediaHistoryItemOut[]
  lastJobId?: string | null
  lastJobStatus?: JobOut['status'] | null
  lastJobError?: string | null
}

export type ClipReferenceKind = StudioAssetKind | 'image' | 'video' | 'audio'
export type ClipReferenceMediaKind = 'image' | 'video' | 'audio'

export interface PersistedClipReference {
  index: number
  assetId: string
  assetCode?: string
  name: string
  kind: ClipReferenceKind
  mediaKind?: ClipReferenceMediaKind
  mediaUrl?: string
}

export interface PersistedClipOut {
  id: string
  episodeId: string
  clipIndex: number
  durationSeconds: number
  prompt: string
  promptCustomized: boolean
  references: PersistedClipReference[]
  beats?: [number, number] | null
  blocking?: string | null
  cuts?: BackendCut[] | null
  previewUrl?: string | null
  videoUrl?: string | null
  videoModelId?: string | null
  videoStatus: string
  videoHistory: MediaHistoryItemOut[]
  lastJobId?: string | null
  lastJobStatus?: JobOut['status'] | null
  lastJobError?: string | null
}

export interface ProjectDetailOut {
  id: string
  name: string
  mode: 'story' | 'upload'
  sourceText: string
  settings: BackendSettings
  outline?: BackendOutline | null
  scriptConfirmed: boolean
  episodes: PersistedEpisodeOut[]
  assets: PersistedAssetOut[]
  storyboards: Record<string, PersistedClipOut[]>
  activeJobs: JobOut[]
  createdAt: string
  updatedAt: string
}

export interface TextModelPriceOut {
  inputPricePerMillion: string
  cachedInputPricePerMillion: string
  outputPricePerMillion: string
}

export interface ImageModelPriceOut {
  tier: 'web' | '1k' | '2k' | '4k'
  creditPrice: string
}

export interface VideoModelPriceOut {
  ruleKey: string
  unit: 'second' | 'call'
  creditPrice: string
}

export interface ModelCatalogItemOut {
  id: string
  mediaType: 'text' | 'image' | 'video'
  category?: string
  displayName: string
  isDefault: boolean
  capabilities: Record<string, unknown>
  defaults: Record<string, unknown>
  textPrice?: TextModelPriceOut | null
  imagePrices: ImageModelPriceOut[]
  videoPrices: VideoModelPriceOut[]
}

export interface ModelCatalogOut {
  text: ModelCatalogItemOut[]
  image: ModelCatalogItemOut[]
  video: ModelCatalogItemOut[]
}

export interface OssUploadPolicyOut {
  host: string
  key: string
  url: string
  fields: Record<string, string>
  expiresAt: string
}
