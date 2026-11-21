<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Handle, Position } from '@xyflow/vue'
import { AlertCircle, Check, CircleDashed, CircleDot, FolderOpen, Loader2, Pencil, Upload, X } from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import MediaPlayer from '@/components/ui/MediaPlayer.vue'
import VideoThumbnail from '@/components/ui/VideoThumbnail.vue'
import { useUiStore } from '@/stores/ui'
import { canvasNodeLabels, computeCanvasMediaBox, isGenerationNode, outputKind, parseCanvasRatio, type CanvasGenerationSettings, type CanvasMedia, type CanvasNode, type CanvasNodeData, type CanvasNodeKind } from '../canvas-model'
import { canvasNodeIcons } from '../canvas-node-icons'
import type { CanvasNodeGenerationState } from '../canvas-store'
import CanvasGenerationPanel from './CanvasGenerationPanel.vue'
import CanvasMarkdown from './CanvasMarkdown.vue'
import CanvasTextEditor from './CanvasTextEditor.vue'
import CanvasMediaToolbar from './CanvasMediaToolbar.vue'
import CanvasAudioEditor from './CanvasAudioEditor.vue'

const props = defineProps<{
  kind: CanvasNodeKind
  data: CanvasNodeData
  selected: boolean
  panelsVisible: boolean
  generationState?: CanvasNodeGenerationState
  uploading?: boolean
  connecting: boolean
  outputConnected: boolean
  references: CanvasNode[]
}>()
const emit = defineEmits<{
  edit: [value: Partial<CanvasNodeData>]
  replace: [file: File]
  generate: [settings: CanvasGenerationSettings]
  cover: [media: CanvasMedia]
  preview: [kind: 'image' | 'video', media: CanvasMedia]
  collect: [title: string]
  browse: []
  remove: []
  unlink: [id: string]
  clipAudio: [file: File]
}>()

const ui = useUiStore()
const titleInput = ref<HTMLInputElement>()
const fileInput = ref<HTMLInputElement>()
const intrinsicRatio = ref<number>()
const preferSettingsRatio = ref(false)
const confirmingDelete = ref(false)
const editingTitle = ref(false)
const titleDraft = ref('')
const editingText = ref(false)
const resultOpen = ref(false)
const audioEdit = ref<'trim' | 'clip' | 'speed'>()
const textDraft = ref('')
let originalText: string | undefined
const title = computed(() => props.data.title || canvasNodeLabels[props.kind])
const canGenerate = computed(() => props.kind === 'text' || isGenerationNode(props.kind))
const mediaKind = computed(() => outputKind(props.kind))
const isGenerating = computed(() => Boolean(props.generationState))
const generationLabel = computed(() => {
  const state = props.generationState
  if (!state) return ''
  if (state.progress > 0 && state.progress < 100) {
    return `${state.stepLabel} ${state.progress}%`
  }
  return state.stepLabel
})
const activeRatio = computed<number | null>(() => {
  if (props.kind === 'text' || mediaKind.value === 'audio') return null
  if (isGenerationNode(props.kind)) {
    const configured = parseCanvasRatio(props.data.settings?.ratio)
    if (!props.data.media) return configured ?? 16 / 9
    if (preferSettingsRatio.value && configured !== null) return configured
    return intrinsicRatio.value ?? configured ?? 16 / 9
  }
  if (!props.data.media) return null
  return intrinsicRatio.value ?? 16 / 9
})
const mediaBox = computed(() => (activeRatio.value !== null ? computeCanvasMediaBox(activeRatio.value) : null))
const mediaHeightStyle = computed(() => (mediaBox.value ? { height: `${mediaBox.value.height}px` } : undefined))
const placeholderRatioLabel = computed(() => {
  const raw = props.data.settings?.ratio
  if (raw === 'auto') return '自动比例'
  return raw || '16:9'
})
const nodeWidth = computed(() => {
  if (props.kind === 'text') return 320
  if (mediaBox.value) return mediaBox.value.width + 18
  return 280
})
const prompt = computed({
  get: () => props.data.prompt ?? '',
  set: value => emit('edit', { prompt: value }),
})

