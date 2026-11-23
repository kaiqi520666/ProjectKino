<script setup lang="ts">
import { computed, onMounted, ref, useTemplateRef } from 'vue'
import {
  AlertCircle,
  Boxes,
  Check,
  CheckCircle2,
  CheckSquare,
  Clock,
  History,
  ImageIcon,
  ImageOff,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  ScanText,
  Sparkles,
  Trash2,
  X,
} from 'lucide-vue-next'
import EmptyState from '@/components/business/EmptyState.vue'
import MediaHistoryDialog from '@/components/business/MediaHistoryDialog.vue'
import type { MediaHistoryItem } from '@/components/business/MediaHistoryDialog.vue'
import ImagePreview from '@/components/ui/ImagePreview.vue'
import UiAlert from '@/components/ui/UiAlert.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiTabs from '@/components/ui/UiTabs.vue'
import { useAuthStore } from '@/stores/auth'
import { useGenerationStore } from '@/stores/generation'
import { useUiStore } from '@/stores/ui'
import {
  apiErrorMessage,
  createAssetApi,
  deleteAssetApi,
  deleteAssetImageHistoryApi,
  getJob,
  getProjectDetail,
  isRetryableApiError,
  selectAssetImageHistoryApi,
  startBatchGenerateAssetImages,
  startExtractAssets,
  startGenerateAssetImage,
  updateAssetApi,
  watchJob,
} from '../api'
import type { ProjectDetailOut } from '../api-types'
import { assetKindIcons } from '../asset-icons'
import StudioAssetEditor from '../components/StudioAssetEditor.vue'
import StudioBatchImageDialog from '../components/StudioBatchImageDialog.vue'
import { useBatchJobTracker } from '../composables/useBatchJobTracker'
import { useModelCatalog } from '../composables/useModelCatalog'
import { assetKindOptions } from '../studio-assets'
import type { StudioAsset, StudioAssetDraft, StudioAssetKind } from '../studio-assets'
import type { StudioProject } from '../studio-project'
import { useStudioStore } from '../studio-store'

interface ImageBatchMeta {
  modelId: string
  tier: 'web' | '1k' | '2k' | '4k'
  ratio?: string
}

const props = defineProps<{ project: StudioProject }>()
const auth = useAuthStore()
const studio = useStudioStore()
const generation = useGenerationStore()
const ui = useUiStore()
const { imageModels, ensureLoaded: ensureModelCatalog } = useModelCatalog()
const category = ref<StudioAssetKind>('character')
const editor = useTemplateRef<InstanceType<typeof StudioAssetEditor>>('editor')
const deleteOpen = ref(false)
const refreshOpen = ref(false)
const batchOpen = ref(false)
const batchInitialIds = ref<string[]>([])
const batchSubmitting = ref(false)
const submittingAssetId = ref<string | null>(null)
const selectMode = ref(false)
const checkedAssetIds = ref<string[]>([])
const assetToDelete = ref<StudioAsset>()
const generating = ref(false)
const historyAssetId = ref<string | null>(null)
const historySelecting = ref(false)
const historyDeletingId = ref<string | null>(null)
const dismissedJobIds = ref<Set<string>>(new Set())

const imageModelNames = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const model of imageModels.value) map[model.id] = model.displayName
  return map
})

const historyAsset = computed(() =>
  historyAssetId.value
    ? (props.project.assets ?? []).find((item) => item.backendId === historyAssetId.value) ?? null
    : null,
)

const historyOpen = computed({
  get: () => historyAsset.value !== null,
  set: (value: boolean) => {
    if (!value) historyAssetId.value = null
  },
})

onMounted(() => {
  void ensureModelCatalog()
})

const activeImageJobs = computed(() =>
  (props.project.activeJobs ?? []).filter((job) => job.jobType === 'asset_image'),
)

const activeImageAssetIds = computed(() => {
  const ids = new Set<string>()
  for (const job of activeImageJobs.value) {
    if (job.targetId) ids.add(job.targetId)
  }
  for (const asset of props.project.assets ?? []) {
    if (asset.imageStatus === 'generating' && asset.backendId) {
      ids.add(asset.backendId)
    }
  }
  return ids
})

const hasActiveImageJobs = computed(() => activeImageJobs.value.length > 0 || activeImageAssetIds.value.size > 0)

const activeImageCount = computed(() => activeImageAssetIds.value.size)

const {
  tracker: batchTracker,
  summary: batchSummary,
  trackJobs: trackImageBatchJobs,
  startPolling: startBatchPolling,
  failedReason: failedReasonForId,
  dismiss: dismissBatchBanner,
} = useBatchJobTracker<ImageBatchMeta>({
  jobType: 'asset_image',
  pollIntervalMs: 3000,
  fallbackErrorMessage: '图片生成失败',
  canPoll: () => !!props.project.persisted,
  activeCount: activeImageCount,
  hasActiveJobs: hasActiveImageJobs,
  fetchProjectDetail: () => getProjectDetail(props.project.id),
  fetchJob: getJob,
  onDetail: (detail) => {
    studio.hydrateProjectDetail(detail)
    void auth.refreshBalance()
  },
  isStillRunning: (detail) =>
    (detail.activeJobs ?? []).some((j) => j.jobType === 'asset_image')
    || detail.assets.some((a) => a.imageStatus === 'generating'),
  onBatchComplete: ({ okCount, failCount }) => {
    ui.notify(
      failCount > 0
        ? `批量生图结束：成功 ${okCount} 张，失败 ${failCount} 张（失败已自动退还冻结积分）`
        : `批量生图完成：共生成 ${okCount} 张资产图片`,
      failCount > 0 ? 'info' : 'success',
    )
  },
})

