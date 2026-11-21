<script setup lang="ts">
import { computed, ref } from 'vue'
import { Copy, Download, Expand, FolderPlus, History, ImageUp, ListMusic, RefreshCw, Scissors, Gauge } from 'lucide-vue-next'
import { DropdownMenuContent, DropdownMenuItem, DropdownMenuPortal, DropdownMenuRoot, DropdownMenuTrigger } from 'reka-ui'
import ImagePreview from '@/components/ui/ImagePreview.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import { useUiStore } from '@/stores/ui'
import type { CanvasAsset, CanvasMedia } from '../canvas-model'
import { useCanvasPopup } from '../useCanvasPopup'

const props = defineProps<{
  kind: CanvasAsset['kind']
  media?: CanvasMedia
  history?: CanvasMedia[]
  text?: string
}>()
const emit = defineEmits<{ replace: []; cover: []; preview: []; collect: []; restore: [media: CanvasMedia]; audioEdit: [mode: 'trim' | 'clip' | 'speed']; textEdit: [] }>()
const ui = useUiStore()
const { open: videoHistoryOpen, triggerKey: videoHistoryTriggerKey } = useCanvasPopup()
const imageHistoryOpen = ref(false)
const selectedImage = ref<CanvasMedia>()
const historyImages = computed(() => [...(props.history ?? [])].reverse().map(({ url, name }) => ({ src: url, title: name })))

function showImageHistory() {
  selectedImage.value = props.media ?? props.history?.at(-1)
  imageHistoryOpen.value = true
}

function restoreImage() {
  if (selectedImage.value) emit('restore', selectedImage.value)
  imageHistoryOpen.value = false
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    ui.notify('已复制文本')
  } catch {
    ui.notify('无法访问剪贴板', 'error')
  }
}

