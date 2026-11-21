<script setup lang="ts">
import { computed, ref } from 'vue'
import { X } from 'lucide-vue-next'
import ImagePreview from '@/components/ui/ImagePreview.vue'
import MediaPlayer from '@/components/ui/MediaPlayer.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import VideoPreview from '@/components/ui/VideoPreview.vue'
import { canvasNodeLabels, outputKind, type CanvasNode } from '../canvas-model'
import { canvasNodeIcons } from '../canvas-node-icons'
import CanvasMarkdown from './CanvasMarkdown.vue'

const props = defineProps<{ nodes: CanvasNode[] }>()
const emit = defineEmits<{ remove: [id: string]; reorder: [ids: string[]] }>()
const preview = ref<CanvasNode>()
const previewKind = computed(() => outputKind(preview.value?.type))
const images = computed(() => props.nodes.flatMap(node => outputKind(node.type) === 'image' && node.data.media
  ? [{ src: node.data.media.url, title: name(node) }] : []))
const open = ref(false)
const dragged = ref<string>()

function name(node: CanvasNode) {
  return node.data.title || canvasNodeLabels[node.type ?? 'text']
}

function move(id: string, target: number) {
  const ids = props.nodes.map(node => node.id)
  const from = ids.indexOf(id)
  if (from < 0 || target < 0 || target >= ids.length || from === target) return
  ids.splice(from, 1)
  ids.splice(target, 0, id)
  emit('reorder', ids)
}

function show(node: CanvasNode) {
  preview.value = node
  open.value = true
}
</script>

<template>
  <div class="canvas-reference-list" role="group" aria-label="已连接的引用">
    <div v-for="(node, index) in nodes" :key="node.id" class="canvas-reference-item" draggable="true"
      @dragstart.stop="dragged = node.id; $event.dataTransfer?.setData('text/plain', node.id)" @dragend="dragged = undefined"
      @dragover.prevent @drop.stop.prevent="dragged && move(dragged, index); dragged = undefined"
      @keydown.alt.left.stop.prevent="move(node.id, index - 1)" @keydown.alt.right.stop.prevent="move(node.id, index + 1)">
      <button type="button" class="canvas-reference-preview" :title="name(node)" :aria-label="'预览引用 ' + name(node)" @click="show(node)">
        <img v-if="outputKind(node.type) === 'image' && node.data.media" :src="node.data.media.url" alt="" draggable="false" />
        <video v-else-if="outputKind(node.type) === 'video' && node.data.media" :src="node.data.media.url + '#t=0.05'" preload="metadata" muted playsinline aria-hidden="true" />
        <component :is="canvasNodeIcons[node.type ?? 'text']" v-else :size="18" />
        <span class="canvas-reference-index">{{ index + 1 }}</span>
      </button>
      <button type="button" class="canvas-reference-remove" :title="'移除引用 ' + name(node)" :aria-label="'移除引用 ' + name(node)" @click="emit('remove', node.id)"><X :size="12" /></button>
    </div>
  </div>
  <ImagePreview v-if="previewKind === 'image' && preview?.data.media" v-model:open="open" :src="preview.data.media.url" :title="name(preview)" :items="images" />
  <VideoPreview v-else-if="previewKind === 'video' && preview?.data.media" v-model:open="open" :src="preview.data.media.url" :title="name(preview)" />
  <UiDialog v-else v-model:open="open" :title="preview ? name(preview) : '引用预览'" size="wide">
    <CanvasMarkdown v-if="preview?.data.text" :value="preview.data.text" />
    <MediaPlayer v-else-if="previewKind === 'audio' && preview?.data.media" :key="preview.data.media.url"
      kind="audio" :src="preview.data.media.url" :label="name(preview)" />
    <p v-else class="canvas-ref-empty">暂无内容</p>
  </UiDialog>
</template>

<style scoped>
.canvas-reference-list { display: flex; flex-wrap: wrap; gap: 7px; padding: 1px 1px 8px; }
.canvas-reference-item { position: relative; width: 50px; height: 50px; flex: none; overflow: hidden; border: 1px solid var(--border-control); border-radius: 5px; background: var(--color-elevated); }
.canvas-reference-preview { position: relative; display: flex; align-items: center; justify-content: center; width: 100%; height: 100%; padding: 0; border: 0; overflow: hidden; background: transparent; color: var(--color-muted); cursor: pointer; }
.canvas-reference-preview :is(img, video) { display: block; width: 100%; height: 100%; max-width: none; object-fit: cover; }
.canvas-reference-index { position: absolute; left: 3px; bottom: 3px; padding: 0 3px; border-radius: 3px; background: var(--color-canvas); color: var(--color-gold-soft); font-size: var(--font-size-caption); }
.canvas-reference-remove { position: absolute; top: 2px; right: 2px; display: grid; place-items: center; width: 17px; height: 17px; border-radius: 50%; background: var(--color-canvas); color: var(--color-muted); cursor: pointer; }
.canvas-reference-remove:hover, .canvas-reference-preview:hover { color: var(--color-gold-soft); }
.canvas-ref-empty { color: var(--color-muted); }
</style>