function isAssetGenerating(asset: StudioAsset) {
  return !!asset.backendId && activeImageAssetIds.value.has(asset.backendId)
}

function failedReasonForAsset(asset: StudioAsset) {
  return failedReasonForId(asset.backendId)
}

function assetJobAlert(
  asset: StudioAsset,
): { status: 'failed' | 'review'; message: string; jobId?: string } | null {
  if (isAssetGenerating(asset)) return null
  const transient = failedReasonForAsset(asset)
  if (transient) {
    return { status: 'failed', message: transient, jobId: asset.lastJobId }
  }
  if (asset.lastJobStatus === 'review' || asset.lastJobStatus === 'failed') {
    if (asset.lastJobId && dismissedJobIds.value.has(asset.lastJobId)) return null
    return {
      status: asset.lastJobStatus,
      message:
        asset.lastJobError
        || (asset.lastJobStatus === 'review'
          ? '上游状态待后台核对，积分冻结中'
          : '最近一次生图失败，请重试'),
      jobId: asset.lastJobId,
    }
  }
  return null
}

function dismissAssetJobAlert(jobId?: string) {
  if (!jobId) return
  const next = new Set(dismissedJobIds.value)
  next.add(jobId)
  dismissedJobIds.value = next
}

function openAssetHistory(asset: StudioAsset) {
  if (!asset.backendId) return
  historyAssetId.value = asset.backendId
}

async function handleSelectAssetHistory(item: MediaHistoryItem) {
  const target = historyAsset.value
  if (!target?.backendId || historySelecting.value) return
  historySelecting.value = true
  try {
    const updated = await selectAssetImageHistoryApi(props.project.id, target.backendId, item.id)
    studio.applyPersistedAsset(props.project.id, updated)
    const synced = (props.project.assets ?? []).find((a) => a.backendId === updated.id)
    if (synced) editor.value?.syncAsset(synced)
    historyAssetId.value = null
    ui.notify(`已将「${target.name}」切换为所选历史图片`, 'success')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    historySelecting.value = false
  }
}

async function handleDeleteAssetHistory(item: MediaHistoryItem) {
  const target = historyAsset.value
  if (!target?.backendId || historyDeletingId.value) return
  historyDeletingId.value = item.id
  try {
    const updated = await deleteAssetImageHistoryApi(props.project.id, target.backendId, item.id)
    studio.applyPersistedAsset(props.project.id, updated)
    const synced = (props.project.assets ?? []).find((a) => a.backendId === updated.id)
    if (synced) editor.value?.syncAsset(synced)
    ui.notify('已移除该条历史记录', 'info')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    historyDeletingId.value = null
  }
}

const missingImageCount = computed(() =>
  (props.project.assets ?? []).filter(
    (a) => !!a.backendId && !a.imageUrl && !!a.prompt.trim() && !activeImageAssetIds.value.has(a.backendId),
  ).length,
)

const groups = computed(() => assetKindOptions.map((item) => {
  const assets = props.project.assets?.filter(({ kind }) => kind === item.value) ?? []
  const images = assets.flatMap(asset => asset.imageUrl ? [{ src: asset.imageUrl, title: asset.name }] : [])
  return { ...item, icon: assetKindIcons[item.value], count: assets.length, assets, images }
}))

const missingScriptAssetIds = computed(() => {
  const scriptResult = props.project.scriptResult
  if (!scriptResult) return []
  const existing = new Set((props.project.assets ?? []).map(({ id }) => id))
  const needed = new Set<string>()
  for (const episode of scriptResult.episodes) {
    for (const scene of episode.scenes) {
      if (scene.sceneId) needed.add(scene.sceneId)
      for (const id of scene.characters) needed.add(id)
      for (const id of scene.props) needed.add(id)
    }
  }
  return [...needed].filter((id) => !existing.has(id))
})
const hasExistingAssets = computed(() => !!props.project.assets?.length)
const canIncrementalSync = computed(() => !!props.project.scriptResult && hasExistingAssets.value && missingScriptAssetIds.value.length > 0)

const checkedSet = computed(() => new Set(checkedAssetIds.value))

function openBatchDialog(presetIds: string[] = []) {
  if (!props.project.persisted) {
    ui.notify('示例项目暂不支持批量生图', 'info')
    return
  }
  batchInitialIds.value = presetIds
  batchOpen.value = true
}

function toggleSelectMode() {
  selectMode.value = !selectMode.value
  if (!selectMode.value) checkedAssetIds.value = []
}

