import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { apiErrorMessage, getProjectDetail, startGenerateClipStoryboardGrid, watchJob } from '../api'
import type { ModelCatalogItemOut } from '../api-types'
import { resolveDefaultImageModel, resolveImageTierForModel, type ImageTier } from '../model-defaults'
import type { StudioProject } from '../studio-project'
import type { StoryboardClip } from '../studio-storyboard'
import { useStudioStore } from '../studio-store'

interface ReferenceLike {
  id: string
  kind: string
}

interface UseClipStoryboardGridOptions {
  project: ComputedRef<StudioProject>
  clips: ComputedRef<StoryboardClip[]>
  clip: ComputedRef<StoryboardClip | undefined>
  references: ComputedRef<ReferenceLike[]>
  selectedRatio: Ref<string>
  imageModels: Ref<ModelCatalogItemOut[]>
  ensureModelCatalog: () => Promise<unknown>
  flushPromptSave: () => Promise<void>
}

export function useClipStoryboardGrid(options: UseClipStoryboardGridOptions) {
  const auth = useAuthStore()
  const studio = useStudioStore()
  const ui = useUiStore()

  const gridDialogOpen = ref(false)
  const gridModelId = ref('')
  const gridTier = ref<ImageTier>('1k')
  const gridRatio = ref<string>(options.project.value.creation.settings.ratio || '16:9')
  const submittingGridClipId = ref<string | null>(null)
  const liveGridStateByClipId = ref<Record<string, { jobId: string; label: string }>>({})
  const watchedGridJobIds = new Set<string>()

  const activeGridJobsByClipId = computed(() => {
    const map = new Map<string, { id: string; status: string; progress: number; stepLabel: string }>()
    for (const job of options.project.value.activeJobs ?? []) {
      if (
        job.jobType === 'asset_image'
        && job.jobMeta?.action === 'clip_storyboard_grid'
        && job.targetId
      ) {
        map.set(job.targetId, {
          id: job.id,
          status: job.status,
          progress: job.progress,
          stepLabel: job.stepLabel,
        })
      }
    }
    return map
  })

  const currentStoryboardGridRef = computed(() =>
    options.references.value.find((item) => item.kind === 'storyboard_grid' || item.id.startsWith('grid:')) ?? null,
  )

  const hasStoryboardGrid = computed(() => currentStoryboardGridRef.value !== null)

  const isCurrentClipGridGenerating = computed(() => {
    const id = options.clip.value?.backendId
    if (!id) return false
    return (
      submittingGridClipId.value === id
      || Boolean(liveGridStateByClipId.value[id])
      || activeGridJobsByClipId.value.has(id)
    )
  })

  const currentClipGridProgressLabel = computed(() => {
    const id = options.clip.value?.backendId
    if (!id) return ''
    const live = liveGridStateByClipId.value[id]
    if (live?.label) return live.label
    const active = activeGridJobsByClipId.value.get(id)
    if (!active) return submittingGridClipId.value === id ? '规划宫格中…' : ''
    if (active.progress > 0) return `宫格 ${active.progress}%`
    return active.stepLabel || '生成宫格中…'
  })

  function setLiveGridLabel(targetClipId: string, jobId: string, label: string) {
    liveGridStateByClipId.value = {
      ...liveGridStateByClipId.value,
      [targetClipId]: { jobId, label },
    }
  }

  function clearLiveGridState(targetClipId: string, jobId: string) {
    const existing = liveGridStateByClipId.value[targetClipId]
    if (existing && existing.jobId === jobId) {
      const next = { ...liveGridStateByClipId.value }
      delete next[targetClipId]
      liveGridStateByClipId.value = next
    }
  }

  function trackClipGridJob(
    jobId: string,
    targetClipId: string,
    targetClipNo: number | null,
    initialLabel = '规划宫格中…',
  ) {
    if (watchedGridJobIds.has(jobId)) return
    watchedGridJobIds.add(jobId)
    setLiveGridLabel(targetClipId, jobId, initialLabel)

    void watchJob(jobId, (liveJob) => {
      const label =
        liveJob.progress > 0 ? `宫格 ${liveJob.progress}%` : (liveJob.stepLabel || '生成宫格中…')
      setLiveGridLabel(targetClipId, jobId, label)
    })
      .then(async (finalJob) => {
        const prefix = targetClipNo ? `片段 ${targetClipNo} ` : ''
        if (finalJob.status === 'succeeded') {
          try {
            const detail = await getProjectDetail(options.project.value.id)
            studio.hydrateProjectDetail(detail)
          } catch {
            // Ignore transient refresh errors; next load will sync.
          }
          void auth.refreshBalance()
          ui.notify(`${prefix}分镜宫格图已生成并自动挂载`, 'success')
        } else if (finalJob.status === 'review') {
          void auth.refreshBalance()
          ui.notify(finalJob.errorMessage || '分镜宫格生成待后台核对（积分冻结中）', 'info')
        } else {
          void auth.refreshBalance()
          ui.notify(finalJob.errorMessage || '分镜宫格生成失败（已退还冻结积分）', 'error')
        }
      })
      .catch((error) => {
        ui.notify(apiErrorMessage(error), 'error')
      })
      .finally(() => {
        watchedGridJobIds.delete(jobId)
        clearLiveGridState(targetClipId, jobId)
      })
  }

  watch(
    activeGridJobsByClipId,
    (jobsMap) => {
      for (const [targetClipId, activeJob] of jobsMap.entries()) {
        const matchedClip = options.clips.value.find((item) => item.backendId === targetClipId)
        const label =
          activeJob.progress > 0 ? `宫格 ${activeJob.progress}%` : (activeJob.stepLabel || '生成宫格中…')
        trackClipGridJob(activeJob.id, targetClipId, matchedClip?.id ?? null, label)
      }
    },
    { immediate: true },
  )

  watch(
    () => options.project.value.creation.settings.ratio,
    (ratio) => {
      if (ratio) gridRatio.value = ratio
    },
  )

  const currentGridModel = computed(
    () => options.imageModels.value.find((m) => m.id === gridModelId.value) ?? options.imageModels.value[0] ?? null,
  )

  const estimatedGridQuote = computed(() => {
    const model = currentGridModel.value
    const price = model?.imagePrices.find((p) => p.tier === gridTier.value) ?? model?.imagePrices[0]
    if (!price) return null
    const val = Number(price.creditPrice)
    return Number.isFinite(val) ? String(Number(val.toFixed(2))) : null
  })

  const plannedGridSummary = computed(() => {
    const cutCount = options.clip.value?.cuts?.length ?? 0
    if (cutCount <= 0) {
      return '系统将按本片段内容规划 2×2（4 格）无字分镜宫格图，生成后自动挂入参考素材并写入【分镜宫格驱动】。'
    }
    const layout = cutCount <= 4 ? '2×2（4 格）' : cutCount <= 6 ? '2×3（6 格）' : '3×3（9 格）'
    return `本片段共 ${cutCount} 个镜头，将自动拆满 ${layout} 无字零黑块宫格图，生成后自动挂入参考素材并写入【分镜宫格驱动】。`
  })

  function openGridDialog(clipLocked: boolean) {
    if (!options.clip.value?.backendId || !options.project.value.persisted || clipLocked) return
    gridRatio.value = options.selectedRatio.value || options.project.value.creation.settings.ratio || '16:9'
    void options.ensureModelCatalog().then(() => {
      const models = options.imageModels.value
      if (!models.length) return
      const preferred = resolveDefaultImageModel(
        models,
        options.project.value.creation.settings.imageModelId,
      )
      if (preferred) {
        gridModelId.value = preferred.id
        gridTier.value = resolveImageTierForModel(
          preferred,
          options.project.value.creation.settings.imageTier,
        )
      }
    })
    gridDialogOpen.value = true
  }

  async function submitClipStoryboardGrid() {
    const activeClip = options.clip.value
    if (!activeClip?.backendId || !options.project.value.persisted) return
    if (!currentGridModel.value) {
      ui.notify('暂无可用的图片生成模型', 'error')
      return
    }
    const targetClipId = activeClip.backendId
    const targetClipNo = activeClip.id
    gridDialogOpen.value = false
    submittingGridClipId.value = targetClipId
    try {
      await options.flushPromptSave()
      const accepted = await startGenerateClipStoryboardGrid(options.project.value.id, targetClipId, {
        modelId: currentGridModel.value.id,
        tier: gridTier.value,
        ratio: gridRatio.value || options.selectedRatio.value || options.project.value.creation.settings.ratio || '16:9',
      })
      void auth.refreshBalance()
      trackClipGridJob(accepted.job.id, targetClipId, targetClipNo, '规划宫格中…')
      try {
        const detail = await getProjectDetail(options.project.value.id)
        studio.hydrateProjectDetail(detail)
      } catch {
        // Tracking is already active via watchJob.
      }
    } catch (error) {
      ui.notify(apiErrorMessage(error), 'error')
    } finally {
      if (submittingGridClipId.value === targetClipId) {
        submittingGridClipId.value = null
      }
    }
  }

  return {
    gridDialogOpen,
    gridModelId,
    gridTier,
    gridRatio,
    hasStoryboardGrid,
    isCurrentClipGridGenerating,
    currentClipGridProgressLabel,
    currentGridModel,
    estimatedGridQuote,
    plannedGridSummary,
    openGridDialog,
    submitClipStoryboardGrid,
  }
}
