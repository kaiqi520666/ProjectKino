import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import { episodePage, episodePageSize, readEpisode } from '../src/features/studio/studio-project.ts'
import { useStudioStore } from '../src/features/studio/studio-store.ts'

const settings = { name: 'Night Files', ratio: '16:9', visualStyle: 'live-action', language: 'zh-CN', episodeCount: 7, maxSegmentDuration: 15, backgroundMusic: true } as const

test('keeps the submitted settings and original story with a sparse episode draft', () => {
  setActivePinia(createPinia())
  const store = useStudioStore()
  const id = store.createProject({ mode: 'story', settings, story: 'A note arrives at night.' })
  const project = store.getProject(id)!
  assert.deepEqual(project.creation, { mode: 'story', settings, story: 'A note arrives at night.' })
  assert.equal(project.scriptConfirmed, false)
  assert.equal(readEpisode(project, 1).example, true)
  assert.equal(readEpisode(project, 7).script, '')
})

test('preserves a local source file and requires reconfirmation after saving an edit', () => {
  setActivePinia(createPinia())
  const store = useStudioStore()
  const file = new File(['Script text'], 'source.txt', { type: 'text/plain' })
  const id = store.createProject({ mode: 'upload', settings, file })
  const project = store.getProject(id)!
  assert.equal(project.creation.mode === 'upload' && project.creation.file, file)
  store.confirmScript(id)
  assert.equal(project.scriptConfirmed, true)
  assert.equal(store.saveEpisode(id, { number: 8, title: 'Out of range', summary: '', script: '' }), false)
  assert.equal(project.scriptConfirmed, true)
  assert.equal(store.saveEpisode(id, { number: 7, title: ' Finale ', summary: 'End', script: 'A door closes.' }), true)
  assert.equal(readEpisode(project, 7).title, 'Finale')
  assert.equal(project.scriptConfirmed, false)
})

test('episode pagination never eagerly creates the full list', () => {
  assert.deepEqual(episodePage(7, 1), [1, 2, 3, 4, 5, 6, 7])
  assert.deepEqual(episodePage(14, 2), [13, 14])
  assert.equal(episodePage(Number.MAX_SAFE_INTEGER, 1).length, episodePageSize)
})

test('appending an episode extends only its project and requires reconfirmation', () => {
  setActivePinia(createPinia())
  const store = useStudioStore()
  const creation = { mode: 'story', settings, story: 'A note arrives at night.' } as const
  const id = store.createProject(creation)
  const otherId = store.createProject({ ...creation })
  const project = store.getProject(id)!
  const originalEpisode = { ...readEpisode(project, 1) }
  store.confirmScript(id)

  assert.equal(store.appendEpisode(id), 8)
  assert.equal(project.creation.settings.episodeCount, 8)
  assert.equal(store.getProject(otherId)?.creation.settings.episodeCount, 7)
  assert.equal(project.scriptConfirmed, false)
  assert.deepEqual(readEpisode(project, 1), originalEpisode)
  assert.equal(readEpisode(project, 8).script, '')
  assert.equal(store.saveEpisode(id, { ...readEpisode(project, 8), script: 'A second note arrives.' }), true)
})

test('storyboard previews respect the project cap and preserve episode-specific prompt edits', () => {
  setActivePinia(createPinia())
  const store = useStudioStore()
  for (const cap of [15, 30] as const) {
    const id = store.createProject({ mode: 'story', settings: { ...settings, maxSegmentDuration: cap }, story: 'A note arrives at night.' })
    const project = store.getProject(id)!
    store.generateExampleStoryboard(id, 1)
    assert.equal(project.storyboards?.[1], undefined)
    store.confirmScript(id)
    store.generateExampleStoryboard(id, 8)
    assert.equal(project.storyboards?.[8], undefined)
    store.generateExampleStoryboard(id, 1)
    const first = store.getProject(id)?.storyboards?.[1]
    assert.ok(first)
    assert.equal(Math.max(...first.clips.map(({ durationSeconds }) => durationSeconds)), cap)
    assert.ok(first.clips.every(({ videoUrl }) => !videoUrl))
    assert.ok(first.clips.every(({ assetIds }) => assetIds.every((id) => first.assets.some((asset) => asset.id === id))))

    store.saveClipPrompt(id, 1, 2, 'Revised video prompt')
    store.generateExampleStoryboard(id, 1)
    store.generateExampleStoryboard(id, 2)
    assert.equal(store.getProject(id)?.storyboards?.[1]?.clips[1]?.prompt, 'Revised video prompt')
    assert.notEqual(project.storyboards?.[2]?.clips[1]?.prompt, 'Revised video prompt')
  }
})

