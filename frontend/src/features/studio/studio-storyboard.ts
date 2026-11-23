import type { JobOut, MediaHistoryItemOut } from './api-types.ts'
import { defaultSegmentDuration } from './components/drama-creation.ts'
import type { DramaSettings } from './components/drama-creation.ts'
import type { StudioEpisode } from './studio-project.ts'

export interface StoryboardAsset {
  id: string
  kind: 'character' | 'scene' | 'prop'
  name: string
  imageUrl?: string
}

export interface StoryboardCut {
  index: number
  seconds: number
  shotSize: '特写' | '近景' | '中景' | '全景' | '远景'
  camera: string
  framePrompt: string
  beats: [number, number]
}

export interface StoryboardReference {
  index: number
  assetId: string
  name: string
  kind: 'character' | 'scene' | 'prop' | 'image' | 'video' | 'audio'
  mediaKind?: 'image' | 'video' | 'audio'
  mediaUrl?: string
}

export interface StoryboardClip {
  id: number
  backendId?: string
  durationSeconds: number
  prompt: string
  assetIds: string[]
  references?: StoryboardReference[]
  beats?: [number, number]
  blocking?: string
  cuts?: StoryboardCut[]
  previewUrl?: string
  videoUrl?: string
  videoModelId?: string
  videoStatus?: string
  videoHistory?: MediaHistoryItemOut[]
  lastJobId?: string
  lastJobStatus?: JobOut['status']
  lastJobError?: string
}

export interface EpisodeStoryboard {
  assets: StoryboardAsset[]
  clips: StoryboardClip[]
}

export function createExampleStoryboard(episode: StudioEpisode, settings: DramaSettings): EpisodeStoryboard {
  const cap = settings.maxSegmentDuration ?? defaultSegmentDuration
  const lines = episode.script.split(/\n\s*\n/u).map((line) => line.trim()).filter(Boolean)
  const opening = lines[0] ?? '交代故事发生的地点和时间。'
  const action = lines[1] ?? '让主角进入画面，通过动作交代当前处境。'
  const ending = lines.length > 2 ? lines.slice(2).join('\n\n') : '留在角色的反应上，为下一段留出悬念。'

  return {
    assets: [
      { id: 'lead', kind: 'character', name: '主角' },
      { id: 'location', kind: 'scene', name: '开场场景' },
      { id: 'object', kind: 'prop', name: episode.example ? '手机' : '示例道具' },
    ],
    clips: [
      { id: 1, durationSeconds: Math.round(cap * 0.6), prompt: opening, assetIds: ['lead', 'location', 'object'], previewUrl: `/images/art-styles/${settings.visualStyle}.webp` },
      { id: 2, durationSeconds: cap, prompt: action, assetIds: ['lead', 'location', 'object'] },
      { id: 3, durationSeconds: Math.round(cap * 0.8), prompt: ending, assetIds: ['lead', 'object'] },
    ],
  }
}
