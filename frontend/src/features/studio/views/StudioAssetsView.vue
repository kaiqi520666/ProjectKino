<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, useTemplateRef, watch } from 'vue'
import {
  AlertCircle,
  Boxes,
  Check,
  CheckCircle2,
  CheckSquare,
  ImageIcon,
  ImageOff,
  Loader2,
  MapPin,
  Package,
  Pencil,
  Plus,
  RefreshCw,
  ScanText,
  Sparkles,
  Trash2,
  UserRound,
  X,
} from 'lucide-vue-next'
import EmptyState from '@/components/business/EmptyState.vue'
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
  getJob,
  getModelCatalog,
  getProjectDetail,
  isRetryableApiError,
  startBatchGenerateAssetImages,
  startExtractAssets,
  startGenerateAssetImage,
  updateAssetApi,
  watchJob,
} from '../api'
import type { ModelCatalogItemOut, ProjectDetailOut } from '../api-types'
import StudioAssetEditor from '../components/StudioAssetEditor.vue'
import StudioBatchImageDialog from '../components/StudioBatchImageDialog.vue'
import { assetKindOptions } from '../studio-assets'
import type { StudioAsset, StudioAssetDraft, StudioAssetKind } from '../studio-assets'
import type { StudioProject } from '../studio-project'
import { useStudioStore } from '../studio-store'

interface BatchTracker {
  modelId: string
  tier: 'web' | '1k' | '2k' | '4k'
  ratio?: string
  jobToAsset: Record<string, string>
  succeededAssets: string[]
  failedAssets: Record<string, string>
  dismissed: boolean
}

const props = defineProps<{ project: StudioProject }>()
const auth = useAuthStore()
const studio = useStudioStore()
const generation = useGenerationStore()
const ui = useUiStore()
const categoryIcons = { character: UserRound, scene: MapPin, prop: Package }
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
const imageModels = ref<ModelCatalogItemOut[]>([])
const batchTracker = ref<BatchTracker | null>(null)
const checkedJobTerminals = new Set<string>()
let pollTimer: ReturnType<typeof setInterval> | null = null
let pollingInFlight = false

onMounted(async () => {
  try {
    const catalog = await getModelCatalog()
    imageModels.value = catalog.image
  } catch {
    // 保留默认模型兜底选项。
  }
})

