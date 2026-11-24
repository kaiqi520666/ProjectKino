import { computed, onBeforeUnmount, ref, type Component, type ComputedRef, type ShallowRef } from 'vue'
import { Film, Image as ImageIcon, LayoutGrid, Music } from 'lucide-vue-next'
import {
  remapPromptOnSlotRemove,
  removeStoryboardGridPromptBlock,
  type PromptReferenceOption,
} from '@/components/business/prompt-references'
import type { AssetLibraryItem } from '@/features/assets/asset-library-types'
import { useUiStore } from '@/stores/ui'
import { apiErrorMessage, getProjectDetail, updateClipApi } from '../api'
import type { ModelCatalogItemOut, PersistedClipReference } from '../api-types'
import { assetCategoryItems, assetKindIcons } from '../asset-icons'
import { assetDisplayName, assetStateLabel, findAssetSiblings, type StudioAsset } from '../studio-assets'
import type { StudioProject } from '../studio-project'
import type { EpisodeStoryboard, StoryboardClip } from '../studio-storyboard'
import { useStudioStore } from '../studio-store'

export interface ResolvedClipReference {
  id: string
  name: string
  displayName: string
  stateLabel: string
  kind: 'character' | 'scene' | 'prop' | 'image' | 'video' | 'audio' | 'storyboard_grid'
  mediaKind: 'image' | 'video' | 'audio'
  modalityIndex: number
  mediaUrl?: string
  slotLabel: string
  index?: number
  icon: Component
  imageUrl?: string
  siblings: StudioAsset[]
  gridLayout?: string
  cellMapping?: Array<{ cutIndex: number; cells: number[] }>
}

interface UseClipReferencesOptions {
  project: ComputedRef<StudioProject>
  episodeNumber: ComputedRef<number>
  storyboard: ComputedRef<EpisodeStoryboard | undefined>
  clip: ComputedRef<StoryboardClip | undefined>
  currentVideoModel: ComputedRef<ModelCatalogItemOut | null>
  isLocked: () => boolean
  flushPromptSave: () => Promise<void>
  audioElement: Readonly<ShallowRef<HTMLAudioElement | null>>
}

