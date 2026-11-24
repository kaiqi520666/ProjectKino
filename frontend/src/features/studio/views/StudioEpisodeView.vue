<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, useTemplateRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clapperboard,
  Clock,
  Download,
  Film,
  History,
  Image as ImageIcon,
  Loader2,
  Music,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Sparkles,
  Video,
  X,
} from 'lucide-vue-next'
import {
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuPortal,
  DropdownMenuRoot,
  DropdownMenuTrigger,
} from 'reka-ui'
import EmptyState from '@/components/business/EmptyState.vue'
import MediaHistoryDialog from '@/components/business/MediaHistoryDialog.vue'
import type { MediaHistoryItem } from '@/components/business/MediaHistoryDialog.vue'
import RichPromptInput from '@/components/business/RichPromptInput.vue'
import {
  remapPromptOnSlotRemove,
  type PromptReferenceOption,
} from '@/components/business/prompt-references'
import ImagePreview from '@/components/ui/ImagePreview.vue'
import UiAlert from '@/components/ui/UiAlert.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiTextarea from '@/components/ui/UiTextarea.vue'
import VideoPreview from '@/components/ui/VideoPreview.vue'
import AssetLibraryDialog from '@/features/assets/AssetLibraryDialog.vue'
import type { AssetLibraryItem } from '@/features/assets/asset-library-types'
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
  updateClipApi,
} from '../api'
import type { PersistedClipReference } from '../api-types'
import { assetCategoryItems, assetKindIcons } from '../asset-icons'
import { defaultSegmentDuration } from '../components/drama-creation'
import EpisodeAssetsSidebar from '../components/EpisodeAssetsSidebar.vue'
import EpisodeClipStrip from '../components/EpisodeClipStrip.vue'
import StudioBatchVideoDialog from '../components/StudioBatchVideoDialog.vue'
import VideoModelPicker from '../components/VideoModelPicker.vue'
import VideoParamsPopover from '../components/VideoParamsPopover.vue'
import { useBatchJobTracker } from '../composables/useBatchJobTracker'
import { useModelCatalog } from '../composables/useModelCatalog'
import { computeStoryboardLocks, formatElapsedSeconds } from '../storyboard-job-helpers'
import { useStoryboardJobStore } from '../storyboard-job-store'
import { assetDisplayName, assetStateLabel, findAssetSiblings } from '../studio-assets'
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
const storyboardJobs = useStoryboardJobStore()
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

const previewClip = ref<{ id: number; src: string; poster?: string; title?: string } | null>(null)
const previewOpen = computed({
  get: () => previewClip.value !== null,
  set: (value: boolean) => {
    if (!value) previewClip.value = null
  },
})
const refAudioEl = useTemplateRef<HTMLAudioElement>('refAudioEl')
const playingRefAudioId = ref<string | null>(null)
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
const regenFormId = useId()
const regenOpen = ref(false)
const regenScope = ref<'clip' | 'episode'>('clip')
const regenRefreshRefs = ref(true)
const regenFeedback = ref('')
const addClipFormId = useId()
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

