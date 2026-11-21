<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowUp, Check, ChevronDown, Coins, Loader2, Maximize2, Sparkles } from 'lucide-vue-next'
import {
  SelectContent, SelectItem, SelectItemIndicator, SelectItemText, SelectPortal,
  SelectRoot, SelectTrigger, SelectValue, SelectViewport,
} from 'reka-ui'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import type { ModelCatalogItemOut } from '@/features/studio/api-types'
import ImageModelPicker from '@/features/studio/components/ImageModelPicker.vue'
import ImageParamsPopover from '@/features/studio/components/ImageParamsPopover.vue'
import VideoModelPicker from '@/features/studio/components/VideoModelPicker.vue'
import VideoParamsPopover from '@/features/studio/components/VideoParamsPopover.vue'
import { useModelCatalog } from '@/features/studio/composables/useModelCatalog'
import { useAuthStore } from '@/stores/auth'
import { outputKind, type CanvasGenerationSettings, type CanvasImageTier, type CanvasNode, type CanvasNodeKind } from '../canvas-model'
import { useCanvasPopup } from '../useCanvasPopup'
import CanvasPromptInput from './CanvasPromptInput.vue'
import CanvasNodeReferences from './CanvasNodeReferences.vue'

type VideoResolution = '480p' | '720p' | '1080p'

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
const hasInput = computed(
  () =>
    Boolean(prompt.value.trim())
    || props.references.some(node =>
      Boolean(node.data.text?.trim())
      || (props.kind === 'text' && outputKind(node.type) === 'image' && Boolean(node.data.media?.url)),
    ),
)
const imageReferenceCount = computed(() => props.references.filter(node => outputKind(node.type) === 'image').length)

const DEFAULT_RATIOS = ['16:9', '9:16', '1:1', '4:3', '3:4'] as const
const TIER_ORDER: readonly CanvasImageTier[] = ['web', '1k', '2k', '4k']

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

function getModelResolutions(model: ModelCatalogItemOut | null): VideoResolution[] {
  const raw = model?.capabilities?.resolutions
  if (Array.isArray(raw)) {
    const cleaned = raw
      .map(item => String(item).trim().toLowerCase())
      .filter((v): v is VideoResolution => v === '480p' || v === '720p' || v === '1080p')
    if (cleaned.length) return cleaned
  }
  return ['720p']
}

function getModelDurationRange(model: ModelCatalogItemOut | null): { min: number; max: number } {
  const caps = model?.capabilities ?? {}
  const min = Math.max(1, Math.round(Number(caps.minDuration) || 4))
  const max = Math.max(min, Math.round(Number(caps.maxDuration) || 15))
  return { min, max }
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

const ratio = computed(() => {
  const allowed = getModelRatios(selectedModel.value)
  const current = props.settings?.ratio
  if (current && allowed.includes(current)) return current
  const def = typeof selectedModel.value?.defaults?.ratio === 'string' ? selectedModel.value.defaults.ratio : ''
  if (def && allowed.includes(def)) return def
  return allowed[0] ?? '16:9'
})

const tier = computed<CanvasImageTier>(() => {
  const allowed = getModelTiers(selectedModel.value)
  const current = props.settings?.tier
  if (current && allowed.includes(current)) return current
  const def = typeof selectedModel.value?.defaults?.tier === 'string' ? selectedModel.value.defaults.tier : ''
  if (def && allowed.includes(def as CanvasImageTier)) return def as CanvasImageTier
  if (allowed.includes('1k')) return '1k'
  return allowed[0] ?? '1k'
})

const resolution = computed<VideoResolution>(() => {
  const allowed = getModelResolutions(selectedModel.value)
  const current = props.settings?.resolution?.toLowerCase()
  if (current && allowed.includes(current as VideoResolution)) return current as VideoResolution
  const def = typeof selectedModel.value?.defaults?.resolution === 'string'
    ? selectedModel.value.defaults.resolution.toLowerCase()
    : ''
  if (def && allowed.includes(def as VideoResolution)) return def as VideoResolution
  return allowed[0] ?? '720p'
})

const durationSeconds = computed(() => {
  const { min, max } = getModelDurationRange(selectedModel.value)
  const current = props.settings?.durationSeconds
  if (typeof current === 'number' && Number.isFinite(current)) {
    return Math.min(max, Math.max(min, Math.round(current)))
  }
  const def = Number(selectedModel.value?.defaults?.durationSeconds)
  if (Number.isFinite(def) && def >= min && def <= max) return Math.round(def)
  return Math.min(max, Math.max(min, 5))
})

const usageMultiplier = computed(() => {
  const parsed = Number(auth.user?.usageMultiplier)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1
})

const textPricingInfo = computed<{ summary: string; tooltip: string } | null>(() => {
  if (props.kind !== 'text') return null
  const tp = selectedModel.value?.textPrice
  if (!tp) return null
  const input = Number(tp.inputPricePerMillion) * usageMultiplier.value
  const output = Number(tp.outputPricePerMillion) * usageMultiplier.value
  const cached = Number(tp.cachedInputPricePerMillion) * usageMultiplier.value
  if (!Number.isFinite(input) || !Number.isFinite(output) || !Number.isFinite(cached)) return null
  const inStr = formatCreditsNum(input)
  const outStr = formatCreditsNum(output)
  const cacheStr = formatCreditsNum(cached)
  return {
    summary: `输入 ${inStr} · 输出 ${outStr} · 缓存 ${cacheStr} 积分/百万`,
    tooltip: `每百万 Token 计费：输入 ${inStr} 积分 · 输出 ${outStr} 积分 · 缓存命中 ${cacheStr} 积分`,
  }
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
  const { min, max } = getModelDurationRange(nextModel)
  const nextDuration = Math.min(max, Math.max(min, durationSeconds.value))
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
      <VideoParamsPopover
        v-else-if="kind === 'video-generation'"
        v-model:open="parametersOpen"
        :model="selectedModel"
        :resolution="resolution"
        :ratio="ratio"
        :duration="durationSeconds"
        :show-default-ratio-hint="false"
        :trigger-data-popup="parametersTriggerKey"
        align="start"
        @update:resolution="onResolutionChange"
        @update:ratio="onRatioChange"
        @update:duration="onDurationChange"
      />
      <span
        v-if="textPricingInfo"
        class="canvas-credits canvas-text-pricing"
        :title="textPricingInfo.tooltip"
      >
        <Coins :size="14" aria-hidden="true" />
        <span>{{ textPricingInfo.summary }}</span>
      </span>
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
.canvas-generation-controls :deep(.vmp-trigger),
.canvas-generation-controls :deep(.vp-trigger) { height: 36px; border-radius: 6px; background: var(--color-elevated); }
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
.canvas-model-option { min-height: 36px; padding-right: 10px; }
.canvas-generation-controls :is(.canvas-expand, .canvas-submit) { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 6px; }
.canvas-generation-controls .canvas-expand { margin-left: auto; }
.canvas-generation-controls .canvas-text-pricing { margin-left: auto; font-variant-numeric: tabular-nums; }
.canvas-generation-controls .canvas-text-pricing + .canvas-expand { margin-left: 0; }
.canvas-credits { display: inline-flex; align-items: center; gap: 4px; color: var(--color-muted); font-size: var(--font-size-caption); white-space: nowrap; }
.canvas-generation-controls .canvas-submit { border-radius: 50%; background: var(--color-gold); color: var(--color-canvas); }
.canvas-generation-controls .canvas-submit:disabled { opacity: .42; cursor: default; }
@media (max-width: 520px) {
  .canvas-model-select { width: 128px; }
}
</style>