watch(() => props.selected, value => {
  if (!value) editingTitle.value = false
})
watch(() => props.data.media?.url, () => {
  intrinsicRatio.value = undefined
  preferSettingsRatio.value = false
})
watch(() => props.data.settings?.ratio, (next, prev) => {
  if (next !== prev) {
    preferSettingsRatio.value = parseCanvasRatio(next) !== null
  }
})

async function startRename() {
  titleDraft.value = title.value
  editingTitle.value = true
  await nextTick()
  titleInput.value?.select()
}

function rename() {
  if (!editingTitle.value) return
  if (titleDraft.value.trim()) emit('edit', { title: titleDraft.value.trim() })
  editingTitle.value = false
}

function renameKey(event: KeyboardEvent) {
  if (event.isComposing) return
  if (event.key === 'Enter') rename()
  if (event.key === 'Escape') editingTitle.value = false
}

function replaceFile(file?: File) {
  if (!file) return
  if (!file.type.startsWith(mediaKind.value + '/')) {
    ui.notify('文件类型与节点不符', 'error')
    return
  }
  emit('replace', file)
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  replaceFile(input.files?.[0])
  input.value = ''
}

function dropMedia(event: DragEvent) {
  const file = event.dataTransfer?.files[0]
  if (!file) return
  event.stopPropagation()
  event.preventDefault()
  replaceFile(file)
}

function onImageLoad(event: Event) {
  const image = event.currentTarget as HTMLImageElement
  if (image.naturalHeight && image.naturalWidth) intrinsicRatio.value = image.naturalWidth / image.naturalHeight
}

function editText() {
  originalText = props.data.text
  textDraft.value = originalText ?? ''
  editingText.value = true
}

function saveText() {
  if (textDraft.value !== (originalText ?? '')) {
    const newerText = props.data.text !== originalText ? props.data.text : undefined
    emit('edit', { text: textDraft.value, draft: props.data.draft ?? newerText })
  }
  editingText.value = false
}

function generate(effectiveSettings: CanvasGenerationSettings) {
  const hasInput = Boolean(prompt.value.trim()) || props.references.some(node => Boolean(node.data.text?.trim()))
  if (hasInput) emit('generate', effectiveSettings)
  else ui.notify('请输入提示词或连接包含正文的文本节点', 'error')
}

function preview(media: CanvasMedia) {
  if (mediaKind.value === 'video' || mediaKind.value === 'image') emit('preview', mediaKind.value, media)
}
</script>

