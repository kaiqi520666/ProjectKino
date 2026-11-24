import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import {
  resolveProjectCoverUrl,
  resolveProjectProgress,
} from '../src/features/projects/project-progress.ts'
import {
  buildEpisodeNavItems,
  resolveNeighborEpisodes,
} from '../src/features/studio/studio-project.ts'
import { useStudioStore } from '../src/features/studio/studio-store.ts'

test('resolveProjectCoverUrl follows custom > auto > style priority', () => {
  const custom = resolveProjectCoverUrl({
    coverUrl: 'https://cdn.example.com/custom.png',
    autoCoverUrl: 'https://cdn.example.com/auto.png',
    visualStyle: 'noir-comic',
  })
  assert.deepEqual(custom, {
    url: 'https://cdn.example.com/custom.png',
    isCustom: true,
    isAuto: false,
  })

  const auto = resolveProjectCoverUrl({
    coverUrl: null,
    autoCoverUrl: 'https://cdn.example.com/auto.png',
    visualStyle: 'noir-comic',
  })
  assert.deepEqual(auto, {
    url: 'https://cdn.example.com/auto.png',
    isCustom: false,
    isAuto: true,
  })

  const fallback = resolveProjectCoverUrl({
    coverUrl: '   ',
    autoCoverUrl: null,
    styleCoverUrl: 'https://cdn.example.com/framedrama/system/art-styles/live-action.webp',
    visualStyle: 'unknown-style',
  })
  assert.deepEqual(fallback, {
    url: 'https://cdn.example.com/framedrama/system/art-styles/live-action.webp',
    isCustom: false,
    isAuto: false,
  })
})

test('resolveProjectProgress covers all production stages and target routes', () => {
  const partialDraft = resolveProjectProgress({
    scriptConfirmed: false,
    episodeCount: 2,
    plannedEpisodeCount: 5,
    assetCount: 0,
  })
  assert.equal(partialDraft.label, '剧本草稿 2/5 集')
  assert.equal(partialDraft.tone, 'draft')
  assert.equal(partialDraft.targetRoute, 'studio-script')

  const confirmedOnly = resolveProjectProgress({
    scriptConfirmed: true,
    episodeCount: 5,
    plannedEpisodeCount: 5,
    assetCount: 0,
  })
  assert.equal(confirmedOnly.label, '剧本已确认')
  assert.equal(confirmedOnly.tone, 'ready')
  assert.equal(confirmedOnly.targetRoute, 'studio-assets')

  const assetsExtracted = resolveProjectProgress({
    scriptConfirmed: true,
    episodeCount: 5,
    plannedEpisodeCount: 5,
    assetCount: 8,
    assetImageReadyCount: 0,
  })
  assert.equal(assetsExtracted.label, '已提资产 8 项')
  assert.equal(assetsExtracted.targetRoute, 'studio-assets')

  const assetsRendered = resolveProjectProgress({
    scriptConfirmed: true,
    episodeCount: 5,
    plannedEpisodeCount: 5,
    assetCount: 8,
    assetImageReadyCount: 5,
  })
  assert.equal(assetsRendered.label, '资产出图 5/8')
  assert.equal(assetsRendered.targetRoute, 'studio-assets')

  const storyboardStage = resolveProjectProgress({
    scriptConfirmed: true,
    episodeCount: 5,
    plannedEpisodeCount: 5,
    assetCount: 8,
    assetImageReadyCount: 8,
    storyboardEpisodeCount: 3,
    clipCount: 15,
    clipVideoReadyCount: 0,
  })
  assert.equal(storyboardStage.label, '已拆分镜 3/5 集')
  assert.equal(storyboardStage.tone, 'progress')
  assert.equal(storyboardStage.targetRoute, 'studio-storyboard')

  const videoStage = resolveProjectProgress({
    scriptConfirmed: true,
    episodeCount: 5,
    plannedEpisodeCount: 5,
    assetCount: 8,
    assetImageReadyCount: 8,
    storyboardEpisodeCount: 4,
    clipCount: 20,
    clipVideoReadyCount: 12,
  })
  assert.equal(videoStage.label, '视频 12/20 段')
  assert.equal(videoStage.tone, 'progress')
  assert.equal(videoStage.targetRoute, 'studio-storyboard')

  const partialComposed = resolveProjectProgress({
    scriptConfirmed: true,
    episodeCount: 5,
    plannedEpisodeCount: 5,
    assetCount: 8,
    assetImageReadyCount: 8,
    storyboardEpisodeCount: 5,
    clipCount: 25,
    clipVideoReadyCount: 20,
    composedEpisodeCount: 3,
  })
  assert.equal(partialComposed.label, '已合成 3/5 集')
  assert.equal(partialComposed.tone, 'done')
  assert.equal(partialComposed.targetRoute, 'studio-storyboard')

  const fullyComposed = resolveProjectProgress({
    scriptConfirmed: true,
    episodeCount: 5,
    plannedEpisodeCount: 5,
    assetCount: 8,
    assetImageReadyCount: 8,
    storyboardEpisodeCount: 5,
    clipCount: 25,
    clipVideoReadyCount: 25,
    composedEpisodeCount: 5,
  })
  assert.equal(fullyComposed.label, '全剧已合成 5/5 集')
  assert.equal(fullyComposed.tone, 'done')
  assert.equal(fullyComposed.percent, 100)
})

