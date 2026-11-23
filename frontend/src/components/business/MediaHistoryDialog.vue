<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Download, Trash2 } from 'lucide-vue-next'
import ImagePreview from '@/components/ui/ImagePreview.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'

export interface MediaHistoryItem {
  id: string
  url: string
  key?: string | null
  name?: string
  source?: 'ai' | 'upload' | 'rescue'
  jobId?: string | null
  modelId?: string | null
  tier?: string | null
  resolution?: string | null
  ratio?: string | null
  duration?: number | null
  createdAt?: string | null
}

const props = withDefaults(
  defineProps<{
    kind: 'image' | 'video'
    title: string
    items: readonly MediaHistoryItem[]
    currentUrl?: string
    selecting?: boolean
    deletingId?: string | null
    deletable?: boolean
    modelNames?: Readonly<Record<string, string>>
  }>(),
  {
    currentUrl: undefined,
    selecting: false,
    deletingId: null,
    deletable: false,
    modelNames: undefined,
  },
)

const emit = defineEmits<{
  select: [item: MediaHistoryItem]
  delete: [item: MediaHistoryItem]
}>()

const open = defineModel<boolean>('open', { default: false })
const selectedId = ref<string>()

const reversedItems = computed(() => [...props.items].reverse())

const selected = computed<MediaHistoryItem | undefined>(() => {
  if (!reversedItems.value.length) return undefined
  if (selectedId.value) {
    const found = reversedItems.value.find((item) => item.id === selectedId.value)
    if (found) return found
  }
  const active = props.currentUrl
    ? reversedItems.value.find((item) => item.url === props.currentUrl)
    : undefined
  return active ?? reversedItems.value[0]
})

const previewImages = computed(() =>
  reversedItems.value.map((item) => ({
    src: item.url,
    title: displayLabel(item),
  })),
)

watch(open, (visible) => {
  if (!visible) return
  const active = props.currentUrl
    ? reversedItems.value.find((item) => item.url === props.currentUrl)
    : undefined
  selectedId.value = active?.id ?? reversedItems.value[0]?.id
})

watch(
  () => props.items,
  (next) => {
    if (!open.value) return
    if (!next.length) {
      selectedId.value = undefined
      return
    }
    if (selectedId.value && next.some((item) => item.id === selectedId.value)) return
    const active = props.currentUrl ? next.find((item) => item.url === props.currentUrl) : undefined
    selectedId.value = active?.id ?? next.at(-1)?.id
  },
)

function isCurrent(item?: MediaHistoryItem): boolean {
  return !!item && !!props.currentUrl && item.url === props.currentUrl
}

function sourceLabel(source?: MediaHistoryItem['source']): string {
  if (source === 'upload') return '本地上传'
  if (source === 'rescue') return '后台补录'
  return 'AI 生成'
}

function displayLabel(item: MediaHistoryItem): string {
  if (item.modelId) {
    const mapped = props.modelNames?.[item.modelId]
    if (mapped) return mapped
    return item.modelId
  }
  if (item.source === 'upload') return '本地上传'
  if (item.source === 'rescue') return '后台补录'
  if (item.name?.trim()) return item.name.trim()
  return props.kind === 'image' ? '历史图片' : '历史视频'
}

function formatTier(tier?: string | null): string | null {
  if (!tier) return null
  if (tier.toLowerCase() === 'web') return 'Web'
  return tier.toUpperCase()
}

function formatMetaChips(item: MediaHistoryItem): string[] {
  const chips: string[] = []
  if (item.source === 'rescue') chips.push('补录')
  else if (item.source === 'upload' && item.modelId) chips.push('上传')
  const tier = formatTier(item.tier)
  if (tier) chips.push(tier)
  if (item.resolution) chips.push(item.resolution)
  if (item.ratio) chips.push(item.ratio)
  if (typeof item.duration === 'number' && Number.isFinite(item.duration) && item.duration > 0) {
    chips.push(`${item.duration.toFixed(1).replace(/\.0$/, '')}s`)
  }
  return chips
}