<template>
  <article class="canvas-node" :class="{ 'is-selected': selected, 'is-connecting': connecting }" :style="{ width: nodeWidth + 'px' }" :aria-label="title">
    <div v-if="panelsVisible && (data.media || kind === 'text')" class="canvas-node-top">
      <CanvasMediaToolbar
        :kind="mediaKind"
        :media="data.media"
        :history="data.history"
        :text="data.text"
        @replace="fileInput?.click()"
        @cover="data.media && emit('cover', data.media)"
        @preview="data.media && preview(data.media)"
        @collect="emit('collect', title)"
        @restore="emit('edit', { media: $event })"
        @audio-edit="audioEdit = $event"
        @text-edit="editText"
      />
    </div>

    <header class="canvas-node-header">
      <component :is="canvasNodeIcons[kind]" :size="15" aria-hidden="true" />
      <input v-if="editingTitle" ref="titleInput" v-model="titleDraft" class="nodrag nopan" aria-label="节点名称" maxlength="60" @blur="rename" @keydown.stop="renameKey" />
      <h2 v-else :title="title" tabindex="0" @dblclick.stop="startRename" @keydown.enter.stop.prevent="startRename" @keydown.space.stop.prevent="startRename">{{ title }}</h2>
      <button type="button" class="canvas-node-close nodrag nopan" title="删除节点" aria-label="删除节点" @click.stop="confirmingDelete = true"><X :size="15" /></button>
    </header>

    <div class="canvas-node-card" @drop="kind !== 'text' && dropMedia($event)">
      <Handle v-if="canGenerate" type="target" :position="Position.Left" :class="{ 'is-linked': references.length }" aria-label="引用输入">
        <CircleDot v-if="references.length" :size="17" /><CircleDashed v-else :size="17" />
      </Handle>
      <Handle type="source" :position="Position.Right" :class="{ 'is-linked': outputConnected }" aria-label="引用输出">
        <CircleDot v-if="outputConnected" :size="17" /><CircleDashed v-else :size="17" />
      </Handle>

      <div v-if="kind === 'text'" class="canvas-node-copy" :class="{ 'has-text': data.text?.trim() || data.draft }">
        <div v-if="data.text?.trim()" class="canvas-node-markdown nodrag nowheel">
          <CanvasMarkdown :value="data.text" variant="node" />
        </div>
        <div v-if="data.draft" class="canvas-text-draft-actions nodrag nopan">
          <UiButton variant="secondary" size="sm" @click.stop="resultOpen = true">查看生成结果</UiButton>
        </div>
        <span v-if="isGenerating" class="canvas-text-status" role="status"><Loader2 :size="13" class="ui-spin" aria-hidden="true" />{{ generationLabel }}</span>
        <button type="button" class="canvas-edit-text nodrag nopan" title="编辑文本" aria-label="编辑文本" @click.stop="editText"><Pencil :size="14" />编辑</button>
      </div>
      <template v-else>
        <input ref="fileInput" type="file" :accept="mediaKind + '/*'" :aria-label="'上传' + title" hidden @change="onFileChange" />
        <template v-if="data.media">
          <img v-if="mediaKind === 'image'" :key="data.media.url" class="canvas-node-image" :style="mediaHeightStyle" :src="data.media.url" :alt="data.media.name" draggable="false" @load="onImageLoad" />
          <VideoThumbnail v-else-if="mediaKind === 'video'" :key="data.media.url" class="canvas-node-video nodrag nopan"
            :style="mediaHeightStyle"
            :src="data.media.url" :label="'预览视频 ' + data.media.name"
            @ratio="intrinsicRatio = $event" @click.stop="preview(data.media)" />
          <MediaPlayer v-else-if="mediaKind === 'audio'" :key="data.media.url" kind="audio" :src="data.media.url" :label="data.media.name" />
        </template>
        <div v-else-if="!canGenerate" class="canvas-node-empty canvas-upload">
          <component :is="canvasNodeIcons[kind]" :size="28" aria-hidden="true" />
          <div class="canvas-upload-actions">
            <button class="nodrag nopan" type="button" @click.stop="fileInput?.click()"><Upload :size="14" />本地上传</button>
            <button class="nodrag nopan" type="button" @click.stop="emit('browse')"><FolderOpen :size="14" />从素材库选择</button>
          </div>
        </div>
        <div v-else class="canvas-node-empty is-generation" :style="mediaHeightStyle">
          <component :is="canvasNodeIcons[kind]" :size="36" aria-hidden="true" />
          <span class="canvas-empty-ratio">{{ placeholderRatioLabel }}</span>
        </div>
        <div v-if="isGenerating || uploading" class="canvas-node-progress" role="status">
          <Loader2 :size="20" class="ui-spin" aria-hidden="true" />
          <span>{{ uploading ? '正在上传…' : generationLabel }}</span>
        </div>
      </template>

      <div v-if="data.lastError && !isGenerating" class="canvas-node-error nodrag nopan" :title="data.lastError">
        <AlertCircle :size="14" aria-hidden="true" />
        <span>{{ data.lastError }}</span>
        <button type="button" aria-label="清除错误提示" @click.stop="emit('edit', { lastError: undefined })"><X :size="13" /></button>
      </div>
    </div>

    <div v-if="panelsVisible && canGenerate" class="canvas-node-panels">
      <CanvasGenerationPanel v-model="prompt" :kind="kind" :references="references" :settings="data.settings" :generating="isGenerating || (kind === 'text' && !!data.draft)" @settings="emit('edit', { settings: $event })" @generate="generate($event)"
        @remove-reference="emit('unlink', $event)" @reorder-references="emit('edit', { referenceOrder: $event })" />
    </div>

    <UiDialog v-model:open="editingText" title="编辑文本" size="editor">
      <CanvasTextEditor v-model="textDraft" />
      <template #footer>
        <UiButton variant="ghost" @click="editingText = false">取消</UiButton>
        <UiButton variant="primary" @click="saveText">保存</UiButton>
      </template>
    </UiDialog>
    <UiDialog v-model:open="resultOpen" title="生成结果" description="生成期间正文已修改。可保留当前正文，或用这份结果替换。" size="editor">
      <CanvasMarkdown v-if="data.draft" class="canvas-result-preview" :value="data.draft" />
      <template #footer>
        <UiButton variant="ghost" @click="resultOpen = false; emit('edit', { draft: undefined })">保留正文</UiButton>
        <UiButton variant="primary" @click="resultOpen = false; emit('edit', { text: data.draft, draft: undefined })"><template #leading><Check :size="14" /></template>替换正文</UiButton>
      </template>
    </UiDialog>
    <UiDialog v-model:open="confirmingDelete" title="删除节点" :description="'删除「' + title + '」及其连线？'">
      <template #footer>
        <UiButton variant="ghost" @click="confirmingDelete = false">取消</UiButton>
        <UiButton variant="primary" @click="confirmingDelete = false; emit('remove')">删除</UiButton>
      </template>
    </UiDialog>
    <CanvasAudioEditor v-if="audioEdit && data.media" :mode="audioEdit" :media="data.media" @close="audioEdit = undefined"
      @replace="audioEdit === 'clip' ? emit('clipAudio', $event) : emit('replace', $event)" />
  </article>