test('resolveNeighborEpisodes and buildEpisodeNavItems reflect episode statuses', () => {
  assert.deepEqual(resolveNeighborEpisodes(1, 5), { prev: null, next: 2 })
  assert.deepEqual(resolveNeighborEpisodes(3, 5), { prev: 2, next: 4 })
  assert.deepEqual(resolveNeighborEpisodes(5, 5), { prev: 4, next: null })
  assert.deepEqual(resolveNeighborEpisodes(1, 1), { prev: null, next: null })
  assert.deepEqual(resolveNeighborEpisodes(0, 5), { prev: null, next: null })

  setActivePinia(createPinia())
  const store = useStudioStore()
  const id = store.createProject({
    mode: 'story',
    settings: {
      name: '测试短剧',
      ratio: '16:9',
      visualStyle: 'live-action',
      language: 'zh-CN',
      episodeCount: 4,
      maxSegmentDuration: 15,
      backgroundMusic: true,
    },
    story: '故事梗概',
  })
  const project = store.getProject(id)!
  project.episodes[1] = {
    number: 1,
    title: '开端',
    summary: '',
    script: '',
    composedVideoUrl: 'https://cdn.example.com/ep1.mp4',
  }
  project.episodes[2] = { number: 2, title: '转折', summary: '', script: '' }
  project.storyboards = {
    1: { assets: [], clips: [{ id: 1, durationSeconds: 10, prompt: 'a', assetIds: [], videoUrl: 'https://cdn.example.com/c1.mp4' }] },
    2: {
      assets: [],
      clips: [
        { id: 1, durationSeconds: 10, prompt: 'a', assetIds: [], videoUrl: 'https://cdn.example.com/c2.mp4' },
        { id: 2, durationSeconds: 10, prompt: 'b', assetIds: [] },
      ],
    },
    3: { assets: [], clips: [{ id: 1, durationSeconds: 10, prompt: 'a', assetIds: [] }] },
  }

  const navItems = buildEpisodeNavItems(project)
  assert.equal(navItems.length, 4)
  assert.deepEqual(navItems[0], { number: 1, title: '开端', statusTone: 'composed', statusText: '已合成' })
  assert.deepEqual(navItems[1], { number: 2, title: '转折', statusTone: 'video', statusText: '1/2 视频' })
  assert.deepEqual(navItems[2], { number: 3, title: '', statusTone: 'storyboard', statusText: '1 段分镜' })
  assert.deepEqual(navItems[3], { number: 4, title: '', statusTone: 'pending', statusText: '待拆分镜' })
})

test('applyProjectMeta updates settings and cover in store', () => {
  setActivePinia(createPinia())
  const store = useStudioStore()
  const id = store.createProject({
    mode: 'story',
    settings: {
      name: '旧名称',
      ratio: '16:9',
      visualStyle: 'live-action',
      language: 'zh-CN',
      episodeCount: 5,
      maxSegmentDuration: 15,
      backgroundMusic: true,
    },
    story: '故事梗概',
  })

  const ok = store.applyProjectMeta(id, {
    id,
    name: '新短剧名',
    settings: {
      name: '新短剧名',
      ratio: '9:16',
      language: 'zh-CN',
      visualStyle: 'noir-comic',
      episodeCount: 5,
      maxSegmentDuration: 30,
      backgroundMusic: false,
      imageModelId: 'gpt-image-2',
      imageTier: '2k',
      videoModelId: 'vid-30s',
    },
    coverUrl: 'https://cdn.example.com/custom-cover.png',
    coverKey: 'framedrama/1/images/custom-cover.png',
    updatedAt: '2026-11-25T00:00:00Z',
  })

  assert.equal(ok, true)
  const project = store.getProject(id)!
  assert.equal(project.creation.settings.name, '新短剧名')
  assert.equal(project.creation.settings.ratio, '9:16')
  assert.equal(project.creation.settings.visualStyle, 'noir-comic')
  assert.equal(project.creation.settings.maxSegmentDuration, 30)
  assert.equal(project.creation.settings.backgroundMusic, false)
  assert.equal(project.creation.settings.imageModelId, 'gpt-image-2')
  assert.equal(project.creation.settings.imageTier, '2k')
  assert.equal(project.creation.settings.videoModelId, 'vid-30s')
  assert.equal(project.coverUrl, 'https://cdn.example.com/custom-cover.png')
  assert.equal(project.coverKey, 'framedrama/1/images/custom-cover.png')
})
