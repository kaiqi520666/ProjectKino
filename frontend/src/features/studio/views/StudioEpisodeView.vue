<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Clapperboard, Sparkles } from 'lucide-vue-next'
import EmptyState from '@/components/business/EmptyState.vue'
import MediaHistoryDialog from '@/components/business/MediaHistoryDialog.vue'
import type { MediaHistoryItem } from '@/components/business/MediaHistoryDialog.vue'
import UiButton from '@/components/ui/UiButton.vue'
import VideoPreview from '@/components/ui/VideoPreview.vue'
import AssetLibraryDialog from '@/features/assets/AssetLibraryDialog.vue'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import {
  apiErrorMessage,
  createClipApi,
  deleteClipApi,
  deleteClipVideoHistoryApi,
  getJob,
  getProjectDetail,
  reorderClipsApi,
  selectClipVideoHistoryApi,
  startBatchGenerateClipVideos,
  startComposeEpisode,
  startGenerateClipVideo,
  startGenerateNewClip,
  startGenerateStoryboard,
  startRegenerateClipStoryboard,
} from '../api'
import { defaultSegmentDuration } from '../components/drama-creation'
import EpisodeActionDialogs from '../components/EpisodeActionDialogs.vue'
import EpisodeAssetsSidebar from '../components/EpisodeAssetsSidebar.vue'
import EpisodeClipPromptPanel, { type ClipJobAlertInfo } from '../components/EpisodeClipPromptPanel.vue'
import EpisodeClipReferences from '../components/EpisodeClipReferences.vue'
import EpisodeClipStrip from '../components/EpisodeClipStrip.vue'
import EpisodeJobBanners from '../components/EpisodeJobBanners.vue'
import EpisodeToolbar from '../components/EpisodeToolbar.vue'
import StudioBatchVideoDialog from '../components/StudioBatchVideoDialog.vue'
import { useBatchJobTracker } from '../composables/useBatchJobTracker'
import { useClipPromptSync } from '../composables/useClipPromptSync'
import { useClipReferences } from '../composables/useClipReferences'
import { useClipStoryboardGrid } from '../composables/useClipStoryboardGrid'
import { useEpisodeLibraryActions } from '../composables/useEpisodeLibraryActions'
import { useModelCatalog } from '../composables/useModelCatalog'
import {
  isClipDurationExceededByModel,
  modelMaxDuration,
  modelMinDuration,
  resolveDefaultVideoModel,
} from '../model-defaults'
import { computeStoryboardLocks, formatElapsedSeconds } from '../storyboard-job-helpers'
import { useStoryboardJobStore } from '../storyboard-job-store'
import {
  buildEpisodeNavItems,
  episodeLabel,
  isEpisodeNumber,
  readEpisode,
  resolveNeighborEpisodes,
  type StudioProject,
} from '../studio-project'
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
const router = useRouter()
const auth = useAuthStore()
const studio = useStudioStore()
const storyboardJobs = useStoryboardJobStore()
const ui = useUiStore()
const { imageModels, videoModels, ensureLoaded: ensureModelCatalog } = useModelCatalog()

const projectRef = computed(() => props.project)
const number = computed(() => Number(route.params.episode))
const totalEpisodes = computed(() => props.project.creation.settings.episodeCount)
const episode = computed(() =>
  isEpisodeNumber(number.value, totalEpisodes.value)
    ? readEpisode(props.project, number.value)
    : null,
)
const projectName = computed(() => props.project.creation.settings.name)
const episodeIndex = computed(() => (episode.value ? `第 ${episode.value.number} 集` : '本集不存在'))
const episodeName = computed(() => episode.value?.title.trim() ?? '')
const title = computed(() => `${projectName.value} · ${episode.value ? episodeLabel(episode.value) : episodeIndex.value}`)
const cap = computed(() => props.project.creation.settings.maxSegmentDuration ?? defaultSegmentDuration)
const storyboard = computed(() => (episode.value ? props.project.storyboards?.[number.value] : undefined))
const clips = computed(() => storyboard.value?.clips ?? [])
const selectedId = ref<number>()
const clip = computed(() => clips.value.find(({ id }) => selectedId.value === id) ?? clips.value[0])
const selectedClipIndex = computed(() =>
  clip.value ? clips.value.findIndex((item) => item.id === clip.value!.id) : -1,
)
const readyCount = computed(() => clips.value.filter(({ videoUrl }) => videoUrl).length)
const missingVideoCount = computed(() => clips.value.filter(({ videoUrl, backendId }) => backendId && !videoUrl).length)

const episodeNavItems = computed(() => buildEpisodeNavItems(props.project))
const neighborEpisodes = computed(() => resolveNeighborEpisodes(number.value, totalEpisodes.value))