onUnmounted(() => {
  stopBatchPolling()
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

function isAssetGenerating(asset: StudioAsset) {
  return !!asset.backendId && activeImageAssetIds.value.has(asset.backendId)
}

function failedReasonForAsset(asset: StudioAsset) {
  if (!asset.backendId) return ''
  return batchTracker.value?.failedAssets[asset.backendId] ?? ''
}

const missingImageCount = computed(() =>
  (props.project.assets ?? []).filter(
    (a) => !!a.backendId && !a.imageUrl && !!a.prompt.trim() && !activeImageAssetIds.value.has(a.backendId),
  ).length,
)

const groups = computed(() => assetKindOptions.map((item) => {
  const assets = props.project.assets?.filter(({ kind }) => kind === item.value) ?? []
  const images = assets.flatMap(asset => asset.imageUrl ? [{ src: asset.imageUrl, title: asset.name }] : [])
  return { ...item, icon: categoryIcons[item.value], count: assets.length, assets, images }
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

const batchSummary = computed(() => {
  const tracker = batchTracker.value
  const activeCount = activeImageAssetIds.value.size
  if (tracker && !tracker.dismissed) {
    const total = Object.keys(tracker.jobToAsset).length
    const succeeded = tracker.succeededAssets.length
    const failedIds = Object.keys(tracker.failedAssets)
    const failed = failedIds.length
    const running = Math.max(0, total - succeeded - failed)
    const done = succeeded + failed
    const percent = total > 0 ? Math.round((done / total) * 100) : 0
    return {
      visible: true,
      total,
      succeeded,
      failed,
      failedIds,
      running,
      percent,
      finished: running === 0 && activeCount === 0,
      modelId: tracker.modelId,
      tier: tracker.tier,
    }
  }
  if (activeCount > 0) {
    return {
      visible: true,
      total: activeCount,
      succeeded: 0,
      failed: 0,
      failedIds: [] as string[],
      running: activeCount,
      percent: 15,
      finished: false,
      modelId: '',
      tier: '1k' as const,
    }
  }
  return null
})

function startBatchPolling() {
  if (pollTimer !== null || !props.project.persisted) return
  pollTimer = setInterval(() => {
    void pollBatchProgress()
  }, 3000)
}

function stopBatchPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function pollBatchProgress() {
  if (pollingInFlight || !props.project.persisted) return
  pollingInFlight = true
  try {
    const detail = await getProjectDetail(props.project.id)
    studio.hydrateProjectDetail(detail)
    void auth.refreshBalance()

    const activeIds = new Set(
      (detail.activeJobs ?? [])
        .filter((j) => j.jobType === 'asset_image')
        .map((j) => j.id),
    )

    const tracker = batchTracker.value
    if (tracker) {
      const newlyFinishedJobIds = Object.keys(tracker.jobToAsset).filter(
        (jid) => !activeIds.has(jid) && !checkedJobTerminals.has(jid),
      )
      for (const jid of newlyFinishedJobIds) {
        checkedJobTerminals.add(jid)
        try {
          const job = await getJob(jid)
          const aid = tracker.jobToAsset[jid]
          if (!aid) continue
          if (job.status === 'succeeded') {
            if (!tracker.succeededAssets.includes(aid)) tracker.succeededAssets.push(aid)
            delete tracker.failedAssets[aid]
          } else if (job.status === 'failed' || job.status === 'review') {
            tracker.failedAssets[aid] = job.errorMessage || '图片生成失败'
          } else {
            // 尚未进入终态，放回下次继续检查
            checkedJobTerminals.delete(jid)
          }
        } catch {
          checkedJobTerminals.delete(jid)
        }
      }
    }

    const stillRunning = activeIds.size > 0
      || detail.assets.some((a) => a.imageStatus === 'generating')
    if (!stillRunning) {
      stopBatchPolling()
      if (tracker && !tracker.dismissed) {
        const okCount = tracker.succeededAssets.length
        const failCount = Object.keys(tracker.failedAssets).length
        if (okCount > 0 || failCount > 0) {
          ui.notify(
            failCount > 0
              ? `批量生图结束：成功 ${okCount} 张，失败 ${failCount} 张（失败已自动退还冻结积分）`
              : `批量生图完成：共生成 ${okCount} 张资产图片`,
            failCount > 0 ? 'info' : 'success',
          )
        }
      }
    }
  } catch {
    // 静默忽略单次轮询波动，下个周期重试。
  } finally {
    pollingInFlight = false
  }
}

watch(
  hasActiveImageJobs,
  (active) => {
    if (active) startBatchPolling()
    else if (!batchSummary.value || batchSummary.value.finished) stopBatchPolling()
  },
  { immediate: true },
)

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

function trackImageJobs(
  jobs: Array<{ id: string; targetId?: string | null }>,
  modelId: string,
  tier: 'web' | '1k' | '2k' | '4k',
  ratio?: string,
) {
  const existing = batchTracker.value
  const shouldMerge = !!existing && !existing.dismissed && !!batchSummary.value && !batchSummary.value.finished
  const tracker: BatchTracker = shouldMerge
    ? {
        ...existing,
        modelId,
        tier,
        ratio,
        jobToAsset: { ...existing.jobToAsset },
        succeededAssets: [...existing.succeededAssets],
        failedAssets: { ...existing.failedAssets },
        dismissed: false,
      }
    : {
        modelId,
        tier,
        ratio,
        jobToAsset: {},
        succeededAssets: [],
        failedAssets: {},
        dismissed: false,
      }

  for (const job of jobs) {
    if (!job.targetId) continue
    tracker.jobToAsset[job.id] = job.targetId
    checkedJobTerminals.delete(job.id)
    delete tracker.failedAssets[job.targetId]
    tracker.succeededAssets = tracker.succeededAssets.filter((aid) => aid !== job.targetId)
  }
  batchTracker.value = tracker
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

    trackImageJobs(res.jobs, payload.modelId, payload.tier, payload.ratio)

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
  const ids = Object.keys(tracker.failedAssets)
  if (!ids.length) return
  void submitBatchImageGeneration({
    assetIds: ids,
    modelId: tracker.modelId,
    tier: tracker.tier,
    ratio: tracker.ratio,
  })
}

function dismissBatchBanner() {
  if (batchTracker.value) batchTracker.value.dismissed = true
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
    trackImageJobs([accepted.job], options.modelId, options.tier, options.ratio)

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
  const defaultModel = imageModels.value.find((m) => m.isDefault)?.id || imageModels.value[0]?.id || 'gpt-image-2'
  const tierVal = asset.imageTier
  const tier: 'web' | '1k' | '2k' | '4k' = tierVal === 'web' || tierVal === '1k' || tierVal === '2k' || tierVal === '4k' ? tierVal : '1k'
  void generateAssetImage(asset, {
    modelId: asset.imageModelId || defaultModel,
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
                    <div v-if="isAssetGenerating(asset)" class="studio-asset-loading-mask">
                      <Loader2 class="is-spin" :size="16" aria-hidden="true" />
                      <span>生图中</span>
                    </div>
                  </div>
                  <div class="studio-asset-details">
                    <h2 :title="asset.name">{{ asset.name }}</h2>
                    <p v-if="asset.description">{{ asset.description }}</p>
                  </div>
                </div>
                <div class="studio-asset-actions">
                  <span
                    class="studio-asset-status"
                    :class="{
                      'is-generating': isAssetGenerating(asset),
                      'is-failed': !isAssetGenerating(asset) && (asset.imageStatus === 'failed' || !!failedReasonForAsset(asset)),
                      'has-image': !isAssetGenerating(asset) && !failedReasonForAsset(asset) && !!asset.imageUrl,
                    }"
                    :title="failedReasonForAsset(asset)"
                  >
                    <Loader2 v-if="isAssetGenerating(asset)" class="is-spin" :size="14" aria-hidden="true" />
                    <AlertCircle
                      v-else-if="asset.imageStatus === 'failed' || failedReasonForAsset(asset)"
                      :size="14"
                      aria-hidden="true"
                    />
                    <component :is="asset.imageUrl ? ImageIcon : ImageOff" v-else :size="14" aria-hidden="true" />
                    <template v-if="isAssetGenerating(asset)">生图中…</template>
                    <template v-else-if="failedReasonForAsset(asset)">重绘失败</template>
                    <template v-else-if="asset.imageStatus === 'failed'">生成失败</template>
                    <template v-else>{{ asset.imageUrl ? '已有图片' : '暂无图片' }}</template>
                  </span>
                  <div class="studio-asset-buttons">
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
.studio-asset-loading-mask {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  border-radius: 6px;
  background: rgb(9 10 13 / 72%);
  color: var(--color-gold-soft);
  font-size: 11px;
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
.studio-asset-status.is-failed { color: var(--color-error); }
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
