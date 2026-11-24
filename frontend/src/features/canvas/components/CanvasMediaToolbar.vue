<script setup lang="ts">
import { computed, ref } from 'vue'
import { Copy, Download, Expand, FolderPlus, Gauge, History, ImageUp, ListMusic, RefreshCw, Scissors } from 'lucide-vue-next'
import MediaHistoryDialog from '@/components/business/MediaHistoryDialog.vue'
import type { MediaHistoryItem } from '@/components/business/MediaHistoryDialog.vue'
import { useModelCatalog } from '@/features/studio/composables/useModelCatalog'
import { useUiStore } from '@/stores/ui'
import type { CanvasAsset, CanvasMedia } from '../canvas-model'

const props = defineProps<{
  kind: CanvasAsset['kind']
  media?: CanvasMedia
  history?: CanvasMedia[]
  text?: string
}>()
const emit = defineEmits<{ replace: []; cover: []; preview: []; collect: []; restore: [media: CanvasMedia]; audioEdit: [mode: 'trim' | 'clip' | 'speed']; textEdit: [] }>()
const ui = useUiStore()
const { imageModels, videoModels } = useModelCatalog()
const historyOpen = ref(false)

const historyKind = computed<'image' | 'video' | null>(() =>
  props.kind === 'image' || props.kind === 'video' ? props.kind : null,
)

const modelNames = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const model of imageModels.value) map[model.id] = model.displayName
  for (const model of videoModels.value) map[model.id] = model.displayName
  return map
})

const historyEntries = computed<Array<{ item: MediaHistoryItem; raw: CanvasMedia }>>(() =>
  (props.history ?? []).map((entry, index) => ({
    raw: entry,
    item: {
      id: entry.jobId ? `${entry.jobId}-${index}` : `${entry.url}-${index}`,
      url: entry.url,
      key: entry.key ?? null,
      name: entry.name,
      source: entry.jobId || entry.modelId ? 'ai' : 'upload',
      jobId: entry.jobId ?? null,
      modelId: entry.modelId ?? null,
      createdAt: entry.createdAt ?? null,
    },
  })),
)

const historyItems = computed<MediaHistoryItem[]>(() => historyEntries.value.map((entry) => entry.item))

function handleSelectHistory(item: MediaHistoryItem) {
  const matched = historyEntries.value.find((entry) => entry.item.id === item.id)
  if (matched) emit('restore', matched.raw)
  historyOpen.value = false
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
    <button v-if="historyKind && historyItems.length" type="button" @click="historyOpen = true">
      <History :size="15" />历史结果 · {{ historyItems.length }}
    </button>
    <button v-if="media && kind === 'audio'" type="button" @click="emit('audioEdit', 'trim')"><Scissors :size="15" />裁剪音频</button>
    <button v-if="media && kind === 'audio'" type="button" @click="emit('audioEdit', 'clip')"><ListMusic :size="15" />提取音频片段</button>
    <button v-if="media && kind === 'audio'" type="button" @click="emit('audioEdit', 'speed')"><Gauge :size="15" />倍速</button>
    <button v-if="media" type="button" @click="emit('replace')"><RefreshCw :size="15" />替换{{ kind === 'image' ? '图片' : kind === 'video' ? '视频' : '音频' }}</button>
    <a v-if="media" :href="media.url" :download="media.name" aria-label="下载" title="下载"><Download :size="16" /></a>
    <button v-else-if="text?.trim()" type="button" title="下载文本" aria-label="下载文本" @click="downloadText(text)"><Download :size="16" /></button>
    <button v-if="kind === 'text'" type="button" title="展开文本" aria-label="展开文本" @click="emit('textEdit')"><Expand :size="16" /></button>
    <button v-if="media && kind !== 'audio'" type="button" :aria-label="kind === 'image' ? '放大预览' : '预览视频'" :title="kind === 'image' ? '放大预览' : '预览视频'" @click="emit('preview')"><Expand :size="16" /></button>
  </div>
  <MediaHistoryDialog
    v-if="historyKind"
    v-model:open="historyOpen"
    :kind="historyKind"
    :title="historyKind === 'image' ? '图片历史结果' : '视频历史结果'"
    :items="historyItems"
    :current-url="media?.url"
    :model-names="modelNames"
    @select="handleSelectHistory"
  />
</template>

<style scoped>
.canvas-media-toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; width: max-content; max-width: calc(100vw - 24px); gap: 3px; padding: 5px; border: 1px solid var(--border-control); border-radius: 8px; background: var(--color-surface); box-shadow: 0 6px 16px rgb(0 0 0 / 32%); cursor: default; }
.canvas-media-toolbar button, .canvas-media-toolbar a { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-width: var(--control-height-sm); height: var(--control-height-sm); min-height: var(--control-height-sm); padding: 0 9px; border-radius: var(--radius-control-xs); color: var(--color-text); font-size: 13px; text-decoration: none; white-space: nowrap; cursor: pointer; }
.canvas-media-toolbar :is(button, a) svg { width: 17px; height: 17px; flex: none; color: var(--color-muted); }
.canvas-media-toolbar :is(button, a):hover { background: var(--gold-tint); color: var(--color-gold-soft); }
.canvas-media-toolbar :is(button, a):hover svg { color: inherit; }
</style>