const deleteOpen = ref(false)
const pickerOpen = ref(false)
const batchOpen = ref(false)
const batchInitialIds = ref<string[]>([])
const batchSubmitting = ref(false)
const submittingClipId = ref<string | null>(null)
const selectMode = ref(false)
const checkedClipIds = ref<string[]>([])
const reorderingClips = ref(false)
const previewClip = ref<{ id: number; src: string; poster?: string; title?: string } | null>(null)
const previewOpen = computed({
  get: () => previewClip.value !== null,
  set: (value: boolean) => {
    if (!value) previewClip.value = null
  },
})
const refAudioEl = useTemplateRef<HTMLAudioElement>('refAudioEl')
const submittingAction = ref(false)
const clipToDelete = ref<number>()
const selectedVideoModelId = ref('')
const selectedResolution = ref<'480p' | '720p' | '1080p'>('720p')
const selectedRatio = ref(props.project.creation.settings.ratio || '16:9')
const selectedDuration = ref(10)
const clipHistoryOpen = ref(false)
const clipHistorySelecting = ref(false)
const clipHistoryDeletingId = ref<string | null>(null)
const dismissedClipJobIds = ref<Set<string>>(new Set())
const regenOpen = ref(false)
const regenScope = ref<'clip' | 'episode'>('clip')
const regenRefreshRefs = ref(true)
const regenFeedback = ref('')
const addClipOpen = ref(false)
const addClipFeedback = ref('')
const addClipPosition = ref<'after' | 'end'>('after')
const addClipDuration = ref(10)
const addClipBusy = ref(false)
let deleteTrigger: HTMLButtonElement | undefined
const clipStrip = useTemplateRef<InstanceType<typeof EpisodeClipStrip>>('clipStrip')

const videoModelNames = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const model of videoModels.value) map[model.id] = model.displayName
  return map
})

const currentVideoModel = computed(
  () => videoModels.value.find((m) => m.id === selectedVideoModelId.value) ?? videoModels.value[0] ?? null,
)

function syncDefaultVideoModel(force = false) {
  if (!videoModels.value.length) return
  const currentValid =
    !force
    && selectedVideoModelId.value
    && videoModels.value.some((m) => m.id === selectedVideoModelId.value)
  if (currentValid) return
  const projectCap = props.project.creation.settings.maxSegmentDuration ?? defaultSegmentDuration
  const preferred = props.project.creation.settings.videoModelId
  const resolved = resolveDefaultVideoModel(videoModels.value, projectCap, preferred)
  if (resolved) selectedVideoModelId.value = resolved.id
}

onMounted(async () => {
  await ensureModelCatalog()
  syncDefaultVideoModel()
})

watch(
  () => [
    props.project.id,
    props.project.creation.settings.videoModelId,
    props.project.creation.settings.maxSegmentDuration,
  ] as const,
  () => {
    syncDefaultVideoModel(true)
  },
)

const episodeClipBackendIds = computed(
  () => new Set(clips.value.map((c) => c.backendId).filter((id): id is string => Boolean(id))),
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
  canPoll: () => Boolean(props.project.persisted),
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
    return (
      (detail.activeJobs ?? []).some(
        (j) => j.jobType === 'clip_video' && j.targetId && epClipIds.has(j.targetId),
      ) || epClips.some((c) => c.videoStatus === 'generating')
    )
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
  return Boolean(item?.backendId && activeClipIds.value.has(item.backendId))
}

function clipJobProgress(item: StoryboardClip): string {
  if (!item.backendId) return '生成中'
  const job = activeVideoJobsByClipId.value.get(item.backendId)
  if (!job || job.status === 'queued') return '排队中'
  if (job.progress > 0) return `${job.progress}%`
  return '生成中'
}

function clipJobAlert(item?: StoryboardClip): ClipJobAlertInfo | null {
  if (!item || isClipGenerating(item)) return null
  const transient = failedReasonForClipId(item.backendId)
  if (transient) {
    return { status: 'failed', message: transient, jobId: item.lastJobId }
  }
  if (item.lastJobStatus === 'review' || item.lastJobStatus === 'failed') {
    if (item.lastJobId && dismissedClipJobIds.value.has(item.lastJobId)) return null
    return {
      status: item.lastJobStatus,
      message:
        item.lastJobError
        || (item.lastJobStatus === 'review'
          ? '上游状态待后台核对，积分冻结中'
          : '最近一次生视频失败，请重试'),
      jobId: item.lastJobId,
    }
  }
  return null
}

function dismissClipJobAlert(jobId?: string) {
  if (!jobId) return
  const next = new Set(dismissedClipJobIds.value)
  next.add(jobId)
  dismissedClipJobIds.value = next
}

function clipFailedReason(item: StoryboardClip): string {
  return clipJobAlert(item)?.message ?? ''
}

