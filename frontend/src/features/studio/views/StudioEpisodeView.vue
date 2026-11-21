<script setup lang="ts">
import { computed, nextTick, onMounted, ref, useTemplateRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Boxes,
  Check,
  CheckCircle2,
  CheckSquare,
  ChevronRight,
  Clapperboard,
  Download,
  Film,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  Video,
  X,
} from 'lucide-vue-next'
import EmptyState from '@/components/business/EmptyState.vue'
import ImagePreview from '@/components/ui/ImagePreview.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiIconButton from '@/components/ui/UiIconButton.vue'
import UiTextarea from '@/components/ui/UiTextarea.vue'
import VideoPreview from '@/components/ui/VideoPreview.vue'
import { useAuthStore } from '@/stores/auth'
import { useGenerationStore } from '@/stores/generation'
import { useUiStore } from '@/stores/ui'
import {
  apiErrorMessage,
  createClipApi,
  deleteClipApi,
  getJob,
  getProjectDetail,
  isRetryableApiError,
  reorderClipsApi,
  startBatchGenerateClipVideos,
  startComposeEpisode,
  startGenerateClipVideo,
  startGenerateStoryboard,
  updateClipApi,
  watchJob,
} from '../api'
import { assetCategoryItems, assetKindIcons } from '../asset-icons'
import { defaultSegmentDuration } from '../components/drama-creation'
import StudioBatchVideoDialog from '../components/StudioBatchVideoDialog.vue'
import VideoModelPicker from '../components/VideoModelPicker.vue'
import VideoParamsPopover from '../components/VideoParamsPopover.vue'
import { useBatchJobTracker } from '../composables/useBatchJobTracker'
import { useModelCatalog } from '../composables/useModelCatalog'
import type { StudioAsset } from '../studio-assets'
import { episodeLabel, isEpisodeNumber, readEpisode } from '../studio-project'
import type { StudioProject } from '../studio-project'
import type { StoryboardClip } from '../studio-storyboard'
import { useStudioStore } from '../studio-store'

interface VideoBatchMeta {
  episodeNumber: number
  modelId: string
  resolution: '480p' | '720p' | '1080p'
  ratio?: string
  durationSeconds?: number
}

const props = defineProps<{ project: StudioProject }>()
const route = useRoute()
const auth = useAuthStore()
const studio = useStudioStore()
const generation = useGenerationStore()
const ui = useUiStore()
const { videoModels, ensureLoaded: ensureModelCatalog } = useModelCatalog()
const selectedId = ref<number>()
const deleteOpen = ref(false)
const pickerOpen = ref(false)
const batchOpen = ref(false)
const batchInitialIds = ref<string[]>([])
const batchSubmitting = ref(false)
const submittingClipId = ref<string | null>(null)
const selectMode = ref(false)
const checkedClipIds = ref<string[]>([])
const reorderingClips = ref(false)
const dragSourceIndex = ref<number | null>(null)
const dragOverIndex = ref<number | null>(null)

const previewClip = ref<{ id: number; src: string; poster?: string } | null>(null)
const previewOpen = computed({
  get: () => previewClip.value !== null,
  set: (value: boolean) => {
    if (!value) previewClip.value = null
  },
})
const generating = ref(false)
const clipToDelete = ref<number>()
const selectedVideoModelId = ref('')
const selectedResolution = ref<'480p' | '720p' | '1080p'>('720p')
const selectedRatio = ref(props.project.creation.settings.ratio || '16:9')
const selectedDuration = ref(10)
let deleteTrigger: HTMLButtonElement | undefined
const clipList = useTemplateRef<HTMLOListElement>('clipList')

onMounted(async () => {
  await ensureModelCatalog()
  if (!selectedVideoModelId.value || !videoModels.value.some((m) => m.id === selectedVideoModelId.value)) {
    const def = videoModels.value.find((m) => m.isDefault) ?? videoModels.value[0]
    if (def) selectedVideoModelId.value = def.id
  }
})

const number = computed(() => Number(route.params.episode))
const episode = computed(() => isEpisodeNumber(number.value, props.project.creation.settings.episodeCount)
  ? readEpisode(props.project, number.value) : null)
const projectName = computed(() => props.project.creation.settings.name)
const episodeIndex = computed(() => episode.value ? `第 ${episode.value.number} 集` : '本集不存在')
const episodeName = computed(() => episode.value?.title.trim() ?? '')
const title = computed(() => `${projectName.value} · ${episode.value ? episodeLabel(episode.value) : episodeIndex.value}`)
const cap = computed(() => props.project.creation.settings.maxSegmentDuration ?? defaultSegmentDuration)
const storyboard = computed(() => episode.value ? props.project.storyboards?.[number.value] : undefined)
const clips = computed(() => storyboard.value?.clips ?? [])
const clip = computed(() => clips.value.find(({ id }) => selectedId.value === id) ?? clips.value[0])
const selectedClipIndex = computed(() =>
  clip.value ? clips.value.findIndex((item) => item.id === clip.value!.id) : -1,
)
const readyCount = computed(() => clips.value.filter(({ videoUrl }) => videoUrl).length)
const missingVideoCount = computed(() => clips.value.filter(({ videoUrl, backendId }) => backendId && !videoUrl).length)

const episodeClipBackendIds = computed(
  () => new Set(clips.value.map((c) => c.backendId).filter((id): id is string => !!id)),
)

