<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from 'vue'
import {
  FileText,
  Film,
  Image as ImageIcon,
  Loader2,
  Maximize2,
  Music,
  Package,
  Pause,
  Play,
  Plus,
  Search,
  Trash2,
  UserRound,
  X,
} from 'lucide-vue-next'
import ImagePreview from '@/components/ui/ImagePreview.vue'
import UiButton from '@/components/ui/UiButton.vue'
import VideoPreview from '@/components/ui/VideoPreview.vue'
import { useUiStore } from '@/stores/ui'
import { apiErrorMessage } from '@/features/studio/api'
import {
  assetDisplayName,
  assetStateLabel,
  type StudioAsset,
  type StudioAssetKind,
} from '@/features/studio/studio-assets'
import {
  buildAcceptAttribute,
  isHttpMediaUrl,
  type AssetLibraryItem,
  type AssetLibraryMode,
  type AssetLibrarySource,
  type AssetMediaKind,
  type UploadableMediaKind,
} from './asset-library-types'
import { useUserAssetsStore } from './user-assets-store'

const props = withDefaults(
  defineProps<{
    mode?: AssetLibraryMode
    allowedKinds?: readonly AssetMediaKind[]
    projectAssets?: readonly StudioAsset[]
    defaultSource?: AssetLibrarySource
    /** In multiple mode, keys (mediaUrl or id) pre-selected on open */
    initialSelectedKeys?: readonly string[]
    /** Items whose id or mediaUrl is in this set cannot be selected again */
    disabledKeys?: readonly string[]
    /** Per-kind selection caps in multiple mode (e.g. { image: 9, video: 3, audio: 3 }) */
    maxByKind?: Partial<Record<AssetMediaKind, number>>
    /** Overall selection cap in multiple mode */
    maxSelect?: number
    /** Require a valid HTTP(S) mediaUrl to select an item */
    requireHttpUrl?: boolean
    /** Allow deleting personal assets */
    deletable?: boolean
    /** Full-page height mode for /assets view */
    fullPage?: boolean
  }>(),
  {
    mode: 'single',
    allowedKinds: () => ['image', 'video', 'audio'] as const,
    defaultSource: 'personal',
    initialSelectedKeys: () => [],
    disabledKeys: () => [],
    requireHttpUrl: false,
    deletable: true,
    fullPage: false,
  },
)

const emit = defineEmits<{
  select: [item: AssetLibraryItem]
  confirm: [items: AssetLibraryItem[]]
  cancel: []
}>()

const ui = useUiStore()
const userAssets = useUserAssetsStore()
const fileInput = useTemplateRef<HTMLInputElement>('fileInput')
const audioPlayer = useTemplateRef<HTMLAudioElement>('audioPlayer')

const hasProjectSource = computed(() => props.projectAssets !== undefined)
const source = ref<AssetLibrarySource>(
  props.projectAssets !== undefined ? props.defaultSource : 'personal',
)
const personalKindFilter = ref<AssetMediaKind | 'all'>('all')
const projectKindFilter = ref<StudioAssetKind | 'all'>('all')
const keyword = ref('')
const dragOver = ref(false)
const deletingId = ref<string | null>(null)
const pendingDeleteId = ref<string | null>(null)
let deleteConfirmTimer: ReturnType<typeof setTimeout> | null = null

const playingAudioId = ref<string | null>(null)
const previewItem = ref<AssetLibraryItem | null>(null)
const previewOpen = computed({
  get: () => previewItem.value !== null,
  set: (val: boolean) => {
    if (!val) previewItem.value = null
  },
})

const selectedItems = ref<AssetLibraryItem[]>([])

const allowedKindSet = computed(() => new Set<AssetMediaKind>(props.allowedKinds))
const uploadableKinds = computed<UploadableMediaKind[]>(() =>
  props.allowedKinds.filter(
    (k): k is UploadableMediaKind => k === 'image' || k === 'video' || k === 'audio',
  ),
)
const acceptAttr = computed(() => buildAcceptAttribute(uploadableKinds.value))

const uploadTypeCaption = computed(() => {
  const labels: string[] = []
  if (uploadableKinds.value.includes('image')) labels.push('图片')
  if (uploadableKinds.value.includes('video')) labels.push('视频')
  if (uploadableKinds.value.includes('audio')) labels.push('音频')
  return labels.join(' · ')
})