test('removing an asset only changes the requested project and removes it once', () => {
  setActivePinia(createPinia())
  const store = useStudioStore()
  const creation = { mode: 'story', settings, story: 'A note arrives at night.' } as const
  const id = store.createProject(creation)
  const otherId = store.createProject(creation)
  store.loadExampleAssets(id)
  store.loadExampleAssets(otherId)
  const project = store.getProject(id)!
  const assetIds = project.assets!.map(({ id }) => id)
  const [removedId, ...remaining] = assetIds
  assert.ok(removedId)

  assert.equal(store.removeAsset(id, removedId), true)
  assert.equal(store.removeAsset(id, removedId), false)
  assert.deepEqual(project.assets?.map(({ id }) => id), remaining)
  assert.deepEqual(store.getProject(otherId)?.assets?.map(({ id }) => id), assetIds)
})

test('asset edits, additions, and removals stay synced with assetResult for storyboard requests', () => {
  setActivePinia(createPinia())
  const store = useStudioStore()
  const id = store.createProject({ mode: 'story', settings, story: 'A note arrives at night.' })
  store.applyAssets(id, {
    settings,
    assets: [
      { id: 'C01', kind: 'character', name: '陈九河', description: '香头', prompt: '原提示词', episodeNumbers: [1], voice: '旧音色' },
      { id: 'S01', kind: 'scene', name: '坟地', description: '山村坟地', prompt: '原场景词', episodeNumbers: [1], voice: '' },
    ],
  })
  const project = store.getProject(id)!

  assert.equal(store.saveAsset(id, 'C01', {
    name: ' 陈九河（改） ',
    description: ' 关外老香头 ',
    prompt: ' 新提示词 ',
    voice: ' 低沉东北男中音 ',
  }), true)
  const updated = project.assetResult?.assets.find(({ id }) => id === 'C01')
  assert.equal(updated?.name, '陈九河（改）')
  assert.equal(updated?.description, '关外老香头')
  assert.equal(updated?.prompt, '新提示词')
  assert.equal(updated?.voice, '低沉东北男中音')

  // Clearing optional fields keeps backend non-empty Text constraints intact while allowing voice to clear.
  assert.equal(store.saveAsset(id, 'C01', { name: '陈九河', description: '', prompt: '', voice: '' }), true)
  assert.equal(updated?.description, '关外老香头')
  assert.equal(updated?.prompt, '新提示词')
  assert.equal(updated?.voice, '')

  assert.equal(store.createAsset(id, 'prop', { name: ' 铜铃 ', description: '', prompt: '', voice: 'ignored' }), true)
  assert.equal(project.assetResult?.assets.length, 3)
  const created = project.assetResult?.assets[2]
  assert.equal(created?.name, '铜铃')
  assert.equal(created?.description, '铜铃')
  assert.equal(created?.prompt, '铜铃')
  assert.equal(created?.voice, '')

  assert.equal(store.removeAsset(id, 'S01'), true)
  assert.deepEqual(project.assetResult?.assets.map(({ id }) => id), ['C01', created!.id])
})