function toggleCardCheck(asset: StudioAsset) {
  if (!asset.backendId || isAssetGenerating(asset)) return
  const id = asset.backendId
  if (checkedSet.value.has(id)) {
    checkedAssetIds.value = checkedAssetIds.value.filter((item) => item !== id)
  } else {
    checkedAssetIds.value = [...checkedAssetIds.value, id]
  }
}

function openBatchFromSelection() {
  if (!checkedAssetIds.value.length) return
  openBatchDialog([...checkedAssetIds.value])
}

async function submitBatchImageGeneration(payload: {
  assetIds: string[]
  modelId: string
  tier: 'web' | '1k' | '2k' | '4k'
  ratio?: string
}) {
  if (batchSubmitting.value) return
  batchSubmitting.value = true
  try {
    const res = await startBatchGenerateAssetImages(props.project.id, payload)
    batchOpen.value = false
    selectMode.value = false
    checkedAssetIds.value = []

    trackImageBatchJobs(res.jobs, {
      modelId: payload.modelId,
      tier: payload.tier,
      ratio: payload.ratio,
    })

    const detail = await getProjectDetail(props.project.id)
    studio.hydrateProjectDetail(detail)
    void auth.refreshBalance()
    startBatchPolling()

    const skipHint = res.skipped.length ? `，已自动跳过 ${res.skipped.length} 项` : ''
    ui.notify(
      `已提交 ${res.acceptedCount} 项批量生图任务（预冻结 ${Number(Number(res.totalFrozenCredits).toFixed(2))} 积分${skipHint}），后台并发生成中`,
      'success',
    )
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    batchSubmitting.value = false
  }
}

function retryFailedBatchAssets() {
  const tracker = batchTracker.value
  if (!tracker) return
  const ids = Object.keys(tracker.failedById)
  if (!ids.length) return
  void submitBatchImageGeneration({
    assetIds: ids,
    modelId: tracker.meta.modelId,
    tier: tracker.meta.tier,
    ratio: tracker.meta.ratio,
  })
}

function handleRecognizeClick() {
  if (!props.project.scriptResult) {
    studio.loadExampleAssets(props.project.id)
    return
  }
  if (!hasExistingAssets.value) {
    void generateFromScript('full')
    return
  }
  if (canIncrementalSync.value) {
    void generateFromScript('incremental')
    return
  }
  refreshOpen.value = true
}

async function generateFromScript(mode: 'full' | 'incremental' = 'full') {
  const scriptResult = props.project.scriptResult
  if (!scriptResult) {
    studio.loadExampleAssets(props.project.id)
    return
  }
  if (generating.value || generation.isRunning) return

  const incremental = mode === 'incremental'
  const missingCount = missingScriptAssetIds.value.length

  refreshOpen.value = false
  await generation.runTask(
    incremental
      ? {
          title: `正在增量补充 ${missingCount} 项新资产`,
          subtitle: `${props.project.creation.settings.name} · 保留已有资产与图片`,
          description: '仅针对剧本新增出场的角色、场景或道具生成设定与提示词',
          steps: [
            '比对当前剧本与已有资产列表，定位新增编号',
            '并发为新增资产生成设定、静态音色与生图提示词',
            '合并回项目资产表并刷新出场集数',
          ],
          hint: '已有资产的图片与手动修改将完整保留',
          formatError: apiErrorMessage,
          canRetryError: isRetryableApiError,
          successMessage: () => `已补充 ${missingCount} 项新资产`,
        }
      : {
          title: hasExistingAssets.value ? '正在重新识别项目资产' : '正在批量生成项目资产',
          subtitle: `${props.project.creation.settings.name} · 共 ${scriptResult.episodes.length} 集剧本`,
          description: '正在从已确认剧本汇总出场角色、场景与道具，并并发生成设定与提示词',
          steps: [
            '汇总全剧实际出场的角色、场景与道具清单',
            '并发生成角色三视图提示词、静态音色与场景/道具设定',
            '执行资产完整性与禁人名质量门校验',
          ],
          hint: '后台队列正在并发识别资产，完成后自动刷新列表',
          formatError: apiErrorMessage,
          canRetryError: isRetryableApiError,
          successMessage: (detail: ProjectDetailOut) => `已生成 ${detail.assets.length} 项项目资产`,
        },
    async (controls) => {
      generating.value = true
      try {
        const accepted = await startExtractAssets(props.project.id, mode)
        controls.setJobId(accepted.job.id)
        controls.setProgress(accepted.job.progress)
        await watchJob(accepted.job.id, (job) => {
          controls.setProgress(job.progress)
          if (job.stepLabel) controls.setDescription(job.stepLabel)
          controls.setStep(Math.min(2, Math.max(0, job.stepIndex - 1)))
        })
        const detail = await getProjectDetail(props.project.id)
        studio.hydrateProjectDetail(detail)
        if (!incremental) category.value = 'character'
        ui.notify(
          incremental ? `已增量补充 ${missingCount} 项新资产` : `已生成 ${detail.assets.length} 项资产`,
          'success',
        )
        return detail
      } finally {
        generating.value = false
        void auth.refreshBalance()
      }
    },
  )
}

