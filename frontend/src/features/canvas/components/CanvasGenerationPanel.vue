<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowUp, Check, ChevronDown, Coins, Maximize2, RectangleHorizontal, Sparkles } from 'lucide-vue-next'
import {
  PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger,
  RadioGroupItem, RadioGroupRoot,
  SelectContent, SelectItem, SelectItemIndicator, SelectItemText, SelectPortal,
  SelectRoot, SelectTrigger, SelectValue, SelectViewport,
} from 'reka-ui'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import type { CanvasGenerationSettings, CanvasNode, CanvasNodeKind } from '../canvas-model'
import { useCanvasPopup } from '../useCanvasPopup'
import CanvasPromptInput from './CanvasPromptInput.vue'
import CanvasNodeReferences from './CanvasNodeReferences.vue'

const props = defineProps<{ kind: CanvasNodeKind; references: CanvasNode[]; settings?: CanvasGenerationSettings; generating?: boolean }>()
const emit = defineEmits<{ settings: [value: CanvasGenerationSettings]; generate: []; removeReference: [id: string]; reorderReferences: [ids: string[]] }>()
const prompt = defineModel<string>({ default: '' })
const { open: modelOpen, triggerKey: modelTriggerKey } = useCanvasPopup()
const { open: parametersOpen, triggerKey: parametersTriggerKey } = useCanvasPopup()
const expanded = ref(false)
const expandedPrompt = ref('')
const expandedOrder = ref<string[]>([])
const expandedReferences = computed(() => {
  const nodes = new Map(props.references.map(node => [node.id, node]))
  return expandedOrder.value.flatMap(id => nodes.get(id) ?? [])
})
const hasPrompt = computed(() => !!prompt.value.trim())
const ratios = [
  { value: '16:9', shape: '16 / 9' },
  { value: '9:16', shape: '9 / 16' },
  { value: '1:1', shape: '1' },
  { value: '4:3', shape: '4 / 3' },
  { value: '3:4', shape: '3 / 4' },
]
const resolutions = computed(() => props.kind === 'image-generation' ? ['1K', '2K'] : ['720P', '1080P'])
const durations = ['15 秒', '30 秒']
const ratio = computed(() => props.settings?.ratio ?? '16:9')
const resolution = computed(() => props.settings?.resolution ?? resolutions.value[0])
const duration = computed(() => props.settings?.duration ?? durations[0])
const parameters = computed(() =>
  [ratio.value, resolution.value, props.kind === 'video-generation' ? duration.value : ''].filter(Boolean).join(' · '),
)
const models = computed(() => {
  if (props.kind === 'text') return ['DeepSeek', 'Qwen']
  if (props.kind === 'image-generation') return ['Qwen Image', 'FLUX']
  return ['Seedance', 'Kling']
})