test('replaceEpisode updates only the target episode and clears only its storyboard, while replaceScript resets downstream data', () => {
  setActivePinia(createPinia())
  const store = useStudioStore()
  const ep1 = {
    number: 1, title: '旧第1集', summary: '旧梗概1', targetSeconds: 120,
    hook: 'h1', cliff: 'c1', hookBeat: [1, 1] as [number, number], seconds: 110, scenes: [], script: '旧剧本1',
  }
  const ep2 = {
    number: 2, title: '旧第2集', summary: '旧梗概2', targetSeconds: 120,
    hook: 'h2', cliff: 'c2', hookBeat: [1, 1] as [number, number], seconds: 112, scenes: [], script: '旧剧本2',
  }
  const initialScript = { settings: { ...settings, episodeCount: 2 }, outline: {}, episodes: [ep1, ep2] }
  const id = store.createProjectFromScript(
    { mode: 'story', settings: { ...settings, episodeCount: 2 }, story: '原始故事' },
    initialScript,
    '原始故事',
  )
  store.confirmScript(id)
  store.applyAssets(id, {
    settings: { ...settings, episodeCount: 2 },
    assets: [{ id: 'C01', kind: 'character', name: '陈默', description: '主角', prompt: 'p', episodeNumbers: [1, 2], voice: 'v' }],
  })
  store.applyStoryboard(id, {
    settings: { ...settings, episodeCount: 2 },
    episodes: [
      { number: 1, assets: [{ id: 'C01', kind: 'character', name: '陈默' }], clips: [{ id: 1, durationSeconds: 10, prompt: 'p1', assetIds: ['C01'] }] },
      { number: 2, assets: [{ id: 'C01', kind: 'character', name: '陈默' }], clips: [{ id: 1, durationSeconds: 10, prompt: 'p2', assetIds: ['C01'] }] },
    ],
  })

  const project = store.getProject(id)!
  assert.equal(project.sourceText, '原始故事')

  // Rewrite episode 2 only.
  const rewrittenEp2 = { ...ep2, title: '新第2集', script: '重写后的第2集' }
  assert.equal(store.replaceEpisode(id, rewrittenEp2), true)
  assert.equal(project.episodes[2]?.title, '新第2集')
  assert.equal(project.scriptResult?.episodes.find((item) => item.number === 2)?.script, '重写后的第2集')
  assert.equal(project.storyboards?.[2], undefined)
  assert.ok(project.storyboards?.[1])
  assert.equal(project.assets?.length, 1)
  assert.equal(project.scriptConfirmed, false)

  // Append episode 3 preserves existing assets and episode 1 storyboard.
  const ep3 = {
    number: 3, title: '续写第3集', summary: '新梗概3', targetSeconds: 120,
    hook: 'h3', cliff: 'c3', hookBeat: [1, 1] as [number, number], seconds: 115, scenes: [], script: '续写剧本3',
  }
  const appendedNumber = store.applyAppendedEpisode(id, {
    settings: { ...settings, episodeCount: 3 },
    outline: {},
    episodes: [ep1, rewrittenEp2, ep3],
  })
  assert.equal(appendedNumber, 3)
  assert.equal(project.creation.settings.episodeCount, 3)
  assert.equal(project.episodes[3]?.title, '续写第3集')
  assert.ok(project.storyboards?.[1])
  assert.equal(project.assets?.length, 1)

  // Regenerate whole story clears stale assets and storyboards.
  const newEp1 = { ...ep1, title: '全新第1集', script: '全新剧本1' }
  assert.equal(store.replaceScript(id, { settings: { ...settings, episodeCount: 1 }, outline: {}, episodes: [newEp1] }), true)
  assert.equal(project.creation.settings.episodeCount, 1)
  assert.equal(project.episodes[1]?.title, '全新第1集')
  assert.equal(project.episodes[2], undefined)
  assert.equal(project.assets, undefined)
  assert.equal(project.assetResult, undefined)
  assert.equal(project.storyboards, undefined)
})

test('applyAssets preserves uploaded images, custom assets, and edits during incremental sync, and applyStoryboard carries imageUrl', () => {
  setActivePinia(createPinia())
  const store = useStudioStore()
  const id = store.createProject({ mode: 'story', settings, story: 'A note arrives at night.' })
  store.applyAssets(id, {
    settings,
    assets: [
      { id: 'C01', kind: 'character', name: '陈九河', description: '旧描述', prompt: '旧提示词', episodeNumbers: [1], voice: '旧音色' },
    ],
  })
  assert.equal(store.saveAsset(id, 'C01', {
    name: '陈九河（定妆）',
    description: '手改描述',
    prompt: '手改提示词',
    voice: '手改音色',
    imageUrl: 'data:image/png;base64,AAA',
  }), true)
  assert.equal(store.createAsset(id, 'prop', { name: '手工道具', description: '自建', prompt: '自建词', imageUrl: 'data:image/png;base64,BBB' }), true)
  const project = store.getProject(id)!
  const customId = project.assets![1]!.id

  // Incremental sync keeps edits, imageUrl, and manually added custom assets while appending C02.
  store.applyAssets(id, {
    settings,
    assets: [
      { id: 'C01', kind: 'character', name: '陈九河', description: '新描述', prompt: '新提示词', episodeNumbers: [1, 2], voice: '新音色' },
      { id: 'C02', kind: 'character', name: '栓子', description: '新角色', prompt: '栓子词', episodeNumbers: [2], voice: '少年音' },
    ],
  }, { preserveEdits: true })

  assert.deepEqual(project.assets?.map((item) => item.id), ['C01', 'C02', customId])
  assert.equal(project.assets?.[0]?.name, '陈九河（定妆）')
  assert.equal(project.assets?.[0]?.prompt, '手改提示词')
  assert.equal(project.assets?.[0]?.imageUrl, 'data:image/png;base64,AAA')
  assert.deepEqual(project.assetResult?.assets.find((item) => item.id === 'C01')?.episodeNumbers, [1, 2])
  assert.equal(project.assetResult?.assets.find((item) => item.id === 'C01')?.prompt, '手改提示词')

  // Full refresh updates AI text while still preserving imageUrl and custom assets.
  store.applyAssets(id, {
    settings,
    assets: [
      { id: 'C01', kind: 'character', name: '陈九河', description: '刷新描述', prompt: '刷新提示词', episodeNumbers: [1, 2], voice: '刷新音色' },
      { id: 'C02', kind: 'character', name: '栓子', description: '刷新角色', prompt: '刷新栓子', episodeNumbers: [2], voice: '少年音' },
    ],
  })
  assert.equal(project.assets?.[0]?.prompt, '刷新提示词')
  assert.equal(project.assets?.[0]?.imageUrl, 'data:image/png;base64,AAA')
  assert.ok(project.assets?.some((item) => item.id === customId))

  // Storyboard inherits imageUrl from project.assets.
  store.applyStoryboard(id, {
    settings,
    episodes: [
      {
        number: 1,
        assets: [{ id: 'C01', kind: 'character', name: '陈九河' }],
        clips: [{ id: 1, durationSeconds: 10, prompt: 'p', assetIds: ['C01'] }],
      },
    ],
  })
  assert.equal(project.storyboards?.[1]?.assets[0]?.imageUrl, 'data:image/png;base64,AAA')
})