function formatTime(iso?: string | null): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function confirmSelect() {
  if (!selected.value || isCurrent(selected.value) || props.selecting) return
  emit('select', selected.value)
}

function downloadName(item: MediaHistoryItem): string {
  if (item.name?.trim()) return item.name.trim()
  const ext = props.kind === 'image' ? 'png' : 'mp4'
  return `${props.title}-${item.id.slice(0, 8)}.${ext}`
}
</script>

<template>
  <UiDialog v-model:open="open" :title="title" size="wide">
    <div v-if="reversedItems.length" class="media-history">
      <div class="media-history-list" role="listbox" :aria-label="title">
        <div
          v-for="(item, idx) in reversedItems"
          :key="item.id"
          class="media-history-row"
          :class="{ 'is-selected': selected?.id === item.id, 'is-current': isCurrent(item) }"
        >
          <button
            type="button"
            class="media-history-item"
            :aria-pressed="selected?.id === item.id"
            @click="selectedId = item.id"
          >
            <span class="media-history-thumb">
              <img v-if="kind === 'image'" :src="item.url" alt="" loading="lazy" />
              <video
                v-else
                :src="item.url + '#t=0.05'"
                muted
                playsinline
                preload="metadata"
                aria-hidden="true"
              />
            </span>
            <span class="media-history-info">
              <span class="media-history-head">
                <strong class="media-history-name">{{ displayLabel(item) }}</strong>
                <span v-if="isCurrent(item)" class="media-history-badge">当前</span>
              </span>
              <span class="media-history-meta">
                <span class="media-history-ver">#{{ reversedItems.length - idx }}</span>
                <span v-for="chip in formatMetaChips(item)" :key="chip" class="media-history-chip">{{ chip }}</span>
                <span v-if="formatTime(item.createdAt)" class="media-history-time">{{ formatTime(item.createdAt) }}</span>
              </span>
            </span>
          </button>
          <button
            v-if="deletable && !isCurrent(item)"
            type="button"
            class="media-history-delete"
            :disabled="deletingId === item.id || selecting"
            aria-label="删除此历史版本"
            title="从历史记录中移除"
            @click.stop="emit('delete', item)"
          >
            <Trash2 :size="14" aria-hidden="true" />
          </button>
        </div>
      </div>

      <div v-if="selected" class="media-history-stage">
        <ImagePreview
          v-if="kind === 'image'"
          :src="selected.url"
          :title="displayLabel(selected)"
          :items="previewImages"
        >
          <template #trigger>
            <button type="button" class="media-history-zoom" aria-label="放大预览历史图片" title="点击放大预览">
              <img class="media-history-preview" :src="selected.url" :alt="displayLabel(selected)" />
            </button>
          </template>
        </ImagePreview>
        <video
          v-else
          :key="selected.url"
          class="media-history-video"
          :src="selected.url"
          controls
          playsinline
          preload="metadata"
        />

        <div class="media-history-detail">
          <div class="media-history-detail-meta">
            <span>{{ sourceLabel(selected.source) }}</span>
            <span v-if="selected.modelId">· {{ displayLabel(selected) }}</span>
            <span v-for="chip in formatMetaChips(selected)" :key="chip">· {{ chip }}</span>
            <span v-if="formatTime(selected.createdAt)">· {{ formatTime(selected.createdAt) }}</span>
          </div>
          <a
            class="media-history-download"
            :href="selected.url"
            :download="downloadName(selected)"
            target="_blank"
            rel="noopener"
          >
            <Download :size="14" aria-hidden="true" />下载
          </a>
        </div>
      </div>
    </div>
    <p v-else class="media-history-empty">暂无历史版本记录。</p>

    <template #footer>
      <span v-if="selected && isCurrent(selected)" class="media-history-footer-hint">当前正在使用此版本</span>
      <UiButton variant="ghost" @click="open = false">取消</UiButton>
      <UiButton
        variant="primary"
        :disabled="!selected || isCurrent(selected) || selecting"
        @click="confirmSelect"
      >
        {{ selecting ? '切换中...' : '设为当前版本' }}
      </UiButton>
    </template>
  </UiDialog>
