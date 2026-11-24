import { acceptHMRUpdate, defineStore } from 'pinia'
import { ref } from 'vue'
import { defaultEpisodeDuration, defaultSegmentDuration } from './components/drama-creation.ts'
import type { DramaCreation, DramaSettings } from './components/drama-creation.ts'
import type {
  AssetResult,
  BackendEpisode,
  BackendScene,
  BackendSettings,
  PersistedAssetOut,
  PersistedClipOut,
  ProjectDetailOut,
  ProjectMetaOut,
  ProjectSummaryOut,
  ScriptResult,
  StoryboardResult,
} from './api-types.ts'
import { normalizeScenes, renderStructuredScript, scenesSeconds } from './script-structure.ts'
import { createExampleAssets } from './studio-assets.ts'
import type { StudioAsset, StudioAssetDraft, StudioAssetKind } from './studio-assets.ts'
import { isEpisodeNumber, readEpisode } from './studio-project.ts'
import type { StudioEpisode, StudioProject, StudioProjectProgressStats } from './studio-project.ts'
import { createExampleStoryboard } from './studio-storyboard.ts'
import type { EpisodeStoryboard, StoryboardAsset } from './studio-storyboard.ts'

function normalizeAssetDraft(draft: StudioAssetDraft): StudioAssetDraft {
  return {
    name: draft.name.trim(),
    description: draft.description.trim(),
    prompt: draft.prompt.trim(),
    imageUrl: draft.imageUrl,
    voice: draft.voice?.trim() ?? '',
  }
}

function toDramaSettings(settings: BackendSettings): DramaSettings {
  const { name, ratio, language, visualStyle, episodeCount, maxSegmentDuration } = settings
  const tier = settings.imageTier
  return {
    name,
    ratio,
    language,
    visualStyle,
    episodeCount,
    maxSegmentDuration,
    secondsPerEpisode: settings.secondsPerEpisode ?? defaultEpisodeDuration,
    backgroundMusic: settings.backgroundMusic ?? true,
    ...(settings.imageModelId ? { imageModelId: settings.imageModelId } : {}),
    ...(tier === 'web' || tier === '1k' || tier === '2k' || tier === '4k' ? { imageTier: tier } : {}),
    ...(settings.videoModelId ? { videoModelId: settings.videoModelId } : {}),
  }
}

