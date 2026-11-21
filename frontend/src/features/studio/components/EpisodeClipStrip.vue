<script setup lang="ts">
import { ref, useTemplateRef } from 'vue'
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckSquare,
  Clapperboard,
  Loader2,
  Play,
  Plus,
  Trash2,
  Video,
} from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import UiIconButton from '@/components/ui/UiIconButton.vue'
import type { StoryboardClip } from '../studio-storyboard'

const props = defineProps<{
  clips: StoryboardClip[]
  selectedClipId?: number
  selectedClipIndex: number
  persisted: boolean
  selectMode: boolean
  checkedIds: ReadonlySet<string>
  checkedCount: number
  reordering: boolean
  isClipGenerating: (clip: StoryboardClip) => boolean
  clipJobProgress: (clip: StoryboardClip) => string
  clipFailedReason: (clip: StoryboardClip) => string
}>()

const emit = defineEmits<{
  select: [clipId: number]
  move: [fromIndex: number, toIndex: number]
  toggleSelectMode: []
  toggleCheck: [clip: StoryboardClip]
  openBatchFromSelection: []
  preview: [clip: StoryboardClip]
  delete: [clipId: number, event: MouseEvent]
  add: []
}>()

const clipList = useTemplateRef<HTMLOListElement>('clipList')
const dragSourceIndex = ref<number | null>(null)
const dragOverIndex = ref<number | null>(null)

function handleDragStart(index: number, event: DragEvent) {
  if (props.selectMode || props.reordering || props.clips.length <= 1) {
    event.preventDefault()
    return
  }
  dragSourceIndex.value = index
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(index))
  }
}

function handleDragOver(index: number, event: DragEvent) {
  if (dragSourceIndex.value === null) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
  dragOverIndex.value = index
}

function handleDrop(index: number, event: DragEvent) {
  event.preventDefault()
  const from = dragSourceIndex.value
  dragSourceIndex.value = null
  dragOverIndex.value = null
  if (from !== null && from !== index) {
    emit('move', from, index)
  }
}

function handleDragEnd() {
  dragSourceIndex.value = null
  dragOverIndex.value = null
}

function scrollToEnd() {
  const list = clipList.value
  if (list) list.scrollLeft = list.scrollWidth
}

function focusSelectedOrAdd() {
  const target = clipList.value?.querySelector<HTMLButtonElement>(
    '.episode-clip[aria-pressed="true"], .episode-clip-add',
  )
  target?.focus({ preventScroll: true })
}

defineExpose({ scrollToEnd, focusSelectedOrAdd })
</script>