const kindLabels: Record<AssetMediaKind, string> = {
  image: '图片',
  video: '视频',
  audio: '音频',
  text: '文本',
}

const projectKindLabels: Record<StudioAssetKind, string> = {
  character: '角色',
  scene: '场景',
  prop: '物品',
}

const projectKindIcons: Record<StudioAssetKind, typeof UserRound> = {
  character: UserRound,
  scene: ImageIcon,
  prop: Package,
}

const allPersonalItems = computed<AssetLibraryItem[]>(() =>
  userAssets.items
    .filter((item) => allowedKindSet.value.has(item.kind))
    .map((item) => ({
      id: item.id,
      key: item.mediaUrl || item.id,
      source: 'personal' as const,
      kind: item.kind,
      title: item.title,
      mediaUrl: item.mediaUrl ?? undefined,
      mediaKey: item.mediaKey ?? undefined,
      mediaName: item.mediaName ?? undefined,
      text: item.textContent ?? undefined,
      userAsset: item,
      createdAt: item.createdAt,
    })),
)

const allProjectItems = computed<AssetLibraryItem[]>(() => {
  if (!props.projectAssets || !allowedKindSet.value.has('image')) return []
  return props.projectAssets.map((asset) => {
    const id = asset.backendId || asset.id
    const state = assetStateLabel(asset)
    return {
      id,
      key: asset.imageUrl || id,
      source: 'project' as const,
      kind: 'image' as const,
      title: assetDisplayName(asset),
      mediaUrl: asset.imageUrl,
      mediaKey: asset.imageKey,
      tag: asset.parentAssetId ? state : projectKindLabels[asset.kind],
      projectAsset: asset,
    }
  })
})

const allLookupItems = computed(() => [...allProjectItems.value, ...allPersonalItems.value])

const visibleItems = computed<AssetLibraryItem[]>(() => {
  const q = keyword.value.trim().toLowerCase()
  const base =
    source.value === 'project'
      ? allProjectItems.value.filter(
          (item) =>
            projectKindFilter.value === 'all' || item.projectAsset?.kind === projectKindFilter.value,
        )
      : allPersonalItems.value.filter(
          (item) => personalKindFilter.value === 'all' || item.kind === personalKindFilter.value,
        )

  if (!q) return base
  return base.filter(
    (item) =>
      item.title.toLowerCase().includes(q)
      || (item.tag && item.tag.toLowerCase().includes(q))
      || (item.text && item.text.toLowerCase().includes(q)),
  )
})

const disabledKeySet = computed(() => new Set(props.disabledKeys))
const selectedIndexMap = computed(() => {
  const map = new Map<string, number>()
  selectedItems.value.forEach((item, idx) => {
    map.set(item.key, idx + 1)
    map.set(item.id, idx + 1)
  })
  return map
})

function isItemDisabled(item: AssetLibraryItem): boolean {
  if (disabledKeySet.value.has(item.id) || disabledKeySet.value.has(item.key)) return true
  if (item.mediaUrl && disabledKeySet.value.has(item.mediaUrl)) return true
  if (props.mode !== 'manage' && item.kind !== 'text') {
    if (props.requireHttpUrl && !isHttpMediaUrl(item.mediaUrl)) return true
    if (!item.mediaUrl) return true
  }
  return false
}

function disabledTag(item: AssetLibraryItem): string {
  if (
    disabledKeySet.value.has(item.id)
    || disabledKeySet.value.has(item.key)
    || (item.mediaUrl && disabledKeySet.value.has(item.mediaUrl))
  ) {
    return '已添加'
  }
  if (item.source === 'project' && !item.mediaUrl) return '未生图'
  return ''
}

function selectedOrder(item: AssetLibraryItem): number | undefined {
  return selectedIndexMap.value.get(item.key) ?? selectedIndexMap.value.get(item.id)
}

function countSelectedByKind(kind: AssetMediaKind): number {
  return selectedItems.value.filter((item) => item.kind === kind).length
}

