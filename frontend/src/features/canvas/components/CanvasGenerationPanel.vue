<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowUp, Check, ChevronDown, Coins, Loader2, Maximize2, RectangleHorizontal, Sparkles } from 'lucide-vue-next'
import {
  PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger,
  RadioGroupItem, RadioGroupRoot,
  SelectContent, SelectItem, SelectItemIndicator, SelectItemText, SelectPortal,
  SelectRoot, SelectTrigger, SelectValue, SelectViewport,
} from 'reka-ui'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import type { ModelCatalogItemOut } from '@/features/studio/api-types'
import ImageModelPicker from '@/features/studio/components/ImageModelPicker.vue'
import ImageParamsPopover from '@/features/studio/components/ImageParamsPopover.vue'
import VideoModelPicker from '@/features/studio/components/VideoModelPicker.vue'
import { useModelCatalog } from '@/features/studio/composables/useModelCatalog'
import { useAuthStore } from '@/stores/auth'
import { outputKind, type CanvasGenerationSettings, type CanvasImageTier, type CanvasNode, type CanvasNodeKind } from '../canvas-model'
import { useCanvasPopup } from '../useCanvasPopup'
import CanvasPromptInput from './CanvasPromptInput.vue'
import CanvasNodeReferences from './CanvasNodeReferences.vue'

const props = defineProps<{ kind: CanvasNodeKind; references: CanvasNode[]; settings?: CanvasGenerationSettings; generating?: boolean }>()
const emit = defineEmits<{
  settings: [value: CanvasGenerationSettings]
  generate: [settings: CanvasGenerationSettings]
  removeReference: [id: string]
  reorderReferences: [ids: string[]]
}>()
const prompt = defineModel<string>({ default: '' })
const { open: modelOpen, triggerKey: modelTriggerKey } = useCanvasPopup()
const { open: parametersOpen, triggerKey: parametersTriggerKey } = useCanvasPopup()
const catalog = useModelCatalog()
const auth = useAuthStore()

const expanded = ref(false)
const expandedPrompt = ref('')
const expandedOrder = ref<string[]>([])
const expandedReferences = computed(() => {
  const nodes = new Map(props.references.map(node => [node.id, node]))
  return expandedOrder.value.flatMap(id => nodes.get(id) ?? [])
})
const hasInput = computed(() => Boolean(prompt.value.trim()) || props.references.some(node => Boolean(node.data.text?.trim())))
const imageReferenceCount = computed(() => props.references.filter(node => outputKind(node.type) === 'image').length)

const RATIO_SHAPES: Record<string, string> = {
  '16:9': '16 / 9',
  '9:16': '9 / 16',
  '1:1': '1',
  '4:3': '4 / 3',
  '3:4': '3 / 4',
  '21:9': '21 / 9',
  '3:2': '3 / 2',
  '2:3': '2 / 3',
}
const DEFAULT_RATIOS = ['16:9', '9:16', '1:1', '4:3', '3:4'] as const
const TIER_ORDER: readonly CanvasImageTier[] = ['web', '1k', '2k', '4k']
const TIER_LABELS: Record<CanvasImageTier, string> = {
  web: 'Web',
  '1k': '1K',
  '2k': '2K',
  '4k': '4K',
}
const DURATION_CANDIDATES = [4, 5, 6, 8, 10, 12, 15] as const

function formatCreditsNum(value: number): string {
  if (!Number.isFinite(value)) return '0'
  return Number(value.toFixed(2)).toString()
}

function getModelRatios(model: ModelCatalogItemOut | null): string[] {
  const raw = model?.capabilities?.ratios
  if (Array.isArray(raw)) {
    const cleaned = raw.map(item => String(item).trim()).filter(Boolean)
    if (cleaned.length) return cleaned
  }
  return [...DEFAULT_RATIOS]
}

function getModelTiers(model: ModelCatalogItemOut | null): CanvasImageTier[] {
  if (model?.imagePrices?.length) {
    const available = new Set(model.imagePrices.map(p => p.tier))
    const ordered = TIER_ORDER.filter(t => available.has(t))
    if (ordered.length) return ordered
  }
  return ['1k', '2k']
}

