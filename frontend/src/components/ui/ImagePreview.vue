<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ChevronLeft, ChevronRight, Download, ImageOff, Maximize, Minus, Plus, Scan } from 'lucide-vue-next'
import MediaPreviewDialog from './MediaPreviewDialog.vue'
import UiIconButton from './UiIconButton.vue'

type PreviewImage = { src: string; title: string }
const props = defineProps<PreviewImage & { items?: PreviewImage[] }>()
const open = defineModel<boolean>('open', { default: false })
const viewport = ref<HTMLElement>()
const image = ref<HTMLImageElement>()
const size = ref({ width: 0, height: 0 })
const natural = ref({ width: 0, height: 0 })
const failed = ref(false)
const manualScale = ref<number>()
const index = ref(0)
const drag = ref<{ id: number; x: number; y: number; left: number; top: number; moved: boolean }>()
let suppressCloseClick = false

const items = computed(() => props.items?.some(item => item.src === props.src && item.title === props.title)
  ? props.items : [{ src: props.src, title: props.title }])
const current = computed(() => items.value[index.value] ?? items.value[0]!)
const fit = computed(() => natural.value.width && natural.value.height
  ? Math.min(1, size.value.width / natural.value.width, size.value.height / natural.value.height)
  : 0)
const scale = computed(() => manualScale.value ?? fit.value)
const minScale = computed(() => Math.min(fit.value, 0.1))
const ready = computed(() => fit.value > 0 && !failed.value)
const pannable = computed(() => natural.value.width * scale.value > size.value.width ||
  natural.value.height * scale.value > size.value.height)

watch(viewport, (element, _, onCleanup) => {
  if (!element) return
  const measure = () => { size.value = { width: element.clientWidth, height: element.clientHeight } }
  const observer = new ResizeObserver(measure)
  observer.observe(element)
  measure()
  onCleanup(() => observer.disconnect())
})

watch([open, () => props.src, () => props.title], ([visible]) => {
  if (visible) index.value = Math.max(0, items.value.findIndex(item => item.src === props.src && item.title === props.title))
}, { immediate: true })

watch([open, () => current.value.src], () => {
  manualScale.value = undefined
  natural.value = { width: 0, height: 0 }
  failed.value = false
  drag.value = undefined
  viewport.value?.scrollTo(0, 0)
})

function loaded(event: Event) {
  const target = event.currentTarget as HTMLImageElement
  natural.value = { width: target.naturalWidth, height: target.naturalHeight }
}

async function setScale(value?: number, point?: { x: number; y: number }) {
  const element = viewport.value
  const target = image.value
  if (!element || !target || !ready.value) return
  const area = element.getBoundingClientRect()
  const rect = target.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  const anchor = point ?? { x: area.left + area.width / 2, y: area.top + area.height / 2 }
  const x = Math.max(0, Math.min(1, (anchor.x - rect.left) / rect.width))
  const y = Math.max(0, Math.min(1, (anchor.y - rect.top) / rect.height))
  manualScale.value = value === undefined ? undefined : Math.min(4, Math.max(minScale.value, value))
  await nextTick()
  if (image.value !== target) return
  const after = target.getBoundingClientRect()
  element.scrollLeft += after.left + after.width * x - anchor.x
  element.scrollTop += after.top + after.height * y - anchor.y
}

function zoomWheel(event: WheelEvent) {
  if (event.deltaY) void setScale(scale.value * (event.deltaY < 0 ? 1.15 : 1 / 1.15), { x: event.clientX, y: event.clientY })
}

function startDrag(event: PointerEvent) {
  const element = viewport.value
  if (!element || !pannable.value || event.pointerType === 'touch' || event.button !== 0) return
  element.setPointerCapture(event.pointerId)
  drag.value = { id: event.pointerId, x: event.clientX, y: event.clientY, left: element.scrollLeft, top: element.scrollTop, moved: false }
}

function moveDrag(event: PointerEvent) {
  const element = viewport.value
  const start = drag.value
  if (!element || start?.id !== event.pointerId) return
  if (Math.abs(event.clientX - start.x) > 4 || Math.abs(event.clientY - start.y) > 4) {
    start.moved = true
  }
  element.scrollLeft = start.left + start.x - event.clientX
  element.scrollTop = start.top + start.y - event.clientY
}

function endDrag() {
  if (drag.value?.moved) suppressCloseClick = true
  drag.value = undefined
}

function handleViewportClick(event: MouseEvent) {
  if (suppressCloseClick) {
    suppressCloseClick = false
    return
  }
  const target = event.target
  if (!(target instanceof HTMLElement)) return
  if (target === image.value || target.closest('button, a')) return
  open.value = false
}

function move(step: number) {
  index.value = ((index.value + step) % items.value.length + items.value.length) % items.value.length
}

function handleKey(event: KeyboardEvent) {
  if (event.altKey || event.ctrlKey || event.metaKey) return
  if (items.value.length > 1 && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
    event.preventDefault()
    move(event.key === 'ArrowLeft' ? -1 : 1)
  }
}
</script>

