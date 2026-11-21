<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, Clapperboard, Sparkles, Video } from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import type { ModelCatalogItemOut } from '../api-types'
import VideoModelPicker from './VideoModelPicker.vue'
import VideoParamsPopover from './VideoParamsPopover.vue'
import type { StudioAsset } from '../studio-assets'
import type { StoryboardClip } from '../studio-storyboard'

const props = withDefaults(
  defineProps<{
    episodeNumber: number
    clips: StoryboardClip[]
    projectAssets: StudioAsset[]
    projectRatio?: string
    activeClipIds: ReadonlySet<string>
    videoModels: ModelCatalogItemOut[]
    initialSelectedIds?: string[]
    submitting?: boolean
  }>(),
  {
    projectRatio: '16:9',
    initialSelectedIds: () => [],
    submitting: false,
  },
)

const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{
  submit: [payload: {
    clipIds: string[]
    modelId: string
    resolution: '480p' | '720p' | '1080p'
    ratio?: string
    durationSeconds?: number
  }]
}>()

const selectedIds = ref<string[]>([])
const selectedModelId = ref('cc-sd2-fast-720')
const selectedResolution = ref<'480p' | '720p' | '1080p'>('720p')
const selectedRatio = ref(props.projectRatio || '16:9')
const durationMode = ref<'keep' | 'override'>('keep')
const overrideDuration = ref(10)

const assetsByCode = computed(() => new Map(props.projectAssets.map((a) => [a.id, a])))
const assetsByBackendId = computed(
  () => new Map(props.projectAssets.filter((a) => a.backendId).map((a) => [a.backendId!, a])),
)

const modelCatalogList = computed<ModelCatalogItemOut[]>(() => {
  if (props.videoModels.length) return props.videoModels
  return [
    {
      id: 'cc-sd2-fast-720',
      mediaType: 'video',
      category: 'Seedance 2.0',
      displayName: 'Seedance 2.0 极速 720p',
      isDefault: true,
      capabilities: {
        description: '快速稳定不限并发，适合日常分镜批量出片',
        minDuration: 4,
        maxDuration: 15,
        maxPromptChars: 5000,
        maxReferenceImages: 9,
        maxReferenceVideos: 3,
        maxReferenceAudios: 3,
        resolutions: ['720p'],
      },
      defaults: { resolution: '720p' },
      imagePrices: [],
      videoPrices: [{ ruleKey: 'default', unit: 'call', creditPrice: '15.0000' }],
    },
  ]
})

const currentModel = computed(
  () => modelCatalogList.value.find((m) => m.id === selectedModelId.value) ?? modelCatalogList.value[0],
)

const minDuration = computed(() => Number(currentModel.value?.capabilities?.minDuration || 4))
const maxDuration = computed(() => Number(currentModel.value?.capabilities?.maxDuration || 15))
const maxPromptChars = computed(() => Number(currentModel.value?.capabilities?.maxPromptChars || 5000))
const maxReferenceImages = computed(() => Number(currentModel.value?.capabilities?.maxReferenceImages ?? 9))

function missingReferenceName(clip: StoryboardClip): string {
  for (const refItem of clip.references ?? []) {
    const asset = assetsByCode.value.get(refItem.assetId) ?? assetsByBackendId.value.get(refItem.assetId)
    const url = (asset?.imageUrl ?? '').trim()
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      return asset?.name || refItem.name || '参考素材'
    }
  }
  return ''
}

function effectiveClipDuration(clip: StoryboardClip): number {
  return durationMode.value === 'override' ? overrideDuration.value : clip.durationSeconds
}

function disabledReason(clip: StoryboardClip): string {
  if (!clip.backendId) return '未保存'
  if (props.activeClipIds.has(clip.backendId)) return '生成中'
  const text = clip.prompt.trim()
  if (!text) return '缺提示词'
  if (text.length > maxPromptChars.value) return `超 ${maxPromptChars.value} 字`
  const dur = effectiveClipDuration(clip)
  if (dur < minDuration.value) return `少于 ${minDuration.value}s`
  if (dur > maxDuration.value) return `超 ${maxDuration.value}s`
  if ((clip.references?.length ?? 0) > maxReferenceImages.value) return `参考图超 ${maxReferenceImages.value} 张`
  const missingRef = missingReferenceName(clip)
  if (missingRef) return '缺参考图'
  return ''
}

function isSelectable(clip: StoryboardClip) {
  return !disabledReason(clip)
}