<template>
  <section class="episode-strip" aria-labelledby="episode-strip-title">
    <div class="episode-section-head">
      <div class="episode-strip-left">
        <h2 id="episode-strip-title">片段列表</h2>
        <span class="episode-meta">{{ clips.length }} 个片段（支持拖拽或左右按钮调序）</span>
      </div>
      <div v-if="clips.length" class="episode-strip-actions">
        <template v-if="clips.length > 1 && selectedClipIndex >= 0">
          <UiButton
            variant="outline"
            size="sm"
            :disabled="reordering || selectedClipIndex <= 0"
            title="将当前选中片段向前移动一位"
            @click="emit('move', selectedClipIndex, selectedClipIndex - 1)"
          >
            <template #leading><ArrowLeft :size="13" aria-hidden="true" /></template>前移
          </UiButton>
          <UiButton
            variant="outline"
            size="sm"
            :disabled="reordering || selectedClipIndex >= clips.length - 1"
            title="将当前选中片段向后移动一位"
            @click="emit('move', selectedClipIndex, selectedClipIndex + 1)"
          >
            <template #leading><ArrowRight :size="13" aria-hidden="true" /></template>后移
          </UiButton>
        </template>
        <template v-if="persisted && selectMode">
          <span class="episode-meta">已选 {{ checkedCount }} 段</span>
          <UiButton variant="primary" size="sm" :disabled="!checkedCount" @click="emit('openBatchFromSelection')">
            <template #leading><Video :size="13" aria-hidden="true" /></template>
            生成 / 重生成已选 ({{ checkedCount }})
          </UiButton>
        </template>
        <UiButton v-if="persisted" :variant="selectMode ? 'secondary' : 'outline'" size="sm" @click="emit('toggleSelectMode')">
          <template #leading><CheckSquare :size="13" aria-hidden="true" /></template>
          {{ selectMode ? '退出多选' : '多选' }}
        </UiButton>
      </div>
    </div>

    <ol ref="clipList" class="episode-clips">
      <li
        v-for="(item, idx) in clips"
        :key="item.backendId || item.id"
        :class="{ 'is-dragging': dragSourceIndex === idx, 'is-drop-target': dragOverIndex === idx && dragSourceIndex !== idx }"
        :draggable="!selectMode && !reordering && clips.length > 1"
        @dragstart="handleDragStart(idx, $event)"
        @dragover="handleDragOver(idx, $event)"
        @drop="handleDrop(idx, $event)"
        @dragend="handleDragEnd"
      >
        <button
          type="button"
          class="episode-clip"
          :class="{
            'is-generating': isClipGenerating(item),
            'is-checked': selectMode && !!item.backendId && checkedIds.has(item.backendId),
          }"
          :aria-pressed="selectedClipId === item.id"
          @click="emit('select', item.id)"
        >
          <span class="episode-clip-thumb">
            <img v-if="item.previewUrl" :src="item.previewUrl" alt="" />
            <video
              v-else-if="item.videoUrl"
              class="episode-clip-video-thumb"
              :src="`${item.videoUrl}#t=0.1`"
              muted
              playsinline
              preload="metadata"
            />
            <Clapperboard v-else :size="22" :stroke-width="1.5" aria-hidden="true" />
            <Check v-if="item.videoUrl && !isClipGenerating(item)" class="episode-clip-ready" :size="15" aria-label="已有视频" />
            <span
              v-if="!isClipGenerating(item) && (item.videoStatus === 'failed' || clipFailedReason(item))"
              class="episode-clip-failed"
              :title="clipFailedReason(item) || '视频生成失败'"
            >
              <AlertCircle :size="13" aria-hidden="true" />
            </span>
            <span v-if="isClipGenerating(item)" class="episode-clip-loading-mask">
              <Loader2 class="is-spin" :size="15" aria-hidden="true" />
              <span>{{ clipJobProgress(item) }}</span>
            </span>
          </span>
          <span class="episode-clip-caption"><strong>片段 {{ item.id }}</strong><span>{{ item.durationSeconds }} 秒</span></span>
        </button>

        <button
          v-if="selectMode && item.backendId"
          type="button"
          class="episode-clip-check"
          :class="{ 'is-checked': checkedIds.has(item.backendId) }"
          :disabled="isClipGenerating(item)"
          :aria-label="`选择片段 ${item.id}`"
          @click.stop="emit('toggleCheck', item)"
        >
          <Check v-if="checkedIds.has(item.backendId)" :size="11" :stroke-width="2.6" />
        </button>

        <button
          v-if="item.videoUrl && !isClipGenerating(item)"
          type="button"
          class="episode-clip-play"
          :aria-label="`播放片段 ${item.id}`"
          :title="`播放片段 ${item.id}`"
          @click.stop="emit('preview', item)"
        >
          <Play :size="15" fill="currentColor" aria-hidden="true" />
        </button>

        <UiIconButton
          v-if="!selectMode && !isClipGenerating(item)"
          class="episode-clip-delete"
          :label="`删除片段 ${item.id}`"
          @click="emit('delete', item.id, $event)"
        >
          <Trash2 :size="14" aria-hidden="true" />
        </UiIconButton>
      </li>
      <li>
        <button type="button" class="episode-clip episode-clip-add" @click="emit('add')">
          <Plus :size="22" aria-hidden="true" />
          新增镜头
        </button>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.episode-strip {
  grid-row: 3;
  min-width: 0;
  padding: 12px 16px;
  border-top: 1px solid var(--border-subtle);
}
.episode-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.episode-section-head h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
}
.episode-strip-left,
.episode-strip-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.episode-strip-actions .ui-button {
  min-height: 28px;
  padding-inline: 8px;
  font-size: 12px;
}
.episode-meta {
  margin: 0;
  color: var(--color-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.episode-clips {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  margin: 8px 0 0;
  padding: 3px 3px 5px;
  list-style: none;
}
.episode-clips > li {
  position: relative;
  display: grid;
  flex: 0 0 132px;
  transition: opacity .15s, transform .15s;
}
.episode-clips > li.is-dragging { opacity: 0.45; }
.episode-clips > li.is-drop-target .episode-clip {
  border-color: var(--color-gold);
  box-shadow: 0 0 0 2px rgb(240 184 75 / 45%);
}
.episode-clip {
  width: 100%;
  padding: 0;
  overflow: hidden;
  border: 1px solid var(--border-control);
  border-radius: 7px;
  color: var(--color-text);
  background: var(--color-surface);
  cursor: pointer;
  transition: border-color .15s;
}
.episode-clip.is-generating { border-color: rgb(240 184 75 / 45%); }
.episode-clip.is-checked { border-color: var(--color-gold); box-shadow: 0 0 0 1px var(--color-gold); }
.episode-clip-thumb {
  position: relative;
  display: grid;
  place-items: center;
  overflow: hidden;
  aspect-ratio: 16 / 9;
  background: var(--surface-hover);
  color: var(--color-muted);
}
.episode-clip-thumb img {
  width: 100%;
  height: 100%;
  min-height: 0;
  object-fit: cover;
}
.episode-clip-video-thumb { width: 100%; height: 100%; object-fit: cover; pointer-events: none; }
.episode-clip-ready {
  position: absolute;
  inset: 5px auto auto 5px;
  color: var(--color-gold-soft);
  filter: drop-shadow(0 1px 2px rgb(0 0 0 / 70%));
}
.episode-clip-failed {
  position: absolute;
  inset: 5px auto auto 5px;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgb(9 10 13 / 82%);
  color: var(--color-error);
}
.episode-clip-loading-mask {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  background: rgb(9 10 13 / 74%);
  color: var(--color-gold-soft);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.episode-clip-check {
  position: absolute;
  top: 5px;
  right: 5px;
  z-index: 2;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border: 1px solid rgb(255 255 255 / 45%);
  border-radius: 5px;
  background: rgb(9 10 13 / 82%);
  color: var(--color-ink);
  cursor: pointer;
}
.episode-clip-check.is-checked {
  border-color: var(--color-gold);
  background: var(--color-gold);
}
.episode-clip-play {
  position: absolute;
  top: 22px;
  left: 50%;
  transform: translateX(-50%);
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  padding-left: 2px;
  border: 1px solid rgb(240 184 75 / 55%);
  border-radius: 50%;
  background: rgb(9 10 13 / 78%);
  color: var(--color-gold-soft);
  cursor: pointer;
  transition: transform .15s, background-color .15s, border-color .15s, color .15s;
}
.episode-clip-play:is(:hover, :focus-visible) {
  transform: translateX(-50%) scale(1.08);
  border-color: var(--color-gold);
  background: var(--color-gold);
  color: var(--color-ink);
}
.episode-clips :deep(.episode-clip-delete) {
  position: absolute;
  inset: 5px 5px auto auto;
  width: 28px;
  height: 28px;
  border-color: var(--border-control);
  border-radius: 6px;
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
}
.episode-clips :deep(.episode-clip-delete:is(:hover, :focus-visible)) {
  border-color: var(--color-error);
  color: var(--color-error);
}
@media (hover: hover) and (pointer: fine) {
  .episode-clips > li:not(:hover):not(:focus-within) :deep(.episode-clip-delete) {
    opacity: 0;
    pointer-events: none;
  }
}
.episode-clip-caption {
  display: flex;
  justify-content: space-between;
  gap: 4px;
  padding: 6px 8px;
  font-size: 12px;
}
.episode-clip-caption span { color: var(--color-muted); }
.episode-clip:hover,
.episode-clip[aria-pressed="true"] { border-color: var(--color-gold); }
.episode-clip[aria-pressed="true"] .episode-clip-caption {
  color: var(--color-gold-soft);
  background: var(--gold-tint);
}
.episode-clip:focus-visible { outline: 2px solid var(--color-gold); outline-offset: 2px; }
.episode-clip-add {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-style: dashed;
  color: var(--color-muted);
  font-size: 13px;
}
.episode-clip-add:is(:hover, :focus-visible) {
  color: var(--color-gold-soft);
  background: var(--gold-tint);
}
.is-spin { animation: spin 1s linear infinite; }
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