test('saveStructuredEpisode syncs scenes, rendered script, seconds, speakers, and clears scriptEdited flag', () => {
  setActivePinia(createPinia())
  const store = useStudioStore()
  const scriptResult = {
    settings: { ...settings, episodeCount: 1 },
    outline: {
      characters: [
        { id: 'C01', name: '林晚' },
        { id: 'C02', name: '物业老张' },
      ],
      scenes: [{ id: 'S01', name: '302室卧室', kind: '内景', time: '夜' }],
    },
    episodes: [
      {
        number: 1,
        title: '三短一长',
        summary: '梗概',
        targetSeconds: 120,
        hook: '敲墙声',
        cliff: '门缝纸条',
        hookBeat: [1, 3] as [number, number],
        seconds: 10,
        scenes: [
          {
            sceneId: 'S01',
            lighting: '昏暗台灯',
            characters: ['C01'],
            props: [],
            flow: [
              { action: '林晚关掉台灯。' },
              { speaker: 'C01', delivery: '低声', line: '又来了……' },
              { action: '墙面传来三短一长。' },
            ],
          },
        ],
        script: '旧正文',
      },
    ],
  }
  const id = store.createProjectFromScript({ mode: 'story', settings: { ...settings, episodeCount: 1 }, story: '故事' }, scriptResult)
  const project = store.getProject(id)!

  const saved = store.saveStructuredEpisode(id, 1, '三短一长（改）', [
    {
      sceneId: 'S01',
      lighting: ' 路灯冷光 ',
      characters: ['C01'],
      props: [],
      flow: [
        { action: ' 林晚猛地坐起身。 ' },
        { speaker: 'C02', delivery: '门外喊', line: '302室开一下门！' },
        { action: '   ' },
      ],
    },
  ])
  assert.equal(saved, true)
  assert.equal(project.scriptEdited, false)
  assert.equal(project.episodes[1]?.title, '三短一长（改）')
  assert.match(project.episodes[1]?.script ?? '', /第一场/)
  assert.match(project.episodes[1]?.script ?? '', /内景 · 302室卧室 · 夜/)
  assert.match(project.episodes[1]?.script ?? '', /物业老张：302室开一下门！/)

  const updated = project.scriptResult!.episodes[0]!
  assert.equal(updated.scenes[0]?.lighting, '路灯冷光')
  assert.deepEqual(updated.scenes[0]?.characters, ['C01', 'C02'])
  assert.equal(updated.scenes[0]?.flow.length, 2)
  assert.deepEqual(updated.hookBeat, [1, 2])
  assert.ok(updated.seconds > 2.5)
})