function change(key: keyof CanvasGenerationSettings, value: unknown) {
  if (typeof value === 'string') emit('settings', { ...props.settings, [key]: value })
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
      <SelectRoot v-model:open="modelOpen" :model-value="settings?.model ?? models[0]" @update:model-value="change('model', $event)">
        <SelectTrigger :data-canvas-popup="modelTriggerKey" class="canvas-generation-trigger canvas-model-select" aria-label="模型">
          <Sparkles :size="16" aria-hidden="true" />
          <SelectValue class="canvas-model-value" />
          <ChevronDown class="canvas-generation-chevron" :size="14" aria-hidden="true" />
        </SelectTrigger>
        <SelectPortal>
          <SelectContent class="ui-popover canvas-model-popover" position="popper" side="top" align="start" :side-offset="8" :collision-padding="12">
            <SelectViewport>
              <SelectItem v-for="model in models" :key="model" class="ui-select-item canvas-model-option" :value="model">
                <SelectItemText>{{ model }}</SelectItemText>
                <SelectItemIndicator><Check :size="15" aria-hidden="true" /></SelectItemIndicator>
              </SelectItem>
            </SelectViewport>
          </SelectContent>
        </SelectPortal>
      </SelectRoot>
      <PopoverRoot v-if="kind !== 'text'" v-model:open="parametersOpen">
        <PopoverTrigger :data-canvas-popup="parametersTriggerKey" class="canvas-generation-trigger canvas-parameters" aria-label="生成参数">
          <RectangleHorizontal :size="16" aria-hidden="true" />
          <span>{{ parameters }}</span>
          <ChevronDown class="canvas-generation-chevron" :size="14" aria-hidden="true" />
        </PopoverTrigger>
        <PopoverPortal>
          <PopoverContent class="ui-popover canvas-parameter-popover" side="top" align="start" :side-offset="8" :collision-padding="12">
            <div class="canvas-parameter-section">
              <p>比例</p>
              <RadioGroupRoot class="canvas-parameter-options canvas-ratio-options" aria-label="比例" :model-value="ratio" @update:model-value="change('ratio', $event)">
                <RadioGroupItem v-for="option in ratios" :key="option.value" class="canvas-parameter-option canvas-ratio-option" :value="option.value">
                  <span class="canvas-ratio-icon" aria-hidden="true"><span :style="{ aspectRatio: option.shape }" /></span>
                  {{ option.value }}
                </RadioGroupItem>
              </RadioGroupRoot>
            </div>
            <div class="canvas-parameter-section">
              <p>分辨率</p>
              <RadioGroupRoot class="canvas-parameter-options" aria-label="分辨率" :model-value="resolution" @update:model-value="change('resolution', $event)">
                <RadioGroupItem v-for="option in resolutions" :key="option" class="canvas-parameter-option" :value="option">{{ option }}</RadioGroupItem>
              </RadioGroupRoot>
            </div>
            <div v-if="kind === 'video-generation'" class="canvas-parameter-section">
              <p>时长</p>
              <RadioGroupRoot class="canvas-parameter-options" aria-label="时长" :model-value="duration" @update:model-value="change('duration', $event)">
                <RadioGroupItem v-for="option in durations" :key="option" class="canvas-parameter-option" :value="option">{{ option }}</RadioGroupItem>
              </RadioGroupRoot>
            </div>
          </PopoverContent>
        </PopoverPortal>
      </PopoverRoot>
      <button type="button" class="canvas-expand" title="展开提示词" aria-label="展开提示词" @click="expandPrompt"><Maximize2 :size="15" /></button>
      <span v-if="kind !== 'text'" class="canvas-credits"><Coins :size="14" />积分待定</span>
      <button type="button" class="canvas-submit" title="模拟生成" aria-label="模拟生成" :disabled="!hasPrompt || generating" @click="$emit('generate')"><ArrowUp :size="17" /></button>
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
.canvas-generation-controls button { color: var(--color-muted); font-size: var(--font-size-body); cursor: pointer; }
.canvas-generation-trigger { display: inline-flex; align-items: center; gap: 7px; min-height: 36px; padding: 0 9px; border: 1px solid transparent; border-radius: 6px; white-space: nowrap; }
.canvas-generation-trigger svg { flex: none; }
.canvas-model-select { width: 154px; border-color: var(--border-control); background: var(--color-elevated); }
.canvas-model-value { flex: 1; min-width: 0; overflow: hidden; text-align: start; text-overflow: ellipsis; }
.canvas-generation-trigger:is(:hover, [data-state='open']), .canvas-expand:hover { color: var(--color-gold-soft); background: var(--gold-tint); }
.canvas-generation-trigger[data-state='open'] { border-color: var(--color-gold); }
.canvas-generation-trigger[data-state='open'] .canvas-generation-chevron { rotate: 180deg; }
:global(.ui-popover.canvas-model-popover) { z-index: 100; width: 194px; max-width: var(--reka-select-content-available-width); max-height: var(--reka-select-content-available-height); overflow: auto; cursor: default; }
:global(.ui-popover.canvas-parameter-popover) { z-index: 100; width: 304px; max-width: var(--reka-popover-content-available-width); max-height: var(--reka-popover-content-available-height); overflow: auto; padding: 12px; cursor: default; }
.canvas-model-option { min-height: 36px; padding-right: 10px; }
.canvas-parameter-section + .canvas-parameter-section { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border-subtle); }
.canvas-parameter-section p { margin: 0 0 6px; color: var(--color-muted); font-size: var(--font-size-caption); }
.canvas-parameter-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
.canvas-ratio-options { grid-template-columns: repeat(auto-fit, minmax(44px, 1fr)); }
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