function getModelResolutions(model: ModelCatalogItemOut | null): string[] {
  const raw = model?.capabilities?.resolutions
  if (Array.isArray(raw)) {
    const cleaned = raw.map(item => String(item).trim().toLowerCase()).filter(Boolean)
    if (cleaned.length) return cleaned
  }
  return ['720p', '1080p']
}

function getModelDurations(model: ModelCatalogItemOut | null): number[] {
  const caps = model?.capabilities ?? {}
  if (Array.isArray(caps.durations)) {
    const explicit = caps.durations
      .map(item => Number(item))
      .filter(n => Number.isInteger(n) && n >= 1 && n <= 60)
    if (explicit.length) return [...new Set(explicit)].sort((a, b) => a - b)
  }
  const minD = Math.max(1, Math.round(Number(caps.minDuration) || 4))
  const maxD = Math.max(minD, Math.round(Number(caps.maxDuration) || 15))
  const filtered = DURATION_CANDIDATES.filter(d => d >= minD && d <= maxD)
  const set = new Set<number>(filtered)
  if (!set.size) {
    set.add(minD)
    if (maxD !== minD) set.add(maxD)
  }
  return [...set].sort((a, b) => a - b)
}

const models = computed<ModelCatalogItemOut[]>(() => {
  if (props.kind === 'text') return catalog.textModels.value
  if (props.kind === 'image-generation') return catalog.imageModels.value
  return catalog.videoModels.value
})

const selectedModel = computed<ModelCatalogItemOut | null>(() => {
  const list = models.value
  if (!list.length) return null
  if (props.settings?.modelId) {
    const found = list.find(item => item.id === props.settings?.modelId)
    if (found) return found
  }
  return list.find(item => item.isDefault) ?? list[0] ?? null
})

const selectedModelId = computed(() => selectedModel.value?.id ?? props.settings?.modelId ?? '')

const ratios = computed(() =>
  getModelRatios(selectedModel.value).map(value => ({
    value,
    shape: RATIO_SHAPES[value] ?? value.replace(':', ' / '),
  })),
)

const imageTiers = computed(() =>
  getModelTiers(selectedModel.value).map(value => ({
    value,
    label: TIER_LABELS[value],
  })),
)

const videoResolutions = computed(() =>
  getModelResolutions(selectedModel.value).map(value => ({
    value,
    label: value.toUpperCase(),
  })),
)

const videoDurations = computed(() => getModelDurations(selectedModel.value))

const ratio = computed(() => {
  const current = props.settings?.ratio
  if (current && ratios.value.some(opt => opt.value === current)) return current
  const def = typeof selectedModel.value?.defaults?.ratio === 'string' ? selectedModel.value.defaults.ratio : ''
  if (def && ratios.value.some(opt => opt.value === def)) return def
  return ratios.value[0]?.value ?? '16:9'
})

const tier = computed<CanvasImageTier>(() => {
  const current = props.settings?.tier
  if (current && imageTiers.value.some(opt => opt.value === current)) return current
  const def = typeof selectedModel.value?.defaults?.tier === 'string' ? selectedModel.value.defaults.tier : ''
  if (def && imageTiers.value.some(opt => opt.value === def)) return def as CanvasImageTier
  if (imageTiers.value.some(opt => opt.value === '1k')) return '1k'
  return imageTiers.value[0]?.value ?? '1k'
})

const resolution = computed(() => {
  const current = props.settings?.resolution?.toLowerCase()
  if (current && videoResolutions.value.some(opt => opt.value === current)) return current
  const def = typeof selectedModel.value?.defaults?.resolution === 'string'
    ? selectedModel.value.defaults.resolution.toLowerCase()
    : ''
  if (def && videoResolutions.value.some(opt => opt.value === def)) return def
  return videoResolutions.value[0]?.value ?? '720p'
})