export const useStudioStore = defineStore('studio', () => {
  const projects = ref<StudioProject[]>([])

  function createProject(creation: DramaCreation) {
    const id = crypto.randomUUID()
    projects.value.unshift({
      id,
      creation,
      scriptConfirmed: false,
      episodes: {
        1: {
          number: 1,
          title: '第 1 集',
          summary: '主角收到一条来自陌生号码的消息。',
          script: '内景 · 书房 · 夜\n\n窗外下着雨。手机亮起，一条陌生号码发来的消息出现在屏幕上。\n\n主角放下手中的书，拿起手机。',
          example: true,
        },
      },
    })
    return id
  }

  function getProject(id: string) {
    return projects.value.find((project) => project.id === id)
  }

  function clearProjects() {
    projects.value = []
  }

  function removeProject(id: string) {
    const index = projects.value.findIndex((project) => project.id === id)
    if (index < 0) return false
    projects.value.splice(index, 1)
    return true
  }

  function summaryToProgressStats(summary: ProjectSummaryOut): StudioProjectProgressStats {
    const epCount = summary.episodeCount || 0
    const planned = Math.max(summary.settings.episodeCount || 0, summary.plannedEpisodeCount ?? epCount, epCount)
    return {
      episodeCount: epCount,
      plannedEpisodeCount: planned,
      assetCount: summary.assetCount || 0,
      assetImageReadyCount: summary.assetImageReadyCount ?? 0,
      storyboardEpisodeCount: summary.storyboardEpisodeCount ?? 0,
      clipCount: summary.clipCount ?? 0,
      clipVideoReadyCount: summary.clipVideoReadyCount ?? 0,
      composedEpisodeCount: summary.composedEpisodeCount ?? 0,
    }
  }

  function syncProjectSummaries(summaries: ProjectSummaryOut[]) {
    const existingById = new Map(projects.value.map((item) => [item.id, item]))
    const next: StudioProject[] = []
    for (const summary of summaries) {
      const prev = existingById.get(summary.id)
      const settings = toDramaSettings({
        ...summary.settings,
        name: summary.name,
        episodeCount: Math.max(summary.settings.episodeCount || 1, summary.episodeCount || 1),
      })
      const progressStats = summaryToProgressStats(summary)
      if (prev && prev.loadedDetail) {
        prev.creation.settings = settings
        prev.scriptConfirmed = summary.scriptConfirmed
        prev.coverUrl = summary.coverUrl ?? null
        prev.coverKey = summary.coverKey ?? null
        prev.autoCoverUrl = summary.autoCoverUrl ?? prev.autoCoverUrl ?? null
        prev.updatedAt = summary.updatedAt
        prev.progressStats = progressStats
        prev.persisted = true
        next.push(prev)
      } else {
        next.push({
          id: summary.id,
          persisted: true,
          loadedDetail: false,
          creation: { mode: 'story', settings, story: '' },
          episodes: prev?.episodes ?? {},
          coverUrl: summary.coverUrl ?? null,
          coverKey: summary.coverKey ?? null,
          autoCoverUrl: summary.autoCoverUrl ?? null,
          updatedAt: summary.updatedAt,
          progressStats,
          scriptConfirmed: summary.scriptConfirmed,
        })
      }
    }
    // 保留尚未落库的纯本地示例草稿。
    for (const item of projects.value) {
      if (!item.persisted) next.push(item)
    }
    projects.value = next
  }

  function hydrateProjectDetail(detail: ProjectDetailOut): StudioProject {
    const settings = toDramaSettings({
      ...detail.settings,
      name: detail.name,
      episodeCount: Math.max(detail.settings.episodeCount || 1, detail.episodes.length || 1),
    })

    const episodes: Partial<Record<number, StudioEpisode>> = {}
    const backendEpisodes: BackendEpisode[] = []
    for (const ep of detail.episodes) {
      episodes[ep.number] = {
        number: ep.number,
        title: ep.title,
        summary: ep.summary,
        script: ep.script,
        ...(ep.composedVideoUrl ? { composedVideoUrl: ep.composedVideoUrl } : {}),
        ...(ep.composedDuration != null ? { composedDuration: ep.composedDuration } : {}),
      }
      backendEpisodes.push({
        number: ep.number,
        title: ep.title,
        summary: ep.summary,
        targetSeconds: ep.targetSeconds,
        seconds: ep.seconds,
        hook: ep.hook,
        cliff: ep.cliff,
        hookBeat: ep.hookBeat,
        scenes: ep.scenes,
        script: ep.script,
        warnings: ep.warnings ?? [],
      })
    }

    const scriptResult: ScriptResult | undefined = detail.outline
      ? { settings: detail.settings, outline: detail.outline, episodes: backendEpisodes }
      : undefined

    const uiAssets: StudioAsset[] = detail.assets.map((item) => ({
      id: item.assetCode,
      backendId: item.id,
      ...(item.parentAssetId ? { parentAssetId: item.parentAssetId } : {}),
      ...(item.variantLabel ? { variantLabel: item.variantLabel } : {}),
      kind: item.kind,
      name: item.name,
      description: item.description,
      prompt: item.prompt,
      ...(item.voice ? { voice: item.voice } : {}),
      ...(item.imageUrl ? { imageUrl: item.imageUrl } : {}),
      ...(item.imageModelId ? { imageModelId: item.imageModelId } : {}),
      ...(item.imageTier ? { imageTier: item.imageTier } : {}),
      imageStatus: item.imageStatus,
      imageHistory: item.imageHistory ?? [],
      ...(item.lastJobId ? { lastJobId: item.lastJobId } : {}),
      ...(item.lastJobStatus ? { lastJobStatus: item.lastJobStatus } : {}),
      ...(item.lastJobError ? { lastJobError: item.lastJobError } : {}),
    }))

    const assetResult: AssetResult | undefined = detail.assets.length
      ? {
          settings: detail.settings,
          assets: detail.assets.map((item) => ({
            id: item.assetCode,
            kind: item.kind,
            name: item.name,
            description: item.description || item.name,
            prompt: item.prompt || item.name,
            episodeNumbers: item.episodeNumbers,
            voice: item.voice,
          })),
        }
      : undefined

    const assetByCode = new Map(uiAssets.map((item) => [item.id, item]))
    const assetByBackendId = new Map(uiAssets.filter((item) => item.backendId).map((item) => [item.backendId!, item]))

    const storyboards: Partial<Record<number, EpisodeStoryboard>> = {}
    for (const [epKey, rawClips] of Object.entries(detail.storyboards || {})) {
      const epNum = Number(epKey)
      if (!Number.isSafeInteger(epNum) || !rawClips?.length) continue
      const epAssetMap = new Map<string, StoryboardAsset>()
      const clips = rawClips.map((clip) => {
        const refs = (clip.references ?? []).map((ref) => {
          const code = ref.assetCode || assetByBackendId.get(ref.assetId)?.id || ref.assetId
          const live = assetByCode.get(code) ?? assetByBackendId.get(ref.assetId)
          if (live || ref.kind === 'character' || ref.kind === 'scene' || ref.kind === 'prop') {
            const boardKind = live?.kind ?? (ref.kind === 'character' || ref.kind === 'scene' || ref.kind === 'prop' ? ref.kind : 'prop')
            epAssetMap.set(code, {
              id: code,
              kind: boardKind,
              name: live?.name || ref.name,
              ...(live?.imageUrl ? { imageUrl: live.imageUrl } : {}),
            })
          }
          return {
            index: ref.index,
            assetId: code,
            name: live?.name || ref.name,
            kind: ref.kind,
            ...(ref.mediaKind ? { mediaKind: ref.mediaKind } : {}),
            ...(ref.mediaUrl ? { mediaUrl: ref.mediaUrl } : {}),
            ...(ref.gridLayout ? { gridLayout: ref.gridLayout } : {}),
            ...(ref.cellMapping?.length ? { cellMapping: ref.cellMapping } : {}),
          }
        })
        return {
          id: clip.clipIndex,
          backendId: clip.id,
          durationSeconds: clip.durationSeconds,
          prompt: clip.prompt,
          assetIds: refs.map((ref) => ref.assetId),
          references: refs,
          beats: clip.beats ?? undefined,
          blocking: clip.blocking ?? undefined,
          cuts: clip.cuts ?? undefined,
          previewUrl: clip.previewUrl ?? undefined,
          videoUrl: clip.videoUrl ?? undefined,
          videoModelId: clip.videoModelId ?? undefined,
          videoStatus: clip.videoStatus,
          videoHistory: clip.videoHistory ?? [],
          lastJobId: clip.lastJobId ?? undefined,
          lastJobStatus: clip.lastJobStatus ?? undefined,
          lastJobError: clip.lastJobError ?? undefined,
        }
      })

      // 补充本集剧本中出现的所有资产到左侧「本集资产」栏。
      const epObj = backendEpisodes.find((item) => item.number === epNum)
      if (epObj) {
        for (const scene of epObj.scenes) {
          for (const code of [scene.sceneId, ...scene.characters, ...scene.props]) {
            if (!code || epAssetMap.has(code)) continue
            const live = assetByCode.get(code)
            if (live) {
              epAssetMap.set(code, {
                id: live.id,
                kind: live.kind,
                name: live.name,
                ...(live.imageUrl ? { imageUrl: live.imageUrl } : {}),
              })
            }
          }
        }
      }

      storyboards[epNum] = {
        assets: [...epAssetMap.values()],
        clips,
      }
    }

    const allClips = Object.values(storyboards).flatMap((board) => board?.clips ?? [])
    const autoCoverCandidate =
      uiAssets.find((a) => !a.parentAssetId && a.kind === 'scene' && a.imageUrl)?.imageUrl
      ?? uiAssets.find((a) => !a.parentAssetId && a.kind === 'character' && a.imageUrl)?.imageUrl
      ?? uiAssets.find((a) => !a.parentAssetId && a.imageUrl)?.imageUrl
      ?? uiAssets.find((a) => a.imageUrl)?.imageUrl
      ?? allClips.find((c) => c.previewUrl)?.previewUrl
      ?? null

    const progressStats: StudioProjectProgressStats = {
      episodeCount: detail.episodes.length,
      plannedEpisodeCount: settings.episodeCount,
      assetCount: uiAssets.length,
      assetImageReadyCount: uiAssets.filter((a) => Boolean(a.imageUrl)).length,
      storyboardEpisodeCount: Object.keys(storyboards).length,
      clipCount: allClips.length,
      clipVideoReadyCount: allClips.filter((c) => Boolean(c.videoUrl)).length,
      composedEpisodeCount: detail.episodes.filter((ep) => Boolean(ep.composedVideoUrl)).length,
    }

    const hydrated: StudioProject = {
      id: detail.id,
      persisted: true,
      loadedDetail: true,
      creation: { mode: 'story', settings, story: detail.sourceText },
      episodes,
      assets: uiAssets.length ? uiAssets : undefined,
      storyboards: Object.keys(storyboards).length ? storyboards : undefined,
      coverUrl: detail.coverUrl ?? null,
      coverKey: detail.coverKey ?? null,
      autoCoverUrl: autoCoverCandidate,
      progressStats,
      scriptConfirmed: detail.scriptConfirmed,
      scriptResult,
      assetResult,
      sourceText: detail.sourceText,
      scriptEdited: false,
      activeJobs: detail.activeJobs,
    }

    const idx = projects.value.findIndex((item) => item.id === detail.id)
    if (idx >= 0) projects.value[idx] = hydrated
    else projects.value.unshift(hydrated)
    return hydrated
  }

  function createProjectFromScript(creation: DramaCreation, result: ScriptResult, sourceText?: string) {
    const id = crypto.randomUUID()
    const episodes: Partial<Record<number, StudioEpisode>> = {}
    for (const episode of result.episodes) {
      episodes[episode.number] = {
        number: episode.number,
        title: episode.title,
        summary: episode.summary,
        script: episode.script,
      }
    }
    const settings = toDramaSettings(result.settings)
    projects.value.unshift({
      id,
      creation: creation.mode === 'story'
        ? { mode: 'story', settings, story: creation.story }
        : { mode: 'upload', settings, file: creation.file },
      episodes,
      scriptConfirmed: false,
      scriptResult: result,
      sourceText: sourceText ?? (creation.mode === 'story' ? creation.story : undefined),
    })
    return id
  }

  function replaceScript(id: string, result: ScriptResult, sourceText?: string) {
    const project = getProject(id)
    if (!project) return false

    const episodes: Partial<Record<number, StudioEpisode>> = {}
    for (const episode of result.episodes) {
      episodes[episode.number] = {
        number: episode.number,
        title: episode.title,
        summary: episode.summary,
        script: episode.script,
      }
    }
    project.creation.settings = toDramaSettings(result.settings)
    project.episodes = episodes
    project.scriptResult = result
    project.scriptConfirmed = false
    project.scriptEdited = false
    if (sourceText !== undefined) project.sourceText = sourceText
    // 重生成全剧会变更角色/场景/道具编号，清空旧资产与旧分镜防 ID 错乱。
    project.assets = undefined
    project.assetResult = undefined
    project.storyboards = undefined
    return true
  }

  function replaceEpisode(id: string, episode: BackendEpisode) {
    const project = getProject(id)
    if (!project?.scriptResult) return false

    project.episodes[episode.number] = {
      number: episode.number,
      title: episode.title,
      summary: episode.summary,
      script: episode.script,
    }
    const list = project.scriptResult.episodes
    const index = list.findIndex((item) => item.number === episode.number)
    if (index >= 0) list[index] = episode
    else {
      list.push(episode)
      list.sort((a, b) => a.number - b.number)
    }
    if (project.storyboards?.[episode.number]) {
      delete project.storyboards[episode.number]
    }
    project.scriptConfirmed = false
    return true
  }

  function applyAppendedEpisode(id: string, result: ScriptResult) {
    const project = getProject(id)
    if (!project) return undefined

    project.creation.settings = toDramaSettings(result.settings)
    project.scriptResult = result
    for (const episode of result.episodes) {
      project.episodes[episode.number] ??= {
        number: episode.number,
        title: episode.title,
        summary: episode.summary,
        script: episode.script,
      }
    }
    const latest = result.episodes[result.episodes.length - 1]
    if (latest) {
      project.episodes[latest.number] = {
        number: latest.number,
        title: latest.title,
        summary: latest.summary,
        script: latest.script,
      }
    }
    project.scriptConfirmed = false
    return latest?.number
  }

  function applyAssets(id: string, result: AssetResult, options?: { preserveEdits?: boolean }) {
    const project = getProject(id)
    if (!project) return false

    const prevById = new Map((project.assets ?? []).map((item) => [item.id, item]))
    const prevBackendById = new Map((project.assetResult?.assets ?? []).map((item) => [item.id, item]))
    const resultIds = new Set(result.assets.map((item) => item.id))
    const preserveEdits = options?.preserveEdits ?? false

    const mergedUiAssets = result.assets.map(({ id: assetId, kind, name, description, prompt, voice }) => {
      const prev = prevById.get(assetId)
      if (preserveEdits && prev) {
        return { ...prev }
      }
      return {
        id: assetId,
        kind,
        name,
        description,
        prompt,
        ...(voice ? { voice } : {}),
        ...(prev?.imageUrl ? { imageUrl: prev.imageUrl } : {}),
      }
    })

    const mergedBackendAssets = result.assets.map((entry) => {
      const prev = prevById.get(entry.id)
      if (preserveEdits && prev) {
        const prevBackend = prevBackendById.get(entry.id)
        return {
          ...entry,
          name: prev.name || entry.name,
          description: prev.description || prevBackend?.description || entry.description,
          prompt: prev.prompt || prevBackend?.prompt || entry.prompt,
          voice: entry.kind === 'character' ? (prev.voice ?? '') : '',
        }
      }
      return { ...entry }
    })

    // 保留用户通过「增加资产」手动添加的自定义资产（非剧本 C/S/P 编号）。
    for (const item of project.assets ?? []) {
      if (resultIds.has(item.id) || /^[CSP]\d+$/u.test(item.id)) continue
      mergedUiAssets.push({ ...item })
      const prevBackend = prevBackendById.get(item.id)
      mergedBackendAssets.push(prevBackend
        ? { ...prevBackend }
        : {
            id: item.id,
            kind: item.kind,
            name: item.name,
            description: item.description || item.name,
            prompt: item.prompt || item.name,
            episodeNumbers: [],
            voice: item.kind === 'character' ? (item.voice ?? '') : '',
          })
    }

    project.assets = mergedUiAssets
    project.assetResult = { settings: result.settings, assets: mergedBackendAssets }
    return true
  }

  function applyStoryboard(id: string, result: StoryboardResult) {
    const project = getProject(id)
    if (!project) return false

    const assetById = new Map((project.assets ?? []).map((item) => [item.id, item]))
    project.storyboards ??= {}
    for (const episode of result.episodes) {
      project.storyboards[episode.number] = {
        assets: episode.assets.map(({ id: assetId, kind, name }) => {
          const matched = assetById.get(assetId)
          return {
            id: assetId,
            kind,
            name: matched?.name || name,
            ...(matched?.imageUrl ? { imageUrl: matched.imageUrl } : {}),
          }
        }),
        clips: episode.clips.map((clip) => ({
          ...clip,
          assetIds: [...clip.assetIds],
          references: clip.references?.map((reference) => ({ ...reference })),
          cuts: clip.cuts?.map((cut) => ({ ...cut, beats: [...cut.beats] as [number, number] })),
        })),
      }
    }
    return true
  }

  function renameProject(id: string, value: string) {
    const project = getProject(id)
    const name = value.trim()
    if (!project || !name) return false

    project.creation.settings = { ...project.creation.settings, name }
    return true
  }

  function applyProjectMeta(id: string, meta: ProjectMetaOut) {
    const project = getProject(id)
    if (!project) return false
    const nextSettings = toDramaSettings({
      ...meta.settings,
      name: meta.name,
      episodeCount: Math.max(meta.settings.episodeCount || 1, project.creation.settings.episodeCount || 1),
    })
    project.creation.settings = nextSettings
    project.coverUrl = meta.coverUrl ?? null
    project.coverKey = meta.coverKey ?? null
    if (project.scriptResult) {
      project.scriptResult = {
        ...project.scriptResult,
        settings: { ...project.scriptResult.settings, ...meta.settings, name: meta.name },
      }
    }
    if (project.assetResult) {
      project.assetResult = {
        ...project.assetResult,
        settings: { ...project.assetResult.settings, ...meta.settings, name: meta.name },
      }
    }
    return true
  }

  function appendEpisode(id: string) {
    const project = getProject(id)
    if (!project) return
    const settings = project.creation.settings
    const number = settings.episodeCount + 1
    if (!Number.isSafeInteger(number)) return
    project.creation.settings = { ...settings, episodeCount: number }
    project.scriptConfirmed = false
    project.scriptEdited = true
    return number
  }

  function saveEpisode(id: string, episode: StudioEpisode) {
    const project = getProject(id)
    const title = episode.title.trim()
    if (!project || !title || !isEpisodeNumber(episode.number, project.creation.settings.episodeCount)) return false
    const { number, summary, script } = episode
    project.episodes[number] = { number, title, summary, script }
    project.scriptConfirmed = false
    project.scriptEdited = true
    return true
  }

  function saveStructuredEpisode(id: string, number: number, rawTitle: string, rawScenes: BackendScene[]) {
    const project = getProject(id)
    const title = rawTitle.trim()
    if (!project?.scriptResult || !title || !isEpisodeNumber(number, project.creation.settings.episodeCount)) return false
    const target = project.scriptResult.episodes.find((item) => item.number === number)
    if (!target) return false

    const scenes = normalizeScenes(rawScenes)
    const script = renderStructuredScript(scenes, project.scriptResult.outline)
    const seconds = scenesSeconds(scenes)

    // 若删减节拍导致 hookBeat 越界，自动钳制到有效范围。
    const [hookScene, hookBeat] = target.hookBeat
    const safeScene = Math.max(1, Math.min(hookScene, scenes.length))
    const safeFlowLen = scenes[safeScene - 1]?.flow.length ?? 1
    const safeBeat = Math.max(1, Math.min(hookBeat, Math.max(1, safeFlowLen)))

    target.title = title
    target.scenes = scenes
    target.seconds = seconds
    target.script = script
    target.hookBeat = [safeScene, safeBeat]

    const current = project.episodes[number]
    project.episodes[number] = {
      number,
      title,
      summary: current?.summary ?? target.summary,
      script,
    }
    project.scriptConfirmed = false
    project.scriptEdited = false
    return true
  }

  function confirmScript(id: string) {
    const project = getProject(id)
    if (project) project.scriptConfirmed = true
  }

  function loadExampleAssets(id: string) {
    const project = getProject(id)
    if (project && !project.assets?.length) project.assets = createExampleAssets()
  }

  function createAsset(id: string, kind: StudioAssetKind, draft: StudioAssetDraft) {
    const project = getProject(id)
    const fields = normalizeAssetDraft(draft)
    if (!project || !fields.name) return false

    const assetId = crypto.randomUUID()
    const voice = kind === 'character' ? (fields.voice ?? '') : ''
    const assets = (project.assets ??= [])
    assets.push({ id: assetId, kind, ...fields, voice })
    if (project.assetResult) {
      project.assetResult.assets.push({
        id: assetId,
        kind,
        name: fields.name,
        description: fields.description || fields.name,
        prompt: fields.prompt || fields.name,
        episodeNumbers: [],
        voice,
      })
    }
    return true
  }

  function saveAsset(id: string, assetId: string, draft: StudioAssetDraft) {
    const project = getProject(id)
    const asset = project?.assets?.find(({ id }) => id === assetId)
    const fields = normalizeAssetDraft(draft)
    if (!project || !asset || !fields.name) return false

    const voice = asset.kind === 'character' ? (fields.voice ?? '') : ''
    Object.assign(asset, fields, { voice })
    const backendAsset = project.assetResult?.assets.find(({ id }) => id === assetId)
    if (backendAsset) {
      backendAsset.name = fields.name
      if (fields.description) backendAsset.description = fields.description
      if (fields.prompt) backendAsset.prompt = fields.prompt
      backendAsset.voice = voice
    }
    return true
  }

  function removeAsset(id: string, assetId: string) {
    const project = getProject(id)
    const assets = project?.assets
    if (!project || !assets) return false

    const index = assets.findIndex((asset) => asset.id === assetId)
    if (index < 0) return false

    assets.splice(index, 1)
    if (project.assetResult) {
      project.assetResult.assets = project.assetResult.assets.filter(({ id }) => id !== assetId)
    }
    return true
  }

  function generateExampleStoryboard(id: string, number: number) {
    const project = getProject(id)
    if (!project?.scriptConfirmed || !isEpisodeNumber(number, project.creation.settings.episodeCount)) return

    const storyboards = (project.storyboards ??= {})
    storyboards[number] ??= createExampleStoryboard(readEpisode(project, number), project.creation.settings)
  }

  function saveClipPrompt(id: string, number: number, clipId: number, prompt: string) {
    const clip = getProject(id)?.storyboards?.[number]?.clips.find(({ id }) => id === clipId)
    if (clip) clip.prompt = prompt
  }

  function saveClipDuration(id: string, number: number, clipId: number, durationSeconds: number) {
    const clip = getProject(id)?.storyboards?.[number]?.clips.find(({ id }) => id === clipId)
    if (clip) clip.durationSeconds = durationSeconds
  }

  function reorderClips(id: string, number: number, fromIndex: number, toIndex: number) {
    const clips = getProject(id)?.storyboards?.[number]?.clips
    if (!clips || fromIndex < 0 || toIndex < 0 || fromIndex >= clips.length || toIndex >= clips.length || fromIndex === toIndex) {
      return false
    }
    const [moved] = clips.splice(fromIndex, 1)
    if (!moved) return false
    clips.splice(toIndex, 0, moved)
    clips.forEach((item, idx) => {
      item.id = idx + 1
    })
    return true
  }

  function appendClip(id: string, number: number) {
    const clips = getProject(id)?.storyboards?.[number]?.clips
    if (!clips) return

    const clipId = clips.reduce((latest, clip) => Math.max(latest, clip.id), 0) + 1
    clips.push({ id: clipId, durationSeconds: defaultSegmentDuration, prompt: '', assetIds: [] })
    return clipId
  }

  function removeClip(id: string, number: number, clipId: number) {
    const clips = getProject(id)?.storyboards?.[number]?.clips
    if (!clips) return false

    const index = clips.findIndex((clip) => clip.id === clipId)
    if (index < 0) return false

    clips.splice(index, 1)
    return true
  }

  function applyPersistedAsset(projectId: string, persisted: PersistedAssetOut) {
    const project = getProject(projectId)
    if (!project?.assets) return
    const idx = project.assets.findIndex(
      (item) => item.backendId === persisted.id || item.id === persisted.assetCode,
    )
    if (idx < 0) return
    const nextAsset: StudioAsset = {
      id: persisted.assetCode,
      backendId: persisted.id,
      ...(persisted.parentAssetId ? { parentAssetId: persisted.parentAssetId } : {}),
      ...(persisted.variantLabel ? { variantLabel: persisted.variantLabel } : {}),
      kind: persisted.kind,
      name: persisted.name,
      description: persisted.description,
      prompt: persisted.prompt,
      ...(persisted.voice ? { voice: persisted.voice } : {}),
      ...(persisted.imageUrl ? { imageUrl: persisted.imageUrl } : {}),
      ...(persisted.imageModelId ? { imageModelId: persisted.imageModelId } : {}),
      ...(persisted.imageTier ? { imageTier: persisted.imageTier } : {}),
      imageStatus: persisted.imageStatus,
      imageHistory: persisted.imageHistory ?? [],
      ...(persisted.lastJobId ? { lastJobId: persisted.lastJobId } : {}),
      ...(persisted.lastJobStatus ? { lastJobStatus: persisted.lastJobStatus } : {}),
      ...(persisted.lastJobError ? { lastJobError: persisted.lastJobError } : {}),
    }
    project.assets[idx] = nextAsset
    if (project.storyboards) {
      for (const board of Object.values(project.storyboards)) {
        if (!board) continue
        for (const sbAsset of board.assets) {
          if (sbAsset.id === nextAsset.id) {
            sbAsset.name = nextAsset.name
            sbAsset.imageUrl = nextAsset.imageUrl
          }
        }
      }
    }
  }

  function applyPersistedClip(projectId: string, episodeNumber: number, persisted: PersistedClipOut) {
    const clips = getProject(projectId)?.storyboards?.[episodeNumber]?.clips
    if (!clips) return
    const clip = clips.find((item) => item.backendId === persisted.id || item.id === persisted.clipIndex)
    if (!clip) return
    clip.videoUrl = persisted.videoUrl ?? undefined
    clip.videoModelId = persisted.videoModelId ?? undefined
    clip.videoStatus = persisted.videoStatus
    clip.videoHistory = persisted.videoHistory ?? []
    clip.lastJobId = persisted.lastJobId ?? undefined
    clip.lastJobStatus = persisted.lastJobStatus ?? undefined
    clip.lastJobError = persisted.lastJobError ?? undefined
  }

  return {
    projects, createProject, createProjectFromScript, syncProjectSummaries, hydrateProjectDetail, clearProjects, removeProject, replaceScript, replaceEpisode, applyAppendedEpisode, getProject, renameProject, applyProjectMeta, appendEpisode, saveEpisode, saveStructuredEpisode, confirmScript,
    applyAssets, applyStoryboard, applyPersistedAsset, applyPersistedClip,
    loadExampleAssets, createAsset, saveAsset, removeAsset, generateExampleStoryboard, saveClipPrompt, saveClipDuration, reorderClips, appendClip, removeClip,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useStudioStore, import.meta.hot))
}