const selectedSummaryText = computed(() => {
  if (!props.maxByKind) {
    if (props.maxSelect) return `已选 ${selectedItems.value.length} / ${props.maxSelect}`
    return `已选 ${selectedItems.value.length}`
  }
  const parts: string[] = []
  const order: Array<[AssetMediaKind, string]> = [
    ['image', '图'],
    ['video', '视'],
    ['audio', '音'],
  ]
  for (const [kind, short] of order) {
    const cap = props.maxByKind[kind]
    if (cap === undefined || !allowedKindSet.value.has(kind)) continue
    parts.push(`${short} ${countSelectedByKind(kind)}/${cap}`)
  }
  return parts.length ? parts.join(' · ') : `已选 ${selectedItems.value.length}`
})

function syncInitialSelection() {
  if (props.mode !== 'multiple') {
    selectedItems.value = []
    return
  }
  const initialSet = new Set(props.initialSelectedKeys)
  if (!initialSet.size) {
    selectedItems.value = []
    return
  }
  const matched: AssetLibraryItem[] = []
  const seen = new Set<string>()
  for (const item of allLookupItems.value) {
    if (seen.has(item.key)) continue
    if (initialSet.has(item.key) || initialSet.has(item.id) || (item.mediaUrl && initialSet.has(item.mediaUrl))) {
      seen.add(item.key)
      matched.push(item)
    }
  }
  selectedItems.value = matched
}

function resetState() {
  stopAudio()
  source.value = props.projectAssets !== undefined ? props.defaultSource : 'personal'
  personalKindFilter.value = 'all'
  projectKindFilter.value = 'all'
  keyword.value = ''
  pendingDeleteId.value = null
  syncInitialSelection()
  void userAssets.ensureLoaded().catch(() => {})
}

onMounted(() => {
  void userAssets.ensureLoaded().then(() => {
    if (props.mode === 'multiple' && props.initialSelectedKeys.length && !selectedItems.value.length) {
      syncInitialSelection()
    }
  }).catch(() => {})
  syncInitialSelection()
})

watch(
  () => [props.defaultSource, props.projectAssets?.length, props.allowedKinds.join(',')] as const,
  () => {
    if (!hasProjectSource.value) source.value = 'personal'
    if (personalKindFilter.value !== 'all' && !allowedKindSet.value.has(personalKindFilter.value)) {
      personalKindFilter.value = 'all'
    }
  },
)

function stopAudio() {
  if (audioPlayer.value) {
    audioPlayer.value.pause()
    audioPlayer.value.currentTime = 0
  }
  playingAudioId.value = null
}

function toggleAudio(item: AssetLibraryItem) {
  const el = audioPlayer.value
  if (!el || !item.mediaUrl) return
  if (playingAudioId.value === item.id) {
    stopAudio()
    return
  }
  el.src = item.mediaUrl
  playingAudioId.value = item.id
  void el.play().catch(() => {
    playingAudioId.value = null
  })
}

function openPreview(item: AssetLibraryItem) {
  if (!item.mediaUrl || (item.kind !== 'image' && item.kind !== 'video')) return
  stopAudio()
  previewItem.value = item
}

function handleCardClick(item: AssetLibraryItem) {
  if (props.mode === 'manage') {
    if (item.kind === 'audio') {
      toggleAudio(item)
    } else if (item.kind === 'image' || item.kind === 'video') {
      openPreview(item)
    }
    return
  }

  if (isItemDisabled(item)) return

  if (props.mode === 'single') {
    stopAudio()
    emit('select', item)
    return
  }

  const existingIdx = selectedItems.value.findIndex(
    (s) => s.key === item.key || s.id === item.id,
  )
  if (existingIdx >= 0) {
    selectedItems.value = selectedItems.value.filter((_, idx) => idx !== existingIdx)
    return
  }

  const kindCap = props.maxByKind?.[item.kind]
  if (kindCap !== undefined && countSelectedByKind(item.kind) >= kindCap) {
    const label = kindLabels[item.kind]
    ui.notify(kindCap <= 0 ? `当前模型不支持参考${label}` : `最多选择 ${kindCap} 个${label}`, 'info')
    return
  }
  if (props.maxSelect !== undefined && selectedItems.value.length >= props.maxSelect) {
    ui.notify(`最多选择 ${props.maxSelect} 项`, 'info')
    return
  }
  selectedItems.value = [...selectedItems.value, item]
}

function handleVideoEnter(event: MouseEvent) {
  const video = (event.currentTarget as HTMLElement | null)?.querySelector('video')
  if (video) void video.play().catch(() => {})
}