export function useClipReferences(options: UseClipReferencesOptions) {
  const studio = useStudioStore()
  const ui = useUiStore()
  const playingRefAudioId = ref<string | null>(null)

  const projectAssetsById = computed(
    () => new Map((options.project.value.assets ?? []).map((item) => [item.id, item])),
  )

  const resolvedStoryboardAssets = computed(() =>
    (options.storyboard.value?.assets ?? []).map((asset) => {
      const live = projectAssetsById.value.get(asset.id)
      return {
        ...asset,
        name: live ? assetDisplayName(live) : asset.name,
        imageUrl: live?.imageUrl ?? asset.imageUrl,
      }
    }),
  )

  const assetGroups = computed(() =>
    assetCategoryItems.map((category) => ({
      ...category,
      assets: resolvedStoryboardAssets.value.filter(({ kind }) => kind === category.kind),
    })),
  )

  const references = computed<ResolvedClipReference[]>(() => {
    const allAssets = options.project.value.assets ?? []
    const listed = options.clip.value?.references
    if (listed?.length) {
      const assets = resolvedStoryboardAssets.value
      let imgIdx = 0
      let vidIdx = 0
      let audIdx = 0
      return listed.map((reference) => {
        const live = projectAssetsById.value.get(reference.assetId)
        const boardAsset = assets.find((asset) => asset.id === reference.assetId)
        const siblings = live ? findAssetSiblings(allAssets, live) : []
        const mediaKind: 'image' | 'video' | 'audio' = live
          ? 'image'
          : reference.mediaKind
            ?? (reference.kind === 'video' || reference.kind === 'audio' ? reference.kind : 'image')
        const modalityIndex =
          mediaKind === 'video' ? ++vidIdx : mediaKind === 'audio' ? ++audIdx : ++imgIdx
        const slotLabel =
          mediaKind === 'video'
            ? `视频${modalityIndex}`
            : mediaKind === 'audio'
              ? `音频${modalityIndex}`
              : `图片${modalityIndex}`
        const icon: Component =
          mediaKind === 'video'
            ? Film
            : mediaKind === 'audio'
              ? Music
              : reference.kind === 'storyboard_grid'
                ? LayoutGrid
                : reference.kind === 'character' || reference.kind === 'scene' || reference.kind === 'prop'
                  ? assetKindIcons[reference.kind]
                  : ImageIcon
        const mediaUrl = live?.imageUrl ?? boardAsset?.imageUrl ?? reference.mediaUrl
        return {
          id: reference.assetId,
          name: live?.name || boardAsset?.name || reference.name,
          displayName: live ? assetDisplayName(live) : (boardAsset?.name || reference.name),
          stateLabel: live ? assetStateLabel(live) : '',
          kind: reference.kind,
          mediaKind,
          modalityIndex,
          mediaUrl,
          slotLabel,
          index: reference.index,
          icon,
          imageUrl: mediaKind === 'image' ? mediaUrl : undefined,
          siblings,
          gridLayout: reference.gridLayout,
          cellMapping: reference.cellMapping,
        }
      })
    }

    let imgIdx = 0
    return assetGroups.value.flatMap(({ icon, assets }) =>
      assets
        .filter((asset) => options.clip.value?.assetIds.includes(asset.id))
        .map((asset) => {
          const live = projectAssetsById.value.get(asset.id)
          const siblings = live ? findAssetSiblings(allAssets, live) : []
          const modalityIndex = ++imgIdx
          return {
            id: asset.id,
            name: live?.name || asset.name,
            displayName: live ? assetDisplayName(live) : asset.name,
            stateLabel: live ? assetStateLabel(live) : '',
            kind: asset.kind,
            mediaKind: 'image' as const,
            modalityIndex,
            mediaUrl: asset.imageUrl,
            slotLabel: `图片${modalityIndex}`,
            icon,
            imageUrl: asset.imageUrl,
            index: undefined,
            siblings,
            gridLayout: undefined,
            cellMapping: undefined,
          }
        }),
    )
  })

  const promptReferences = computed<PromptReferenceOption[]>(() =>
    references.value.map((item) => ({
      tokenKey: item.slotLabel,
      label: `${item.slotLabel} · ${item.displayName}`,
      kind: item.mediaKind,
      thumbnailUrl: item.mediaKind === 'image' ? item.imageUrl : undefined,
    })),
  )

  const usedReferenceKeys = computed(() => {
    const keys: string[] = []
    for (const refItem of references.value) {
      keys.push(refItem.id)
      const live = projectAssetsById.value.get(refItem.id)
      if (live?.backendId) keys.push(live.backendId)
      if (refItem.mediaUrl) keys.push(refItem.mediaUrl)
    }
    return keys
  })

  const remainingRefCaps = computed(() => {
    const caps = options.currentVideoModel.value?.capabilities
    const maxImg = caps?.maxReferenceImages !== undefined && caps.maxReferenceImages !== null ? Number(caps.maxReferenceImages) : 9
    const maxVid = caps?.maxReferenceVideos !== undefined && caps.maxReferenceVideos !== null ? Number(caps.maxReferenceVideos) : 0
    const maxAud = caps?.maxReferenceAudios !== undefined && caps.maxReferenceAudios !== null ? Number(caps.maxReferenceAudios) : 0
    let curImg = 0
    let curVid = 0
    let curAud = 0
    for (const refItem of references.value) {
      if (refItem.mediaKind === 'video') curVid += 1
      else if (refItem.mediaKind === 'audio') curAud += 1
      else curImg += 1
    }
    return {
      image: Math.max(0, maxImg - curImg),
      video: Math.max(0, maxVid - curVid),
      audio: Math.max(0, maxAud - curAud),
    }
  })

  function stopRefAudio() {
    if (options.audioElement.value) {
      options.audioElement.value.pause()
      options.audioElement.value.currentTime = 0
    }
    playingRefAudioId.value = null
  }

  function toggleRefAudio(id: string, url?: string) {
    const el = options.audioElement.value
    if (!el || !url) return
    if (playingRefAudioId.value === id) {
      stopRefAudio()
      return
    }
    el.src = url
    playingRefAudioId.value = id
    void el.play().catch(() => {
      playingRefAudioId.value = null
    })
  }

  function serializeExistingRefs(): PersistedClipReference[] {
    return references.value.map((refItem, idx) => {
      const live = projectAssetsById.value.get(refItem.id)
      return {
        index: idx + 1,
        assetId: live?.backendId || refItem.id,
        assetCode: live ? refItem.id : undefined,
        name: refItem.displayName,
        kind: refItem.kind,
        ...(!live && refItem.mediaUrl ? { mediaKind: refItem.mediaKind, mediaUrl: refItem.mediaUrl } : {}),
        ...(refItem.gridLayout ? { gridLayout: refItem.gridLayout } : {}),
        ...(refItem.cellMapping?.length ? { cellMapping: refItem.cellMapping } : {}),
      }
    })
  }

  async function persistClipReferences(nextRefs: PersistedClipReference[], updatedPrompt?: string) {
    if (!options.clip.value?.backendId || !options.project.value.persisted) return
    try {
      await options.flushPromptSave()
      const patch: { references: PersistedClipReference[]; prompt?: string } = { references: nextRefs }
      if (updatedPrompt !== undefined) patch.prompt = updatedPrompt
      await updateClipApi(options.project.value.id, options.clip.value.backendId, patch)
      const detail = await getProjectDetail(options.project.value.id)
      studio.hydrateProjectDetail(detail)
    } catch (error) {
      ui.notify(apiErrorMessage(error), 'error')
    }
  }

  async function addReferenceLibraryItems(items: AssetLibraryItem[]) {
    if (!options.clip.value || !items.length || options.isLocked()) return
    const current = serializeExistingRefs()
    for (const item of items) {
      if (item.source === 'project' && item.projectAsset) {
        const asset = item.projectAsset
        current.push({
          index: current.length + 1,
          assetId: asset.backendId || asset.id,
          assetCode: asset.id,
          name: assetDisplayName(asset),
          kind: asset.kind,
        })
      } else if (item.mediaUrl && (item.kind === 'image' || item.kind === 'video' || item.kind === 'audio')) {
        current.push({
          index: current.length + 1,
          assetId: item.id,
          name: item.title,
          kind: item.kind,
          mediaKind: item.kind,
          mediaUrl: item.mediaUrl,
        })
      }
    }
    await persistClipReferences(current)
  }

  async function removeReferenceAsset(slotIndex: number) {
    const activeClip = options.clip.value
    if (!activeClip || options.isLocked()) return
    const removed = references.value[slotIndex]
    if (!removed) return
    if (playingRefAudioId.value === removed.id) stopRefAudio()
    const isGridRef = removed.kind === 'storyboard_grid' || removed.id.startsWith('grid:')
    const basePrompt = isGridRef
      ? removeStoryboardGridPromptBlock(activeClip.prompt)
      : { prompt: activeClip.prompt, changed: false }
    const remap = remapPromptOnSlotRemove(
      basePrompt.prompt,
      removed.mediaKind,
      removed.modalityIndex,
      removed.displayName,
    )
    const promptChanged = basePrompt.changed || remap.changed
    const finalPrompt = remap.prompt
    const next = serializeExistingRefs()
      .filter((_, idx) => idx !== slotIndex)
      .map((refItem, idx) => ({ ...refItem, index: idx + 1 }))
    if (promptChanged) {
      studio.saveClipPrompt(options.project.value.id, options.episodeNumber.value, activeClip.id, finalPrompt)
    }
    await persistClipReferences(next, promptChanged ? finalPrompt : undefined)
    if (isGridRef) {
      ui.notify('已移除分镜宫格图并清理提示词驱动块', 'info')
    } else if (remap.changed) {
      ui.notify('已同步更新提示词引用编号', 'info')
    }
  }

  async function switchReferenceVariant(slotIndex: number, target: StudioAsset) {
    if (!options.clip.value || !options.project.value.persisted || options.isLocked()) return
    const currentSlot = references.value[slotIndex]
    if (!currentSlot || currentSlot.id === target.id) return
    if (references.value.some((refItem, idx) => idx !== slotIndex && refItem.id === target.id)) {
      ui.notify(`「${assetDisplayName(target)}」已存在于当前片段的其他参考槽位中`, 'info')
      return
    }
    const next = serializeExistingRefs().map((refItem, idx) => {
      if (idx === slotIndex) {
        return {
          index: idx + 1,
          assetId: target.backendId || target.id,
          assetCode: target.id,
          name: assetDisplayName(target),
          kind: target.kind,
        }
      }
      return refItem
    })
    await persistClipReferences(next)
    ui.notify(`已将${currentSlot.slotLabel}切换为「${assetDisplayName(target)}」`, 'success')
  }

  onBeforeUnmount(() => {
    stopRefAudio()
  })

  return {
    assetGroups,
    references,
    promptReferences,
    usedReferenceKeys,
    remainingRefCaps,
    playingRefAudioId,
    stopRefAudio,
    toggleRefAudio,
    addReferenceLibraryItems,
    removeReferenceAsset,
    switchReferenceVariant,
  }
}