const episodeJob = computed(() => storyboardJobs.getEpisodeJob(props.project.id, number.value))

const locks = computed(() =>
  computeStoryboardLocks({
    episodeNumber: number.value,
    job: episodeJob.value,
    clipGenerating: false,
    syncing: submittingAction.value,
    reordering: reorderingClips.value,
  }),
)

const checkedSet = computed(() => new Set(checkedClipIds.value))

// Placeholder ref updated after grid composable binds; avoids circular init between prompt sync and grid lock.
const gridGeneratingRef = computed(() => grid.isCurrentClipGridGenerating.value)

const currentClipLocked = computed(() =>
  Boolean(
    submittingAction.value
    || isClipGenerating(clip.value)
    || gridGeneratingRef.value
    || locks.value.isClipLocked(clip.value?.backendId),
  ),
)

const { flushPromptSave, updatePrompt, commitClipDuration } = useClipPromptSync({
  project: projectRef,
  episodeNumber: number,
  clip,
  currentClipLocked,
  isClipGenerating,
})

const {
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
} = useClipReferences({
  project: projectRef,
  episodeNumber: number,
  storyboard,
  clip,
  currentVideoModel,
  isLocked: () => currentClipLocked.value,
  flushPromptSave,
  audioElement: refAudioEl,
})

const grid = useClipStoryboardGrid({
  project: projectRef,
  clips,
  clip,
  references,
  selectedRatio,
  imageModels,
  ensureModelCatalog,
  flushPromptSave,
})

const {
  togglingComposedLibrary,
  batchCollectingClips,
  checkedCollectableClips,
  isClipInLibrary,
  isClipLibraryBusy,
  toggleClipLibrary,
  isComposedInLibrary,
  toggleComposedLibrary,
  collectSelectedClips,
} = useEpisodeLibraryActions({
  project: projectRef,
  projectName,
  episodeNumber: number,
  episode,
  clips,
  checkedSet,
})

const episodeJobTitle = computed(() => {
  const action = episodeJob.value?.action
  if (action === 'compose') return `正在合成第 ${number.value} 集完整视频`
  if (action === 'clip_regenerate') return '正在重生成片段分镜'
  if (action === 'clip_create') return `正在为第 ${number.value} 集 AI 生成新片段`
  return `正在拆解第 ${number.value} 集分镜`
})

const nowMs = ref(Date.now())
let elapsedTimer: ReturnType<typeof setInterval> | null = null

watch(
  () => episodeJob.value?.status === 'running',
  (running) => {
    if (elapsedTimer) {
      clearInterval(elapsedTimer)
      elapsedTimer = null
    }
    if (running) {
      nowMs.value = Date.now()
      elapsedTimer = setInterval(() => {
        nowMs.value = Date.now()
      }, 1000)
    }
  },
  { immediate: true },
)

const elapsedLabel = computed(() =>
  episodeJob.value?.status === 'running'
    ? formatElapsedSeconds(Math.floor((nowMs.value - episodeJob.value.startedAt) / 1000))
    : '',
)