function handleVideoLeave(event: MouseEvent) {
  const video = (event.currentTarget as HTMLElement | null)?.querySelector('video')
  if (video) {
    video.pause()
    video.currentTime = 0
  }
}

function requestDelete(id: string) {
  if (deletingId.value) return
  if (pendingDeleteId.value === id) {
    if (deleteConfirmTimer) clearTimeout(deleteConfirmTimer)
    pendingDeleteId.value = null
    void executeDelete(id)
    return
  }
  pendingDeleteId.value = id
  if (deleteConfirmTimer) clearTimeout(deleteConfirmTimer)
  deleteConfirmTimer = setTimeout(() => {
    if (pendingDeleteId.value === id) pendingDeleteId.value = null
  }, 3000)
}

async function executeDelete(id: string) {
  deletingId.value = id
  try {
    if (playingAudioId.value === id) stopAudio()
    await userAssets.removeAsset(id)
    selectedItems.value = selectedItems.value.filter((item) => item.id !== id)
    ui.notify('已删除素材', 'info')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    deletingId.value = null
  }
}

function triggerFilePick() {
  if (userAssets.uploadingCount > 0) return
  fileInput.value?.click()
}

async function handleFiles(fileList: FileList | File[]) {
  const files = Array.from(fileList)
  if (!files.length || !uploadableKinds.value.length) return

  const { uploaded, failed } = await userAssets.uploadFiles(files, uploadableKinds.value)
  if (failed.length) {
    const first = failed[0]!
    ui.notify(
      failed.length === 1 ? `${first.name}：${first.reason}` : `${failed.length} 个文件上传失败（${first.reason}）`,
      'error',
    )
  }
  if (!uploaded.length) return

  if (source.value !== 'personal') {
    source.value = 'personal'
  }
  if (personalKindFilter.value !== 'all' && uploaded.every((u) => u.kind !== personalKindFilter.value)) {
    personalKindFilter.value = 'all'
  }

  if (props.mode === 'multiple') {
    for (const created of uploaded) {
      const mapped = allPersonalItems.value.find((item) => item.id === created.id)
      if (!mapped || selectedOrder(mapped)) continue
      const kindCap = props.maxByKind?.[mapped.kind]
      if (kindCap !== undefined && countSelectedByKind(mapped.kind) >= kindCap) continue
      if (props.maxSelect !== undefined && selectedItems.value.length >= props.maxSelect) continue
      selectedItems.value = [...selectedItems.value, mapped]
    }
  }

  ui.notify(uploaded.length === 1 ? '已上传至素材库' : `已上传 ${uploaded.length} 个素材`, 'success')
}

function onFileInputChange(event: Event) {
  const input = event.currentTarget as HTMLInputElement
  const files = input.files
  if (files?.length) void handleFiles(files)
  input.value = ''
}

function onDropFiles(event: DragEvent) {
  dragOver.value = false
  if (event.dataTransfer?.files?.length) {
    void handleFiles(event.dataTransfer.files)
  }
}

function confirmSelection() {
  stopAudio()
  emit('confirm', [...selectedItems.value])
}

onBeforeUnmount(() => {
  stopAudio()
  if (deleteConfirmTimer) clearTimeout(deleteConfirmTimer)
})

defineExpose({ resetState, stopAudio })
</script>