function downloadText(text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = '画布文本.md'
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
</script>

<template>
    <div class="canvas-media-toolbar nodrag nopan" role="group" aria-label="节点工具栏" @pointerdown.stop @mousedown.stop @keydown.stop @click.stop>
      <button v-if="media || text?.trim()" type="button" @click="emit('collect')"><FolderPlus :size="15" />添加到素材库</button>
      <button v-if="text?.trim()" type="button" @click="copyText(text)"><Copy :size="15" />复制文本</button>
      <button v-if="media && kind === 'image'" type="button" @click="emit('cover')"><ImageUp :size="15" />设为画布封面</button>
      <button v-if="kind === 'image' && history?.length" type="button" @click="showImageHistory"><History :size="15" />历史结果 · {{ history.length }}</button>
      <DropdownMenuRoot v-if="kind === 'video' && history?.length" v-model:open="videoHistoryOpen">
        <DropdownMenuTrigger :data-canvas-popup="videoHistoryTriggerKey" type="button"><History :size="15" />历史结果 · {{ history.length }}</DropdownMenuTrigger>
        <DropdownMenuPortal>
          <DropdownMenuContent class="canvas-history-menu" :side-offset="6">
            <DropdownMenuItem v-for="(entry, index) in [...history].reverse()" :key="index" class="canvas-history-item" @select="emit('restore', entry)">
              <video :src="entry.url + '#t=0.05'" muted playsinline preload="metadata" aria-hidden="true" />
              <span>{{ entry.name }}</span><span v-if="media === entry">当前</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenuPortal>
      </DropdownMenuRoot>
      <button v-if="media && kind === 'audio'" type="button" @click="emit('audioEdit', 'trim')"><Scissors :size="15" />裁剪音频</button>
      <button v-if="media && kind === 'audio'" type="button" @click="emit('audioEdit', 'clip')"><ListMusic :size="15" />提取音频片段</button>
      <button v-if="media && kind === 'audio'" type="button" @click="emit('audioEdit', 'speed')"><Gauge :size="15" />倍速</button>
      <button v-if="media" type="button" @click="emit('replace')"><RefreshCw :size="15" />替换{{ kind === 'image' ? '图片' : kind === 'video' ? '视频' : '音频' }}</button>
      <a v-if="media" :href="media.url" :download="media.name" aria-label="下载" title="下载"><Download :size="16" /></a>
      <button v-else-if="text?.trim()" type="button" title="下载文本" aria-label="下载文本" @click="downloadText(text)"><Download :size="16" /></button>
      <button v-if="kind === 'text'" type="button" title="展开文本" aria-label="展开文本" @click="emit('textEdit')"><Expand :size="16" /></button>
      <button v-if="media && kind !== 'audio'" type="button" :aria-label="kind === 'image' ? '放大预览' : '预览视频'" :title="kind === 'image' ? '放大预览' : '预览视频'" @click="emit('preview')"><Expand :size="16" /></button>
    </div>
  <UiDialog v-if="kind === 'image'" v-model:open="imageHistoryOpen" title="图片历史结果" size="wide">
    <div class="canvas-image-history">
      <div class="canvas-image-history-list">
        <button v-for="(entry, index) in [...(history ?? [])].reverse()" :key="index" type="button" :aria-pressed="entry === selectedImage" @click="selectedImage = entry">
          <img :src="entry.url" alt="" />
          <span>{{ entry.name }}<small v-if="entry === media">当前</small></span>
        </button>
      </div>
      <ImagePreview v-if="selectedImage" :src="selectedImage.url" :title="selectedImage.name" :items="historyImages">
        <template #trigger>
          <button type="button" class="canvas-image-history-open" aria-label="放大历史图片">
            <img class="canvas-image-history-preview" :src="selectedImage.url" alt="" />
          </button>
        </template>
      </ImagePreview>
    </div>
    <template #footer>
      <UiButton variant="ghost" @click="imageHistoryOpen = false">取消</UiButton>
      <UiButton variant="primary" :disabled="!selectedImage" @click="restoreImage">使用此结果</UiButton>
    </template>
  </UiDialog>
</template>

<style scoped>
.canvas-media-toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; width: max-content; max-width: calc(100vw - 24px); gap: 3px; padding: 5px; border: 1px solid var(--border-control); border-radius: 8px; background: var(--color-surface); box-shadow: 0 6px 16px rgb(0 0 0 / 32%); cursor: default; }
.canvas-media-toolbar button, .canvas-media-toolbar a { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-width: 36px; min-height: 36px; padding: 4px 9px; border-radius: 6px; color: var(--color-text); font-size: var(--font-size-body); text-decoration: none; white-space: nowrap; cursor: pointer; }
.canvas-media-toolbar :is(button, a) svg { width: 17px; height: 17px; flex: none; color: var(--color-muted); }
.canvas-media-toolbar :is(button, a):hover { background: var(--gold-tint); color: var(--color-gold-soft); }
.canvas-media-toolbar :is(button, a):hover svg { color: inherit; }
:global(.canvas-history-menu) { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px; width: min(340px, calc(100vw - 24px)); max-height: min(320px, var(--reka-dropdown-menu-content-available-height, 320px)); overflow: auto; z-index: 100; padding: 5px; border: 1px solid var(--border-control); border-radius: 7px; background: var(--color-elevated); color: var(--color-text); }
:global(.canvas-history-item) { display: grid; gap: 4px; padding: 5px; border-radius: 5px; cursor: pointer; font-size: var(--font-size-caption); overflow-wrap: anywhere; }
:global(.canvas-history-item[data-highlighted]) { background: var(--gold-tint); outline: none; }
:global(.canvas-history-item video) { width: 100%; aspect-ratio: 16 / 9; object-fit: cover; border-radius: 3px; background: var(--color-canvas); }
.canvas-image-history { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); align-items: start; gap: 12px; }
.canvas-image-history-list { display: grid; align-content: start; gap: 5px; max-height: 48dvh; overflow: auto; }
.canvas-image-history-list button { display: flex; align-items: center; gap: 6px; padding: 5px; border: 1px solid var(--border-control); border-radius: 5px; text-align: left; font-size: var(--font-size-caption); overflow-wrap: anywhere; cursor: pointer; }
.canvas-image-history-list button[aria-pressed='true'] { border-color: var(--color-gold); color: var(--color-gold-soft); }
.canvas-image-history-list img { flex: none; width: 36px; height: 24px; object-fit: cover; border-radius: 3px; }
.canvas-image-history-list small { display: block; color: var(--color-muted); font-size: inherit; }
.canvas-image-history-open { display: block; width: 100%; cursor: zoom-in; }
.canvas-image-history-preview { width: 100%; max-height: 48dvh; object-fit: contain; border-radius: 5px; background: var(--color-canvas); }
@media (max-width: 480px) {
  .canvas-image-history { grid-template-columns: 1fr; }
  .canvas-image-history-list { max-height: 26dvh; }
  .canvas-image-history-preview { max-height: 30dvh; }
}
</style>
