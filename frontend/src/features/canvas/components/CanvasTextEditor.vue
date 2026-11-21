<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { Bold, Code, Heading2, Italic, List, Quote } from 'lucide-vue-next'
import { ToggleGroupItem, ToggleGroupRoot } from 'reka-ui'
import UiIconButton from '@/components/ui/UiIconButton.vue'
import CanvasMarkdown from './CanvasMarkdown.vue'

const text = defineModel<string>({ required: true })
const source = ref<HTMLTextAreaElement>()
const mode = ref(window.matchMedia('(max-width: 640px)').matches ? 'edit' : 'split')
const modes = [
  { value: 'edit', label: '编辑' },
  { value: 'preview', label: '预览' },
  { value: 'split', label: '分栏' },
]
const formats = [
  { icon: Heading2, label: '标题', prefix: '## ', block: true },
  { icon: Bold, label: '粗体', prefix: '**' },
  { icon: Italic, label: '斜体', prefix: '*' },
  { icon: List, label: '列表', prefix: '- ', block: true },
  { icon: Quote, label: '引用', prefix: '> ', block: true },
  { icon: Code, label: '代码', prefix: '`' },
]

async function format({ prefix, block }: typeof formats[number]) {
  const input = source.value
  if (!input || mode.value === 'preview') return
  const { selectionStart, selectionEnd } = input
  const start = block && selectionStart > 0 ? text.value.lastIndexOf('\n', selectionStart - 1) + 1 : selectionStart
  const selection = text.value.slice(start, selectionEnd)
  const replacement = block ? selection.split('\n').map(line => prefix + line).join('\n') : prefix + selection + prefix
  text.value = text.value.slice(0, start) + replacement + text.value.slice(selectionEnd)
  await nextTick()
  input.focus()
  const from = block ? start + replacement.length : start + prefix.length
  input.setSelectionRange(from, block ? from : from + selection.length)
}
</script>

<template>
  <div class="canvas-text-editor nodrag nopan">
    <div class="canvas-text-editor-toolbar">
      <div class="canvas-text-formats" role="group" aria-label="文本格式">
        <UiIconButton v-for="item in formats" :key="item.label" :label="item.label" :disabled="mode === 'preview'"
          @mousedown.prevent @click="format(item)">
          <component :is="item.icon" :size="16" aria-hidden="true" />
        </UiIconButton>
      </div>
      <ToggleGroupRoot type="single" class="canvas-text-modes" aria-label="正文编辑视图" :model-value="mode"
        @update:model-value="typeof $event === 'string' && $event && (mode = $event)">
        <ToggleGroupItem v-for="item in modes" :key="item.value" :value="item.value">{{ item.label }}</ToggleGroupItem>
      </ToggleGroupRoot>
    </div>
    <div class="canvas-text-panes" :class="'is-' + mode">
      <textarea v-show="mode !== 'preview'" ref="source" v-model="text" aria-label="文本内容" spellcheck="false" />
      <div v-if="mode !== 'edit'" class="canvas-text-preview" role="region" aria-label="正文预览" tabindex="0">
        <CanvasMarkdown :value="text" variant="preview" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.canvas-text-editor { display: flex; flex: 1; flex-direction: column; gap: 10px; min-height: 0; }
.canvas-text-editor-toolbar { display: flex; flex: none; flex-wrap: wrap; justify-content: space-between; gap: 8px; }
.canvas-text-formats, .canvas-text-modes { display: flex; align-items: center; gap: 4px; }
.canvas-text-formats :deep(.ui-icon-button) { width: 32px; height: 32px; border-color: transparent; }
.canvas-text-modes { padding: 3px; border: 1px solid var(--border-control); border-radius: 7px; background: var(--color-canvas); }
.canvas-text-modes button { min-width: 52px; min-height: 28px; padding: 0 7px; border-radius: 4px; color: var(--color-muted); cursor: pointer; }
.canvas-text-modes button:is(:hover, [data-state='on']) { background: var(--gold-tint); color: var(--color-gold-soft); }
.canvas-text-panes { display: grid; flex: 1; grid-template-columns: minmax(0, 1fr); grid-auto-rows: minmax(0, 1fr); gap: 10px; min-height: 0; }
.canvas-text-panes.is-split { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.canvas-text-panes textarea, .canvas-text-preview { min-height: 0; overflow: auto; padding: 12px; border: 1px solid var(--border-control); border-radius: 7px; background: var(--color-canvas); }
.canvas-text-panes textarea { width: 100%; resize: none; font: inherit; line-height: 1.6; cursor: text; }
.canvas-text-panes :is(textarea, .canvas-text-preview):focus-visible { outline: 1px solid var(--color-gold); outline-offset: -1px; }
@media (max-width: 640px) {
  .canvas-text-panes.is-split { grid-template-columns: minmax(0, 1fr); grid-template-rows: repeat(2, minmax(0, 1fr)); }
}
</style>