async function generateAssetImage(
  asset: StudioAsset,
  options: { modelId: string; tier: 'web' | '1k' | '2k' | '4k'; ratio?: string; draft?: StudioAssetDraft },
) {
  if (!props.project.persisted || !asset.backendId) {
    ui.notify('示例项目暂不支持真实 AI 生图', 'info')
    return
  }
  if (submittingAssetId.value === asset.backendId || isAssetGenerating(asset)) return

  const assetName = options.draft?.name.trim() || asset.name
  const isRedraw = !!asset.imageUrl
  submittingAssetId.value = asset.backendId

  try {
    if (options.draft) {
      await updateAssetApi(props.project.id, asset.backendId, options.draft)
      editor.value?.close()
    }

    const accepted = await startGenerateAssetImage(props.project.id, asset.backendId, {
      modelId: options.modelId,
      tier: options.tier,
      ratio: options.ratio,
    })
    trackImageBatchJobs([accepted.job], {
      modelId: options.modelId,
      tier: options.tier,
      ratio: options.ratio,
    })

    const detail = await getProjectDetail(props.project.id)
    studio.hydrateProjectDetail(detail)
    void auth.refreshBalance()
    startBatchPolling()

    ui.notify(`已提交「${assetName}」${isRedraw ? '重绘' : '生图'}任务，后台生成中`, 'success')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    if (submittingAssetId.value === asset.backendId) submittingAssetId.value = null
  }
}

function quickGenerateAssetImage(asset: StudioAsset, event: MouseEvent) {
  if (isAssetGenerating(asset)) return
  if (!asset.prompt.trim()) {
    editAsset(asset, event)
    ui.notify('请先填写该资产的文生图提示词', 'info')
    return
  }
  const defaultModel = imageModels.value.find((m) => m.isDefault)?.id || imageModels.value[0]?.id
  const modelId = asset.imageModelId && imageModels.value.some((m) => m.id === asset.imageModelId)
    ? asset.imageModelId
    : defaultModel
  if (!modelId) {
    ui.notify('图片模型目录尚未加载完成，请稍后重试', 'error')
    void ensureModelCatalog()
    return
  }
  const tierVal = asset.imageTier
  const tier: 'web' | '1k' | '2k' | '4k' = tierVal === 'web' || tierVal === '1k' || tierVal === '2k' || tierVal === '4k' ? tierVal : '1k'
  void generateAssetImage(asset, {
    modelId,
    tier,
  })
}

function addAsset(event: MouseEvent) {
  const kind = assetKindOptions.find(({ value }) => value === category.value)?.value ?? 'character'
  editor.value?.create(kind, event.currentTarget as HTMLButtonElement)
}

async function createAsset(kind: StudioAssetKind, draft: StudioAssetDraft) {
  if (props.project.persisted) {
    try {
      await createAssetApi(props.project.id, kind, draft)
      const detail = await getProjectDetail(props.project.id)
      studio.hydrateProjectDetail(detail)
      category.value = kind
      editor.value?.close()
      return
    } catch (error) {
      ui.notify(apiErrorMessage(error), 'error')
      return
    }
  }
  if (!studio.createAsset(props.project.id, kind, draft)) return

  category.value = kind
  editor.value?.close()
}

function editAsset(asset: StudioAsset, event: MouseEvent) {
  editor.value?.edit(asset, event.currentTarget as HTMLButtonElement)
}

async function saveAsset(assetId: string, draft: StudioAssetDraft) {
  const target = props.project.assets?.find((item) => item.id === assetId)
  if (props.project.persisted && target?.backendId) {
    try {
      await updateAssetApi(props.project.id, target.backendId, draft)
      const detail = await getProjectDetail(props.project.id)
      studio.hydrateProjectDetail(detail)
      editor.value?.close()
      return
    } catch (error) {
      ui.notify(apiErrorMessage(error), 'error')
      return
    }
  }
  if (studio.saveAsset(props.project.id, assetId, draft)) editor.value?.close()
}

function confirmAssetDeletion(asset: StudioAsset) {
  if (isAssetGenerating(asset)) return
  assetToDelete.value = asset
  deleteOpen.value = true
}

async function deleteAsset() {
  const target = assetToDelete.value
  if (target) {
    if (props.project.persisted && target.backendId) {
      try {
        await deleteAssetApi(props.project.id, target.backendId)
        const detail = await getProjectDetail(props.project.id)
        studio.hydrateProjectDetail(detail)
      } catch (error) {
        ui.notify(apiErrorMessage(error), 'error')
      }
    } else {
      studio.removeAsset(props.project.id, target.id)
    }
  }
  deleteOpen.value = false
}
</script>