test('hydrateProjectDetail maps persisted episodes, assets, storyboard references, and active jobs cleanly', () => {
  setActivePinia(createPinia())
  const store = useStudioStore()
  const detail = {
    id: 'proj-uuid-1',
    name: '搬进新家',
    mode: 'story' as const,
    sourceText: '半夜三短一长敲墙声',
    settings: { ...settings, name: '搬进新家', episodeCount: 1 },
    outline: {
      characters: [{ id: 'C01', name: '林晚' }],
      scenes: [{ id: 'S01', name: '卧室', kind: '内景', time: '夜' }],
    },
    scriptConfirmed: true,
    episodes: [
      {
        id: 'ep-uuid-1',
        number: 1,
        title: '三短一长',
        summary: '梗概',
        targetSeconds: 120,
        seconds: 112.5,
        hook: 'h',
        cliff: 'c',
        hookBeat: [1, 1] as [number, number],
        scenes: [{ sceneId: 'S01', lighting: '暗光', characters: ['C01'], props: [], flow: [{ action: '睁眼' }] }],
        script: '第一场',
        warnings: [],
      },
    ],
    assets: [
      {
        id: 'asset-uuid-1',
        assetCode: 'C01',
        kind: 'character' as const,
        name: '林晚',
        description: '主角',
        prompt: '三视图词',
        voice: '清冷女声',
        episodeNumbers: [1],
        imageUrl: 'https://oss.example/framedrama/c01.png',
        imageStatus: 'ready',
        imageHistory: [
          {
            id: 'h-1',
            url: 'https://oss.example/framedrama/c01-old.png',
            key: 'framedrama/c01-old.png',
            source: 'ai' as const,
            modelId: 'gpt-image-2',
            tier: '1k',
            ratio: '16:9',
            createdAt: '2026-11-21T00:00:00Z',
          },
          {
            id: 'h-2',
            url: 'https://oss.example/framedrama/c01.png',
            key: 'framedrama/c01.png',
            source: 'ai' as const,
            modelId: 'gpt-image-2',
            tier: '2k',
            ratio: '16:9',
            createdAt: '2026-11-21T00:05:00Z',
          },
        ],
        lastJobId: 'job-review-1',
        lastJobStatus: 'review' as const,
        lastJobError: '[HTTP 503] 上游超时待核对',
      },
    ],
    storyboards: {
      '1': [
        {
          id: 'clip-uuid-1',
          episodeId: 'ep-uuid-1',
          clipIndex: 1,
          durationSeconds: 12,
          prompt: '@[图片1] = 林晚',
          promptCustomized: false,
          references: [{ index: 1, assetId: 'asset-uuid-1', assetCode: 'C01', name: '林晚', kind: 'character' as const }],
          videoStatus: 'none',
          videoHistory: [],
        },
      ],
    },
    activeJobs: [],
    createdAt: '2026-11-21T00:00:00Z',
    updatedAt: '2026-11-21T00:00:00Z',
  }

  const hydrated = store.hydrateProjectDetail(detail)
  assert.equal(hydrated.persisted, true)
  assert.equal(hydrated.loadedDetail, true)
  assert.equal(hydrated.assets?.[0]?.id, 'C01')
  assert.equal(hydrated.assets?.[0]?.backendId, 'asset-uuid-1')
  assert.equal(hydrated.assets?.[0]?.imageHistory?.length, 2)
  assert.equal(hydrated.assets?.[0]?.lastJobStatus, 'review')
  assert.equal(hydrated.assets?.[0]?.lastJobError, '[HTTP 503] 上游超时待核对')
  assert.equal(hydrated.storyboards?.[1]?.clips[0]?.backendId, 'clip-uuid-1')
  assert.equal(hydrated.storyboards?.[1]?.assets[0]?.imageUrl, 'https://oss.example/framedrama/c01.png')

  store.applyPersistedAsset(detail.id, {
    ...detail.assets[0],
    imageUrl: 'https://oss.example/framedrama/c01-old.png',
    imageTier: '1k',
  })
  assert.equal(hydrated.assets?.[0]?.imageUrl, 'https://oss.example/framedrama/c01-old.png')
  assert.equal(hydrated.storyboards?.[1]?.assets[0]?.imageUrl, 'https://oss.example/framedrama/c01-old.png')
})