</template>

<style scoped>
.media-history {
  display: grid;
  grid-template-columns: minmax(210px, 1fr) minmax(0, 1.85fr);
  align-items: start;
  gap: 14px;
}

.media-history-list {
  display: grid;
  align-content: start;
  gap: 6px;
  max-height: 52dvh;
  overflow: auto;
  padding-right: 2px;
}

.media-history-row {
  position: relative;
  display: flex;
  align-items: stretch;
  border: 1px solid var(--border-control);
  border-radius: 6px;
  background: var(--color-surface);
  transition: border-color 140ms var(--ease-standard), background-color 140ms var(--ease-standard);
}

.media-history-row:hover {
  border-color: var(--border-strong);
}

.media-history-row.is-selected {
  border-color: var(--color-gold);
  background: color-mix(in srgb, var(--gold-tint) 65%, var(--color-surface));
}

.media-history-item {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  text-align: left;
  cursor: pointer;
}

.media-history-thumb {
  flex: none;
  width: 52px;
  height: 36px;
  border-radius: 4px;
  overflow: hidden;
  background: var(--color-canvas);
  border: 1px solid var(--border-subtle);
}

.media-history-thumb img,
.media-history-thumb video {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.media-history-info {
  flex: 1 1 auto;
  min-width: 0;
  display: grid;
  gap: 3px;
}

.media-history-head {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.media-history-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-caption);
  font-weight: 500;
  color: var(--color-text);
}

.media-history-row.is-selected .media-history-name {
  color: var(--color-gold-soft);
}

.media-history-badge {
  flex: none;
  padding: 1px 5px;
  border-radius: 999px;
  background: var(--gold-tint);
  border: 1px solid color-mix(in srgb, var(--color-gold) 45%, transparent);
  color: var(--color-gold-soft);
  font-size: 11px;
  line-height: 1.3;
}

.media-history-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  color: var(--color-muted);
  font-size: 11px;
  line-height: 1.25;
  font-variant-numeric: tabular-nums;
}

.media-history-ver {
  color: var(--color-subtle);
}

.media-history-chip {
  padding: 0 4px;
  border-radius: 3px;
  background: var(--color-elevated);
  border: 1px solid var(--border-subtle);
}

.media-history-time {
  color: var(--color-subtle);
}

.media-history-delete {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  color: var(--color-muted);
  border-left: 1px solid var(--border-subtle);
  cursor: pointer;
  transition: color 140ms var(--ease-standard), background-color 140ms var(--ease-standard);
}

.media-history-delete:hover:not(:disabled) {
  color: var(--color-error);
  background: color-mix(in srgb, var(--color-error) 10%, transparent);
}

.media-history-delete:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.media-history-stage {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.media-history-zoom {
  display: block;
  width: 100%;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  background: var(--color-canvas);
  cursor: zoom-in;
}

.media-history-preview,
.media-history-video {
  display: block;
  width: 100%;
  max-height: 48dvh;
  object-fit: contain;
  border-radius: 6px;
  background: var(--color-canvas);
}

.media-history-video {
  border: 1px solid var(--border-subtle);
}

.media-history-detail {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: var(--color-surface);
  border: 1px solid var(--border-subtle);
  font-size: var(--font-size-caption);
  color: var(--color-muted);
}

.media-history-detail-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
  min-width: 0;
  font-variant-numeric: tabular-nums;
}

.media-history-download {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--color-gold-soft);
  text-decoration: none;
  white-space: nowrap;
}

.media-history-download:hover {
  text-decoration: underline;
}

.media-history-empty {
  margin: 0;
  padding: 20px 0;
  text-align: center;
  color: var(--color-muted);
  font-size: var(--font-size-body);
}

.media-history-footer-hint {
  margin-right: auto;
  color: var(--color-muted);
  font-size: var(--font-size-caption);
}

@media (max-width: 640px) {
  .media-history {
    grid-template-columns: 1fr;
  }

  .media-history-list {
    max-height: 26dvh;
  }

  .media-history-preview,
  .media-history-video {
    max-height: 30dvh;
  }
}
</style>