const durationSeconds = computed(() => {
  const current = props.settings?.durationSeconds
  if (typeof current === 'number' && videoDurations.value.includes(current)) return current
  const def = Number(selectedModel.value?.defaults?.durationSeconds)
  if (Number.isInteger(def) && videoDurations.value.includes(def)) return def
  return videoDurations.value[0] ?? 5
})

const parameters = computed(() => {
  if (props.kind === 'image-generation') {
    return `${ratio.value} · ${TIER_LABELS[tier.value]}`
  }
  return `${ratio.value} · ${resolution.value.toUpperCase()} · ${durationSeconds.value} 秒`
})

const usageMultiplier = computed(() => {
  const parsed = Number(auth.user?.usageMultiplier)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1
})

const estimatedCreditsText = computed(() => {
  const model = selectedModel.value
  if (!model) return catalog.loading.value ? '加载中…' : '积分待定'
  if (props.kind === 'image-generation') {
    const row = model.imagePrices.find(p => p.tier === tier.value) ?? model.imagePrices[0]
    if (!row) return '按量计费'
    const amount = Number(row.creditPrice) * usageMultiplier.value
    return Number.isFinite(amount) ? `${formatCreditsNum(amount)} 积分` : '积分待定'
  }
  if (props.kind === 'video-generation') {
    const row =
      model.videoPrices.find(p => p.ruleKey.toLowerCase() === resolution.value)
      ?? model.videoPrices.find(p => p.ruleKey === 'default')
      ?? model.videoPrices[0]
    if (!row) return '按量计费'
    const base = Number(row.creditPrice)
    const raw = row.unit === 'second' ? base * durationSeconds.value : base
    const amount = raw * usageMultiplier.value
    return Number.isFinite(amount) ? `${formatCreditsNum(amount)} 积分` : '积分待定'
  }
  return ''
})

const effectiveSettings = computed<CanvasGenerationSettings>(() => {
  if (props.kind === 'text') {
    return { modelId: selectedModelId.value || undefined }
  }
  if (props.kind === 'image-generation') {
    return {
      modelId: selectedModelId.value || undefined,
      ratio: ratio.value,
      tier: tier.value,
    }
  }
  return {
    modelId: selectedModelId.value || undefined,
    ratio: ratio.value,
    resolution: resolution.value,
    durationSeconds: durationSeconds.value,
  }
})

function updateSettings(patch: Partial<CanvasGenerationSettings>) {
  emit('settings', { ...effectiveSettings.value, ...patch })
}

function onModelChange(value: unknown) {
  if (typeof value !== 'string' || !value) return
  const nextModel = models.value.find(item => item.id === value) ?? null
  if (props.kind === 'text') {
    emit('settings', { modelId: value })
    return
  }
  const nextRatios = getModelRatios(nextModel)
  const nextRatio = nextRatios.includes(ratio.value) ? ratio.value : (nextRatios[0] ?? '16:9')
  if (props.kind === 'image-generation') {
    const nextTiers = getModelTiers(nextModel)
    const nextTier = nextTiers.includes(tier.value) ? tier.value : (nextTiers[0] ?? '1k')
    emit('settings', { modelId: value, ratio: nextRatio, tier: nextTier })
    return
  }
  const nextResolutions = getModelResolutions(nextModel)
  const nextResolution = nextResolutions.includes(resolution.value)
    ? resolution.value
    : (nextResolutions[0] ?? '720p')
  const nextDurations = getModelDurations(nextModel)
  const nextDuration = nextDurations.includes(durationSeconds.value)
    ? durationSeconds.value
    : (nextDurations[0] ?? 5)
  emit('settings', {
    modelId: value,
    ratio: nextRatio,
    resolution: nextResolution,
    durationSeconds: nextDuration,
  })
}

function onRatioChange(value: unknown) {
  if (typeof value === 'string' && value) updateSettings({ ratio: value })
}

function onTierChange(value: unknown) {
  if (typeof value === 'string' && TIER_ORDER.includes(value as CanvasImageTier)) {
    updateSettings({ tier: value as CanvasImageTier })
  }
}