const canCompose = computed(
  () =>
    clips.value.length > 0
    && readyCount.value === clips.value.length
    && !locks.value.episodeActionsLocked
    && !hasActiveVideoJobs.value,
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

const durationMismatch = computed(() =>
  isClipDurationExceededByModel(clip.value?.durationSeconds, currentVideoModel.value),
)

const recommendedLongVideoModel = computed(() => {
  const targetDur = clip.value?.durationSeconds ?? 30
  const candidate = resolveDefaultVideoModel(
    videoModels.value,
    30,
    props.project.creation.settings.videoModelId,
  )
  if (!candidate || modelMaxDuration(candidate) < targetDur) return null
  return candidate
})

function switchToLongVideoModel() {
  if (!recommendedLongVideoModel.value) return
  selectedVideoModelId.value = recommendedLongVideoModel.value.id
}

watch(
  () => [clip.value?.id, clip.value?.durationSeconds, currentVideoModel.value?.id] as const,
  ([, dur]) => {
    if (!dur) return
    const minD = modelMinDuration(currentVideoModel.value)
    const maxD = modelMaxDuration(currentVideoModel.value)
    selectedDuration.value = dur > maxD ? dur : Math.max(dur, minD)
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
  regenOpen.value = false
  addClipOpen.value = false
  grid.gridDialogOpen.value = false
  clipHistoryOpen.value = false
  selectMode.value = false
  checkedClipIds.value = []
  previewClip.value = null
  stopRefAudio()
})

async function switchEpisode(targetNumber: number) {
  if (!isEpisodeNumber(targetNumber, totalEpisodes.value) || targetNumber === number.value) return
  stopRefAudio()
  try {
    await flushPromptSave()
  } catch {
    // Allow episode switch even if background flush fails transiently.
  }
  await router.push({
    name: 'studio-episode',
    params: { projectId: props.project.id, episode: targetNumber },
  })
}

const anyDialogOpen = computed(
  () =>
    deleteOpen.value
    || pickerOpen.value
    || batchOpen.value
    || regenOpen.value
    || addClipOpen.value
    || grid.gridDialogOpen.value
    || clipHistoryOpen.value
    || previewOpen.value,
)

function handleEpisodeKeydown(event: KeyboardEvent) {
  if (!event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  if (anyDialogOpen.value) return
  const activeEl = document.activeElement as HTMLElement | null
  if (
    activeEl
    && (activeEl.tagName === 'INPUT'
      || activeEl.tagName === 'TEXTAREA'
      || activeEl.isContentEditable)
  ) {
    return
  }
  const target = event.key === 'ArrowLeft' ? neighborEpisodes.value.prev : neighborEpisodes.value.next
  if (target !== null) {
    event.preventDefault()
    void switchEpisode(target)
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleEpisodeKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleEpisodeKeydown)
  if (elapsedTimer) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
})

function openClipPreview(item: { id: number; videoUrl?: string; previewUrl?: string }) {
  if (!item.videoUrl) return
  selectedId.value = item.id
  previewClip.value = { id: item.id, src: item.videoUrl, poster: item.previewUrl }
}

function openRefVideoPreview(url: string, previewTitle: string) {
  stopRefAudio()
  previewClip.value = { id: 0, src: url, title: previewTitle }
}

watch(deleteOpen, (open) => {
  if (open) return
  const trigger = deleteTrigger
  deleteTrigger = undefined
  requestAnimationFrame(() => {
    if (trigger?.isConnected) {
      trigger.focus({ preventScroll: true })
    } else {
      clipStrip.value?.focusSelectedOrAdd()
    }
  })
})

async function handleSelectClipHistory(item: MediaHistoryItem) {
  const target = clip.value
  if (!target?.backendId || clipHistorySelecting.value) return
  clipHistorySelecting.value = true
  try {
    const updated = await selectClipVideoHistoryApi(props.project.id, number.value, target.backendId, item.id)
    studio.applyPersistedClip(props.project.id, number.value, updated)
    clipHistoryOpen.value = false
    ui.notify(`已将片段 ${target.id} 切换为所选历史视频`, 'success')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    clipHistorySelecting.value = false
  }
}

async function handleDeleteClipHistory(item: MediaHistoryItem) {
  const target = clip.value
  if (!target?.backendId || clipHistoryDeletingId.value) return
  clipHistoryDeletingId.value = item.id
  try {
    const updated = await deleteClipVideoHistoryApi(props.project.id, number.value, target.backendId, item.id)
    studio.applyPersistedClip(props.project.id, number.value, updated)
    ui.notify('已移除该条历史记录', 'info')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    clipHistoryDeletingId.value = null
  }
}

async function moveClipOrder(fromIndex: number, toIndex: number) {
  if (
    locks.value.structureLocked
    || reorderingClips.value
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
  const clipIds = ordered.map((item) => item.backendId).filter((id): id is string => Boolean(id))
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

async function openBatchDialog(presetIds: string[] = []) {
  if (locks.value.episodeActionsLocked) return
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

const addClipMaxDuration = computed(() => Math.max(4, Math.min(30, cap.value)))
const addClipDurationPresets = computed(() =>
  addClipMaxDuration.value >= 30 ? [5, 10, 15, 20, 25, 30] : [5, 8, 10, 12, 15],
)

async function openRegenDialog() {
  if (submittingAction.value || locks.value.episodeActionsLocked || hasActiveVideoJobs.value) return
  if (!props.project.scriptResult) {
    studio.generateExampleStoryboard(props.project.id, number.value)
    return
  }
  if (!props.project.assetResult) {
    ui.notify('请先在资产生成页生成资产', 'info')
    return
  }
  try {
    await flushPromptSave()
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
    return
  }
  regenScope.value = clip.value?.backendId ? 'clip' : 'episode'
  regenRefreshRefs.value = true
  regenFeedback.value = ''
  regenOpen.value = true
}

async function generateFromScript(feedback = '') {
  const { scriptResult, assetResult } = props.project
  if (!scriptResult) {
    studio.generateExampleStoryboard(props.project.id, number.value)
    return
  }
  if (!assetResult) {
    ui.notify('请先在资产生成页生成资产', 'info')
    return
  }
  if (submittingAction.value || locks.value.episodeActionsLocked) return

  const episodeNumber = number.value
  const cleanFeedback = feedback.trim()
  submittingAction.value = true
  try {
    await flushPromptSave()
    const accepted = await startGenerateStoryboard(
      props.project.id,
      episodeNumber,
      cleanFeedback ? { feedback: cleanFeedback } : undefined,
    )
    storyboardJobs.trackStoryboardJob(props.project.id, accepted.job, {
      episodeNumber,
      onCompleted: () => {
        if (number.value === episodeNumber) {
          selectedId.value = undefined
        }
      },
    })
    ui.notify(`第 ${episodeNumber} 集分镜已在后台开始拆解，首批片段落库后将实时呈现`, 'info')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    submittingAction.value = false
  }
}

async function submitRegenDialog() {
  if (submittingAction.value || locks.value.episodeActionsLocked) return
  const feedback = regenFeedback.value.trim()
  if (regenScope.value === 'episode') {
    regenOpen.value = false
    await generateFromScript(feedback)
    return
  }
  const activeClip = clip.value
  if (!activeClip?.backendId) {
    regenOpen.value = false
    await generateFromScript(feedback)
    return
  }
  const episodeNumber = number.value
  const clipBackendId = activeClip.backendId
  const clipNumber = activeClip.id
  const refreshReferences = regenRefreshRefs.value
  regenOpen.value = false

  submittingAction.value = true
  try {
    await flushPromptSave()
    const accepted = await startRegenerateClipStoryboard(props.project.id, clipBackendId, {
      feedback,
      refreshReferences,
    })
    storyboardJobs.trackStoryboardJob(props.project.id, accepted.job, {
      episodeNumber,
      onCompleted: () => {
        if (number.value === episodeNumber) {
          selectedId.value = clipNumber
        }
      },
    })
    ui.notify(`片段 ${clipNumber} 分镜正在后台重生成，可继续浏览其他片段或分集`, 'info')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    submittingAction.value = false
  }
}

async function generateClipVideo() {
  const activeClip = clip.value
  if (!activeClip || !props.project.persisted || !activeClip.backendId) {
    ui.notify('示例项目暂不支持真实视频生成', 'info')
    return
  }
  if (
    locks.value.episodeActionsLocked
    || currentClipLocked.value
    || !activeClip.prompt.trim()
    || submittingClipId.value === activeClip.backendId
    || isClipGenerating(activeClip)
  ) {
    return
  }

  if (durationMismatch.value.exceeded) {
    ui.notify(
      `当前片段 ${activeClip.durationSeconds} 秒超出所选模型上限 ${durationMismatch.value.maxDuration} 秒，请先切换支持 30 秒的模型或调短片段时长`,
      'error',
    )
    return
  }
  const clipIndex = activeClip.id
  const backendClipId = activeClip.backendId
  const isRedraw = Boolean(activeClip.videoUrl)
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
  if (!props.project.persisted || !canCompose.value || submittingAction.value) return
  const epNum = number.value
  submittingAction.value = true
  try {
    await flushPromptSave()
    const accepted = await startComposeEpisode(props.project.id, epNum)
    storyboardJobs.trackStoryboardJob(props.project.id, accepted.job, {
      episodeNumber: epNum,
    })
    ui.notify(`第 ${epNum} 集视频已在后台开始合成（免费 0 积分），完成后自动更新成片入口`, 'info')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    submittingAction.value = false
  }
}

async function addClip() {
  if (locks.value.structureLocked) return
  if (!props.project.persisted) {
    const id = studio.appendClip(props.project.id, number.value)
    if (id === undefined) return
    selectedId.value = id
    await nextTick()
    clipStrip.value?.scrollToEnd()
    return
  }
  try {
    await flushPromptSave()
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
    return
  }
  addClipFeedback.value = ''
  addClipPosition.value = clip.value?.backendId ? 'after' : 'end'
  addClipDuration.value = Math.min(addClipMaxDuration.value, Math.max(4, selectedDuration.value || 10))
  addClipOpen.value = true
}

function clampAddClipDuration(raw: number): number {
  const parsed = Number.isFinite(raw) ? Math.round(raw) : 10
  return Math.min(addClipMaxDuration.value, Math.max(4, parsed))
}

async function createBlankClipFromDialog() {
  if (addClipBusy.value || locks.value.structureLocked) return
  addClipBusy.value = true
  const durationSeconds = clampAddClipDuration(addClipDuration.value)
  const insertAfterClipId =
    addClipPosition.value === 'after' && clip.value?.backendId ? clip.value.backendId : undefined
  try {
    const created = await createClipApi(
      props.project.id,
      number.value,
      durationSeconds,
      '',
      insertAfterClipId,
    )
    addClipOpen.value = false
    const detail = await getProjectDetail(props.project.id)
    studio.hydrateProjectDetail(detail)
    selectedId.value = created.clipIndex
    if (!insertAfterClipId) {
      await nextTick()
      clipStrip.value?.scrollToEnd()
    }
    ui.notify(`已新增空白片段 ${created.clipIndex}`, 'success')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    addClipBusy.value = false
  }
}

async function submitAiAddClip() {
  if (submittingAction.value || locks.value.episodeActionsLocked || addClipBusy.value) return
  if (!props.project.assetResult) {
    ui.notify('请先在资产生成页生成资产后再使用 AI 新增片段', 'info')
    return
  }
  const episodeNumber = number.value
  const durationSeconds = clampAddClipDuration(addClipDuration.value)
  const feedback = addClipFeedback.value.trim()
  const insertAfterClipId =
    addClipPosition.value === 'after' && clip.value?.backendId ? clip.value.backendId : undefined
  addClipOpen.value = false

  submittingAction.value = true
  try {
    await flushPromptSave()
    const accepted = await startGenerateNewClip(props.project.id, episodeNumber, {
      durationSeconds,
      feedback,
      insertAfterClipId,
    })
    storyboardJobs.trackStoryboardJob(props.project.id, accepted.job, {
      episodeNumber,
      onCompleted: async (_detail, finalJob) => {
        if (number.value !== episodeNumber) return
        const createdIndex = Number(finalJob.resultPayload?.clipIndex)
        if (Number.isInteger(createdIndex) && createdIndex >= 1) {
          selectedId.value = createdIndex
        }
        if (!insertAfterClipId) {
          await nextTick()
          clipStrip.value?.scrollToEnd()
        }
      },
    })
    ui.notify(`第 ${episodeNumber} 集新片段正在后台生成，完成后将自动插入`, 'info')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    submittingAction.value = false
  }
}

function confirmClipDeletion(id: number, event: MouseEvent) {
  const target = clips.value.find((item) => item.id === id)
  if (locks.value.structureLocked || isClipGenerating(target)) return
  clipToDelete.value = id
  deleteTrigger = event.currentTarget as HTMLButtonElement
  deleteOpen.value = true
}

async function deleteClip() {
  if (locks.value.structureLocked) return
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
    <EpisodeToolbar
      :project-id="project.id"
      :project-name="projectName"
      :persisted="Boolean(project.persisted)"
      :episode="episode"
      :episode-index="episodeIndex"
      :episode-name="episodeName"
      :title="title"
      :has-storyboard="Boolean(storyboard)"
      :clip-count="clips.length"
      :ready-count="readyCount"
      :missing-video-count="missingVideoCount"
      :is-composed-in-library="isComposedInLibrary"
      :toggling-composed-library="togglingComposedLibrary"
      :episode-actions-locked="locks.episodeActionsLocked"
      :is-split-or-regen-running="locks.isEpisodeSplitRunning || locks.isClipRegenRunning"
      :is-compose-running="locks.isComposeRunning"
      :has-active-video-jobs="hasActiveVideoJobs"
      :can-compose="canCompose"
      :episode-nav-items="episodeNavItems"
      :prev-episode-number="neighborEpisodes.prev"
      :next-episode-number="neighborEpisodes.next"
      @switch-episode="switchEpisode"
      @toggle-composed-library="toggleComposedLibrary"
      @open-batch-dialog="openBatchDialog()"
      @open-regen-dialog="openRegenDialog"
      @compose-episode="composeEpisode"
    />

    <EpisodeJobBanners
      :episode-job="episodeJob"
      :episode-job-title="episodeJobTitle"
      :elapsed-label="elapsedLabel"
      :can-compose="canCompose"
      :episode-actions-locked="locks.episodeActionsLocked"
      :batch-summary="batchSummary"
      :batch-submitting="batchSubmitting"
      @retry-compose="composeEpisode"
      @retry-split="generateFromScript()"
      @dismiss-episode-job="storyboardJobs.dismissEpisodeJob(project.id, number)"
      @retry-failed-batch="retryFailedBatchClips"
      @dismiss-batch-banner="dismissBatchBanner"
    />

    <div v-if="episode" class="episode-layout" :class="{ 'episode-layout--solo': !storyboard }">
      <EpisodeAssetsSidebar
        v-if="storyboard"
        :has-assets="Boolean(storyboard?.assets.length)"
        :groups="assetGroups"
      />

      <div v-if="storyboard" class="episode-editor">
        <EpisodeClipReferences
          v-if="clip"
          :clip-id="clip.id"
          :clip-backend-id="clip.backendId"
          :persisted="Boolean(project.persisted)"
          :locked="currentClipLocked"
          :references="references"
          :is-grid-generating="grid.isCurrentClipGridGenerating.value"
          :grid-progress-label="grid.currentClipGridProgressLabel.value"
          :has-storyboard-grid="grid.hasStoryboardGrid.value"
          :playing-ref-audio-id="playingRefAudioId"
          @open-grid-dialog="grid.openGridDialog(currentClipLocked)"
          @open-picker="pickerOpen = true"
          @open-ref-video-preview="openRefVideoPreview"
          @toggle-ref-audio="toggleRefAudio"
          @remove-reference="removeReferenceAsset"
          @switch-variant="switchReferenceVariant"
        />

        <EpisodeClipPromptPanel
          v-if="clip"
          v-model:video-model-id="selectedVideoModelId"
          v-model:resolution="selectedResolution"
          v-model:ratio="selectedRatio"
          v-model:duration="selectedDuration"
          :episode-number="number"
          :clip="clip"
          :persisted="Boolean(project.persisted)"
          :default-ratio="project.creation.settings.ratio || '16:9'"
          :prompt-references="promptReferences"
          :reference-count="references.length"
          :current-clip-locked="currentClipLocked"
          :episode-actions-locked="locks.episodeActionsLocked"
          :clip-alert="clipJobAlert(clip)"
          :duration-mismatch="durationMismatch"
          :recommended-long-video-model="recommendedLongVideoModel"
          :video-models="videoModels"
          :current-video-model="currentVideoModel"
          :is-clip-in-library="isClipInLibrary(clip)"
          :is-clip-library-busy="isClipLibraryBusy(clip)"
          :is-clip-generating="isClipGenerating(clip)"
          :is-submitting-clip="submittingClipId === clip.backendId"
          :estimated-video-quote="estimatedVideoQuote"
          @update-prompt="updatePrompt"
          @dismiss-clip-alert="dismissClipJobAlert"
          @switch-to-long-video-model="switchToLongVideoModel"
          @commit-duration="commitClipDuration"
          @toggle-clip-library="toggleClipLibrary(clip)"
          @open-history="clipHistoryOpen = true"
          @generate-video="generateClipVideo"
        />
        <EmptyState v-else class="episode-clip-empty" title="暂无片段">
          <template #icon><Clapperboard :size="25" :stroke-width="1.5" /></template>
        </EmptyState>

        <EpisodeClipStrip
          ref="clipStrip"
          :clips="clips"
          :selected-clip-id="clip?.id"
          :selected-clip-index="selectedClipIndex"
          :persisted="Boolean(project.persisted)"
          :select-mode="selectMode"
          :checked-ids="checkedSet"
          :checked-count="checkedClipIds.length"
          :checked-collectable-count="checkedCollectableClips.length"
          :batch-collecting="batchCollectingClips"
          :reordering="reorderingClips"
          :locked="locks.structureLocked"
          :regenerating-clip-id="locks.regeneratingClipId"
          :is-clip-generating="isClipGenerating"
          :clip-job-progress="clipJobProgress"
          :clip-failed-reason="clipFailedReason"
          :is-clip-in-library="isClipInLibrary"
          :is-clip-library-busy="isClipLibraryBusy"
          @select="selectedId = $event"
          @move="moveClipOrder"
          @toggle-select-mode="toggleSelectMode"
          @toggle-check="toggleClipCheck"
          @open-batch-from-selection="openBatchFromSelection"
          @collect-selection="collectSelectedClips"
          @toggle-clip-library="toggleClipLibrary"
          @preview="openClipPreview"
          @delete="confirmClipDeletion"
          @add="addClip"
        />
      </div>

      <div v-else-if="locks.isEpisodeSplitRunning" class="episode-skeleton-panel" aria-live="polite">
        <div class="episode-skeleton-grid" aria-hidden="true">
          <div
            v-for="idx in Math.min(8, Math.max(4, episodeJob?.segmentCount || 4))"
            :key="idx"
            class="episode-skeleton-card"
          >
            <span class="episode-skeleton-line is-short"></span>
            <span class="episode-skeleton-line"></span>
            <span class="episode-skeleton-line is-mid"></span>
          </div>
        </div>
      </div>

      <EmptyState v-else class="episode-empty" title="待拆分镜" :description="`单片段最长 ${cap} 秒`">
        <template #icon><Clapperboard :size="25" :stroke-width="1.5" /></template>
        <UiButton
          variant="primary"
          :loading="submittingAction"
          :disabled="submittingAction || locks.episodeActionsLocked"
          @click="generateFromScript()"
        >
          <template v-if="!submittingAction" #leading><Sparkles :size="16" aria-hidden="true" /></template>一键生成本集分镜
        </UiButton>
      </EmptyState>
    </div>

    <StudioBatchVideoDialog
      v-model:open="batchOpen"
      :episode-number="number"
      :clips="clips"
      :project-assets="project.assets ?? []"
      :project-ratio="project.creation.settings.ratio || '16:9'"
      :segment-cap="cap"
      :default-model-id="selectedVideoModelId || project.creation.settings.videoModelId"
      :active-clip-ids="activeClipIds"
      :video-models="videoModels"
      :initial-selected-ids="batchInitialIds"
      :submitting="batchSubmitting"
      @submit="submitBatchClipVideos"
    />

    <AssetLibraryDialog
      v-model:open="pickerOpen"
      title="素材库"
      mode="multiple"
      :allowed-kinds="['image', 'video', 'audio']"
      :project-assets="project.assets ?? []"
      default-source="project"
      :disabled-keys="usedReferenceKeys"
      :max-by-kind="remainingRefCaps"
      require-http-url
      @confirm="addReferenceLibraryItems"
    />

    <audio ref="refAudioEl" hidden @ended="playingRefAudioId = null" />

    <VideoPreview
      v-if="previewClip"
      v-model:open="previewOpen"
      :src="previewClip.src"
      :poster="previewClip.poster"
      :title="previewClip.title || `片段 ${previewClip.id}`"
      autoplay
    />

    <MediaHistoryDialog
      v-model:open="clipHistoryOpen"
      kind="video"
      :title="clip ? `片段 ${clip.id} · 历史视频` : '历史视频'"
      :items="clip?.videoHistory ?? []"
      :current-url="clip?.videoUrl"
      :selecting="clipHistorySelecting"
      :deleting-id="clipHistoryDeletingId"
      :model-names="videoModelNames"
      deletable
      @select="handleSelectClipHistory"
      @delete="handleDeleteClipHistory"
    />

    <EpisodeActionDialogs
      v-model:regen-open="regenOpen"
      v-model:regen-scope="regenScope"
      v-model:regen-refresh-refs="regenRefreshRefs"
      v-model:regen-feedback="regenFeedback"
      v-model:add-clip-open="addClipOpen"
      v-model:add-clip-feedback="addClipFeedback"
      v-model:add-clip-position="addClipPosition"
      v-model:add-clip-duration="addClipDuration"
      v-model:grid-dialog-open="grid.gridDialogOpen.value"
      v-model:grid-model-id="grid.gridModelId.value"
      v-model:grid-tier="grid.gridTier.value"
      v-model:grid-ratio="grid.gridRatio.value"
      v-model:delete-open="deleteOpen"
      :episode-number="number"
      :clip="clip"
      :clip-count="clips.length"
      :ready-count="readyCount"
      :submitting-action="submittingAction"
      :episode-actions-locked="locks.episodeActionsLocked"
      :add-clip-max-duration="addClipMaxDuration"
      :add-clip-duration-presets="addClipDurationPresets"
      :add-clip-busy="addClipBusy"
      :has-storyboard-grid="grid.hasStoryboardGrid.value"
      :planned-grid-summary="grid.plannedGridSummary.value"
      :image-models="imageModels"
      :current-grid-model="grid.currentGridModel.value"
      :default-grid-ratio="selectedRatio || project.creation.settings.ratio || '16:9'"
      :is-current-clip-grid-generating="grid.isCurrentClipGridGenerating.value"
      :estimated-grid-quote="grid.estimatedGridQuote.value"
      :clip-to-delete="clipToDelete"
      @submit-regen="submitRegenDialog"
      @create-blank-clip="createBlankClipFromDialog"
      @submit-ai-add-clip="submitAiAddClip"
      @submit-grid="grid.submitClipStoryboardGrid()"
      @confirm-delete="deleteClip"
    />
  </section>
</template>

<style scoped>
.episode-workbench {
  display: flex;
  flex-direction: column;
  gap: 14px;
  height: 100%;
  min-width: 0;
  min-height: 0;
}

.episode-layout {
  flex: 1;
  display: grid;
  grid-template-columns: clamp(196px, 20%, 268px) minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-panel);
  background: var(--color-surface);
}

.episode-layout--solo {
  grid-template-columns: minmax(0, 1fr);
}

.episode-editor {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.episode-clip-empty {
  grid-row: 1 / 3;
  align-self: center;
}

.episode-empty {
  align-self: center;
}

.episode-skeleton-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 24px;
  min-height: 280px;
}

.episode-skeleton-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 12px;
}

.episode-skeleton-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-panel);
  background: rgb(255 255 255 / 2%);
}

.episode-skeleton-line {
  display: block;
  height: 11px;
  border-radius: 6px;
  background: rgb(255 255 255 / 7%);
  animation: episode-pulse 1.5s ease-in-out infinite;
}

.episode-skeleton-line.is-short {
  width: 42%;
  height: 13px;
}

.episode-skeleton-line.is-mid {
  width: 68%;
}

@keyframes episode-pulse {
  0%, 100% { opacity: 0.45; }
  50% { opacity: 0.9; }
}

@container (max-width: 640px) {
  .episode-layout {
    grid-template: auto 1fr / minmax(0, 1fr);
    min-height: 0;
    overflow: visible;
  }

  .episode-editor {
    height: auto;
    overflow: visible;
  }

  .episode-empty {
    min-height: 280px;
  }
}
</style>