const selectableClips = computed(() => props.clips.filter(isSelectable))
const missingSelectableClips = computed(() => selectableClips.value.filter((c) => !c.videoUrl))
const selectedSet = computed(() => new Set(selectedIds.value))

const selectedClips = computed(() =>
  props.clips.filter((c) => c.backendId && selectedSet.value.has(c.backendId) && isSelectable(c)),
)

const newCount = computed(() => selectedClips.value.filter((c) => !c.videoUrl).length)
const redrawCount = computed(() => selectedClips.value.filter((c) => !!c.videoUrl).length)
const totalSeconds = computed(() => selectedClips.value.reduce((sum, c) => sum + effectiveClipDuration(c), 0))

function clipCreditPrice(clip: StoryboardClip): number | null {
  const model = currentModel.value
  const price = model?.videoPrices.find((p) => p.ruleKey === selectedResolution.value)
    ?? model?.videoPrices.find((p) => p.ruleKey === 'default')
  if (!price) return null
  const unit = Number(price.creditPrice)
  if (!Number.isFinite(unit)) return null
  return price.unit === 'second' ? unit * effectiveClipDuration(clip) : unit
}

const totalEstimatedAmount = computed(() => {
  if (!selectedClips.value.length) return ''
  let total = 0
  for (const c of selectedClips.value) {
    const cost = clipCreditPrice(c)
    if (cost === null) return ''
    total += cost
  }
  return String(Number(total.toFixed(2)))
})

const totalEstimatedText = computed(() => (totalEstimatedAmount.value ? `${totalEstimatedAmount.value} 积分` : ''))

watch(open, (isOpen) => {
  if (!isOpen) return
  durationMode.value = 'keep'
  selectedRatio.value = props.projectRatio || '16:9'
  const hasLongClip = props.clips.some((c) => c.durationSeconds > 15)
  const defaultModel = hasLongClip
    ? (modelCatalogList.value.find((m) => Number(m.capabilities?.maxDuration || 15) >= 30)?.id
      ?? modelCatalogList.value[0]?.id
      ?? 'cc-sd2.5-720')
    : (modelCatalogList.value.find((m) => m.isDefault)?.id ?? modelCatalogList.value[0]?.id ?? 'cc-sd2-fast-720')
  selectedModelId.value = defaultModel

  if (props.initialSelectedIds.length) {
    const allowed = new Set(selectableClips.value.map((c) => c.backendId!))
    selectedIds.value = props.initialSelectedIds.filter((id) => allowed.has(id)).slice(0, 30)
  } else {
    selectedIds.value = missingSelectableClips.value.map((c) => c.backendId!).slice(0, 30)
  }
})

// 切换模型或时长模式后自动剔除不符合条件的勾选
watch([selectedModelId, durationMode, overrideDuration], () => {
  const allowed = new Set(selectableClips.value.map((c) => c.backendId!))
  selectedIds.value = selectedIds.value.filter((id) => allowed.has(id))
})

function toggleClip(clip: StoryboardClip) {
  if (!isSelectable(clip) || !clip.backendId) return
  const id = clip.backendId
  if (selectedSet.value.has(id)) {
    selectedIds.value = selectedIds.value.filter((item) => item !== id)
  } else {
    if (selectedIds.value.length >= 30) return
    selectedIds.value = [...selectedIds.value, id]
  }
}

function selectMissing() {
  selectedIds.value = missingSelectableClips.value.map((c) => c.backendId!).slice(0, 30)
}

function selectAllClips() {
  selectedIds.value = selectableClips.value.map((c) => c.backendId!).slice(0, 30)
}

function clearSelection() {
  selectedIds.value = []
}

function promptSnippet(prompt: string) {
  return prompt.replace(/\s+/gu, ' ').trim().slice(0, 42) || '暂无提示词'
}

function confirmSubmit() {
  const ids = selectedClips.value.map((c) => c.backendId!)
  if (!ids.length || props.submitting) return
  emit('submit', {
    clipIds: ids,
    modelId: selectedModelId.value,
    resolution: selectedResolution.value,
    ratio: selectedRatio.value,
    durationSeconds: durationMode.value === 'override' ? overrideDuration.value : undefined,
  })
}
</script>