<template>
  <section class="studio-assets" aria-label="资产生成">
    <p v-if="project.scriptEdited" class="studio-hint">剧本已手动修改，资产仍基于生成时的结构化剧本。</p>

    <div v-if="selectMode" class="studio-select-bar">
      <span class="studio-select-bar-text">
        已勾选 <strong>{{ checkedAssetIds.length }}</strong> 项资产（可在不同分类间连续勾选）
      </span>
      <div class="studio-select-bar-actions">
        <UiButton variant="ghost" size="sm" :disabled="!checkedAssetIds.length" @click="checkedAssetIds = []">
          清空勾选
        </UiButton>
        <UiButton variant="primary" size="sm" :disabled="!checkedAssetIds.length" @click="openBatchFromSelection">
          <template #leading><Sparkles :size="14" aria-hidden="true" /></template>
          生成 / 重绘已选 ({{ checkedAssetIds.length }})
        </UiButton>
      </div>
    </div>

    <div v-if="batchSummary?.visible" class="studio-batch-banner" :class="{ 'is-done': batchSummary.finished }">
      <div class="studio-batch-banner-head">
        <span class="studio-batch-banner-title">
          <Loader2 v-if="!batchSummary.finished" class="is-spin" :size="15" aria-hidden="true" />
          <CheckCircle2 v-else-if="batchSummary.failed === 0" :size="15" aria-hidden="true" />
          <AlertCircle v-else :size="15" aria-hidden="true" />
          <template v-if="!batchSummary.finished">
            后台批量生图中：已完成 {{ batchSummary.succeeded }} / {{ batchSummary.total }}
            <template v-if="batchSummary.running"> · 进行中 {{ batchSummary.running }}</template>
            <template v-if="batchSummary.failed"> · 失败 {{ batchSummary.failed }}</template>
          </template>
          <template v-else>
            批量生图已完成：成功 {{ batchSummary.succeeded }} 张<template v-if="batchSummary.failed"> · 失败 {{ batchSummary.failed }} 张（已退还积分）</template>
          </template>
        </span>
        <div class="studio-batch-banner-actions">
          <UiButton
            v-if="batchSummary.finished && batchSummary.failedIds.length"
            variant="outline"
            size="sm"
            :loading="batchSubmitting"
            @click="retryFailedBatchAssets"
          >
            <template #leading><RefreshCw :size="13" aria-hidden="true" /></template>
            重试失败项 ({{ batchSummary.failedIds.length }})
          </UiButton>
          <button
            v-if="batchSummary.finished"
            type="button"
            class="studio-batch-close"
            aria-label="关闭批量进度提示"
            @click="dismissBatchBanner"
          >
            <X :size="14" aria-hidden="true" />
          </button>
        </div>
      </div>
      <div class="studio-batch-track" role="progressbar" :aria-valuenow="batchSummary.percent" aria-valuemin="0" aria-valuemax="100">
        <div class="studio-batch-fill" :style="{ width: `${Math.max(6, batchSummary.percent)}%` }"></div>
      </div>
    </div>

    <div class="studio-assets-catalog" :class="{ 'is-empty': !project.assets?.length }">
      <div class="studio-assets-toolbar">
        <UiButton
          v-if="project.persisted && hasExistingAssets"
          :variant="missingImageCount > 0 ? 'primary' : 'outline'"
          size="sm"
          :disabled="generating"
          @click="openBatchDialog()"
        >
          <template #leading><Sparkles :size="14" aria-hidden="true" /></template>
          {{ missingImageCount > 0 ? `批量生图 (${missingImageCount})` : '批量生图 / 重绘' }}
        </UiButton>
        <UiButton
          v-if="project.persisted && hasExistingAssets"
          :variant="selectMode ? 'secondary' : 'outline'"
          size="sm"
          @click="toggleSelectMode"
        >
          <template #leading><CheckSquare :size="14" aria-hidden="true" /></template>
          {{ selectMode ? '退出多选' : '多选' }}
        </UiButton>
        <UiButton
          :variant="canIncrementalSync ? 'primary' : 'outline'"
          size="sm"
          :loading="generating"
          :disabled="generating"
          @click="handleRecognizeClick"
        >
          <template #leading>
            <RefreshCw v-if="hasExistingAssets && !canIncrementalSync" :size="14" aria-hidden="true" />
            <ScanText v-else :size="15" aria-hidden="true" />
          </template>
          {{ canIncrementalSync ? `补充新资产 (${missingScriptAssetIds.length})` : hasExistingAssets ? '重新识别' : '从剧本识别' }}
        </UiButton>
        <UiButton variant="outline" size="sm" @click="addAsset">
          <template #leading><Plus :size="15" aria-hidden="true" /></template>增加资产
        </UiButton>
      </div>

      <EmptyState v-if="!project.assets?.length" class="studio-assets-empty" title="暂无资产">
        <template #icon><Boxes :size="25" :stroke-width="1.5" /></template>
        <UiButton variant="primary" :loading="generating" :disabled="generating" @click="handleRecognizeClick">
          <template v-if="!generating" #leading><ScanText :size="16" aria-hidden="true" /></template>从剧本识别
        </UiButton>
      </EmptyState>
      <UiTabs v-else v-model="category" label="资产分类" :tabs="groups">
        <template v-for="group in groups" :key="group.value" #[group.value]>
          <ul v-if="group.assets.length" class="studio-asset-list">
            <li v-for="asset in group.assets" :key="asset.id">
              <article
                class="studio-asset-card"
                :class="{
                  'is-generating': isAssetGenerating(asset),
                  'is-select-mode': selectMode && !!asset.backendId,
                  'is-checked': selectMode && !!asset.backendId && checkedSet.has(asset.backendId),
                }"
              >
                <button
                  v-if="selectMode && asset.backendId"
                  type="button"
                  class="studio-asset-check"
                  :class="{ 'is-checked': checkedSet.has(asset.backendId) }"
                  :disabled="isAssetGenerating(asset)"
                  :aria-label="`选择 ${asset.name}`"
                  @click="toggleCardCheck(asset)"
                >
                  <Check v-if="checkedSet.has(asset.backendId)" :size="12" :stroke-width="2.6" />
                </button>
                <div class="studio-asset-main">
                  <div class="studio-asset-thumb-wrap">
                    <ImagePreview v-if="asset.imageUrl" :src="asset.imageUrl" :title="asset.name" :items="group.images">
                      <template #trigger>
                        <button type="button" class="studio-asset-thumb" :aria-label="'预览 ' + asset.name">
                          <img :src="asset.imageUrl" alt="" />
                        </button>
                      </template>
                    </ImagePreview>
                    <div v-else class="studio-asset-thumb">
                      <component :is="group.icon" :size="26" :stroke-width="1.5" aria-hidden="true" />
                    </div>
                  </div>
                  <div class="studio-asset-details">
                    <h2 :title="asset.name">{{ asset.name }}</h2>
                    <p v-if="asset.description">{{ asset.description }}</p>
                  </div>
                </div>
                <div
                  v-if="assetJobAlert(asset)"
                  class="studio-asset-job-banner"
                  :class="assetJobAlert(asset)?.status === 'review' ? 'is-review' : 'is-failed'"
                  :title="assetJobAlert(asset)?.message"
                >
                  <Clock v-if="assetJobAlert(asset)?.status === 'review'" :size="13" aria-hidden="true" />
                  <AlertCircle v-else :size="13" aria-hidden="true" />
                  <span class="studio-asset-job-banner-text">
                    <strong>{{ assetJobAlert(asset)?.status === 'review' ? '最近重绘待核对（积分冻结中）' : '最近重绘失败' }}：</strong>
                    {{ assetJobAlert(asset)?.message }}
                  </span>
                  <button
                    v-if="assetJobAlert(asset)?.jobId"
                    type="button"
                    class="studio-asset-job-close"
                    aria-label="忽略本次提示"
                    title="忽略本次提示"
                    @click.stop="dismissAssetJobAlert(assetJobAlert(asset)?.jobId)"
                  >
                    <X :size="12" aria-hidden="true" />
                  </button>
                </div>
                <div class="studio-asset-actions">
                  <span
                    class="studio-asset-status"
                    :class="{
                      'is-generating': isAssetGenerating(asset),
                      'is-review': !isAssetGenerating(asset) && assetJobAlert(asset)?.status === 'review',
                      'is-failed': !isAssetGenerating(asset) && (asset.imageStatus === 'failed' || assetJobAlert(asset)?.status === 'failed'),
                      'has-image': !isAssetGenerating(asset) && !assetJobAlert(asset) && !!asset.imageUrl,
                    }"
                    :title="assetJobAlert(asset)?.message"
                  >
                    <Loader2 v-if="isAssetGenerating(asset)" class="is-spin" :size="14" aria-hidden="true" />
                    <Clock v-else-if="assetJobAlert(asset)?.status === 'review'" :size="14" aria-hidden="true" />
                    <AlertCircle
                      v-else-if="asset.imageStatus === 'failed' || assetJobAlert(asset)?.status === 'failed'"
                      :size="14"
                      aria-hidden="true"
                    />
                    <component :is="asset.imageUrl ? ImageIcon : ImageOff" v-else :size="14" aria-hidden="true" />
                    <template v-if="isAssetGenerating(asset)">生图中…</template>
                    <template v-else-if="assetJobAlert(asset)?.status === 'review'">待核对</template>
                    <template v-else-if="assetJobAlert(asset)?.status === 'failed'">{{ asset.imageUrl ? '重绘失败' : '生成失败' }}</template>
                    <template v-else-if="asset.imageStatus === 'failed'">生成失败</template>
                    <template v-else>{{ asset.imageUrl ? '已有图片' : '暂无图片' }}</template>
                  </span>
                  <div class="studio-asset-buttons">
                    <UiButton
                      v-if="project.persisted && asset.backendId && (asset.imageHistory?.length ?? 0) >= 2"
                      variant="outline"
                      size="sm"
                      :disabled="isAssetGenerating(asset)"
                      :aria-label="`查看${asset.name}历史图片`"
                      @click="openAssetHistory(asset)"
                    >
                      <template #leading><History :size="14" aria-hidden="true" /></template>
                      历史 · {{ asset.imageHistory?.length }}
                    </UiButton>
                    <UiButton
                      v-if="project.persisted && asset.backendId"
                      variant="outline"
                      size="sm"
                      :loading="submittingAssetId === asset.backendId"
                      :disabled="generating || submittingAssetId === asset.backendId || isAssetGenerating(asset)"
                      :aria-label="`AI生成${asset.name}图片`"
                      @click="quickGenerateAssetImage(asset, $event)"
                    >
                      <template v-if="submittingAssetId !== asset.backendId" #leading><Sparkles :size="14" aria-hidden="true" /></template>
                      {{ asset.imageUrl ? '重绘' : 'AI 生图' }}
                    </UiButton>
                    <UiButton variant="outline" size="sm" :aria-label="`编辑${asset.name}`" @click="editAsset(asset, $event)">
                      <template #leading><Pencil :size="14" aria-hidden="true" /></template>编辑
                    </UiButton>
                    <UiButton
                      class="studio-asset-delete"
                      variant="secondary"
                      size="sm"
                      :disabled="isAssetGenerating(asset)"
                      :aria-label="`删除${asset.name}`"
                      title="删除资产"
                      @click="confirmAssetDeletion(asset)"
                    >
                      <template #leading><Trash2 :size="14" aria-hidden="true" /></template>
                    </UiButton>
                  </div>
                </div>
              </article>
            </li>
          </ul>
          <EmptyState v-else :title="`暂无${group.label}`">
            <template #icon><component :is="group.icon" :size="25" :stroke-width="1.5" /></template>
          </EmptyState>
        </template>
      </UiTabs>
    </div>

    <StudioAssetEditor
      ref="editor"
      :image-models="imageModels"
      :persisted="project.persisted"
      :generating-image="!!submittingAssetId"
      @create="createAsset"
      @save="saveAsset"
      @generate-image="generateAssetImage"
      @open-history="openAssetHistory"
    />

    <MediaHistoryDialog
      v-model:open="historyOpen"
      kind="image"
      :title="historyAsset ? `${historyAsset.name} · 历史图片` : '历史图片'"
      :items="historyAsset?.imageHistory ?? []"
      :current-url="historyAsset?.imageUrl"
      :selecting="historySelecting"
      :deleting-id="historyDeletingId"
      :model-names="imageModelNames"
      deletable
      @select="handleSelectAssetHistory"
      @delete="handleDeleteAssetHistory"
    />

    <StudioBatchImageDialog
      v-model:open="batchOpen"
      :assets="project.assets ?? []"
      :active-category="category"
      :active-asset-ids="activeImageAssetIds"
      :image-models="imageModels"
      :initial-selected-ids="batchInitialIds"
      :submitting="batchSubmitting"
      @submit="submitBatchImageGeneration"
    />

    <UiDialog v-model:open="deleteOpen" title="删除资产">
      <p class="studio-asset-delete-message">确定从当前项目删除「{{ assetToDelete?.name }}」吗？</p>
      <template #footer>
        <UiButton variant="ghost" @click="deleteOpen = false">取消</UiButton>
        <UiButton variant="danger" @click="deleteAsset">
          <template #leading><Trash2 :size="15" aria-hidden="true" /></template>确认删除
        </UiButton>
      </template>
    </UiDialog>
    <UiDialog
      v-model:open="refreshOpen"
      title="重新识别剧本资产"
      description="当前剧本涉及的角色、场景与道具已全部在列表中。"
    >
      <UiAlert
        tone="info"
        title="重新识别会刷新 AI 生成的设定、静态音色与生图提示词；已上传的图片与手动新增的资产将会保留。"
      />
      <template #footer>
        <UiButton variant="ghost" :disabled="generating" @click="refreshOpen = false">取消</UiButton>
        <UiButton variant="primary" :disabled="generating" @click="generateFromScript('full')">
          <template #leading><RefreshCw :size="14" aria-hidden="true" /></template>重新识别
        </UiButton>
      </template>
    </UiDialog>
  </section>