<template>
  <div class="asset-lib" :class="{ 'is-full-page': fullPage }">
    <div class="asset-lib-bar">
      <div class="asset-lib-filters">
        <div v-if="hasProjectSource" class="asset-lib-segment" role="tablist" aria-label="素材来源">
          <button
            type="button"
            role="tab"
            :aria-selected="source === 'project'"
            class="asset-lib-seg-btn"
            :class="{ 'is-active': source === 'project' }"
            @click="source = 'project'"
          >
            本项目
          </button>
          <button
            type="button"
            role="tab"
            :aria-selected="source === 'personal'"
            class="asset-lib-seg-btn"
            :class="{ 'is-active': source === 'personal' }"
            @click="source = 'personal'"
          >
            我的素材
          </button>
        </div>

        <div v-if="source === 'project'" class="asset-lib-pills" role="group" aria-label="资产分类">
          <button
            type="button"
            class="asset-lib-pill"
            :class="{ 'is-active': projectKindFilter === 'all' }"
            @click="projectKindFilter = 'all'"
          >
            全部
          </button>
          <button
            v-for="k in (['character', 'scene', 'prop'] as const)"
            :key="k"
            type="button"
            class="asset-lib-pill"
            :class="{ 'is-active': projectKindFilter === k }"
            @click="projectKindFilter = k"
          >
            {{ projectKindLabels[k] }}
          </button>
        </div>

        <div
          v-else-if="allowedKinds.length > 1"
          class="asset-lib-pills"
          role="group"
          aria-label="素材类型"
        >
          <button
            type="button"
            class="asset-lib-pill"
            :class="{ 'is-active': personalKindFilter === 'all' }"
            @click="personalKindFilter = 'all'"
          >
            全部
          </button>
          <button
            v-for="k in allowedKinds"
            :key="k"
            type="button"
            class="asset-lib-pill"
            :class="{ 'is-active': personalKindFilter === k }"
            @click="personalKindFilter = k"
          >
            {{ kindLabels[k] }}
          </button>
        </div>
      </div>

      <label class="asset-lib-search">
        <Search :size="14" aria-hidden="true" />
        <input v-model="keyword" type="text" placeholder="搜索" aria-label="搜索素材" />
        <button
          v-if="keyword"
          type="button"
          class="asset-lib-search-clear"
          aria-label="清空搜索"
          @click="keyword = ''"
        >
          <X :size="12" />
        </button>
      </label>
    </div>

    <div class="asset-lib-body">
      <div class="asset-lib-grid">
        <button
          v-if="uploadableKinds.length"
          type="button"
          class="asset-lib-card asset-lib-upload"
          :class="{ 'is-dragover': dragOver, 'is-uploading': userAssets.uploadingCount > 0 }"
          :disabled="userAssets.uploadingCount > 0"
          @click="triggerFilePick"
          @dragover.prevent="dragOver = true"
          @dragleave.prevent="dragOver = false"
          @drop.prevent="onDropFiles"
        >
          <span class="asset-lib-upload-icon">
            <Loader2 v-if="userAssets.uploadingCount > 0" :size="20" class="ui-spin" />
            <Plus v-else :size="20" :stroke-width="2" />
          </span>
          <span class="asset-lib-upload-title">
            {{ userAssets.uploadingCount > 0 ? '上传中…' : '上传素材' }}
          </span>
          <span v-if="uploadTypeCaption" class="asset-lib-upload-sub">{{ uploadTypeCaption }}</span>
          <input
            ref="fileInput"
            type="file"
            multiple
            :accept="acceptAttr"
            hidden
            @change="onFileInputChange"
          />
        </button>

        <article
          v-for="item in visibleItems"
          :key="`${item.source}:${item.id}`"
          class="asset-lib-card asset-lib-item"
          :class="{
            'is-selected': selectedOrder(item) !== undefined,
            'is-disabled': isItemDisabled(item),
            'is-audio': item.kind === 'audio',
            'is-text': item.kind === 'text',
          }"
          @mouseenter="item.kind === 'video' ? handleVideoEnter($event) : undefined"
          @mouseleave="item.kind === 'video' ? handleVideoLeave($event) : undefined"
        >
          <button
            type="button"
            class="asset-lib-hit"
            :disabled="isItemDisabled(item)"
            :aria-label="item.title"
            @click="handleCardClick(item)"
          >
            <div class="asset-lib-stage">
              <img
                v-if="item.kind === 'image' && item.mediaUrl"
                :src="item.mediaUrl"
                loading="lazy"
                alt=""
                class="asset-lib-media asset-lib-media--image"
              />
              <video
                v-else-if="item.kind === 'video' && item.mediaUrl"
                :src="`${item.mediaUrl}#t=0.05`"
                preload="metadata"
                muted
                playsinline
                loop
                class="asset-lib-media"
              />
              <div v-else-if="item.kind === 'audio'" class="asset-lib-audio-stage">
                <span
                  class="asset-lib-audio-wave"
                  :class="{ 'is-playing': playingAudioId === item.id }"
                  aria-hidden="true"
                >
                  <i /><i /><i /><i /><i />
                </span>
              </div>
              <div v-else-if="item.kind === 'text'" class="asset-lib-text-stage">
                <p>{{ item.text }}</p>
              </div>
              <div v-else class="asset-lib-placeholder">
                <component
                  :is="item.projectAsset ? projectKindIcons[item.projectAsset.kind] : ImageIcon"
                  :size="22"
                  :stroke-width="1.5"
                />
              </div>
            </div>

            <div class="asset-lib-caption">
              <span class="asset-lib-name" :title="item.title">{{ item.title }}</span>
              <span v-if="item.tag" class="asset-lib-tag">{{ item.tag }}</span>
            </div>
          </button>

          <button
            v-if="item.kind === 'audio' && item.mediaUrl"
            type="button"
            class="asset-lib-audio-btn"
            :class="{ 'is-playing': playingAudioId === item.id }"
            :aria-label="playingAudioId === item.id ? '暂停' : '试听'"
            @click.stop="toggleAudio(item)"
          >
            <Pause v-if="playingAudioId === item.id" :size="15" />
            <Play v-else :size="15" />
          </button>

          <span v-if="selectedOrder(item) !== undefined" class="asset-lib-order">
            {{ selectedOrder(item) }}
          </span>
          <span v-else-if="disabledTag(item)" class="asset-lib-status-badge">
            {{ disabledTag(item) }}
          </span>
          <span v-else-if="item.kind === 'video'" class="asset-lib-kind-badge">
            <Film :size="11" />
          </span>
          <span v-else-if="item.kind === 'audio'" class="asset-lib-kind-badge">
            <Music :size="11" />
          </span>
          <span v-else-if="item.kind === 'text'" class="asset-lib-kind-badge">
            <FileText :size="11" />
          </span>

          <div class="asset-lib-actions">
            <button
              v-if="(item.kind === 'image' || item.kind === 'video') && item.mediaUrl"
              type="button"
              class="asset-lib-action-btn"
              title="预览"
              aria-label="预览"
              @click.stop="openPreview(item)"
            >
              <Maximize2 :size="13" />
            </button>
            <button
              v-if="deletable && item.source === 'personal'"
              type="button"
              class="asset-lib-action-btn"
              :class="{ 'is-danger-confirm': pendingDeleteId === item.id }"
              :disabled="deletingId === item.id"
              :title="pendingDeleteId === item.id ? '再次点击确认删除' : '删除'"
              :aria-label="pendingDeleteId === item.id ? '确认删除' : '删除'"
              @click.stop="requestDelete(item.id)"
            >
              <Loader2 v-if="deletingId === item.id" :size="13" class="ui-spin" />
              <span v-else-if="pendingDeleteId === item.id" class="asset-lib-confirm-txt">删除</span>
              <Trash2 v-else :size="13" />
            </button>
          </div>
        </article>
      </div>

      <p
        v-if="!visibleItems.length && !userAssets.loading"
        class="asset-lib-empty"
      >
        暂无素材
      </p>
    </div>

    <div v-if="mode === 'multiple'" class="asset-lib-footer">
      <span class="asset-lib-count">{{ selectedSummaryText }}</span>
      <div class="asset-lib-footer-actions">
        <UiButton variant="ghost" size="sm" @click="emit('cancel')">取消</UiButton>
        <UiButton variant="primary" size="sm" @click="confirmSelection">确认</UiButton>
      </div>
    </div>

    <audio ref="audioPlayer" hidden @ended="playingAudioId = null" />

    <ImagePreview
      v-if="previewItem?.kind === 'image' && previewItem.mediaUrl"
      v-model:open="previewOpen"
      :src="previewItem.mediaUrl"
      :title="previewItem.title"
    />
    <VideoPreview
      v-else-if="previewItem?.kind === 'video' && previewItem.mediaUrl"
      v-model:open="previewOpen"
      :src="previewItem.mediaUrl"
      :title="previewItem.title"
      autoplay
    />
  </div>
