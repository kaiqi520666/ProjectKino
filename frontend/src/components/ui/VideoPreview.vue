<script setup lang="ts">
import { computed, ref } from 'vue'
import { Download, Loader2 } from 'lucide-vue-next'
import MediaPlayer from './MediaPlayer.vue'
import MediaPreviewDialog from './MediaPreviewDialog.vue'

const props = defineProps<{ src: string; title: string; poster?: string; autoplay?: boolean }>()
const open = defineModel<boolean>('open', { default: false })
const player = ref<InstanceType<typeof MediaPlayer>>()
const downloading = ref(false)

const downloadFilename = computed(() => {
  const cleaned = props.title.trim().replace(/[\\/:*?"<>|]+/g, '_') || 'video'
  return /\.(mp4|mov|webm|m4v|mkv)$/i.test(cleaned) ? cleaned : `${cleaned}.mp4`
})

async function downloadVideo() {
  if (!props.src || downloading.value) return
  downloading.value = true
  try {
    const response = await fetch(props.src)
    if (!response.ok) throw new Error('download_failed')
    const blob = await response.blob()
    const blobUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = downloadFilename.value
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(blobUrl), 1000)
  } catch {
    const link = document.createElement('a')
    link.href = props.src
    link.download = downloadFilename.value
    link.target = '_blank'
    link.rel = 'noopener'
    document.body.appendChild(link)
    link.click()
    link.remove()
  } finally {
    downloading.value = false
  }
}
</script>

<template>
  <MediaPreviewDialog v-model:open="open" :title="title" @keydown="player?.handlePreviewKey($event)">
    <template v-if="$slots.trigger" #trigger><slot name="trigger" /></template>
    <template #header-actions>
      <button
        v-if="src"
        type="button"
        class="ui-icon-button video-preview-download"
        :disabled="downloading"
        aria-label="下载视频"
        title="下载视频"
        @click="downloadVideo"
      >
        <Loader2 v-if="downloading" class="video-preview-spin" :size="18" aria-hidden="true" />
        <Download v-else :size="18" aria-hidden="true" />
      </button>
    </template>
    <MediaPlayer
      v-if="open"
      :key="src"
      ref="player"
      kind="video"
      :src="src"
      :label="title"
      :poster="poster"
      :autoplay="autoplay"
      @backdrop-click="open = false"
    />
  </MediaPreviewDialog>
</template>

<style scoped>
.video-preview-download {
  width: 40px;
  height: 40px;
  color: var(--color-text);
  background: var(--color-elevated);
  border-color: var(--border-control);
}
.video-preview-download:is(:hover, :focus-visible):not(:disabled) {
  border-color: rgb(240 184 75 / 45%);
  color: var(--color-gold-soft);
}
.video-preview-spin {
  animation: video-preview-spin 1s linear infinite;
}
@keyframes video-preview-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