</template>

<style scoped>
.studio-assets { display: flex; flex: 1; flex-direction: column; padding-top: 16px; }
.studio-assets-empty { flex: 1; min-height: 240px; }
.studio-assets-catalog { position: relative; }
.studio-assets-catalog.is-empty { display: flex; flex: 1; flex-direction: column; }
.studio-assets-toolbar { position: absolute; inset: 2px 0 auto auto; display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.studio-assets-catalog.is-empty .studio-assets-toolbar { position: static; }
.studio-hint { margin: 0 0 10px; color: var(--color-muted); font-size: 12px; }
.studio-select-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  border: 1px solid rgb(240 184 75 / 35%);
  border-radius: 8px;
  background: var(--gold-tint);
}
.studio-select-bar-text { font-size: 13px; color: var(--color-text); }
.studio-select-bar-text strong { color: var(--color-gold-soft); }
.studio-select-bar-actions { display: flex; align-items: center; gap: 8px; }
.studio-batch-banner {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid rgb(240 184 75 / 30%);
  border-radius: 8px;
  background: var(--color-surface);
}
.studio-batch-banner.is-done {
  border-color: var(--border-subtle);
}
.studio-batch-banner-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.studio-batch-banner-title {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  color: var(--color-gold-soft);
}
.studio-batch-banner.is-done .studio-batch-banner-title { color: var(--color-text); }
.studio-batch-banner-actions { display: flex; align-items: center; gap: 8px; }
.studio-batch-close {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  color: var(--color-muted);
  cursor: pointer;
}
.studio-batch-close:hover { background: var(--surface-hover); color: var(--color-text); }
.studio-batch-track {
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: rgb(255 255 255 / 8%);
}
.studio-batch-fill {
  height: 100%;
  border-radius: inherit;
  background: var(--color-gold);
  transition: width .35s ease;
}
.studio-assets-catalog :deep(.ui-tabs-list) { gap: 20px; padding-right: 450px; }
.studio-assets-catalog :deep(.ui-tab) { white-space: nowrap; }
.studio-asset-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr)); gap: 12px; margin: 14px 0 0; padding: 0; list-style: none; }
.studio-asset-list > li { min-width: 0; }
.studio-asset-card { position: relative; display: flex; flex-direction: column; height: 100%; padding: 12px; border: 1px solid var(--border-subtle); border-radius: var(--radius-panel); background: var(--color-surface); transition: border-color .15s; }
.studio-asset-card.is-generating { border-color: rgb(240 184 75 / 40%); }
.studio-asset-card.is-checked { border-color: var(--color-gold); background: color-mix(in srgb, var(--color-surface) 92%, var(--color-gold) 8%); }
.studio-asset-card.is-select-mode .studio-asset-details h2 { padding-right: 26px; }
.studio-asset-main { display: grid; grid-template-columns: 104px minmax(0, 1fr); align-items: start; gap: 12px; margin-bottom: 10px; }
.studio-asset-thumb-wrap { position: relative; }
.studio-asset-check {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 2;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border: 1px solid var(--border-control);
  border-radius: 5px;
  background: var(--color-canvas);
  color: var(--color-ink);
  cursor: pointer;
}
.studio-asset-check.is-checked {
  border-color: var(--color-gold);
  background: var(--color-gold);
}
.studio-asset-thumb { display: grid; place-items: center; overflow: hidden; width: 100%; aspect-ratio: 4 / 3; border: 1px solid var(--border-subtle); border-radius: 6px; background: var(--color-elevated); color: var(--color-muted); }
.studio-asset-thumb img { width: 100%; height: 100%; min-height: 0; object-fit: cover; }
button.studio-asset-thumb { cursor: zoom-in; }
.studio-asset-details h2 { margin: 0 0 5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--font-size-body); font-weight: 600; }
.studio-asset-details p { display: -webkit-box; overflow: hidden; margin: 0; color: var(--color-muted); font-size: var(--font-size-caption); overflow-wrap: anywhere; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
.studio-asset-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin-top: auto; padding-top: 10px; border-top: 1px solid var(--border-subtle); }
.studio-asset-buttons { display: flex; gap: 6px; margin-left: auto; }
.studio-asset-delete.ui-button { width: 32px; padding: 0; color: var(--color-muted); }
.studio-asset-delete.ui-button:is(:hover, :focus-visible) { color: var(--color-error); }
.studio-asset-delete-message { margin: 0; overflow-wrap: anywhere; }
.studio-asset-status { display: inline-flex; align-items: center; gap: 6px; color: var(--color-muted); font-size: var(--font-size-caption); }
.studio-asset-status.has-image { color: var(--color-success); }
.studio-asset-status.is-generating { color: var(--color-gold-soft); }
.studio-asset-status.is-review { color: var(--color-gold-soft); }
.studio-asset-status.is-failed { color: var(--color-error); }
.studio-asset-job-banner {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 10px;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.4;
}
.studio-asset-job-banner svg { flex: none; margin-top: 2px; }
.studio-asset-job-banner.is-failed {
  border: 1px solid color-mix(in srgb, var(--color-error) 35%, transparent);
  background: color-mix(in srgb, var(--color-error) 10%, transparent);
  color: var(--color-error);
}
.studio-asset-job-banner.is-review {
  border: 1px solid color-mix(in srgb, var(--color-gold) 40%, transparent);
  background: color-mix(in srgb, var(--color-gold) 10%, transparent);
  color: var(--color-gold-soft);
}
.studio-asset-job-banner-text {
  flex: 1 1 auto;
  min-width: 0;
  display: -webkit-box;
  overflow: hidden;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.studio-asset-job-close {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 4px;
  color: inherit;
  opacity: 0.72;
  cursor: pointer;
}
.studio-asset-job-close:hover { opacity: 1; background: rgb(255 255 255 / 8%); }
.is-spin { animation: spin 1s linear infinite; }
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
@media (max-width: 380px) {
  .studio-assets-catalog :deep(.ui-tabs-list) { gap: 10px; }
  .studio-asset-main { grid-template-columns: 84px minmax(0, 1fr); gap: 8px; }
}
@container (max-width: 760px) {
  .studio-assets-toolbar { position: static; margin-bottom: 8px; }
  .studio-assets-catalog :deep(.ui-tabs-list) { padding-right: 0; }
}
</style>