<template>
  <UiDialog
    v-model:open="open"
    :title="`第 ${episodeNumber} 集 · 批量生视频 / 批量重新生成`"
    description="可自由勾选待生成片段或已有视频的片段重新生成（单次最多 30 段，后台并发执行不阻塞页面）。"
    size="landscape"
  >
    <div class="batch-dialog">
      <div class="batch-shortcuts">
        <div class="batch-shortcut-buttons">
          <UiButton variant="outline" size="sm" :disabled="!missingSelectableClips.length" @click="selectMissing">
            全选未生成 ({{ missingSelectableClips.length }})
          </UiButton>
          <UiButton variant="outline" size="sm" :disabled="!selectableClips.length" @click="selectAllClips">
            全选全部 ({{ selectableClips.length }})
          </UiButton>
          <UiButton variant="ghost" size="sm" :disabled="!selectedIds.length" @click="clearSelection">
            清空
          </UiButton>
        </div>
        <span class="batch-count-hint">已选 {{ selectedClips.length }} / {{ clips.length }} 段</span>
      </div>

      <ul class="batch-clip-grid">
        <li v-for="item in clips" :key="item.id">
          <button
            type="button"
            class="batch-clip-item"
            :class="{
              'is-selected': !!item.backendId && selectedSet.has(item.backendId),
              'is-disabled': !isSelectable(item),
            }"
            :disabled="!isSelectable(item)"
            :title="missingReferenceName(item) ? `参考素材「${missingReferenceName(item)}」缺少公网图片` : undefined"
            @click="toggleClip(item)"
          >
            <span class="batch-check" aria-hidden="true">
              <Check v-if="item.backendId && selectedSet.has(item.backendId)" :size="12" :stroke-width="2.6" />
            </span>
            <span class="batch-thumb">
              <img v-if="item.previewUrl" :src="item.previewUrl" alt="" />
              <video
                v-else-if="item.videoUrl"
                :src="`${item.videoUrl}#t=0.1`"
                muted
                playsinline
                preload="metadata"
              />
              <Clapperboard v-else :size="18" aria-hidden="true" />
            </span>
            <span class="batch-info">
              <span class="batch-head">
                <strong>片段 {{ item.id }}</strong>
                <span
                  class="batch-dur"
                  :class="{ 'is-overridden': durationMode === 'override' && effectiveClipDuration(item) !== item.durationSeconds }"
                  :title="durationMode === 'override' && effectiveClipDuration(item) !== item.durationSeconds ? `原 ${item.durationSeconds}s → 统一 ${overrideDuration}s` : undefined"
                >{{ effectiveClipDuration(item) }}s</span>
              </span>
              <span class="batch-snippet">{{ promptSnippet(item.prompt) }}</span>
              <span class="batch-tags">
                <span v-if="disabledReason(item)" class="batch-badge is-disabled">{{ disabledReason(item) }}</span>
                <span v-else-if="item.videoUrl" class="batch-badge is-redraw">已有视频 · 重生成</span>
                <span v-else class="batch-badge is-missing">待生成</span>
              </span>
            </span>
          </button>
        </li>
      </ul>

      <div class="batch-config-bar">
        <div class="batch-config-selects">
          <VideoModelPicker
            v-model="selectedModelId"
            :models="modelCatalogList"
            :project-ratio="selectedRatio"
          />
          <VideoParamsPopover
            v-model:resolution="selectedResolution"
            v-model:ratio="selectedRatio"
            v-model:duration-mode="durationMode"
            v-model:duration="overrideDuration"
            :model="currentModel"
            :default-ratio="projectRatio"
            mode="batch"
          />
        </div>
        <div class="batch-summary">
          <p v-if="selectedClips.length" class="batch-summary-main">
            已选 <strong>{{ selectedClips.length }}</strong> 段（新生成 {{ newCount }} · 重生成 {{ redrawCount }}），共 <strong>{{ totalSeconds }} 秒</strong><template v-if="totalEstimatedText">，预计预冻结 <strong>{{ totalEstimatedText }}</strong></template>
          </p>
          <p v-else class="batch-summary-main">请至少勾选 1 个可生成片段</p>
          <p class="batch-summary-note">每段独立核算：单段失败自动退还该段积分，重新生成失败保留原视频。</p>
        </div>
      </div>
    </div>

    <template #footer>
      <UiButton variant="ghost" size="sm" :disabled="submitting" @click="open = false">取消</UiButton>
      <div class="batch-cta-split" :class="{ 'is-solo': !totalEstimatedAmount || submitting }">
        <span v-if="totalEstimatedAmount && !submitting" class="batch-cta-cost">
          <Sparkles :size="13" class="batch-cta-cost-icon" aria-hidden="true" />
          <strong class="batch-cta-cost-num">{{ totalEstimatedAmount }}</strong>
          <span class="batch-cta-cost-unit">积分</span>
        </span>
        <UiButton
          class="batch-submit-btn"
          variant="primary"
          size="sm"
          :loading="submitting"
          :disabled="!selectedClips.length || submitting"
          @click="confirmSubmit"
        >
          <template v-if="!submitting" #leading><Video :size="14" aria-hidden="true" /></template>
          开始批量生视频 ({{ selectedClips.length }})
        </UiButton>
      </div>
    </template>
  </UiDialog>