</template>

<style scoped>
.asset-lib {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
}

.asset-lib.is-full-page {
  flex: 1 1 auto;
}

.asset-lib-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.asset-lib-filters {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  min-width: 0;
}

.asset-lib-segment {
  display: inline-flex;
  padding: 2px;
  border-radius: 8px;
  border: 1px solid var(--border-control);
  background: rgb(255 255 255 / 3%);
}

.asset-lib-seg-btn {
  height: 28px;
  padding: 0 12px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background 140ms ease, color 140ms ease;
}

.asset-lib-seg-btn:hover {
  color: var(--color-text);
}

.asset-lib-seg-btn.is-active {
  background: rgb(212 175 55 / 16%);
  color: var(--color-gold-soft);
}

.asset-lib-pills {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.asset-lib-pill {
  height: 28px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--color-muted);
  font-size: 12px;
  cursor: pointer;
  transition: background 140ms ease, color 140ms ease, border-color 140ms ease;
}

.asset-lib-pill:hover {
  background: rgb(255 255 255 / 5%);
  color: var(--color-text);
}

.asset-lib-pill.is-active {
  border-color: rgb(212 175 55 / 35%);
  background: rgb(212 175 55 / 10%);
  color: var(--color-gold-soft);
}

.asset-lib-search {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  width: 196px;
  height: 32px;
  padding: 0 10px;
  border-radius: 8px;
  border: 1px solid var(--border-control);
  background: rgb(255 255 255 / 3%);
  color: var(--color-muted);
  transition: border-color 140ms ease;
}