function onResolutionChange(value: unknown) {
  if (typeof value === 'string' && value) updateSettings({ resolution: value })
}

function onDurationChange(value: unknown) {
  const num = Number(value)
  if (Number.isInteger(num) && num >= 1 && num <= 60) {
    updateSettings({ durationSeconds: num })
  }
}

function expandPrompt() {
  expandedPrompt.value = prompt.value
  expandedOrder.value = props.references.map(node => node.id)
  expanded.value = true
}

function applyPrompt() {
  prompt.value = expandedPrompt.value
  const kept = new Set(expandedOrder.value)
  const currentOrder = props.references.map(node => node.id)
  for (const id of currentOrder) {
    if (!kept.has(id)) emit('removeReference', id)
  }
  if (currentOrder.filter(id => kept.has(id)).some((id, index) => id !== expandedOrder.value[index])) {
    emit('reorderReferences', expandedOrder.value)
  }
  expanded.value = false
}
</script>

<template>
  <section class="canvas-generation-panel nodrag nopan nowheel" aria-label="生成设置" @pointerdown.stop @mousedown.stop @keydown.stop @click.stop @contextmenu.prevent>
    <CanvasNodeReferences v-if="references.length" :nodes="references" @remove="emit('removeReference', $event)" @reorder="emit('reorderReferences', $event)" />
    <CanvasPromptInput v-if="!expanded" v-model="prompt" :references="references" />
    <div class="canvas-generation-controls">
      <ImageModelPicker
        v-if="kind === 'image-generation'"
        v-model:open="modelOpen"
        :model-value="selectedModelId"
        :models="models"
        :tier="tier"
        :disabled="!models.length"
        :trigger-data-popup="modelTriggerKey"
        :placeholder="catalog.loading.value ? '加载模型…' : '选择图片模型'"
        @update:model-value="onModelChange"
      />
      <VideoModelPicker
        v-else-if="kind === 'video-generation'"
        :model-value="selectedModelId"
        :models="models"
        :clip-duration="durationSeconds"
        :project-ratio="ratio"
        :reference-count="imageReferenceCount"
        :prompt-length="prompt.length"
        :disabled="!models.length"
        :placeholder="catalog.loading.value ? '加载模型…' : '选择视频模型'"
        @update:model-value="onModelChange"
      />
      <SelectRoot v-else v-model:open="modelOpen" :model-value="selectedModelId" :disabled="!models.length" @update:model-value="onModelChange">
        <SelectTrigger :data-canvas-popup="modelTriggerKey" class="canvas-generation-trigger canvas-model-select" aria-label="模型">
          <Sparkles :size="16" aria-hidden="true" />
          <SelectValue class="canvas-model-value" :placeholder="catalog.loading.value ? '加载模型…' : '暂无可用模型'" />
          <ChevronDown class="canvas-generation-chevron" :size="14" aria-hidden="true" />
        </SelectTrigger>
        <SelectPortal>
          <SelectContent class="ui-popover canvas-model-popover" position="popper" side="top" align="start" :side-offset="8" :collision-padding="12">
            <SelectViewport>
              <SelectItem v-for="model in models" :key="model.id" class="ui-select-item canvas-model-option" :value="model.id">
                <SelectItemText>{{ model.displayName }}</SelectItemText>
                <SelectItemIndicator><Check :size="15" aria-hidden="true" /></SelectItemIndicator>
              </SelectItem>
            </SelectViewport>
          </SelectContent>
        </SelectPortal>
      </SelectRoot>
      <ImageParamsPopover
        v-if="kind === 'image-generation'"
        v-model:open="parametersOpen"
        :model="selectedModel"
        :tier="tier"
        :ratio="ratio"
        :show-default-ratio-hint="false"
        :trigger-data-popup="parametersTriggerKey"
        align="start"
        @update:tier="onTierChange"
        @update:ratio="onRatioChange"
      />
      <PopoverRoot v-else-if="kind === 'video-generation'" v-model:open="parametersOpen">
        <PopoverTrigger :data-canvas-popup="parametersTriggerKey" class="canvas-generation-trigger canvas-parameters" aria-label="生成参数">
          <RectangleHorizontal :size="16" aria-hidden="true" />
          <span>{{ parameters }}</span>
          <ChevronDown class="canvas-generation-chevron" :size="14" aria-hidden="true" />
        </PopoverTrigger>
        <PopoverPortal>
          <PopoverContent class="ui-popover canvas-parameter-popover" side="top" align="start" :side-offset="8" :collision-padding="12">
            <div class="canvas-parameter-section">
              <p>比例</p>
              <RadioGroupRoot class="canvas-parameter-options canvas-ratio-options" aria-label="比例" :model-value="ratio" @update:model-value="onRatioChange">
                <RadioGroupItem v-for="option in ratios" :key="option.value" class="canvas-parameter-option canvas-ratio-option" :value="option.value">
                  <span class="canvas-ratio-icon" aria-hidden="true"><span :style="{ aspectRatio: option.shape }" /></span>
                  {{ option.value }}
                </RadioGroupItem>
              </RadioGroupRoot>
            </div>
            <div class="canvas-parameter-section">
              <p>分辨率</p>
              <RadioGroupRoot
                class="canvas-parameter-options"
                :class="{ 'is-single': videoResolutions.length === 1 }"
                aria-label="分辨率"
                :model-value="resolution"
                @update:model-value="onResolutionChange"
              >
                <RadioGroupItem v-for="option in videoResolutions" :key="option.value" class="canvas-parameter-option" :value="option.value">{{ option.label }}</RadioGroupItem>
              </RadioGroupRoot>
            </div>
            <div class="canvas-parameter-section">
              <p>时长</p>
              <RadioGroupRoot class="canvas-parameter-options canvas-duration-options" aria-label="时长" :model-value="String(durationSeconds)" @update:model-value="onDurationChange">
                <RadioGroupItem v-for="sec in videoDurations" :key="sec" class="canvas-parameter-option" :value="String(sec)">{{ sec }} 秒</RadioGroupItem>
              </RadioGroupRoot>
            </div>
          </PopoverContent>
        </PopoverPortal>
      </PopoverRoot>
      <button type="button" class="canvas-expand" title="展开提示词" aria-label="展开提示词" @click="expandPrompt"><Maximize2 :size="15" /></button>
      <span v-if="kind !== 'text'" class="canvas-credits"><Coins :size="14" />{{ estimatedCreditsText }}</span>
      <button
        type="button"
        class="canvas-submit"
        :title="generating ? '正在生成' : '开始生成'"
        :aria-label="generating ? '正在生成' : '开始生成'"
        :disabled="!hasInput || generating"
        @click="emit('generate', effectiveSettings)"
      >
        <Loader2 v-if="generating" :size="16" class="ui-spin" />
        <ArrowUp v-else :size="17" />
      </button>
    </div>
  </section>
  <UiDialog v-model:open="expanded" title="提示词" size="editor">
    <div v-if="expandedReferences.length" class="canvas-expanded-references">
      <CanvasNodeReferences :nodes="expandedReferences" @remove="expandedOrder = expandedOrder.filter(id => id !== $event)" @reorder="expandedOrder = $event" />
    </div>
    <CanvasPromptInput v-if="expanded" v-model="expandedPrompt" :references="expandedReferences" expanded />
    <template #footer>
      <UiButton variant="ghost" @click="expanded = false">取消</UiButton>
      <UiButton variant="primary" @click="applyPrompt">应用</UiButton>
    </template>
  </UiDialog>
