<script setup lang="ts">
import { computed, ref } from 'vue'
import { Film, Play } from 'lucide-vue-next'

const props = defineProps<{ src: string; label: string; poster?: string; duration?: number }>()
const emit = defineEmits<{ ratio: [value: number] }>()
const measuredDuration = ref(0)
const failed = ref(false)
const time = computed(() => {
  const duration = measuredDuration.value || props.duration || 0
  if (!duration) return ''
  return Math.floor(duration / 60) + ':' + String(Math.floor(duration % 60)).padStart(2, '0')
})

function metadata(event: Event) {
  const video = event.currentTarget as HTMLVideoElement
  measuredDuration.value = Number.isFinite(video.duration) ? video.duration : 0
  if (video.videoWidth > 0 && video.videoHeight > 0) emit('ratio', video.videoWidth / video.videoHeight)
}
</script>

<template>
  <button type="button" class="video-thumbnail" :aria-label="label" :title="label">
    <video v-if="!failed" :src="src" :poster="poster" muted playsinline preload="metadata" aria-hidden="true"
      @loadedmetadata="metadata" @error="failed = true" />
    <img v-else-if="poster" :src="poster" alt="" />
    <Film v-else :size="28" class="video-thumbnail-fallback" aria-hidden="true" />
    <span class="video-thumbnail-play"><Play :size="19" aria-hidden="true" /></span>
    <span v-if="time" class="video-thumbnail-time">{{ time }}</span>
  </button>
</template>

<style scoped>
.video-thumbnail {
  display: grid; place-items: center; position: relative; width: 100%; height: 100%;
  overflow: hidden; border-radius: 5px; background: var(--color-canvas); color: var(--color-text); cursor: pointer;
}
.video-thumbnail :is(video, img) { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; }
.video-thumbnail-fallback { position: absolute; top: 10px; left: 10px; color: var(--color-muted); }
.video-thumbnail-play {
  position: relative; display: grid; place-items: center; width: 44px; height: 44px;
  border: 1px solid rgb(255 255 255 / 38%); border-radius: 50%; background: rgb(7 8 10 / 78%);
  transition: color .15s, background .15s, border-color .15s;
}
.video-thumbnail-play svg { margin-left: 2px; fill: currentColor; }
.video-thumbnail:is(:hover, :focus-visible) .video-thumbnail-play { background: var(--color-gold); border-color: var(--color-gold); color: var(--color-canvas); }
.video-thumbnail-time {
  position: absolute; right: 8px; bottom: 8px; padding: 2px 6px;
  border-radius: 4px; background: rgb(7 8 10 / 88%); font-size: var(--font-size-caption); font-variant-numeric: tabular-nums;
}
</style>