.asset-lib-search:focus-within {
  border-color: rgb(212 175 55 / 50%);
  color: var(--color-text);
}

.asset-lib-search input {
  width: 100%;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--color-text);
  font-size: 12px;
  outline: none;
}

.asset-lib-search input::placeholder {
  color: var(--color-muted);
}

.asset-lib-search-clear {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--color-muted);
  cursor: pointer;
}

.asset-lib-search-clear:hover {
  color: var(--color-text);
}

.asset-lib-body {
  min-height: 220px;
  max-height: 58vh;
  overflow-y: auto;
  padding: 2px;
}

.asset-lib.is-full-page .asset-lib-body {
  max-height: none;
  overflow: visible;
}

.asset-lib-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(172px, 1fr));
  gap: 14px;
}

.asset-lib.is-full-page .asset-lib-grid {
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 16px;
}

.asset-lib-card {
  position: relative;
  display: flex;
  flex-direction: column;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  background: var(--color-surface);
  transition: border-color 150ms ease, box-shadow 150ms ease;
}

.asset-lib-upload {
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 152px;
  border: 1px dashed var(--border-control);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
}

.asset-lib-upload:hover:not(:disabled),
.asset-lib-upload.is-dragover {
  border-color: var(--color-gold);
  background: rgb(212 175 55 / 6%);
}

.asset-lib-upload:disabled {
  cursor: wait;
  opacity: 0.78;
}

.asset-lib-upload-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  border: 1px solid rgb(240 184 75 / 24%);
  background: rgb(240 184 75 / 10%);
  color: var(--color-gold-soft);
}

.asset-lib-upload-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text);
}

.asset-lib-upload-sub {
  font-size: 11px;
  color: var(--color-muted);
}

.asset-lib-item:hover:not(.is-disabled) {
  border-color: var(--focus-ring);
}

.asset-lib-item.is-selected {
  border-color: var(--color-gold);
  box-shadow: 0 0 0 1px var(--color-gold);
}

.asset-lib-item.is-disabled {
  opacity: 0.48;
}