</template>

<style scoped>
.batch-dialog {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}
.batch-shortcuts {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.batch-shortcut-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.batch-count-hint {
  color: var(--color-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.batch-clip-grid {
  display: grid;
  flex: 1;
  align-content: start;
  grid-template-columns: repeat(auto-fill, minmax(235px, 1fr));
  gap: 8px;
  min-height: 0;
  overflow-y: auto;
  margin: 0;
  padding: 2px 4px 2px 0;
  list-style: none;
}
.batch-clip-item {
  display: grid;
  grid-template-columns: 18px 68px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 8px;
  border: 1px solid var(--border-control);
  border-radius: 8px;
  background: var(--color-surface);
  color: var(--color-text);
  text-align: left;
  cursor: pointer;
  transition: border-color .15s, background-color .15s;
}
.batch-clip-item:not(:disabled):hover {
  border-color: rgb(240 184 75 / 50%);
  background: var(--surface-hover);
}
.batch-clip-item.is-selected {
  border-color: var(--color-gold);
  background: var(--gold-tint);
}
.batch-clip-item.is-disabled {
  opacity: 0.48;
  cursor: not-allowed;
}
.batch-check {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border: 1px solid var(--border-control);
  border-radius: 4px;
  background: var(--color-canvas);
  color: var(--color-ink);
}
.batch-clip-item.is-selected .batch-check {
  border-color: var(--color-gold);
  background: var(--color-gold);
}
.batch-thumb {
  display: grid;
  place-items: center;
  width: 68px;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: 5px;
  background: var(--color-elevated);
  color: var(--color-muted);
}
.batch-thumb img,
.batch-thumb video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  pointer-events: none;
}
.batch-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.batch-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
.batch-head strong {
  font-size: 13px;
  font-weight: 600;
}
.batch-dur {
  color: var(--color-muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.batch-dur.is-overridden {
  padding: 0 5px;
  border-radius: 4px;
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-weight: 600;
}
.batch-snippet {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-muted);
  font-size: 11px;
}
.batch-tags {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
}
.batch-badge {
  padding: 0 5px;
  border-radius: 4px;
}
.batch-badge.is-missing {
  background: var(--gold-tint);
  color: var(--color-gold-soft);
}
.batch-badge.is-redraw {
  background: rgb(74 222 128 / 12%);
  color: var(--color-success);
}
.batch-badge.is-disabled {
  background: rgb(255 255 255 / 5%);
  color: var(--color-muted);
}
.batch-config-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-top: auto;
  padding: 10px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--color-canvas);
}
.batch-config-selects {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.batch-summary {
  flex: 1 1 240px;
  text-align: right;
}
.batch-summary-main {
  margin: 0;
  font-size: 13px;
}
.batch-summary-main strong {
  color: var(--color-gold-soft);
}
.batch-summary-note {
  margin: 3px 0 0;
  color: var(--color-muted);
  font-size: 11px;
}
.batch-cta-split {
  display: inline-flex;
  align-items: stretch;
  height: 36px;
  border-radius: 9px;
  overflow: hidden;
  border: 1px solid rgb(240 184 75 / 55%);
  box-shadow: 0 2px 10px rgb(240 184 75 / 12%);
}
.batch-cta-split.is-solo {
  border-color: transparent;
  box-shadow: none;
}
.batch-cta-cost {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0 12px;
  background: #13151c;
  color: var(--color-gold-soft);
  user-select: none;
}
.batch-cta-cost-icon {
  color: var(--color-gold);
  flex-shrink: 0;
}
.batch-cta-cost-num {
  font-size: 16px;
  font-weight: 700;
  color: #f8cc66;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  line-height: 1;
}
.batch-cta-cost-unit {
  font-size: 11px;
  font-weight: 500;
  color: rgb(248 204 102 / 82%);
  line-height: 1;
}
.batch-submit-btn.ui-button {
  min-height: 34px;
  height: 100%;
  padding: 0 15px;
  border: 0;
  border-radius: 0;
}
.batch-cta-split.is-solo .batch-submit-btn.ui-button {
  border-radius: 9px;
}
@media (max-width: 640px) {
  .batch-summary { text-align: left; }
}
</style>
