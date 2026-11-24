import { computed, onMounted, ref, type ComputedRef } from 'vue'
import { formatBatchCollectSummary, isCollectableMediaUrl } from '@/features/assets/user-assets-helpers'
import { useUserAssetsStore } from '@/features/assets/user-assets-store'
import { useUiStore } from '@/stores/ui'
import { apiErrorMessage } from '../api'
import type { StudioEpisode, StudioProject } from '../studio-project'
import type { StoryboardClip } from '../studio-storyboard'

interface UseEpisodeLibraryActionsOptions {
  project: ComputedRef<StudioProject>
  projectName: ComputedRef<string>
  episodeNumber: ComputedRef<number>
  episode: ComputedRef<StudioEpisode | null>
  clips: ComputedRef<StoryboardClip[]>
  checkedSet: ComputedRef<Set<string>>
}

export function useEpisodeLibraryActions(options: UseEpisodeLibraryActionsOptions) {
  const userAssets = useUserAssetsStore()
  const ui = useUiStore()

  const togglingClipLibraryKey = ref<string | null>(null)
  const togglingComposedLibrary = ref(false)
  const batchCollectingClips = ref(false)

  onMounted(() => {
    if (options.project.value.persisted) {
      void userAssets.ensureLoaded().catch(() => {})
    }
  })

  const checkedCollectableClips = computed(() =>
    options.clips.value.filter(
      (item) =>
        Boolean(item.backendId)
        && options.checkedSet.value.has(item.backendId!)
        && isCollectableMediaUrl(item.videoUrl),
    ),
  )

  function clipVideoTitle(item: StoryboardClip): string {
    return `${options.projectName.value} · 第${options.episodeNumber.value}集 片段${item.id}`
  }

  function isClipInLibrary(item?: StoryboardClip): boolean {
    return Boolean(item && isCollectableMediaUrl(item.videoUrl) && userAssets.isSaved('video', item.videoUrl))
  }

  function isClipLibraryBusy(item: StoryboardClip): boolean {
    return togglingClipLibraryKey.value === (item.backendId || String(item.id))
  }

  async function toggleClipLibrary(item?: StoryboardClip) {
    if (!options.project.value.persisted || !item || !isCollectableMediaUrl(item.videoUrl)) return
    const lockKey = item.backendId || String(item.id)
    if (togglingClipLibraryKey.value === lockKey) return
    togglingClipLibraryKey.value = lockKey
    const videoTitle = clipVideoTitle(item)
    try {
      const result = await userAssets.toggleMediaAsset({
        kind: 'video',
        title: videoTitle,
        mediaUrl: item.videoUrl,
        mediaKey: null,
        mediaName: `${videoTitle}.mp4`,
        sourceType: 'studio',
        sourceId: item.backendId ?? null,
      })
      ui.notify(
        result.saved ? `已加入「${videoTitle}」到素材库` : `已从素材库移除「${videoTitle}」`,
        result.saved ? 'success' : 'info',
      )
    } catch (error) {
      ui.notify(apiErrorMessage(error), 'error')
    } finally {
      if (togglingClipLibraryKey.value === lockKey) togglingClipLibraryKey.value = null
    }
  }

  const isComposedInLibrary = computed(() =>
    Boolean(
      options.episode.value
      && isCollectableMediaUrl(options.episode.value.composedVideoUrl)
      && userAssets.isSaved('video', options.episode.value.composedVideoUrl),
    ),
  )

  async function toggleComposedLibrary() {
    const ep = options.episode.value
    if (
      !options.project.value.persisted
      || !ep
      || !isCollectableMediaUrl(ep.composedVideoUrl)
      || togglingComposedLibrary.value
    ) {
      return
    }
    togglingComposedLibrary.value = true
    const videoTitle = `${options.projectName.value} · 第${ep.number}集成片`
    try {
      const result = await userAssets.toggleMediaAsset({
        kind: 'video',
        title: videoTitle,
        mediaUrl: ep.composedVideoUrl,
        mediaKey: null,
        mediaName: `${options.projectName.value}-第${ep.number}集.mp4`,
        sourceType: 'studio',
        sourceId: options.project.value.id,
      })
      ui.notify(
        result.saved ? `已加入「${videoTitle}」到素材库` : `已从素材库移除「${videoTitle}」`,
        result.saved ? 'success' : 'info',
      )
    } catch (error) {
      ui.notify(apiErrorMessage(error), 'error')
    } finally {
      togglingComposedLibrary.value = false
    }
  }

  async function collectSelectedClips() {
    if (!options.project.value.persisted || batchCollectingClips.value || !checkedCollectableClips.value.length) {
      return
    }
    batchCollectingClips.value = true
    try {
      const result = await userAssets.collectBatchMediaAssets(
        checkedCollectableClips.value.map((item) => {
          const videoTitle = clipVideoTitle(item)
          return {
            kind: 'video' as const,
            title: videoTitle,
            mediaUrl: item.videoUrl,
            mediaKey: null,
            mediaName: `${videoTitle}.mp4`,
            sourceType: 'studio' as const,
            sourceId: item.backendId ?? null,
          }
        }),
      )
      const feedback = formatBatchCollectSummary(result)
      ui.notify(feedback.message, feedback.tone)
    } catch (error) {
      ui.notify(apiErrorMessage(error), 'error')
    } finally {
      batchCollectingClips.value = false
    }
  }

  return {
    togglingComposedLibrary,
    batchCollectingClips,
    checkedCollectableClips,
    isClipInLibrary,
    isClipLibraryBusy,
    toggleClipLibrary,
    isComposedInLibrary,
    toggleComposedLibrary,
    collectSelectedClips,
  }
}