</template>

<style scoped>
.canvas-expanded-references { flex-shrink: 0; max-height: 22dvh; overflow-y: auto; }
.canvas-generation-panel { width: 100%; padding: 12px 14px 10px; border: 1px solid var(--border-control); border-radius: 8px; background: var(--color-surface); box-shadow: 0 8px 22px rgb(0 0 0 / 28%); cursor: default; }
.canvas-generation-panel:focus-within { border-color: var(--color-gold); }
.canvas-generation-controls { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; padding-top: 8px; border-top: 1px solid var(--border-subtle); }
.canvas-generation-controls > :is(.canvas-generation-trigger, .canvas-expand, .canvas-submit) { color: var(--color-muted); font-size: var(--font-size-body); cursor: pointer; }
.canvas-generation-controls :deep(.imp-trigger),
.canvas-generation-controls :deep(.ip-trigger),
.canvas-generation-controls :deep(.vmp-trigger) { height: 36px; border-radius: 6px; background: var(--color-elevated); }
.canvas-generation-controls :deep(.imp-trigger),
.canvas-generation-controls :deep(.vmp-trigger) { max-width: 210px; }
.canvas-generation-trigger { display: inline-flex; align-items: center; gap: 7px; min-height: 36px; padding: 0 9px; border: 1px solid transparent; border-radius: 6px; white-space: nowrap; }
.canvas-generation-trigger svg { flex: none; }
.canvas-model-select { width: 154px; border-color: var(--border-control); background: var(--color-elevated); }
.canvas-model-value { flex: 1; min-width: 0; overflow: hidden; text-align: start; text-overflow: ellipsis; }
.canvas-generation-trigger:is(:hover, [data-state='open']), .canvas-expand:hover { color: var(--color-gold-soft); background: var(--gold-tint); }
.canvas-generation-trigger[data-state='open'] { border-color: var(--color-gold); }
.canvas-generation-trigger[data-state='open'] .canvas-generation-chevron { rotate: 180deg; }
:global(.ui-popover.canvas-model-popover) { z-index: 100; width: 240px; max-width: var(--reka-select-content-available-width); max-height: var(--reka-select-content-available-height); overflow: auto; cursor: default; }
:global(.ui-popover.canvas-parameter-popover) { z-index: 100; width: 304px; max-width: var(--reka-popover-content-available-width); max-height: var(--reka-popover-content-available-height); overflow: auto; padding: 12px; cursor: default; }
.canvas-model-option { min-height: 36px; padding-right: 10px; }
.canvas-parameter-section + .canvas-parameter-section { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border-subtle); }
.canvas-parameter-section p { margin: 0 0 6px; color: var(--color-muted); font-size: var(--font-size-caption); }
.canvas-parameter-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
.canvas-parameter-options.is-single { grid-template-columns: minmax(0, 1fr); }
.canvas-ratio-options { grid-template-columns: repeat(auto-fit, minmax(44px, 1fr)); }
.canvas-duration-options { grid-template-columns: repeat(auto-fit, minmax(56px, 1fr)); }
.canvas-parameter-option { display: grid; place-items: center; gap: 3px; min-height: 34px; padding: 4px; border: 1px solid var(--border-control); border-radius: 6px; background: var(--color-surface); color: var(--color-text); font-size: var(--font-size-caption); cursor: pointer; }
.canvas-parameter-option:hover { background: var(--surface-hover); }
.canvas-parameter-option[data-state='checked'] { border-color: var(--color-gold); background: var(--gold-tint); color: var(--color-gold-soft); }
.canvas-ratio-option { min-height: 48px; }
.canvas-ratio-icon { display: grid; place-items: center; width: 24px; height: 18px; }
.canvas-ratio-icon span { height: 13px; border: 1px solid currentColor; border-radius: 2px; }
.canvas-generation-controls :is(.canvas-expand, .canvas-submit) { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 6px; }
.canvas-generation-controls .canvas-expand { margin-left: auto; }
.canvas-credits { display: inline-flex; align-items: center; gap: 4px; color: var(--color-muted); font-size: var(--font-size-caption); white-space: nowrap; }
.canvas-generation-controls .canvas-submit { border-radius: 50%; background: var(--color-gold); color: var(--color-canvas); }
.canvas-generation-controls .canvas-submit:disabled { opacity: .42; cursor: default; }
@media (max-width: 520px) {
  .canvas-model-select { width: 128px; }
}
</style>