</template>

<style scoped>
.canvas-node { position: relative; transition: width .18s ease; }
.canvas-node-header { display: flex; align-items: center; gap: 7px; height: 28px; padding: 0 3px 0 5px; margin-bottom: 3px; }
.canvas-node-header > svg { flex: none; color: var(--color-muted); }
.canvas-node-header h2 { flex: 1; min-width: 0; margin: 0; overflow: hidden; font-size: var(--font-size-body); font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.canvas-node-header input { flex: 1; min-width: 0; padding: 2px 4px; background: var(--color-elevated); border-radius: 4px; font-size: var(--font-size-body); cursor: text; }
.canvas-node-close { display: grid; place-items: center; width: 24px; height: 24px; flex: none; border-radius: 4px; color: var(--color-muted); opacity: 0; pointer-events: none; cursor: pointer; }
.canvas-node:is(:hover, :focus-within) .canvas-node-close { opacity: 1; pointer-events: auto; }
.canvas-node-close:is(:hover, :focus-visible), .canvas-edit-text:is(:hover, :focus-visible) { background: var(--gold-tint); color: var(--color-gold-soft); }
.canvas-node-card { position: relative; padding: 8px; border: 1px solid var(--border-subtle); border-radius: 8px; background: var(--color-surface); }
.canvas-node.is-selected .canvas-node-card { border-color: var(--color-gold); box-shadow: 0 0 0 1px var(--gold-tint); }
.canvas-node-copy { display: grid; min-height: 156px; place-items: center; }
.canvas-node-copy.has-text { display: flex; flex-direction: column; gap: 6px; }
.canvas-node-markdown { max-height: 240px; padding: 4px; overflow: auto; cursor: text; user-select: text; }
.canvas-edit-text { display: inline-flex; align-items: center; gap: 6px; padding: 5px 7px; border-radius: 5px; color: var(--color-muted); cursor: pointer; font-size: var(--font-size-caption); }
.has-text .canvas-edit-text { align-self: flex-end; margin-top: auto; }
.canvas-node-image { display: block; width: 100%; height: 240px; border-radius: 5px; background: var(--color-canvas); object-fit: contain; transition: height .18s ease; }
.canvas-node-video { height: 240px; transition: height .18s ease; }
.canvas-node-empty { display: grid; place-items: center; width: 100%; height: 126px; color: var(--color-muted); border-radius: 5px; }
.canvas-node-empty.is-generation { align-content: center; gap: 8px; background: var(--color-canvas); transition: height .18s ease; }
.canvas-empty-ratio { padding: 2px 8px; border: 1px solid var(--border-subtle); border-radius: 999px; font-size: var(--font-size-caption); font-variant-numeric: tabular-nums; color: var(--color-muted); }
.canvas-upload { align-content: center; gap: 10px; }
.canvas-upload-actions { display: flex; flex-wrap: wrap; justify-content: center; gap: 6px; }
.canvas-upload-actions button { display: inline-flex; align-items: center; gap: 5px; padding: 5px 7px; border: 1px solid var(--border-control); border-radius: 5px; font-size: var(--font-size-caption); cursor: pointer; }
.canvas-upload-actions button:is(:hover, :focus-visible) { background: var(--gold-tint); color: var(--color-gold-soft); }
.canvas-node :deep(.vue-flow__handle) { display: grid; place-items: center; width: 24px; height: 24px; border: 0; border-radius: 50%; background: transparent; color: var(--color-muted); opacity: 0; }
.canvas-node :deep(.vue-flow__handle-left) { left: -13px; }
.canvas-node :deep(.vue-flow__handle-right) { right: -13px; }
.canvas-node :deep(.vue-flow__handle svg) { pointer-events: none; }
.canvas-node:is(:hover, :focus-within, .is-connecting) :deep(.vue-flow__handle), .canvas-node :deep(.vue-flow__handle.is-linked) { opacity: 1; }
.canvas-node :deep(.vue-flow__handle:hover), .canvas-node.is-selected :deep(.vue-flow__handle.is-linked) { color: var(--color-gold-soft); }
.canvas-node-top, .canvas-node-panels { position: absolute; z-index: 1; left: 50%; transform: translateX(-50%); }
.canvas-node-top { bottom: calc(100% + 9px); }
.canvas-node-panels { top: calc(100% + 12px); width: min(660px, calc(100vw - 28px)); }
.canvas-text-draft-actions { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; margin-top: auto; }
.canvas-text-status { display: inline-flex; align-items: center; gap: 5px; color: var(--color-gold-soft); font-size: var(--font-size-caption); }
.canvas-node-progress { position: absolute; inset: 8px; z-index: 2; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 12px; border-radius: 5px; background: rgb(11 11 14 / 76%); backdrop-filter: blur(2px); color: var(--color-gold-soft); font-size: var(--font-size-caption); text-align: center; }
.canvas-node-error { display: flex; align-items: center; gap: 6px; margin-top: 8px; padding: 6px 8px; border: 1px solid rgb(239 68 68 / 32%); border-radius: 5px; background: rgb(239 68 68 / 10%); color: #fca5a5; font-size: var(--font-size-caption); }
.canvas-node-error > svg { flex: none; }
.canvas-node-error > span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.canvas-node-error > button { flex: none; display: grid; place-items: center; width: 20px; height: 20px; border-radius: 4px; color: inherit; cursor: pointer; }
.canvas-node-error > button:hover { background: rgb(239 68 68 / 20%); }
.canvas-result-preview { overflow: auto; }
@media (hover: none) {
  .canvas-node.is-selected .canvas-node-close { opacity: 1; pointer-events: auto; }
  .canvas-node.is-selected :deep(.vue-flow__handle) { opacity: 1; }
}
</style>