const activeVideoJobsByClipId = computed(() => {
  const map = new Map<string, { id: string; status: string; progress: number; stepLabel: string }>()
  for (const job of props.project.activeJobs ?? []) {
    if (job.jobType === 'clip_video' && job.targetId && episodeClipBackendIds.value.has(job.targetId)) {
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

const activeClipIds = computed(() => {
  const ids = new Set<string>(activeVideoJobsByClipId.value.keys())
  for (const item of clips.value) {
    if (item.videoStatus === 'generating' && item.backendId) {
      ids.add(item.backendId)
    }
  }
  return ids
})

const hasActiveVideoJobs = computed(() => activeClipIds.value.size > 0)

const activeClipCount = computed(() => activeClipIds.value.size)

const {
  tracker: batchTracker,
  summary: batchSummary,
  trackJobs: trackVideoBatchJobs,
  startPolling: startBatchPolling,
  failedReason: failedReasonForClipId,
  dismiss: dismissBatchBanner,
} = useBatchJobTracker<VideoBatchMeta>({
  jobType: 'clip_video',
  pollIntervalMs: 5000,
  fallbackErrorMessage: '视频生成失败',
  canPoll: () => !!props.project.persisted,
  activeCount: activeClipCount,
  hasActiveJobs: hasActiveVideoJobs,
  isInScope: (meta) => meta.episodeNumber === number.value,
  fetchProjectDetail: () => getProjectDetail(props.project.id),
  fetchJob: getJob,
  onDetail: (detail) => {
    studio.hydrateProjectDetail(detail)
    void auth.refreshBalance()
  },
  isStillRunning: (detail) => {
    const epClips = detail.storyboards[String(number.value)] ?? []
    const epClipIds = new Set(epClips.map((c) => c.id))
    return (detail.activeJobs ?? []).some(
      (j) => j.jobType === 'clip_video' && j.targetId && epClipIds.has(j.targetId),
    ) || epClips.some((c) => c.videoStatus === 'generating')
  },
  onBatchComplete: ({ okCount, failCount }) => {
    ui.notify(
      failCount > 0
        ? `第 ${number.value} 集批量生视频结束：成功 ${okCount} 段，失败 ${failCount} 段（失败已自动退还积分）`
        : `第 ${number.value} 集批量生视频完成：共生成 ${okCount} 段视频`,
      failCount > 0 ? 'info' : 'success',
    )
  },
})

function isClipGenerating(item?: StoryboardClip) {
  return !!item?.backendId && activeClipIds.value.has(item.backendId)
}

function clipJobProgress(item: StoryboardClip): string {
  if (!item.backendId) return '生成中'
  const job = activeVideoJobsByClipId.value.get(item.backendId)
  if (!job || job.status === 'queued') return '排队中'
  if (job.progress > 0) return `${job.progress}%`
  return '生成中'
}

function clipFailedReason(item: StoryboardClip): string {
  return failedReasonForClipId(item.backendId)
}

const canCompose = computed(
  () => clips.value.length > 0 && readyCount.value === clips.value.length && !generating.value && !hasActiveVideoJobs.value,
)

const checkedSet = computed(() => new Set(checkedClipIds.value))

const projectAssetsById = computed(() => new Map((props.project.assets ?? []).map((item) => [item.id, item])))
const resolvedStoryboardAssets = computed(() => (storyboard.value?.assets ?? []).map((asset) => {
  const live = projectAssetsById.value.get(asset.id)
  return {
    ...asset,
    name: live?.name || asset.name,
    imageUrl: live?.imageUrl ?? asset.imageUrl,
  }
}))
const assetGroups = computed(() => assetCategoryItems.map((category) => ({
  ...category,
  assets: resolvedStoryboardAssets.value.filter(({ kind }) => kind === category.kind),
})))
const references = computed(() => {
  const listed = clip.value?.references
  if (listed?.length) {
    const assets = resolvedStoryboardAssets.value
    return listed.map((reference) => {
      const live = projectAssetsById.value.get(reference.assetId)
      const boardAsset = assets.find((asset) => asset.id === reference.assetId)
      return {
        id: reference.assetId,
        name: live?.name || boardAsset?.name || reference.name,
        kind: reference.kind,
        index: reference.index as number | undefined,
        icon: assetKindIcons[reference.kind],
        imageUrl: live?.imageUrl ?? boardAsset?.imageUrl,
      }
    })
  }
  return assetGroups.value.flatMap(({ icon, assets }) =>
    assets.filter((asset) => clip.value?.assetIds.includes(asset.id)).map((asset) => ({
      id: asset.id, name: asset.name, kind: asset.kind, icon, imageUrl: asset.imageUrl, index: undefined as number | undefined,
    })),
  )
})

const availablePickerAssets = computed(() => {
  const used = new Set(references.value.map((r) => r.id))
  return (props.project.assets ?? []).filter((item) => !used.has(item.id))
})

const currentVideoModel = computed(
  () => videoModels.value.find((m) => m.id === selectedVideoModelId.value) ?? videoModels.value[0] ?? null,
)

const estimatedVideoQuote = computed(() => {
  const dur = selectedDuration.value || clip.value?.durationSeconds || 10
  const model = currentVideoModel.value
  const price = model?.videoPrices.find((p) => p.ruleKey === selectedResolution.value)
    ?? model?.videoPrices.find((p) => p.ruleKey === 'default')
  if (!price) return null
  const unitPrice = Number(price.creditPrice)
  if (!Number.isFinite(unitPrice)) return null
  const unitVal = Number(unitPrice.toFixed(2))
  const totalVal = Number((price.unit === 'second' ? unitPrice * dur : unitPrice).toFixed(2))
  const hint = price.unit === 'second'
    ? `按秒计费：${unitVal} 积分/秒 × ${dur}s = ${totalVal} 积分`
    : `按条计费：${totalVal} 积分/条`
  return {
    amount: String(totalVal),
    unitHint: price.unit === 'second' ? `${unitVal}/秒` : '',
    hint,
  }
})

watch(
  () => [clip.value?.id, clip.value?.durationSeconds] as const,
  ([, dur]) => {
    if (!dur) return
    const minD = Number(currentVideoModel.value?.capabilities?.minDuration || 4)
    const maxD = Number(currentVideoModel.value?.capabilities?.maxDuration || 15)
    selectedDuration.value = Math.min(Math.max(dur, minD), maxD)
  },
  { immediate: true },
)

watch(
  () => props.project.creation.settings.ratio,
  (ratio) => {
    if (ratio) selectedRatio.value = ratio
  },
)

watch(number, () => {
  selectedId.value = undefined
  deleteOpen.value = false
  pickerOpen.value = false
  batchOpen.value = false
  selectMode.value = false
  checkedClipIds.value = []
  previewClip.value = null
})

function openClipPreview(item: { id: number; videoUrl?: string; previewUrl?: string }) {
  if (!item.videoUrl) return
  selectedId.value = item.id
  previewClip.value = { id: item.id, src: item.videoUrl, poster: item.previewUrl }
}

watch(deleteOpen, (open) => {
  if (open) return

  const trigger = deleteTrigger
  deleteTrigger = undefined
  requestAnimationFrame(() => {
    const target = trigger?.isConnected ? trigger : clipList.value?.querySelector<HTMLButtonElement>(
      '.episode-clip[aria-pressed="true"], .episode-clip-add',
    )
    target?.focus({ preventScroll: true })
  })
})

async function commitClipDuration(seconds: number) {
  const activeClip = clip.value
  if (!activeClip || !Number.isInteger(seconds) || seconds < 1 || seconds > 60 || seconds === activeClip.durationSeconds) return
  await updateClipDuration(String(seconds))
}

async function updateClipDuration(value?: string) {
  const activeClip = clip.value
  const parsed = Number(value)
  if (!activeClip || !Number.isInteger(parsed) || parsed < 1 || parsed > 60 || parsed === activeClip.durationSeconds) return
  if (isClipGenerating(activeClip)) return

  const previous = activeClip.durationSeconds
  studio.saveClipDuration(props.project.id, number.value, activeClip.id, parsed)
  if (props.project.persisted && activeClip.backendId) {
    try {
      await updateClipApi(props.project.id, activeClip.backendId, { durationSeconds: parsed })
    } catch (error) {
      studio.saveClipDuration(props.project.id, number.value, activeClip.id, previous)
      ui.notify(apiErrorMessage(error), 'error')
    }
  }
}

async function moveClipOrder(fromIndex: number, toIndex: number) {
  if (
    reorderingClips.value
    || fromIndex < 0
    || toIndex < 0
    || fromIndex >= clips.value.length
    || toIndex >= clips.value.length
    || fromIndex === toIndex
  ) {
    return
  }

  if (!props.project.persisted) {
    if (studio.reorderClips(props.project.id, number.value, fromIndex, toIndex)) {
      selectedId.value = toIndex + 1
    }
    return
  }

  const ordered = [...clips.value]
  const [moved] = ordered.splice(fromIndex, 1)
  if (!moved) return
  ordered.splice(toIndex, 0, moved)
  const clipIds = ordered.map((item) => item.backendId).filter((id): id is string => !!id)
  if (clipIds.length !== ordered.length) return

  reorderingClips.value = true
  try {
    await flushPromptSave()
    await reorderClipsApi(props.project.id, number.value, clipIds)
    const detail = await getProjectDetail(props.project.id)
    studio.hydrateProjectDetail(detail)
    selectedId.value = toIndex + 1
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    reorderingClips.value = false
  }
}

function handleClipDragStart(index: number, event: DragEvent) {
  if (selectMode.value || reorderingClips.value || clips.value.length <= 1) {
    event.preventDefault()
    return
  }
  dragSourceIndex.value = index
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(index))
  }
}

function handleClipDragOver(index: number, event: DragEvent) {
  if (dragSourceIndex.value === null) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
  dragOverIndex.value = index
}

function handleClipDrop(index: number, event: DragEvent) {
  event.preventDefault()
  const from = dragSourceIndex.value
  dragSourceIndex.value = null
  dragOverIndex.value = null
  if (from !== null && from !== index) {
    void moveClipOrder(from, index)
  }
}

function handleClipDragEnd() {
  dragSourceIndex.value = null
  dragOverIndex.value = null
}

async function openBatchDialog(presetIds: string[] = []) {
  if (!props.project.persisted) {
    ui.notify('示例项目暂不支持批量生视频', 'info')
    return
  }
  try {
    await flushPromptSave()
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
    return
  }
  batchInitialIds.value = presetIds
  batchOpen.value = true
}

function toggleSelectMode() {
  selectMode.value = !selectMode.value
  if (!selectMode.value) checkedClipIds.value = []
}

function toggleClipCheck(item: StoryboardClip) {
  if (!item.backendId || isClipGenerating(item)) return
  const id = item.backendId
  if (checkedSet.value.has(id)) {
    checkedClipIds.value = checkedClipIds.value.filter((v) => v !== id)
  } else {
    checkedClipIds.value = [...checkedClipIds.value, id]
  }
}

function openBatchFromSelection() {
  if (!checkedClipIds.value.length) return
  void openBatchDialog([...checkedClipIds.value])
}

async function submitBatchClipVideos(payload: {
  clipIds: string[]
  modelId: string
  resolution: '480p' | '720p' | '1080p'
  ratio?: string
  durationSeconds?: number
}) {
  if (batchSubmitting.value) return
  batchSubmitting.value = true
  try {
    await flushPromptSave()
    const res = await startBatchGenerateClipVideos(props.project.id, number.value, payload)
    batchOpen.value = false
    selectMode.value = false
    checkedClipIds.value = []

    trackVideoBatchJobs(res.jobs, {
      episodeNumber: number.value,
      modelId: payload.modelId,
      resolution: payload.resolution,
      ratio: payload.ratio,
      durationSeconds: payload.durationSeconds,
    })

    const detail = await getProjectDetail(props.project.id)
    studio.hydrateProjectDetail(detail)
    void auth.refreshBalance()
    startBatchPolling()

    const skipHint = res.skipped.length ? `，已跳过 ${res.skipped.length} 段` : ''
    ui.notify(
      `已提交 ${res.acceptedCount} 段批量生视频（共 ${res.totalDurationSeconds}s，预冻结 ${Number(Number(res.totalFrozenCredits).toFixed(2))} 积分${skipHint}），后台并发渲染中`,
      'success',
    )
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    batchSubmitting.value = false
  }
}

function retryFailedBatchClips() {
  const tracker = batchTracker.value
  if (!tracker) return
  const ids = Object.keys(tracker.failedById)
  if (!ids.length) return
  void submitBatchClipVideos({
    clipIds: ids,
    modelId: tracker.meta.modelId,
    resolution: tracker.meta.resolution,
    ratio: tracker.meta.ratio,
    durationSeconds: tracker.meta.durationSeconds,
  })
}

async function generateFromScript() {
  const { scriptResult, assetResult } = props.project
  if (!scriptResult) {
    studio.generateExampleStoryboard(props.project.id, number.value)
    return
  }
  if (!assetResult) {
    ui.notify('请先在资产生成页生成资产', 'info')
    return
  }
  if (generating.value || generation.isRunning) return

  const episodeNumber = number.value
  await generation.runTask(
    {
      title: `正在生成第 ${episodeNumber} 集分镜`,
      subtitle: `${props.project.creation.settings.name} · 单片段最长 ${cap.value} 秒`,
      description: '正在按剧本节拍切分片段与镜头，并拼装视频与关键帧提示词',
      steps: [
        '按单段时长上限切分片段与 2–5 秒镜头',
        '分批设计机位、构图、运镜、走位与关键帧提示词',
        '按参考图合同拼装视频提示词并执行节拍覆盖校验',
      ],
      hint: '后台队列正在分批生成单集分镜，完成后自动刷新片段',
      formatError: apiErrorMessage,
      canRetryError: isRetryableApiError,
      successMessage: () => `第 ${episodeNumber} 集分镜已生成`,
    },
    async (controls) => {
      generating.value = true
      try {
        const accepted = await startGenerateStoryboard(props.project.id, episodeNumber)
        controls.setJobId(accepted.job.id)
        controls.setProgress(accepted.job.progress)
        await watchJob(accepted.job.id, (job) => {
          controls.setProgress(job.progress)
          if (job.stepLabel) controls.setDescription(job.stepLabel)
          controls.setStep(job.stepIndex <= 1 ? 1 : 2)
        })
        const detail = await getProjectDetail(props.project.id)
        studio.hydrateProjectDetail(detail)
        selectedId.value = undefined
        ui.notify(`第 ${episodeNumber} 集分镜已生成`, 'success')
        return detail
      } finally {
        generating.value = false
        void auth.refreshBalance()
      }
    },
  )
}

let promptSaveTimer: ReturnType<typeof setTimeout> | null = null
let pendingPromptSave: { clipId: string; prompt: string } | null = null

async function flushPromptSave() {
  if (promptSaveTimer) {
    clearTimeout(promptSaveTimer)
    promptSaveTimer = null
  }
  if (pendingPromptSave && props.project.persisted) {
    const payload = pendingPromptSave
    pendingPromptSave = null
    await updateClipApi(props.project.id, payload.clipId, { prompt: payload.prompt })
  }
}

function updatePrompt(value: string) {
  if (!clip.value) return
  studio.saveClipPrompt(props.project.id, number.value, clip.value.id, value)
  const backendClipId = clip.value.backendId
  if (props.project.persisted && backendClipId) {
    pendingPromptSave = { clipId: backendClipId, prompt: value }
    if (promptSaveTimer) clearTimeout(promptSaveTimer)
    promptSaveTimer = setTimeout(() => {
      promptSaveTimer = null
      if (!pendingPromptSave) return
      const payload = pendingPromptSave
      pendingPromptSave = null
      void updateClipApi(props.project.id, payload.clipId, { prompt: payload.prompt }).catch(() => {})
    }, 500)
  }
}

async function persistClipReferences(
  nextRefs: Array<{ index: number; assetId: string; assetCode?: string; name: string; kind: StudioAsset['kind'] }>,
) {
  if (!clip.value?.backendId || !props.project.persisted) return
  try {
    await updateClipApi(props.project.id, clip.value.backendId, { references: nextRefs })
    const detail = await getProjectDetail(props.project.id)
    studio.hydrateProjectDetail(detail)
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  }
}

async function addReferenceAsset(asset: StudioAsset) {
  if (!clip.value) return
  const current = references.value.map((ref, idx) => {
    const live = projectAssetsById.value.get(ref.id)
    return {
      index: idx + 1,
      assetId: live?.backendId || ref.id,
      assetCode: ref.id,
      name: ref.name,
      kind: ref.kind,
    }
  })
  current.push({
    index: current.length + 1,
    assetId: asset.backendId || asset.id,
    assetCode: asset.id,
    name: asset.name,
    kind: asset.kind,
  })
  pickerOpen.value = false
  await persistClipReferences(current)
}

async function removeReferenceAsset(assetCode: string) {
  if (!clip.value) return
  const next = references.value
    .filter((ref) => ref.id !== assetCode)
    .map((ref, idx) => {
      const live = projectAssetsById.value.get(ref.id)
      return {
        index: idx + 1,
        assetId: live?.backendId || ref.id,
        assetCode: ref.id,
        name: ref.name,
        kind: ref.kind,
      }
    })
  await persistClipReferences(next)
}

async function generateClipVideo() {
  const activeClip = clip.value
  if (!activeClip || !props.project.persisted || !activeClip.backendId) {
    ui.notify('示例项目暂不支持真实视频生成', 'info')
    return
  }
  if (!activeClip.prompt.trim() || submittingClipId.value === activeClip.backendId || isClipGenerating(activeClip)) return

  const clipIndex = activeClip.id
  const backendClipId = activeClip.backendId
  const isRedraw = !!activeClip.videoUrl
  const modelId = currentVideoModel.value?.id
  if (!modelId) {
    ui.notify('视频模型目录尚未加载完成，请稍后重试', 'error')
    void ensureModelCatalog()
    return
  }
  const resolution = selectedResolution.value
  const ratio = selectedRatio.value
  const durationSeconds = selectedDuration.value
  submittingClipId.value = backendClipId

  try {
    await flushPromptSave()
    const accepted = await startGenerateClipVideo(props.project.id, backendClipId, {
      modelId,
      resolution,
      ratio,
      durationSeconds,
    })
    trackVideoBatchJobs([accepted.job], {
      episodeNumber: number.value,
      modelId,
      resolution,
      ratio,
      durationSeconds,
    })

    const detail = await getProjectDetail(props.project.id)
    studio.hydrateProjectDetail(detail)
    void auth.refreshBalance()
    startBatchPolling()

    ui.notify(`已提交片段 ${clipIndex} ${isRedraw ? '重新生成' : '视频生成'}任务，后台渲染中`, 'success')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    if (submittingClipId.value === backendClipId) submittingClipId.value = null
  }
}

async function composeEpisode() {
  if (!props.project.persisted || !canCompose.value || generating.value || generation.isRunning) return
  const epNum = number.value
  const totalClips = clips.value.length

  await generation.runTask(
    {
      title: `正在合成第 ${epNum} 集完整视频`,
      subtitle: `共 ${totalClips} 个片段 · FFmpeg 免费合成（0 积分）`,
      description: '正在将合成任务派发至独立媒体 Worker',
      steps: [
        '从阿里云 OSS 拉取本集全部片段视频',
        '使用 FFmpeg 归一化帧率与音轨并无缝拼接',
        '将合成本集 MP4 回传至阿里云 OSS',
        '更新本集成片播放与下载入口',
      ],
      hint: '本集视频合成完全免费，不消耗任何积分',
      formatError: apiErrorMessage,
      canRetryError: isRetryableApiError,
      successMessage: () => `第 ${epNum} 集视频已合成完成`,
    },
    async (controls) => {
      generating.value = true
      try {
        const accepted = await startComposeEpisode(props.project.id, epNum)
        controls.setJobId(accepted.job.id)
        controls.setProgress(accepted.job.progress)
        await watchJob(accepted.job.id, (job) => {
          controls.setProgress(job.progress)
          if (job.stepLabel) controls.setDescription(job.stepLabel)
          controls.setStep(Math.min(3, Math.max(0, job.stepIndex - 1)))
        })
        const detail = await getProjectDetail(props.project.id)
        studio.hydrateProjectDetail(detail)
        ui.notify(`第 ${epNum} 集完整视频已合成`, 'success')
        return detail
      } finally {
        generating.value = false
      }
    },
  )
}

async function addClip() {
  if (props.project.persisted) {
    try {
      const created = await createClipApi(props.project.id, number.value, cap.value, '')
      const detail = await getProjectDetail(props.project.id)
      studio.hydrateProjectDetail(detail)
      selectedId.value = created.clipIndex
      await nextTick()
      const list = clipList.value
      if (list) list.scrollLeft = list.scrollWidth
      return
    } catch (error) {
      ui.notify(apiErrorMessage(error), 'error')
      return
    }
  }
  const id = studio.appendClip(props.project.id, number.value)
  if (id === undefined) return

  selectedId.value = id
  await nextTick()
  const list = clipList.value
  if (list) list.scrollLeft = list.scrollWidth
}

function confirmClipDeletion(id: number, event: MouseEvent) {
  const target = clips.value.find((item) => item.id === id)
  if (isClipGenerating(target)) return
  clipToDelete.value = id
  deleteTrigger = event.currentTarget as HTMLButtonElement
  deleteOpen.value = true
}

async function deleteClip() {
  const id = clipToDelete.value
  if (id === undefined) return
  const index = clips.value.findIndex((item) => item.id === id)
  const target = clips.value[index]
  const wasSelected = clip.value?.id === id

  if (props.project.persisted && target?.backendId) {
    try {
      await deleteClipApi(props.project.id, target.backendId)
      const detail = await getProjectDetail(props.project.id)
      studio.hydrateProjectDetail(detail)
      if (wasSelected) {
        selectedId.value = (clips.value[index] ?? clips.value[index - 1])?.id
      }
    } catch (error) {
      ui.notify(apiErrorMessage(error), 'error')
    }
  } else if (studio.removeClip(props.project.id, number.value, id) && wasSelected) {
    selectedId.value = (clips.value[index] ?? clips.value[index - 1])?.id
  }
  deleteOpen.value = false
}
</script>

<template>
  <section class="episode-workbench" aria-labelledby="episode-workbench-title">
    <header class="episode-toolbar">
      <div class="episode-heading">
        <RouterLink
          class="episode-back ui-button ui-button--outline ui-button--sm"
          :to="{ name: 'studio-storyboard', params: { projectId: project.id } }"
          aria-label="返回分镜列表"
          title="返回分镜列表"
        >
          <ArrowLeft :size="14" aria-hidden="true" />
        </RouterLink>
        <span class="episode-heading-divider" aria-hidden="true"></span>
        <h1 id="episode-workbench-title" :title="title">
          <span class="episode-project-name">{{ projectName }}</span>
          <ChevronRight class="episode-heading-separator" :size="13" aria-hidden="true" />
          <span class="episode-index">{{ episodeIndex }}</span>
          <template v-if="episodeName && episodeName !== episodeIndex">
            <span class="episode-heading-separator" aria-hidden="true">·</span>
            <span class="episode-name">{{ episodeName }}</span>
          </template>
        </h1>
      </div>
      <div v-if="episode" class="episode-actions">
        <span v-if="clips.length" class="episode-meta">{{ readyCount }}/{{ clips.length }} 片段已有视频</span>
        <template v-if="episode.composedVideoUrl">
          <VideoPreview :src="episode.composedVideoUrl" :title="`${episodeIndex} 完整成片`" autoplay>
            <template #trigger>
              <button type="button" class="ui-button ui-button--outline ui-button--sm">
                <Play :size="14" aria-hidden="true" />观看成片<template v-if="episode.composedDuration"> ({{ Math.round(episode.composedDuration) }}s)</template>
              </button>
            </template>
          </VideoPreview>
          <a
            class="ui-button ui-button--outline ui-button--sm"
            :href="episode.composedVideoUrl"
            :download="`${projectName}-第${episode.number}集.mp4`"
            target="_blank"
            rel="noopener"
          >
            <Download :size="14" aria-hidden="true" />下载成片
          </a>
        </template>
        <UiButton
          v-if="storyboard && clips.length && project.persisted"
          :variant="missingVideoCount > 0 ? 'primary' : 'outline'"
          size="sm"
          :disabled="generating"
          @click="openBatchDialog()"
        >
          <template #leading><Video :size="14" aria-hidden="true" /></template>
          {{ missingVideoCount > 0 ? `批量生视频 (${missingVideoCount})` : '批量重新生成' }}
        </UiButton>
        <UiButton v-if="storyboard" variant="outline" size="sm" :loading="generating" :disabled="generating || hasActiveVideoJobs" @click="generateFromScript">
          <template v-if="!generating" #leading><Sparkles :size="14" aria-hidden="true" /></template>重新生成分镜
        </UiButton>
        <UiButton variant="primary" size="sm" :disabled="!canCompose" @click="composeEpisode">
          <template #leading><Film :size="14" aria-hidden="true" /></template>
          {{ episode.composedVideoUrl ? '重新合成本集' : '合成本集视频' }}
        </UiButton>
      </div>
    </header>

    <div v-if="batchSummary?.visible" class="episode-batch-banner" :class="{ 'is-done': batchSummary.finished }">
      <div class="episode-batch-banner-head">
        <span class="episode-batch-banner-title">
          <Loader2 v-if="!batchSummary.finished" class="is-spin" :size="15" aria-hidden="true" />
          <CheckCircle2 v-else-if="batchSummary.failed === 0" :size="15" aria-hidden="true" />
          <AlertCircle v-else :size="15" aria-hidden="true" />
          <template v-if="!batchSummary.finished">
            后台批量生视频中：已完成 {{ batchSummary.succeeded }} / {{ batchSummary.total }}
            <template v-if="batchSummary.running"> · 进行中 {{ batchSummary.running }}</template>
            <template v-if="batchSummary.failed"> · 失败 {{ batchSummary.failed }}</template>
          </template>
          <template v-else>
            批量生视频已完成：成功 {{ batchSummary.succeeded }} 段<template v-if="batchSummary.failed"> · 失败 {{ batchSummary.failed }} 段（已自动退还积分）</template>
          </template>
        </span>
        <div class="episode-batch-banner-actions">
          <UiButton
            v-if="batchSummary.finished && batchSummary.failedIds.length"
            variant="outline"
            size="sm"
            :loading="batchSubmitting"
            @click="retryFailedBatchClips"
          >
            <template #leading><RefreshCw :size="13" aria-hidden="true" /></template>
            重试失败片段 ({{ batchSummary.failedIds.length }})
          </UiButton>
          <button
            v-if="batchSummary.finished"
            type="button"
            class="episode-batch-close"
            aria-label="关闭批量视频进度提示"
            @click="dismissBatchBanner"
          >
            <X :size="14" aria-hidden="true" />
          </button>
        </div>
      </div>
      <div class="episode-batch-track" role="progressbar" :aria-valuenow="batchSummary.percent" aria-valuemin="0" aria-valuemax="100">
        <div class="episode-batch-fill" :style="{ width: `${Math.max(6, batchSummary.percent)}%` }"></div>
      </div>
    </div>

    <div v-if="episode" class="episode-layout" :class="{ 'episode-layout--solo': !storyboard }">
      <aside v-if="storyboard" class="episode-assets" aria-labelledby="episode-assets-title">
        <h2 id="episode-assets-title"><Boxes :size="17" aria-hidden="true" />本集资产</h2>
        <p v-if="!storyboard?.assets.length" class="episode-meta episode-assets-empty">暂无本集资产</p>
        <div v-else class="episode-asset-groups">
          <section v-for="group in assetGroups" :key="group.kind" class="episode-asset-group">
            <h3><component :is="group.icon" :size="15" aria-hidden="true" />{{ group.label }}<span>{{ group.assets.length }}</span></h3>
            <ul v-if="group.assets.length" class="episode-asset-grid">
              <li v-for="asset in group.assets" :key="asset.id">
                <ImagePreview v-if="asset.imageUrl" :src="asset.imageUrl" :title="asset.name">
                  <template #trigger>
                    <button type="button" class="episode-asset-thumb" :aria-label="'预览资产 ' + asset.name"><img :src="asset.imageUrl" alt="" /></button>
                  </template>
                </ImagePreview>
                <span v-else class="episode-asset-thumb">
                  <component :is="group.icon" :size="22" :stroke-width="1.5" aria-hidden="true" />
                </span>
                <span class="episode-asset-name">{{ asset.name }}</span>
              </li>
            </ul>
          </section>
        </div>
      </aside>

      <div v-if="storyboard" class="episode-editor">
        <section v-if="clip" class="episode-references" aria-labelledby="episode-clip-title">
          <div class="episode-reference-materials">
            <div class="episode-section-head">
              <h2 id="episode-clip-title"><Clapperboard :size="17" aria-hidden="true" />片段 {{ clip.id }}</h2>
            </div>
            <ul class="episode-reference-list" aria-label="片段参考素材">
              <li v-for="asset in references" :key="asset.id">
                <div class="episode-reference-thumb-wrap">
                  <ImagePreview v-if="asset.imageUrl" :src="asset.imageUrl" :title="asset.name">
                    <template #trigger>
                      <button type="button" class="episode-asset-thumb" :aria-label="'预览片段参考 ' + asset.name"><img :src="asset.imageUrl" alt="" /></button>
                    </template>
                  </ImagePreview>
                  <span v-else class="episode-asset-thumb">
                    <component :is="asset.icon" :size="20" :stroke-width="1.5" aria-hidden="true" />
                  </span>
                  <span v-if="asset.index" class="episode-reference-no">图片{{ asset.index }}</span>
                  <button
                    v-if="project.persisted && clip.backendId"
                    type="button"
                    class="episode-reference-remove"
                    :aria-label="`移除参考 ${asset.name}`"
                    title="移除该参考素材"
                    @click="removeReferenceAsset(asset.id)"
                  >
                    <X :size="11" aria-hidden="true" />
                  </button>
                </div>
                <span class="episode-asset-name" :title="asset.name">{{ asset.name }}</span>
              </li>
              <li>
                <UiButton
                  class="episode-reference-add"
                  variant="secondary"
                  size="sm"
                  :disabled="!project.persisted || !clip.backendId || !availablePickerAssets.length"
                  :title="availablePickerAssets.length ? '从项目资产中添加参考图' : '项目所有资产已添加'"
                  @click="pickerOpen = true"
                >
                  <template #leading><Plus :size="17" aria-hidden="true" /></template>
                  添加素材
                </UiButton>
              </li>
            </ul>
          </div>
        </section>

        <section v-if="clip" class="episode-prompt" aria-label="片段提示词编辑">
          <UiTextarea
            :key="clip.id"
            :model-value="clip.prompt"
            label="视频提示词"
            :rows="5"
            @update:model-value="updatePrompt"
          />
          <div class="episode-prompt-actions">
            <div class="episode-video-controls">
              <VideoModelPicker
                v-model="selectedVideoModelId"
                :models="videoModels"
                :clip-duration="selectedDuration"
                :project-ratio="selectedRatio"
                :reference-count="references.length"
                :prompt-length="clip.prompt.trim().length"
                :disabled="isClipGenerating(clip)"
              />
              <VideoParamsPopover
                v-model:resolution="selectedResolution"
                v-model:ratio="selectedRatio"
                v-model:duration="selectedDuration"
                :model="currentVideoModel"
                :default-ratio="project.creation.settings.ratio || '16:9'"
                mode="single"
                :disabled="isClipGenerating(clip)"
                @duration-commit="commitClipDuration"
              />
            </div>
            <div class="episode-video-controls">
              <div
                class="episode-cta-split"
                :class="{ 'is-solo': !estimatedVideoQuote || isClipGenerating(clip) }"
              >
                <span
                  v-if="estimatedVideoQuote && !isClipGenerating(clip)"
                  class="episode-cta-cost"
                  :title="estimatedVideoQuote.hint"
                >
                  <Sparkles :size="13" class="episode-cta-cost-icon" aria-hidden="true" />
                  <strong class="episode-cta-cost-num">{{ estimatedVideoQuote.amount }}</strong>
                  <span class="episode-cta-cost-unit">积分</span>
                </span>
                <UiButton
                  class="episode-generate-btn"
                  variant="primary"
                  size="sm"
                  :loading="submittingClipId === clip.backendId || isClipGenerating(clip)"
                  :disabled="!clip.prompt.trim() || !currentVideoModel || generating || submittingClipId === clip.backendId || isClipGenerating(clip)"
                  @click="generateClipVideo"
                >
                  <template v-if="submittingClipId !== clip.backendId && !isClipGenerating(clip)" #leading><Video :size="15" aria-hidden="true" /></template>
                  {{ isClipGenerating(clip) ? '生成中…' : clip.videoUrl ? '重新生成视频' : '生成视频' }}
                </UiButton>
              </div>
            </div>
          </div>
        </section>
        <EmptyState v-else class="episode-clip-empty" title="暂无片段">
          <template #icon><Clapperboard :size="25" :stroke-width="1.5" /></template>
        </EmptyState>

        <section class="episode-strip" aria-labelledby="episode-strip-title">
          <div class="episode-section-head">
            <div class="episode-strip-left">
              <h2 id="episode-strip-title">片段列表</h2>
              <span class="episode-meta">{{ clips.length }} 个片段（支持拖拽或左右按钮调序）</span>
            </div>
            <div v-if="clips.length" class="episode-strip-actions">
              <template v-if="clips.length > 1 && selectedClipIndex >= 0">
                <UiButton
                  variant="outline"
                  size="sm"
                  :disabled="reorderingClips || selectedClipIndex <= 0"
                  title="将当前选中片段向前移动一位"
                  @click="moveClipOrder(selectedClipIndex, selectedClipIndex - 1)"
                >
                  <template #leading><ArrowLeft :size="13" aria-hidden="true" /></template>前移
                </UiButton>
                <UiButton
                  variant="outline"
                  size="sm"
                  :disabled="reorderingClips || selectedClipIndex >= clips.length - 1"
                  title="将当前选中片段向后移动一位"
                  @click="moveClipOrder(selectedClipIndex, selectedClipIndex + 1)"
                >
                  <template #leading><ArrowRight :size="13" aria-hidden="true" /></template>后移
                </UiButton>
              </template>
              <template v-if="project.persisted && selectMode">
                <span class="episode-meta">已选 {{ checkedClipIds.length }} 段</span>
                <UiButton variant="primary" size="sm" :disabled="!checkedClipIds.length" @click="openBatchFromSelection">
                  <template #leading><Video :size="13" aria-hidden="true" /></template>
                  生成 / 重生成已选 ({{ checkedClipIds.length }})
                </UiButton>
              </template>
              <UiButton v-if="project.persisted" :variant="selectMode ? 'secondary' : 'outline'" size="sm" @click="toggleSelectMode">
                <template #leading><CheckSquare :size="13" aria-hidden="true" /></template>
                {{ selectMode ? '退出多选' : '多选' }}
              </UiButton>
            </div>
          </div>
          <ol ref="clipList" class="episode-clips">
            <li
              v-for="(item, idx) in clips"
              :key="item.backendId || item.id"
              :class="{ 'is-dragging': dragSourceIndex === idx, 'is-drop-target': dragOverIndex === idx && dragSourceIndex !== idx }"
              :draggable="!selectMode && !reorderingClips && clips.length > 1"
              @dragstart="handleClipDragStart(idx, $event)"
              @dragover="handleClipDragOver(idx, $event)"
              @drop="handleClipDrop(idx, $event)"
              @dragend="handleClipDragEnd"
            >
              <button
                type="button"
                class="episode-clip"
                :class="{
                  'is-generating': isClipGenerating(item),
                  'is-checked': selectMode && !!item.backendId && checkedSet.has(item.backendId),
                }"
                :aria-pressed="clip?.id === item.id"
                @click="selectedId = item.id"
              >
                <span class="episode-clip-thumb">
                  <img v-if="item.previewUrl" :src="item.previewUrl" alt="" />
                  <video
                    v-else-if="item.videoUrl"
                    class="episode-clip-video-thumb"
                    :src="`${item.videoUrl}#t=0.1`"
                    muted
                    playsinline
                    preload="metadata"
                  />
                  <Clapperboard v-else :size="22" :stroke-width="1.5" aria-hidden="true" />
                  <Check v-if="item.videoUrl && !isClipGenerating(item)" class="episode-clip-ready" :size="15" aria-label="已有视频" />
                  <span
                    v-if="!isClipGenerating(item) && (item.videoStatus === 'failed' || clipFailedReason(item))"
                    class="episode-clip-failed"
                    :title="clipFailedReason(item) || '视频生成失败'"
                  >
                    <AlertCircle :size="13" aria-hidden="true" />
                  </span>
                  <span v-if="isClipGenerating(item)" class="episode-clip-loading-mask">
                    <Loader2 class="is-spin" :size="15" aria-hidden="true" />
                    <span>{{ clipJobProgress(item) }}</span>
                  </span>
                </span>
                <span class="episode-clip-caption"><strong>片段 {{ item.id }}</strong><span>{{ item.durationSeconds }} 秒</span></span>
              </button>
              <button
                v-if="selectMode && item.backendId"
                type="button"
                class="episode-clip-check"
                :class="{ 'is-checked': checkedSet.has(item.backendId) }"
                :disabled="isClipGenerating(item)"
                :aria-label="`选择片段 ${item.id}`"
                @click.stop="toggleClipCheck(item)"
              >
                <Check v-if="checkedSet.has(item.backendId)" :size="11" :stroke-width="2.6" />
              </button>
              <button
                v-if="item.videoUrl && !isClipGenerating(item)"
                type="button"
                class="episode-clip-play"
                :aria-label="`播放片段 ${item.id}`"
                :title="`播放片段 ${item.id}`"
                @click.stop="openClipPreview(item)"
              >
                <Play :size="15" fill="currentColor" aria-hidden="true" />
              </button>
              <UiIconButton
                v-if="!selectMode && !isClipGenerating(item)"
                class="episode-clip-delete"
                :label="`删除片段 ${item.id}`"
                @click="confirmClipDeletion(item.id, $event)"
              >
                <Trash2 :size="14" aria-hidden="true" />
              </UiIconButton>
            </li>
            <li>
              <button type="button" class="episode-clip episode-clip-add" @click="addClip">
                <Plus :size="22" aria-hidden="true" />
                新增镜头
              </button>
            </li>
          </ol>
        </section>
      </div>

      <EmptyState v-else class="episode-empty" title="待拆分镜" :description="`单片段最长 ${cap} 秒`">
        <template #icon><Clapperboard :size="25" :stroke-width="1.5" /></template>
        <UiButton variant="primary" :loading="generating" :disabled="generating" @click="generateFromScript">
          <template v-if="!generating" #leading><Sparkles :size="16" aria-hidden="true" /></template>一键生成本集分镜
        </UiButton>
      </EmptyState>
    </div>

    <StudioBatchVideoDialog
      v-model:open="batchOpen"
      :episode-number="number"
      :clips="clips"
      :project-assets="project.assets ?? []"
      :project-ratio="project.creation.settings.ratio || '16:9'"
      :active-clip-ids="activeClipIds"
      :video-models="videoModels"
      :initial-selected-ids="batchInitialIds"
      :submitting="batchSubmitting"
      @submit="submitBatchClipVideos"
    />

    <UiDialog v-model:open="pickerOpen" title="添加片段参考素材" description="点击下方项目资产即可按序追加为当前片段的参考图片（图片N）。">
      <ul v-if="availablePickerAssets.length" class="picker-asset-grid">
        <li v-for="asset in availablePickerAssets" :key="asset.id">
          <button type="button" class="picker-asset-card" @click="addReferenceAsset(asset)">
            <span class="picker-asset-thumb">
              <img v-if="asset.imageUrl" :src="asset.imageUrl" alt="" />
              <component :is="assetKindIcons[asset.kind]" v-else :size="20" aria-hidden="true" />
            </span>
            <span class="picker-asset-info">
              <strong>{{ asset.name }}</strong>
              <small :class="{ 'is-ready': !!asset.imageUrl }">{{ asset.imageUrl ? '已有图片' : '暂未生图' }}</small>
            </span>
          </button>
        </li>
      </ul>
      <p v-else class="episode-meta">项目中的所有资产均已添加到该片段。</p>
      <template #footer>
        <UiButton variant="ghost" @click="pickerOpen = false">关闭</UiButton>
      </template>
    </UiDialog>

    <VideoPreview
      v-if="previewClip"
      v-model:open="previewOpen"
      :src="previewClip.src"
      :poster="previewClip.poster"
      :title="`片段 ${previewClip.id}`"
      autoplay
    />

    <UiDialog v-model:open="deleteOpen" title="删除片段" :description="`确定删除本集的片段 ${clipToDelete} 吗？`">
      <template #footer>
        <UiButton variant="ghost" @click="deleteOpen = false">取消</UiButton>
        <UiButton variant="danger" @click="deleteClip">确认删除</UiButton>
      </template>
    </UiDialog>
  </section>
</template>

<style scoped>
.episode-workbench { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.episode-toolbar, .episode-heading, .episode-actions, .episode-section-head {
  display: flex;
  align-items: center;
  gap: 12px;
}
.episode-toolbar {
  justify-content: space-between;
  flex-wrap: wrap;
  padding: 8px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-panel);
  background: var(--color-surface);
}
.episode-batch-banner {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid rgb(240 184 75 / 32%);
  border-radius: var(--radius-panel);
  background: var(--color-surface);
}
.episode-batch-banner.is-done { border-color: var(--border-subtle); }
.episode-batch-banner-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.episode-batch-banner-title {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  color: var(--color-gold-soft);
}
.episode-batch-banner.is-done .episode-batch-banner-title { color: var(--color-text); }
.episode-batch-banner-actions { display: flex; align-items: center; gap: 8px; }
.episode-batch-close {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  color: var(--color-muted);
  cursor: pointer;
}
.episode-batch-close:hover { background: var(--surface-hover); color: var(--color-text); }
.episode-batch-track {
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: rgb(255 255 255 / 8%);
}
.episode-batch-fill {
  height: 100%;
  border-radius: inherit;
  background: var(--color-gold);
  transition: width .35s ease;
}
.episode-heading { flex: 1 1 240px; min-width: 0; gap: 8px; }
.episode-heading-divider { flex: 0 0 1px; height: 18px; background: var(--border-subtle); }
.episode-heading h1 {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 6px;
  min-width: 0;
  margin: 0;
  font-size: var(--font-size-body);
  font-weight: 500;
  line-height: 1.4;
  white-space: nowrap;
}
.episode-project-name, .episode-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.episode-project-name { max-width: 38%; color: var(--color-muted); }
.episode-heading-separator, .episode-index { flex-shrink: 0; }
.episode-heading-separator { color: var(--color-muted); }
.episode-name { color: var(--color-gold-soft); }
.episode-actions { flex-wrap: wrap; }
.episode-toolbar .ui-button { gap: 6px; min-height: 30px; padding-inline: 10px; }
.episode-back.ui-button { flex: 0 0 30px; width: 30px; padding: 0; }
.episode-layout {
  flex: 1;
  display: grid;
  grid-template-columns: clamp(196px, 20%, 268px) minmax(0, 1fr);
  min-height: 536px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-panel);
  background: var(--color-surface);
}
.episode-layout--solo { grid-template-columns: minmax(0, 1fr); }
.episode-workbench h2, .episode-workbench h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
}
.episode-assets > h2, .episode-section-head h2 svg { color: var(--color-gold-soft); }
.episode-assets { min-width: 0; padding: 16px; border-right: 1px solid var(--border-subtle); }
.episode-asset-groups { display: grid; gap: 16px; margin-top: 16px; }
.episode-asset-group { min-width: 0; }
.episode-asset-group h3 { margin-bottom: 8px; color: var(--color-muted); font-weight: 500; }
.episode-asset-group h3 span { color: var(--color-muted); font-size: 12px; font-weight: 400; }
.episode-asset-grid, .episode-reference-list, .episode-clips { margin: 0; padding: 0; list-style: none; }
.episode-asset-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.episode-asset-thumb, .episode-clip-thumb {
  display: grid;
  place-items: center;
  overflow: hidden;
  background: var(--surface-hover);
  color: var(--color-muted);
}
.episode-asset-thumb { aspect-ratio: 4 / 3; border: 1px solid var(--border-subtle); border-radius: 6px; }
button.episode-asset-thumb { width: 100%; cursor: zoom-in; }
.episode-asset-thumb img, .episode-clip-thumb img {
  width: 100%;
  height: 100%;
  min-height: 0;
  object-fit: cover;
}
.episode-asset-name { display: block; margin-top: 4px; font-size: 12px; overflow-wrap: anywhere; }
.episode-editor { display: grid; grid-template-rows: auto minmax(min-content, 1fr) auto; min-width: 0; }
.episode-references, .episode-prompt, .episode-strip { min-width: 0; padding: 12px 16px; }
.episode-section-head { justify-content: space-between; flex-wrap: wrap; }
.episode-strip-left, .episode-strip-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.episode-strip-actions .ui-button { min-height: 28px; padding-inline: 8px; font-size: 12px; }
.episode-meta { margin: 0; color: var(--color-muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.episode-assets-empty { margin-top: 12px; }
.episode-references { display: block; }
.episode-reference-materials { min-width: 0; }
.episode-reference-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.episode-reference-list li { flex: 0 1 84px; min-width: 0; max-width: 100%; }
.episode-reference-thumb-wrap { position: relative; }
.episode-reference-no {
  position: absolute;
  top: 4px;
  left: 4px;
  padding: 0 5px;
  border: 1px solid rgb(240 184 75 / 26%);
  border-radius: 4px;
  background: rgb(9 10 13 / 78%);
  color: var(--color-gold-soft);
  font-size: 10px;
  font-weight: 500;
  line-height: 17px;
  pointer-events: none;
}
.episode-reference-remove {
  position: absolute;
  top: 4px;
  right: 4px;
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border: 1px solid rgb(255 255 255 / 16%);
  border-radius: 50%;
  background: rgb(9 10 13 / 82%);
  color: var(--color-text);
  cursor: pointer;
  opacity: 0;
  transition: opacity .15s, border-color .15s, color .15s;
}
.episode-reference-thumb-wrap:is(:hover, :focus-within) .episode-reference-remove { opacity: 1; }
.episode-reference-remove:is(:hover, :focus-visible) { border-color: var(--color-error); color: var(--color-error); }
.episode-reference-list .episode-asset-name {
  overflow: hidden;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.episode-reference-add.ui-button {
  flex-direction: column;
  gap: 3px;
  width: 100%;
  min-height: 0;
  aspect-ratio: 4 / 3;
  padding: 4px;
  border-style: dashed;
  border-radius: 6px;
  background: transparent;
  color: var(--color-muted);
  opacity: 1;
}
.episode-reference-add.ui-button:not(:disabled):is(:hover, :focus-visible) {
  border-color: var(--color-gold);
  color: var(--color-gold-soft);
}
.episode-prompt-actions > span { display: flex; align-items: center; gap: 6px; }
.episode-prompt { display: flex; flex-direction: column; border-top: 1px solid var(--border-subtle); }
.episode-prompt :deep(.ui-field) { display: flex; flex: 1; flex-direction: column; }
.episode-prompt :deep(textarea) { flex: 1; width: 100%; min-height: 142px; }
.episode-prompt-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; margin-top: 10px; }
.episode-video-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.episode-cta-split {
  display: inline-flex;
  align-items: stretch;
  height: 36px;
  border-radius: 9px;
  overflow: hidden;
  border: 1px solid rgb(240 184 75 / 55%);
  box-shadow: 0 2px 10px rgb(240 184 75 / 12%);
}
.episode-cta-split.is-solo {
  border-color: transparent;
  box-shadow: none;
}
.episode-cta-cost {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  padding: 0 12px;
  background: #13151c;
  color: var(--color-gold-soft);
  user-select: none;
}
.episode-cta-cost-icon {
  align-self: center;
  color: var(--color-gold);
  flex-shrink: 0;
}
.episode-cta-cost-num {
  align-self: center;
  font-size: 16px;
  font-weight: 700;
  color: #f8cc66;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  line-height: 1;
}
.episode-cta-cost-unit {
  align-self: center;
  font-size: 11px;
  font-weight: 500;
  color: rgb(248 204 102 / 82%);
  line-height: 1;
}
.episode-generate-btn.ui-button {
  min-height: 34px;
  height: 100%;
  padding: 0 15px;
  border: 0;
  border-radius: 0;
}
.episode-cta-split.is-solo .episode-generate-btn.ui-button {
  border-radius: 9px;
}
.episode-clip-empty { grid-row: 1 / 3; align-self: center; }
.episode-strip { grid-row: 3; border-top: 1px solid var(--border-subtle); }
.episode-clips {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  margin-top: 8px;
  padding: 3px 3px 5px;
}
.episode-clips > li { position: relative; display: grid; flex: 0 0 132px; transition: opacity .15s, transform .15s; }
.episode-clips > li.is-dragging { opacity: 0.45; }
.episode-clips > li.is-drop-target .episode-clip { border-color: var(--color-gold); box-shadow: 0 0 0 2px rgb(240 184 75 / 45%); }
.episode-clip {
  width: 100%;
  padding: 0;
  overflow: hidden;
  border: 1px solid var(--border-control);
  border-radius: 7px;
  color: var(--color-text);
  background: var(--color-surface);
  cursor: pointer;
  transition: border-color .15s;
}
.episode-clip.is-generating { border-color: rgb(240 184 75 / 45%); }
.episode-clip.is-checked { border-color: var(--color-gold); box-shadow: 0 0 0 1px var(--color-gold); }
.episode-clip-thumb { position: relative; aspect-ratio: 16 / 9; }
.episode-clip-video-thumb { width: 100%; height: 100%; object-fit: cover; pointer-events: none; }
.episode-clip-ready { position: absolute; inset: 5px auto auto 5px; color: var(--color-gold-soft); filter: drop-shadow(0 1px 2px rgb(0 0 0 / 70%)); }
.episode-clip-failed {
  position: absolute;
  inset: 5px auto auto 5px;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgb(9 10 13 / 82%);
  color: var(--color-error);
}
.episode-clip-loading-mask {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  background: rgb(9 10 13 / 74%);
  color: var(--color-gold-soft);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.episode-clip-check {
  position: absolute;
  top: 5px;
  right: 5px;
  z-index: 2;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border: 1px solid rgb(255 255 255 / 45%);
  border-radius: 5px;
  background: rgb(9 10 13 / 82%);
  color: var(--color-ink);
  cursor: pointer;
}
.episode-clip-check.is-checked {
  border-color: var(--color-gold);
  background: var(--color-gold);
}
.episode-clip-play {
  position: absolute;
  top: 22px;
  left: 50%;
  transform: translateX(-50%);
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  padding-left: 2px;
  border: 1px solid rgb(240 184 75 / 55%);
  border-radius: 50%;
  background: rgb(9 10 13 / 78%);
  color: var(--color-gold-soft);
  cursor: pointer;
  transition: transform .15s, background-color .15s, border-color .15s, color .15s;
}
.episode-clip-play:is(:hover, :focus-visible) {
  transform: translateX(-50%) scale(1.08);
  border-color: var(--color-gold);
  background: var(--color-gold);
  color: var(--color-ink);
}
.episode-clips :deep(.episode-clip-delete) {
  position: absolute;
  inset: 5px 5px auto auto;
  width: 28px;
  height: 28px;
  border-color: var(--border-control);
  border-radius: 6px;
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
}
.episode-clips :deep(.episode-clip-delete:is(:hover, :focus-visible)) { border-color: var(--color-error); color: var(--color-error); }
@media (hover: hover) and (pointer: fine) {
  .episode-clips > li:not(:hover):not(:focus-within) :deep(.episode-clip-delete) { opacity: 0; pointer-events: none; }
}
.episode-clip-caption { display: flex; justify-content: space-between; gap: 4px; padding: 6px 8px; font-size: 12px; }
.episode-clip-caption span { color: var(--color-muted); }
.episode-clip:hover, .episode-clip[aria-pressed="true"] { border-color: var(--color-gold); }
.episode-clip[aria-pressed="true"] .episode-clip-caption { color: var(--color-gold-soft); background: var(--gold-tint); }
.episode-clip:focus-visible { outline: 2px solid var(--color-gold); outline-offset: 2px; }
.episode-clip-add {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-style: dashed;
  color: var(--color-muted);
  font-size: 13px;
}
.episode-clip-add:is(:hover, :focus-visible) { color: var(--color-gold-soft); background: var(--gold-tint); }
.episode-empty { align-self: center; }
.picker-asset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 360px;
  overflow-y: auto;
}
.picker-asset-card {
  display: flex;
  flex-direction: column;
  width: 100%;
  padding: 6px;
  border: 1px solid var(--border-control);
  border-radius: 8px;
  background: var(--color-surface);
  color: var(--color-text);
  text-align: left;
  cursor: pointer;
}
.picker-asset-card:is(:hover, :focus-visible) { border-color: var(--color-gold); background: var(--surface-hover); }
.picker-asset-thumb {
  display: grid;
  place-items: center;
  width: 100%;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  border-radius: 5px;
  background: var(--color-elevated);
  color: var(--color-muted);
}
.picker-asset-thumb img { width: 100%; height: 100%; object-fit: cover; }
.picker-asset-info { display: flex; flex-direction: column; gap: 2px; padding: 6px 2px 2px; }
.picker-asset-info strong { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.picker-asset-info small { color: var(--color-muted); font-size: 11px; }
.picker-asset-info small.is-ready { color: var(--color-success); }
.is-spin { animation: spin 1s linear infinite; }
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
@container (max-width: 640px) {
  .episode-layout { grid-template: auto 1fr / minmax(0, 1fr); min-height: 0; }
  .episode-assets { border-right: 0; border-bottom: 1px solid var(--border-subtle); }
  .episode-asset-groups { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  .episode-asset-grid { grid-template-columns: repeat(auto-fill, minmax(min(100%, 80px), 1fr)); }
  .episode-empty { min-height: 280px; }
}
</style>