function clipJobAlert(
  item?: StoryboardClip,
): { status: 'failed' | 'review'; message: string; jobId?: string } | null {
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

const currentClipLocked = computed(() =>
  Boolean(
    submittingAction.value
    || isClipGenerating(clip.value)
    || locks.value.isClipLocked(clip.value?.backendId),
  ),
)

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

const checkedSet = computed(() => new Set(checkedClipIds.value))

const projectAssetsById = computed(() => new Map((props.project.assets ?? []).map((item) => [item.id, item])))
const resolvedStoryboardAssets = computed(() => (storyboard.value?.assets ?? []).map((asset) => {
  const live = projectAssetsById.value.get(asset.id)
  return {
    ...asset,
    name: live ? assetDisplayName(live) : asset.name,
    imageUrl: live?.imageUrl ?? asset.imageUrl,
  }
}))
const assetGroups = computed(() => assetCategoryItems.map((category) => ({
  ...category,
  assets: resolvedStoryboardAssets.value.filter(({ kind }) => kind === category.kind),
})))
const references = computed(() => {
  const allAssets = props.project.assets ?? []
  const listed = clip.value?.references
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
      const icon =
        mediaKind === 'video'
          ? Film
          : mediaKind === 'audio'
            ? Music
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
        index: reference.index as number | undefined,
        icon,
        imageUrl: mediaKind === 'image' ? mediaUrl : undefined,
        siblings,
      }
    })
  }
  let imgIdx = 0
  return assetGroups.value.flatMap(({ icon, assets }) =>
    assets.filter((asset) => clip.value?.assetIds.includes(asset.id)).map((asset) => {
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
        index: undefined as number | undefined,
        siblings,
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

const currentVideoModel = computed(
  () => videoModels.value.find((m) => m.id === selectedVideoModelId.value) ?? videoModels.value[0] ?? null,
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
  const caps = currentVideoModel.value?.capabilities
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
  regenOpen.value = false
  addClipOpen.value = false
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
    if (trigger?.isConnected) {
      trigger.focus({ preventScroll: true })
    } else {
      clipStrip.value?.focusSelectedOrAdd()
    }
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
  if (currentClipLocked.value || isClipGenerating(activeClip)) return

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
  if (!clip.value || currentClipLocked.value) return
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

watch(
  () => clip.value?.backendId,
  (nextId, prevId) => {
    if (prevId && nextId !== prevId) {
      void flushPromptSave().catch(() => {})
    }
  },
)

async function persistClipReferences(nextRefs: PersistedClipReference[], updatedPrompt?: string) {
  if (!clip.value?.backendId || !props.project.persisted) return
  try {
    await flushPromptSave()
    const patch: { references: PersistedClipReference[]; prompt?: string } = { references: nextRefs }
    if (updatedPrompt !== undefined) patch.prompt = updatedPrompt
    await updateClipApi(props.project.id, clip.value.backendId, patch)
    const detail = await getProjectDetail(props.project.id)
    studio.hydrateProjectDetail(detail)
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  }
}

function serializeExistingRefs(): PersistedClipReference[] {
  return references.value.map((ref, idx) => {
    const live = projectAssetsById.value.get(ref.id)
    return {
      index: idx + 1,
      assetId: live?.backendId || ref.id,
      assetCode: live ? ref.id : undefined,
      name: ref.displayName,
      kind: ref.kind,
      ...(!live && ref.mediaUrl ? { mediaKind: ref.mediaKind, mediaUrl: ref.mediaUrl } : {}),
    }
  })
}

async function addReferenceLibraryItems(items: AssetLibraryItem[]) {
  if (!clip.value || !items.length || currentClipLocked.value) return
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
  if (!clip.value || currentClipLocked.value) return
  const removed = references.value[slotIndex]
  if (!removed) return
  if (playingRefAudioId.value === removed.id) stopRefAudio()
  const remap = remapPromptOnSlotRemove(
    clip.value.prompt,
    removed.mediaKind,
    removed.modalityIndex,
    removed.displayName,
  )
  const next = serializeExistingRefs()
    .filter((_, idx) => idx !== slotIndex)
    .map((ref, idx) => ({ ...ref, index: idx + 1 }))
  if (remap.changed) {
    studio.saveClipPrompt(props.project.id, number.value, clip.value.id, remap.prompt)
  }
  await persistClipReferences(next, remap.changed ? remap.prompt : undefined)
  if (remap.changed) {
    ui.notify('已同步更新提示词引用编号', 'info')
  }
}

function stopRefAudio() {
  if (refAudioEl.value) {
    refAudioEl.value.pause()
    refAudioEl.value.currentTime = 0
  }
  playingRefAudioId.value = null
}

function toggleRefAudio(id: string, url?: string) {
  const el = refAudioEl.value
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

function openRefVideoPreview(url: string, title: string) {
  stopRefAudio()
  previewClip.value = { id: 0, src: url, title }
}

onBeforeUnmount(() => {
  if (elapsedTimer) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
  stopRefAudio()
  void flushPromptSave().catch(() => {})
})

async function switchReferenceVariant(slotIndex: number, target: StudioAsset) {
  if (!clip.value || !props.project.persisted || currentClipLocked.value) return
  const currentSlot = references.value[slotIndex]
  if (!currentSlot || currentSlot.id === target.id) return
  if (references.value.some((ref, idx) => idx !== slotIndex && ref.id === target.id)) {
    ui.notify(`「${assetDisplayName(target)}」已存在于当前片段的其他参考槽位中`, 'info')
    return
  }
  const next = serializeExistingRefs().map((ref, idx) => {
    if (idx === slotIndex) {
      return {
        index: idx + 1,
        assetId: target.backendId || target.id,
        assetCode: target.id,
        name: assetDisplayName(target),
        kind: target.kind,
      }
    }
    return ref
  })
  await persistClipReferences(next)
  ui.notify(`已将${currentSlot.slotLabel}切换为「${assetDisplayName(target)}」`, 'success')
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
          :disabled="locks.episodeActionsLocked"
          @click="openBatchDialog()"
        >
          <template #leading><Video :size="14" aria-hidden="true" /></template>
          {{ missingVideoCount > 0 ? `批量生视频 (${missingVideoCount})` : '批量重新生成' }}
        </UiButton>
        <UiButton
          v-if="storyboard"
          variant="outline"
          size="sm"
          :loading="locks.isEpisodeSplitRunning || locks.isClipRegenRunning"
          :disabled="locks.episodeActionsLocked || hasActiveVideoJobs"
          @click="openRegenDialog"
        >
          <template v-if="!locks.isEpisodeSplitRunning && !locks.isClipRegenRunning" #leading><Sparkles :size="14" aria-hidden="true" /></template>重新生成分镜
        </UiButton>
        <UiButton
          variant="primary"
          size="sm"
          :loading="locks.isComposeRunning"
          :disabled="!canCompose"
          @click="composeEpisode"
        >
          <template v-if="!locks.isComposeRunning" #leading><Film :size="14" aria-hidden="true" /></template>
          {{ episode.composedVideoUrl ? '重新合成本集' : '合成本集视频' }}
        </UiButton>
      </div>
    </header>

    <div v-if="episodeJob?.status === 'running'" class="episode-job-banner" role="status" aria-live="polite">
      <div class="episode-job-banner-head">
        <div class="episode-job-banner-main">
          <Loader2 class="is-spin" :size="15" aria-hidden="true" />
          <strong>{{ episodeJobTitle }}</strong>
          <span
            v-if="episodeJob.action === 'episode' && episodeJob.totalBatches"
            class="episode-job-pill"
          >
            已落库 {{ episodeJob.completedBatches ?? 0 }}/{{ episodeJob.totalBatches }} 批<template v-if="episodeJob.segmentCount"> · 共 {{ episodeJob.segmentCount }} 段</template>
          </span>
          <span v-if="episodeJob.stepLabel" class="episode-job-banner-step">{{ episodeJob.stepLabel }}</span>
        </div>
        <div class="episode-job-banner-meta">
          <span v-if="elapsedLabel" class="episode-job-banner-elapsed">
            <Clock :size="12" aria-hidden="true" />
            {{ elapsedLabel }}
          </span>
          <span class="episode-job-banner-hint">可切换其他分集并行操作</span>
        </div>
      </div>
      <div class="episode-batch-track" role="progressbar" :aria-valuenow="episodeJob.progress" aria-valuemin="0" aria-valuemax="100">
        <div class="episode-batch-fill" :style="{ width: `${Math.max(6, episodeJob.progress)}%` }"></div>
      </div>
    </div>

    <UiAlert
      v-else-if="episodeJob?.status === 'failed'"
      tone="error"
      :title="episodeJob.jobType === 'episode_compose' ? '本集视频合成失败' : '分镜任务执行失败'"
    >
      {{ episodeJob.errorMessage || episodeJob.stepLabel || '后台任务执行失败，请重试' }}
      <template #action>
        <div class="episode-job-alert-actions">
          <UiButton
            v-if="episodeJob.action === 'compose'"
            variant="outline"
            size="sm"
            :disabled="!canCompose"
            @click="composeEpisode"
          >
            重试合成
          </UiButton>
          <UiButton
            v-else-if="episodeJob.action === 'episode'"
            variant="outline"
            size="sm"
            :disabled="locks.episodeActionsLocked"
            @click="generateFromScript()"
          >
            重新拆分镜
          </UiButton>
          <UiButton
            variant="ghost"
            size="sm"
            @click="storyboardJobs.dismissEpisodeJob(project.id, number)"
          >
            忽略
          </UiButton>
        </div>
      </template>
    </UiAlert>

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
      <EpisodeAssetsSidebar
        v-if="storyboard"
        :has-assets="!!storyboard?.assets.length"
        :groups="assetGroups"
      />

      <div v-if="storyboard" class="episode-editor">
        <section v-if="clip" class="episode-references" aria-labelledby="episode-clip-title">
          <div class="episode-reference-materials">
            <div class="episode-section-head">
              <h2 id="episode-clip-title"><Clapperboard :size="17" aria-hidden="true" />片段 {{ clip.id }}</h2>
            </div>
            <ul class="episode-reference-list" aria-label="片段参考素材">
              <li v-for="(asset, slotIndex) in references" :key="`${asset.id}-${slotIndex}`">
                <div class="episode-reference-thumb-wrap">
                  <ImagePreview v-if="asset.mediaKind === 'image' && asset.imageUrl" :src="asset.imageUrl" :title="asset.displayName">
                    <template #trigger>
                      <button type="button" class="episode-asset-thumb" :aria-label="'预览片段参考 ' + asset.displayName"><img :src="asset.imageUrl" alt="" /></button>
                    </template>
                  </ImagePreview>
                  <button
                    v-else-if="asset.mediaKind === 'video' && asset.mediaUrl"
                    type="button"
                    class="episode-asset-thumb episode-asset-thumb--video"
                    :aria-label="'预览参考视频 ' + asset.displayName"
                    @click="openRefVideoPreview(asset.mediaUrl, asset.displayName)"
                  >
                    <video :src="`${asset.mediaUrl}#t=0.05`" preload="metadata" muted playsinline />
                    <span class="episode-ref-play-dot"><Play :size="12" /></span>
                  </button>
                  <button
                    v-else-if="asset.mediaKind === 'audio' && asset.mediaUrl"
                    type="button"
                    class="episode-asset-thumb episode-asset-thumb--audio"
                    :class="{ 'is-playing': playingRefAudioId === asset.id }"
                    :aria-label="(playingRefAudioId === asset.id ? '暂停 ' : '试听 ') + asset.displayName"
                    @click="toggleRefAudio(asset.id, asset.mediaUrl)"
                  >
                    <Pause v-if="playingRefAudioId === asset.id" :size="18" />
                    <Music v-else :size="18" />
                  </button>
                  <span v-else class="episode-asset-thumb">
                    <component :is="asset.icon" :size="20" :stroke-width="1.5" aria-hidden="true" />
                  </span>
                  <span class="episode-reference-no">{{ asset.slotLabel }}</span>
                  <button
                    v-if="project.persisted && clip.backendId && !currentClipLocked"
                    type="button"
                    class="episode-reference-remove"
                    :aria-label="`移除参考 ${asset.displayName}`"
                    title="移除"
                    @click="removeReferenceAsset(slotIndex)"
                  >
                    <X :size="11" aria-hidden="true" />
                  </button>
                </div>
                <span class="episode-asset-name" :title="asset.displayName">{{ asset.name }}</span>
                <DropdownMenuRoot v-if="project.persisted && clip.backendId && asset.siblings.length >= 2">
                  <DropdownMenuTrigger type="button" class="episode-variant-trigger" :disabled="currentClipLocked" :title="`切换「${asset.name}」变体`">
                    <span>{{ asset.stateLabel }}</span>
                    <ChevronDown :size="11" aria-hidden="true" />
                  </DropdownMenuTrigger>
                  <DropdownMenuPortal>
                    <DropdownMenuContent class="episode-variant-menu" :side-offset="5" align="start">
                      <DropdownMenuItem
                        v-for="sibling in asset.siblings"
                        :key="sibling.backendId || sibling.id"
                        class="episode-variant-option"
                        :class="{ 'is-current': sibling.id === asset.id }"
                        @select="switchReferenceVariant(slotIndex, sibling)"
                      >
                        <span class="episode-variant-option-thumb">
                          <img v-if="sibling.imageUrl" :src="sibling.imageUrl" alt="" />
                          <component :is="asset.icon" v-else :size="13" aria-hidden="true" />
                        </span>
                        <span class="episode-variant-option-label">{{ assetStateLabel(sibling) }}</span>
                        <span v-if="sibling.id === asset.id" class="episode-variant-option-tag">当前</span>
                        <span v-else-if="!sibling.imageUrl" class="episode-variant-option-missing">无图</span>
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenuPortal>
                </DropdownMenuRoot>
              </li>
              <li>
                <UiButton
                  class="episode-reference-add"
                  variant="secondary"
                  size="sm"
                  :disabled="!project.persisted || !clip.backendId || currentClipLocked"
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
          <div
            v-if="clipJobAlert(clip)"
            class="episode-clip-job-banner"
            :class="clipJobAlert(clip)?.status === 'review' ? 'is-review' : 'is-failed'"
            :title="clipJobAlert(clip)?.message"
          >
            <Clock v-if="clipJobAlert(clip)?.status === 'review'" :size="14" aria-hidden="true" />
            <AlertCircle v-else :size="14" aria-hidden="true" />
            <span class="episode-clip-job-banner-text">
              <strong>{{ clipJobAlert(clip)?.status === 'review' ? '最近重绘待后台核对（积分冻结中）' : '最近生视频失败' }}：</strong>
              {{ clipJobAlert(clip)?.message }}
            </span>
            <button
              v-if="clipJobAlert(clip)?.jobId"
              type="button"
              class="episode-clip-job-close"
              aria-label="忽略本次提示"
              title="忽略本次提示"
              @click="dismissClipJobAlert(clipJobAlert(clip)?.jobId)"
            >
              <X :size="13" aria-hidden="true" />
            </button>
          </div>
          <div class="episode-prompt-field">
            <span class="ui-label">视频提示词</span>
            <RichPromptInput
              :key="`${number}-${clip.backendId || clip.id}`"
              :model-value="clip.prompt"
              :references="promptReferences"
              :disabled="currentClipLocked"
              expanded
              :min-height="180"
              placeholder="输入视频提示词，输入 @ 引用上方图片、视频或音频素材"
              mention-title="引用素材"
              @update:model-value="updatePrompt"
            />
          </div>
          <div class="episode-prompt-actions">
            <div class="episode-video-controls">
              <VideoModelPicker
                v-model="selectedVideoModelId"
                :models="videoModels"
                :clip-duration="selectedDuration"
                :project-ratio="selectedRatio"
                :reference-count="references.length"
                :prompt-length="clip.prompt.trim().length"
                :disabled="currentClipLocked"
              />
              <VideoParamsPopover
                v-model:resolution="selectedResolution"
                v-model:ratio="selectedRatio"
                v-model:duration="selectedDuration"
                :model="currentVideoModel"
                :default-ratio="project.creation.settings.ratio || '16:9'"
                mode="single"
                :disabled="currentClipLocked"
                @duration-commit="commitClipDuration"
              />
            </div>
            <div class="episode-video-controls">
              <UiButton
                v-if="project.persisted && clip.backendId && (clip.videoHistory?.length ?? 0) >= 2"
                variant="outline"
                size="sm"
                :disabled="currentClipLocked"
                @click="clipHistoryOpen = true"
              >
                <template #leading><History :size="14" aria-hidden="true" /></template>
                历史 · {{ clip.videoHistory?.length }}
              </UiButton>
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
                  :disabled="!clip.prompt.trim() || !currentVideoModel || locks.episodeActionsLocked || currentClipLocked || submittingClipId === clip.backendId"
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

        <EpisodeClipStrip
          ref="clipStrip"
          :clips="clips"
          :selected-clip-id="clip?.id"
          :selected-clip-index="selectedClipIndex"
          :persisted="!!project.persisted"
          :select-mode="selectMode"
          :checked-ids="checkedSet"
          :checked-count="checkedClipIds.length"
          :reordering="reorderingClips"
          :locked="locks.structureLocked"
          :regenerating-clip-id="locks.regeneratingClipId"
          :is-clip-generating="isClipGenerating"
          :clip-job-progress="clipJobProgress"
          :clip-failed-reason="clipFailedReason"
          @select="selectedId = $event"
          @move="moveClipOrder"
          @toggle-select-mode="toggleSelectMode"
          @toggle-check="toggleClipCheck"
          @open-batch-from-selection="openBatchFromSelection"
          @preview="openClipPreview"
          @delete="confirmClipDeletion"
          @add="addClip"
        />
      </div>

      <div v-else-if="locks.isEpisodeSplitRunning" class="episode-skeleton-panel" aria-live="polite">
        <div class="episode-skeleton-head">
          <Loader2 class="is-spin" :size="20" aria-hidden="true" />
          <div>
            <strong>正在按剧本拆解第 {{ number }} 集分镜…</strong>
            <p>每完成 4 个片段将实时落库并展示，你也可以先切去其他分集并行拆镜</p>
          </div>
        </div>
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

    <UiDialog
      v-model:open="regenOpen"
      title="重新生成分镜"
      :description="regenScope === 'clip' && clip ? `仅重写片段 ${clip.id}，保留其已生成的视频与历史记录。` : `重新按最新剧本生成第 ${number} 集全部分镜。`"
    >
      <form :id="regenFormId" class="episode-modal-form" @submit.prevent="submitRegenDialog">
        <div v-if="clip?.backendId" class="episode-scope-switch" role="radiogroup" aria-label="重生成范围">
          <button
            type="button"
            class="episode-scope-option"
            :class="{ 'is-active': regenScope === 'clip' }"
            @click="regenScope = 'clip'"
          >
            <strong>仅当前片段（片段 {{ clip.id }}）</strong>
            <span>保留已有视频，仅重写本段提示词</span>
          </button>
          <button
            type="button"
            class="episode-scope-option"
            :class="{ 'is-active': regenScope === 'episode' }"
            @click="regenScope = 'episode'"
          >
            <strong>整集分镜（第 {{ number }} 集）</strong>
            <span>按最新剧本全量重切并覆盖</span>
          </button>
        </div>

        <label v-if="regenScope === 'clip' && clip?.backendId" class="episode-modal-check">
          <input v-model="regenRefreshRefs" type="checkbox" />
          <span>同时重新匹配参考素材（自动选用最新资产/变体；取消勾选则保留当前参考素材仅重写提示词）</span>
        </label>

        <UiAlert
          v-else
          tone="warning"
          :title="
            readyCount > 0
              ? `重生成整集将覆盖全部 ${clips.length} 个片段，并清空当前 ${readyCount} 个已生成的视频关联`
              : `重生成整集将按最新剧本覆盖本集全部 ${clips.length} 个片段及手动编辑内容`
          "
        />

        <UiTextarea
          v-model="regenFeedback"
          label="修改要求 / 导演意见（可选）"
          :rows="4"
          :maxlength="500"
          :placeholder="
            regenScope === 'clip'
              ? '可留空直接重写；或说明修改方向，例如：节奏放慢、多给女主面部特写、光线更压抑、换用手持跟拍'
              : '可留空按剧本重生成；或说明整集分镜方向，例如：开场前两镜更有压迫感、多用近景特写、林晓回家戏换便装'
          "
        />
      </form>
      <template #footer>
        <UiButton variant="ghost" :disabled="submittingAction" @click="regenOpen = false">取消</UiButton>
        <UiButton
          type="submit"
          :form="regenFormId"
          :variant="regenScope === 'episode' ? 'danger' : 'primary'"
          :disabled="submittingAction || locks.episodeActionsLocked"
        >
          <template #leading><Sparkles :size="14" aria-hidden="true" /></template>
          {{ regenScope === 'clip' && clip ? `开始重生成片段 ${clip.id}` : `确认重生成第 ${number} 集分镜` }}
        </UiButton>
      </template>
    </UiDialog>

    <UiDialog
      v-model:open="addClipOpen"
      title="新增片段"
      :description="`单片段时长支持 4–${addClipMaxDuration} 秒（跟随当前项目上限）。可用 AI 结合上下文生成，或直接创建空白片段。`"
    >
      <form :id="addClipFormId" class="episode-modal-form" @submit.prevent="submitAiAddClip">
        <UiTextarea
          v-model="addClipFeedback"
          label="片段内容 / 导演要求（可选）"
          :rows="4"
          :maxlength="500"
          placeholder="可留空由 AI 承接上一片段自然续写；或写一句剧情/画面意图，例如：补一段 6 秒悬念过渡，林晓推开档案室门，手电光扫过墙上的旧照片"
        />

        <div class="episode-add-grid">
          <div v-if="clip?.backendId" class="episode-add-field">
            <span class="ui-label">插入位置</span>
            <div class="episode-add-pills">
              <button
                type="button"
                class="episode-add-pill"
                :class="{ 'is-active': addClipPosition === 'after' }"
                @click="addClipPosition = 'after'"
              >
                当前片段后（片段 {{ clip.id + 1 }}）
              </button>
              <button
                type="button"
                class="episode-add-pill"
                :class="{ 'is-active': addClipPosition === 'end' }"
                @click="addClipPosition = 'end'"
              >
                本集末尾（片段 {{ clips.length + 1 }}）
              </button>
            </div>
          </div>

          <div class="episode-add-field">
            <span class="ui-label">目标时长（4–{{ addClipMaxDuration }} 秒）</span>
            <div class="episode-add-duration-row">
              <div class="episode-add-pills">
                <button
                  v-for="sec in addClipDurationPresets"
                  :key="sec"
                  type="button"
                  class="episode-add-pill"
                  :class="{ 'is-active': addClipDuration === sec }"
                  @click="addClipDuration = sec"
                >
                  {{ sec }}s
                </button>
              </div>
              <label class="episode-add-duration-input">
                <input
                  v-model.number="addClipDuration"
                  type="number"
                  min="4"
                  :max="addClipMaxDuration"
                  step="1"
                  aria-label="自定义目标时长（秒）"
                />
                <span>秒</span>
              </label>
            </div>
          </div>
        </div>
      </form>
      <template #footer>
        <div class="episode-add-footer">
          <UiButton
            variant="outline"
            size="sm"
            :loading="addClipBusy"
            :disabled="addClipBusy || submittingAction || locks.episodeActionsLocked"
            @click="createBlankClipFromDialog"
          >
            <template #leading><Plus :size="14" aria-hidden="true" /></template>
            创建空白片段
          </UiButton>
          <div class="episode-add-footer-right">
            <UiButton variant="ghost" size="sm" :disabled="addClipBusy || submittingAction" @click="addClipOpen = false">取消</UiButton>
            <UiButton
              type="submit"
              :form="addClipFormId"
              variant="primary"
              size="sm"
              :disabled="addClipBusy || submittingAction || locks.episodeActionsLocked"
            >
              <template #leading><Sparkles :size="14" aria-hidden="true" /></template>
              AI 生成新片段
            </UiButton>
          </div>
        </div>
      </template>
    </UiDialog>

    <UiDialog v-model:open="deleteOpen" title="删除片段" :description="`确定删除本集的片段 ${clipToDelete} 吗？`">
      <template #footer>
        <UiButton variant="ghost" @click="deleteOpen = false">取消</UiButton>
        <UiButton variant="danger" @click="deleteClip">确认删除</UiButton>
      </template>
    </UiDialog>
  </section>
</template>

<style scoped>
.episode-workbench { display: flex; flex-direction: column; gap: 14px; height: 100%; min-width: 0; min-height: 0; }
.episode-toolbar, .episode-heading, .episode-actions, .episode-section-head {
  display: flex;
  align-items: center;
  gap: 12px;
}
.episode-toolbar {
  flex-shrink: 0;
  justify-content: space-between;
  flex-wrap: wrap;
  padding: 8px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-panel);
  background: var(--color-surface);
}
.episode-batch-banner {
  flex-shrink: 0;
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
.episode-job-banner {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid rgb(240 184 75 / 32%);
  border-radius: var(--radius-panel);
  background: var(--color-surface);
}
.episode-job-banner-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.episode-job-banner-main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-size: 13px;
  color: var(--color-gold-soft);
}
.episode-job-pill {
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--gold-tint);
  border: 1px solid rgb(240 184 75 / 30%);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.episode-job-banner-step {
  color: var(--color-text);
  font-size: 12px;
}
.episode-job-banner-meta {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--color-muted);
}
.episode-job-banner-elapsed {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-variant-numeric: tabular-nums;
  color: var(--color-gold-soft);
}
.episode-job-banner-hint { color: var(--color-muted); }
.episode-job-alert-actions { display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0; }
.episode-skeleton-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 24px;
  min-height: 280px;
}
.episode-skeleton-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  color: var(--color-gold-soft);
}
.episode-skeleton-head strong { display: block; font-size: 15px; margin-bottom: 4px; }
.episode-skeleton-head p { margin: 0; font-size: 13px; color: var(--color-muted); }
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
.episode-skeleton-line.is-short { width: 42%; height: 13px; }
.episode-skeleton-line.is-mid { width: 68%; }
@keyframes episode-pulse {
  0%, 100% { opacity: 0.45; }
  50% { opacity: 0.9; }
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
  min-height: 0;
  overflow: hidden;
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
.episode-section-head h2 svg { color: var(--color-gold-soft); }
.episode-reference-list { margin: 0; padding: 0; list-style: none; }
.episode-asset-thumb {
  display: grid;
  place-items: center;
  overflow: hidden;
  aspect-ratio: 4 / 3;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: var(--surface-hover);
  color: var(--color-muted);
}
button.episode-asset-thumb { width: 100%; cursor: zoom-in; }
.episode-asset-thumb img {
  width: 100%;
  height: 100%;
  min-height: 0;
  object-fit: cover;
}
.episode-asset-name { display: block; margin-top: 4px; font-size: 12px; overflow-wrap: anywhere; }
.episode-editor { display: grid; grid-template-rows: auto minmax(0, 1fr) auto; height: 100%; min-width: 0; min-height: 0; overflow: hidden; }
.episode-references, .episode-prompt { min-width: 0; padding: 12px 16px; }
.episode-section-head { justify-content: space-between; flex-wrap: wrap; }
.episode-meta { margin: 0; color: var(--color-muted); font-size: 12px; font-variant-numeric: tabular-nums; }
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
.episode-prompt { display: flex; flex-direction: column; min-height: 0; overflow: hidden; border-top: 1px solid var(--border-subtle); }
.episode-prompt :deep(.ui-field) { display: flex; flex: 1; flex-direction: column; }
.episode-prompt :deep(textarea) { flex: 1; width: 100%; min-height: 142px; }
.episode-prompt-actions { flex-shrink: 0; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; margin-top: 10px; }
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
.episode-clip-job-banner {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  padding: 7px 10px;
  border-radius: 7px;
  font-size: 12px;
  line-height: 1.45;
}
.episode-clip-job-banner svg { flex: none; margin-top: 2px; }
.episode-clip-job-banner.is-failed {
  border: 1px solid color-mix(in srgb, var(--color-error) 35%, transparent);
  background: color-mix(in srgb, var(--color-error) 10%, transparent);
  color: var(--color-error);
}
.episode-clip-job-banner.is-review {
  border: 1px solid color-mix(in srgb, var(--color-gold) 40%, transparent);
  background: color-mix(in srgb, var(--color-gold) 10%, transparent);
  color: var(--color-gold-soft);
}
.episode-clip-job-banner-text {
  flex: 1 1 auto;
  min-width: 0;
  overflow-wrap: anywhere;
}
.episode-clip-job-close {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  color: inherit;
  opacity: 0.72;
  cursor: pointer;
}
.episode-clip-job-close:hover { opacity: 1; background: rgb(255 255 255 / 8%); }
.episode-clip-empty { grid-row: 1 / 3; align-self: center; }
.episode-empty { align-self: center; }
.episode-prompt-field {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  gap: 6px;
}
.episode-asset-thumb--video { position: relative; cursor: pointer; }
.episode-asset-thumb--video video { width: 100%; height: 100%; object-fit: cover; display: block; }
.episode-ref-play-dot {
  position: absolute;
  inset: 0;
  margin: auto;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: rgb(10 11 14 / 72%);
  color: var(--color-gold-soft);
}
.episode-asset-thumb--audio {
  cursor: pointer;
  background: radial-gradient(circle at 50% 45%, rgb(212 175 55 / 16%), rgb(18 19 24 / 96%) 74%);
  color: var(--color-gold-soft);
}
.episode-asset-thumb--audio.is-playing {
  border-color: var(--color-gold);
  background: var(--gold-tint);
}
.episode-variant-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  max-width: 100%;
  margin-top: 2px;
  padding: 1px 6px;
  border: 1px solid color-mix(in srgb, var(--color-gold) 45%, transparent);
  border-radius: 999px;
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-size: 11px;
  line-height: 1.35;
  cursor: pointer;
}
.episode-variant-trigger span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.episode-variant-trigger:hover { border-color: var(--color-gold); }
:global(.episode-variant-menu) {
  z-index: 120;
  min-width: 168px;
  max-width: 240px;
  padding: 4px;
  border: 1px solid var(--border-control);
  border-radius: 8px;
  background: var(--color-elevated);
  box-shadow: 0 8px 24px rgb(0 0 0 / 40%);
}
:global(.episode-variant-option) {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 7px;
  border-radius: 5px;
  color: var(--color-text);
  font-size: 12px;
  cursor: pointer;
  outline: none;
}
:global(.episode-variant-option[data-highlighted]) {
  background: var(--gold-tint);
  color: var(--color-gold-soft);
}
:global(.episode-variant-option.is-current) {
  color: var(--color-gold-soft);
  font-weight: 500;
}
:global(.episode-variant-option-thumb) {
  flex: none;
  display: grid;
  place-items: center;
  width: 28px;
  height: 20px;
  overflow: hidden;
  border-radius: 3px;
  background: var(--color-canvas);
  color: var(--color-muted);
}
:global(.episode-variant-option-thumb img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
:global(.episode-variant-option-label) {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
:global(.episode-variant-option-tag) {
  flex: none;
  font-size: 10px;
  color: var(--color-gold-soft);
}
:global(.episode-variant-option-missing) {
  flex: none;
  font-size: 10px;
  color: var(--color-muted);
}
.episode-modal-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.episode-scope-switch {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.episode-scope-option {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 10px 12px;
  border: 1px solid var(--border-control);
  border-radius: 8px;
  background: var(--color-canvas);
  color: var(--color-text);
  text-align: left;
  cursor: pointer;
  transition: border-color 140ms ease, background-color 140ms ease;
}
.episode-scope-option strong {
  font-size: 13px;
  font-weight: 600;
}
.episode-scope-option span {
  font-size: 11px;
  color: var(--color-muted);
}
.episode-scope-option:hover {
  border-color: rgb(240 184 75 / 45%);
}
.episode-scope-option.is-active {
  border-color: var(--color-gold);
  background: var(--gold-tint);
}
.episode-scope-option.is-active strong {
  color: var(--color-gold-soft);
}
.episode-modal-check {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--color-canvas);
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text);
  cursor: pointer;
  user-select: none;
}
.episode-modal-check input {
  width: 15px;
  height: 15px;
  margin-top: 2px;
  flex: none;
  accent-color: var(--color-gold);
  cursor: pointer;
}
.episode-add-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.episode-add-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.episode-add-duration-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.episode-add-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.episode-add-pill {
  padding: 4px 10px;
  border: 1px solid var(--border-control);
  border-radius: 6px;
  background: var(--color-canvas);
  color: var(--color-muted);
  font-size: 12px;
  cursor: pointer;
  transition: border-color 140ms ease, color 140ms ease, background-color 140ms ease;
}
.episode-add-pill:hover {
  border-color: rgb(240 184 75 / 45%);
  color: var(--color-text);
}
.episode-add-pill.is-active {
  border-color: var(--color-gold);
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-weight: 500;
}
.episode-add-duration-input {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border: 1px solid var(--border-control);
  border-radius: 6px;
  background: var(--color-canvas);
  font-size: 12px;
  color: var(--color-muted);
}
.episode-add-duration-input input {
  width: 46px;
  border: 0;
  background: transparent;
  color: var(--color-text);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  text-align: center;
  outline: none;
}
.episode-add-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
}
.episode-add-footer-right {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.is-spin { animation: spin 1s linear infinite; }
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
@container (max-width: 640px) {
  .episode-layout { grid-template: auto 1fr / minmax(0, 1fr); min-height: 0; overflow: visible; }
  .episode-editor { height: auto; overflow: visible; }
  .episode-prompt-field { min-height: 240px; }
  .episode-empty { min-height: 280px; }
}
</style>