.asset-lib-hit {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.asset-lib-hit:disabled {
  cursor: not-allowed;
}

.asset-lib-stage {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 10;
  overflow: hidden;
  background: var(--color-canvas);
}

.asset-lib-media {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.asset-lib-media--image {
  object-fit: contain;
}

.asset-lib-audio-stage {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  background: radial-gradient(circle at 50% 48%, rgb(212 175 55 / 12%), var(--color-canvas) 74%);
}

.asset-lib-audio-wave {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 30px;
  opacity: 0.45;
}

.asset-lib-audio-wave i {
  display: block;
  width: 3px;
  border-radius: 3px;
  background: var(--color-gold-soft);
}

.asset-lib-audio-wave i:nth-child(1) { height: 12px; }
.asset-lib-audio-wave i:nth-child(2) { height: 22px; }
.asset-lib-audio-wave i:nth-child(3) { height: 30px; }
.asset-lib-audio-wave i:nth-child(4) { height: 18px; }
.asset-lib-audio-wave i:nth-child(5) { height: 10px; }

.asset-lib-audio-wave.is-playing {
  opacity: 0.85;
}

.asset-lib-audio-wave.is-playing i {
  animation: asset-wave 0.9s ease-in-out infinite alternate;
}

.asset-lib-audio-wave.is-playing i:nth-child(2) { animation-delay: 0.15s; }
.asset-lib-audio-wave.is-playing i:nth-child(3) { animation-delay: 0.3s; }
.asset-lib-audio-wave.is-playing i:nth-child(4) { animation-delay: 0.45s; }
.asset-lib-audio-wave.is-playing i:nth-child(5) { animation-delay: 0.6s; }

@keyframes asset-wave {
  from { transform: scaleY(0.45); }
  to { transform: scaleY(1.1); }
}

.asset-lib-audio-btn {
  position: absolute;
  top: calc((100% - 35px) / 2);
  left: 50%;
  z-index: 2;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 1px solid rgb(212 175 55 / 45%);
  background: rgb(12 13 17 / 80%);
  color: var(--color-gold-soft);
  transform: translate(-50%, -50%);
  cursor: pointer;
  backdrop-filter: blur(6px);
  transition: transform 140ms ease, background 140ms ease;
}

.asset-lib-audio-btn:hover,
.asset-lib-audio-btn.is-playing {
  background: var(--color-gold);
  color: #14120c;
  transform: translate(-50%, -50%) scale(1.06);
}

.asset-lib-text-stage {
  display: flex;
  align-items: flex-start;
  width: 100%;
  height: 100%;
  padding: 28px 12px 12px;
  background: var(--color-elevated);
}

.asset-lib-text-stage p {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-muted);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.asset-lib-placeholder {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  color: var(--color-muted);
  background: var(--color-elevated);
}

.asset-lib-caption {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 35px;
  padding: 8px 10px;
  border-top: 1px solid var(--border-subtle);
  background: var(--color-surface);
}

.asset-lib-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text);
}

.asset-lib-tag {
  flex: none;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--color-elevated);
  border: 1px solid var(--border-subtle);
  color: var(--color-muted);
  font-size: 10px;
}

.asset-lib-order {
  position: absolute;
  top: 7px;
  left: 7px;
  z-index: 3;
  display: grid;
  place-items: center;
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  border-radius: 99px;
  background: var(--color-gold);
  color: #14120c;
  font-size: 11px;
  font-weight: 700;
  pointer-events: none;
}

.asset-lib-status-badge {
  position: absolute;
  top: 7px;
  left: 7px;
  z-index: 3;
  padding: 2px 6px;
  border-radius: 5px;
  background: rgb(10 11 14 / 82%);
  color: var(--color-muted);
  font-size: 10px;
  pointer-events: none;
}

.asset-lib-kind-badge {
  position: absolute;
  top: 7px;
  left: 7px;
  z-index: 2;
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: rgb(10 11 14 / 72%);
  color: #e9e4d8;
  backdrop-filter: blur(4px);
  pointer-events: none;
}

.asset-lib-actions {
  position: absolute;
  top: 7px;
  right: 7px;
  z-index: 3;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  opacity: 0;
  transition: opacity 140ms ease;
}

.asset-lib-item:hover .asset-lib-actions,
.asset-lib-item:focus-within .asset-lib-actions,
.asset-lib-actions:has(.is-danger-confirm) {
  opacity: 1;
}

.asset-lib-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 26px;
  height: 26px;
  padding: 0 5px;
  border: 1px solid rgb(255 255 255 / 14%);
  border-radius: 6px;
  background: rgb(12 13 17 / 80%);
  color: #f3f1ec;
  cursor: pointer;
  backdrop-filter: blur(6px);
  transition: background 140ms ease, border-color 140ms ease, color 140ms ease;
}

.asset-lib-action-btn:hover {
  border-color: rgb(212 175 55 / 55%);
  color: var(--color-gold-soft);
}

.asset-lib-action-btn.is-danger-confirm {
  border-color: rgb(239 68 68 / 65%);
  background: rgb(220 38 38 / 90%);
  color: #fff;
}

.asset-lib-confirm-txt {
  font-size: 11px;
  font-weight: 600;
  padding: 0 2px;
}

.asset-lib-empty {
  margin: 24px 0 8px;
  text-align: center;
  font-size: 13px;
  color: var(--color-muted);
}

.asset-lib-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-subtle);
}

.asset-lib-count {
  font-size: 12px;
  color: var(--color-muted);
  font-variant-numeric: tabular-nums;
}

.asset-lib-footer-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 640px) {
  .asset-lib-search {
    width: 100%;
  }
  .asset-lib-grid {
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  }
}
</style>