test('groupStudioAssets and findAssetSiblings group root and variants across character, scene, and prop', async () => {
  const { assetDisplayName, findAssetSiblings, findParentAsset, groupStudioAssets } = await import(
    '../src/features/studio/studio-assets.ts'
  )
  const assets = [
    {
      id: 'C01',
      backendId: 'u-root',
      kind: 'character' as const,
      name: '林薇',
      description: '主造型',
      prompt: '默认',
      imageUrl: 'https://img.example/root.png',
    },
    {
      id: 'v1-code',
      backendId: 'u-v1',
      parentAssetId: 'u-root',
      variantLabel: '晚宴礼服',
      kind: 'character' as const,
      name: '林薇',
      description: '晚宴',
      prompt: '晚宴礼服',
    },
    {
      id: 'v2-code',
      backendId: 'u-v2',
      parentAssetId: 'u-root',
      variantLabel: '战损',
      kind: 'character' as const,
      name: '林薇',
      description: '战损',
      prompt: '战损',
    },
    {
      id: 'C02',
      backendId: 'u-other',
      kind: 'character' as const,
      name: '周明远',
      description: '反派',
      prompt: '西装',
    },
  ]

  const grouped = groupStudioAssets(assets)
  assert.equal(grouped.length, 2)
  assert.equal(grouped[0].root.backendId, 'u-root')
  assert.equal(grouped[0].items.length, 3)
  assert.equal(grouped[1].root.backendId, 'u-other')
  assert.equal(grouped[1].items.length, 1)

  assert.equal(assetDisplayName(assets[0]), '林薇')
  assert.equal(assetDisplayName(assets[1]), '林薇 · 晚宴礼服')
  assert.equal(findParentAsset(assets, assets[1])?.backendId, 'u-root')
  assert.equal(findAssetSiblings(assets, assets[1]).length, 3)
  assert.equal(findAssetSiblings(assets, assets[3]).length, 1)
})

test('planAssetImageWaves partitions roots and variants for two-phase and roots-only modes', async () => {
  const { planAssetImageWaves } = await import('../src/features/studio/studio-assets.ts')
  const assets = [
    {
      id: 'C01',
      backendId: 'u-root-ready',
      kind: 'character' as const,
      name: '林晓',
      description: '已有主图',
      prompt: '默认',
      imageUrl: 'https://cdn.example/c01.png',
    },
    {
      id: 'C01_v1',
      backendId: 'u-v1-ready-parent',
      parentAssetId: 'u-root-ready',
      variantLabel: '便装',
      kind: 'character' as const,
      name: '林晓',
      description: '便装',
      prompt: '便装提示词',
    },
    {
      id: 'C02',
      backendId: 'u-root-missing',
      kind: 'character' as const,
      name: '陈国栋',
      description: '缺主图',
      prompt: '默认',
    },
    {
      id: 'C02_v1',
      backendId: 'u-v1-missing-parent',
      parentAssetId: 'u-root-missing',
      variantLabel: '雨衣',
      kind: 'character' as const,
      name: '陈国栋',
      description: '雨衣',
      prompt: '雨衣提示词',
    },
  ]

  // Default two-phase: C01_v1 runs in Wave 1 (parent already has image and isn't selected),
  // C02 runs in Wave 1, C02_v1 waits for Wave 2.
  const twoPhase = planAssetImageWaves(assets, ['u-v1-ready-parent', 'u-root-missing', 'u-v1-missing-parent'])
  assert.deepEqual(twoPhase.wave1Ids, ['u-v1-ready-parent', 'u-root-missing'])
  assert.deepEqual(twoPhase.wave2VariantIds, ['u-v1-missing-parent'])
  assert.deepEqual(twoPhase.orphanVariantIds, [])

  // Redrawing parent C01 together with C01_v1 defers C01_v1 to Wave 2
  const redrawBoth = planAssetImageWaves(assets, ['u-root-ready', 'u-v1-ready-parent'])
  assert.deepEqual(redrawBoth.wave1Ids, ['u-root-ready'])
  assert.deepEqual(redrawBoth.wave2VariantIds, ['u-v1-ready-parent'])

  // rootsOnly mode skips all variants
  const rootsOnly = planAssetImageWaves(assets, ['u-root-ready', 'u-v1-ready-parent', 'u-root-missing', 'u-v1-missing-parent'], { rootsOnly: true })
  assert.deepEqual(rootsOnly.wave1Ids, ['u-root-ready', 'u-root-missing'])
  assert.deepEqual(rootsOnly.wave2VariantIds, [])

  // Selecting only a variant whose parent has no image surfaces missingParentIds
  const orphan = planAssetImageWaves(assets, ['u-v1-missing-parent'])
  assert.deepEqual(orphan.orphanVariantIds, ['u-v1-missing-parent'])
  assert.deepEqual(orphan.missingParentIds, ['u-root-missing'])
})