<template>
  <MediaPreviewDialog v-model:open="open" :title="current.title" @keydown="handleKey">
    <template v-if="$slots.trigger" #trigger><slot name="trigger" /></template>
    <div ref="viewport" class="image-preview-viewport" :class="{ 'is-pannable': pannable, 'is-dragging': drag }"
      role="region" aria-label="图片查看区域" tabindex="0" @wheel.prevent="zoomWheel"
      @pointerdown="startDrag" @pointermove="moveDrag" @lostpointercapture="endDrag" @click="handleViewportClick">
      <div v-if="failed" class="image-preview-status" role="status"><ImageOff :size="25" aria-hidden="true" />无法加载图片</div>
      <template v-else>
        <div v-if="!ready" class="image-preview-status" role="status">正在加载图片</div>
        <div class="image-preview-stage">
          <img :key="current.src" ref="image" :src="current.src" :alt="current.title" draggable="false"
            :style="{ width: natural.width * scale + 'px', height: natural.height * scale + 'px' }"
            @load="loaded" @error="failed = true" />
        </div>
      </template>
    </div>
    <button v-if="items.length > 1" class="ui-icon-button image-preview-nav is-previous" type="button" aria-label="上一张图片" title="上一张图片" @click="move(-1)">
      <ChevronLeft :size="24" aria-hidden="true" />
    </button>
    <button v-if="items.length > 1" class="ui-icon-button image-preview-nav is-next" type="button" aria-label="下一张图片" title="下一张图片" @click="move(1)">
      <ChevronRight :size="24" aria-hidden="true" />
    </button>
    <template #toolbar>
      <div class="image-preview-tools" role="group" aria-label="图片预览工具">
        <span v-if="items.length > 1" class="image-preview-counter" aria-live="polite">{{ index + 1 }} / {{ items.length }}</span>
        <UiIconButton label="缩小图片" :disabled="!ready || scale <= minScale" @click="setScale(scale / 1.25)"><Minus :size="18" aria-hidden="true" /></UiIconButton>
        <output class="image-preview-zoom" aria-label="缩放比例">{{ ready ? Math.round(scale * 100) + '%' : '—' }}</output>
        <UiIconButton label="放大图片" :disabled="!ready || scale >= 4" @click="setScale(scale * 1.25)"><Plus :size="18" aria-hidden="true" /></UiIconButton>
        <span class="image-preview-divider" aria-hidden="true" />
        <UiIconButton label="适应窗口" :disabled="!ready" :active="ready && manualScale === undefined" @click="setScale()"><Maximize :size="18" aria-hidden="true" /></UiIconButton>
        <UiIconButton label="原始尺寸" :disabled="!ready" :active="ready && manualScale === 1" @click="setScale(1)"><Scan :size="18" aria-hidden="true" /></UiIconButton>
        <a v-if="ready" class="ui-icon-button" :href="current.src" :download="current.title" aria-label="下载图片" title="下载图片">
          <Download :size="18" aria-hidden="true" />
        </a>
      </div>
    </template>
  </MediaPreviewDialog>
</template>

<style scoped>
.image-preview-viewport { position: absolute; inset: 0; overflow: auto; overscroll-behavior: contain; scrollbar-width: none; }
.image-preview-viewport:focus-visible { outline-offset: -2px; }
.image-preview-viewport.is-pannable { cursor: grab; }
.image-preview-viewport.is-dragging { cursor: grabbing; }
.image-preview-stage { display: flex; width: max-content; min-width: 100%; min-height: 100%; }
.image-preview-stage img { display: block; flex: none; margin: auto; max-width: none; user-select: none; }
.image-preview-status { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; gap: 8px; color: var(--color-muted); }
.image-preview-tools {
  display: flex; align-items: center; gap: 3px; max-width: 100%; padding: 5px;
  border: 1px solid var(--border-control); border-radius: 8px; background: var(--color-elevated);
  box-shadow: 0 6px 22px rgb(0 0 0 / 32%);
}
.image-preview-tools .ui-icon-button { border-radius: 5px; }
.image-preview-counter, .image-preview-zoom {
  min-width: 44px; padding-inline: 2px; color: var(--color-muted);
  font-size: var(--font-size-caption); text-align: center; white-space: nowrap; font-variant-numeric: tabular-nums;
}
.image-preview-divider { width: 1px; height: 18px; background: var(--border-control); }
.image-preview-nav {
  position: absolute; top: 50%; transform: translateY(-50%); width: 40px; height: 44px;
  background: rgb(14 15 18 / 85%); border-color: var(--border-control); color: var(--color-text);
}
.image-preview-nav.is-previous { left: 4px; }
.image-preview-nav.is-next { right: 4px; }
@media (max-width: 380px) {
  .image-preview-tools { gap: 1px; }
  .image-preview-tools :deep(.ui-icon-button) { width: 30px; }
}
</style>
