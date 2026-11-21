<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Maximize, Minimize, Pause, Play, Volume2, VolumeX } from 'lucide-vue-next'

const props = defineProps<{
  kind: 'video' | 'audio'
  src: string
  label: string
  poster?: string
  autoplay?: boolean
}>()
const emit = defineEmits<{ backdropClick: [] }>()
const root = ref<HTMLElement>()
const player = ref<HTMLMediaElement>()
const duration = ref(0)
const time = ref(0)
const playing = ref(false)
const muted = ref(false)
const volume = ref(1)
const error = ref(false)
const loading = ref(props.kind === 'video')
const isFullscreen = ref(false)
const peaks = ref<number[]>([])
const waveformRequest = new AbortController()
const progress = computed(() => duration.value ? time.value / duration.value : 0)

function sync() {
  const media = player.value
  if (!media) return
  duration.value = Number.isFinite(media.duration) ? media.duration : 0
  time.value = media.currentTime
  playing.value = !media.paused
  muted.value = media.muted
  volume.value = media.volume
}

async function togglePlayback() {
  const media = player.value
  if (!media) return
  if (media.paused) {
    try {
      await media.play()
    } catch (cause) {
      loading.value = false
      if (!(cause instanceof DOMException && cause.name === 'AbortError')) error.value = true
      sync()
    }
  } else media.pause()
}

function isInsideRenderedVideo(video: HTMLVideoElement, clientX: number, clientY: number) {
  const rect = video.getBoundingClientRect()
  if (!rect.width || !rect.height) return true
  const vw = video.videoWidth
  const vh = video.videoHeight
  if (!vw || !vh) return true
  const boxRatio = rect.width / rect.height
  const videoRatio = vw / vh
  let renderW = rect.width
  let renderH = rect.height
  if (videoRatio > boxRatio) {
    renderH = rect.width / videoRatio
  } else {
    renderW = rect.height * videoRatio
  }
  const left = rect.left + (rect.width - renderW) / 2
  const top = rect.top + (rect.height - renderH) / 2
  return clientX >= left && clientX <= left + renderW && clientY >= top && clientY <= top + renderH
}

function handleVideoClick(event: MouseEvent) {
  if (props.kind !== 'video') return
  const media = player.value
  if (
    media instanceof HTMLVideoElement
    && !isFullscreen.value
    && !isInsideRenderedVideo(media, event.clientX, event.clientY)
  ) {
    emit('backdropClick')
    return
  }
  void togglePlayback()
}

function handleRootClick(event: MouseEvent) {
  if (props.kind === 'video' && !isFullscreen.value && event.target === root.value) {
    emit('backdropClick')
  }
}

function seek(event: Event) {
  if (player.value && duration.value) player.value.currentTime = +(event.target as HTMLInputElement).value
}

function changeVolume(event: Event) {
  if (!player.value) return
  player.value.volume = +(event.target as HTMLInputElement).value
  player.value.muted = false
}

function toggleMute() {
  if (player.value) player.value.muted = !player.value.muted
}

function handlePreviewKey(event: KeyboardEvent) {
  if (error.value || event.defaultPrevented || event.isComposing || event.altKey || event.ctrlKey || event.metaKey) return
  const target = event.target
  if (target instanceof HTMLElement && target.closest('input, textarea, select, [contenteditable]')) return
  if (event.key === ' ' && !(target instanceof HTMLElement && target.closest('button, a'))) {
    event.preventDefault()
    void togglePlayback()
  } else if (duration.value && player.value && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
    event.preventDefault()
    const offset = event.key === 'ArrowLeft' ? -5 : 5
    player.value.currentTime = Math.max(0, Math.min(duration.value, player.value.currentTime + offset))
  }
}

function formatTime(seconds: number) {
  return Math.floor(seconds / 60) + ':' + String(Math.floor(seconds % 60)).padStart(2, '0')
}

async function fullscreen() {
  if (!(player.value instanceof HTMLVideoElement)) return false
  const element = root.value
  try {
    if (document.fullscreenElement === element) {
      await document.exitFullscreen()
      return true
    }
    if (element?.requestFullscreen) {
      await element.requestFullscreen()
      return true
    }
    const video = player.value as HTMLVideoElement & { webkitEnterFullscreen?: () => void }
    if (video.webkitEnterFullscreen) {
      video.webkitEnterFullscreen()
      return true
    }
  } catch {
    return false
  }
  return false
}

function readFullscreen() {
  isFullscreen.value = !!root.value && document.fullscreenElement === root.value
}

async function loadWaveform() {
  if (props.kind !== 'audio' || !window.OfflineAudioContext) return
  try {
    const response = await fetch(props.src, { signal: waveformRequest.signal })
    if (!response.ok) return
    const bytes = await response.arrayBuffer()
    const audio = await new OfflineAudioContext(1, 1, 8000).decodeAudioData(bytes)
    if (waveformRequest.signal.aborted) return
    const samples = audio.getChannelData(0)
    const step = Math.max(1, Math.floor(samples.length / 88))
    const levels = Array.from({ length: 88 }, (_, index) => {
      let peak = 0
      const start = index * step
      for (let i = start; i < Math.min(start + step, samples.length); i += 1) {
        peak = Math.max(peak, Math.abs(samples[i] ?? 0))
      }
      return peak
    })
    const max = Math.max(...levels, .01)
    peaks.value = levels.map(level => Math.max(2, level / max * 58))
  } catch {
    // Playback and seeking remain available when decoding the waveform fails.
  }
}

onMounted(() => {
  void loadWaveform()
  if (props.autoplay && props.kind === 'video' && player.value) {
    player.value.play().then(() => {
      loading.value = false
      sync()
    }).catch(() => {
      // 若浏览器策略拦截自动播放，保持就绪态由用户手动点播放。
      sync()
    })
  }
})
onBeforeUnmount(() => {
  player.value?.pause()
  waveformRequest.abort()
})
defineExpose({ handlePreviewKey })
</script>

<template>
  <div ref="root" class="canvas-player" :class="'is-' + kind" @fullscreenchange="readFullscreen" @click="handleRootClick">
    <component
      :is="kind" ref="player" :src="src" :aria-label="label" :poster="kind === 'video' ? poster : undefined" playsinline
      :preload="kind === 'video' ? 'auto' : 'metadata'"
      @loadedmetadata="sync" @timeupdate="sync" @durationchange="sync" @playing="loading = false; sync()" @pause="sync" @ended="sync"
      @loadeddata="loading = false" @canplay="loading = false" @waiting="loading = true"
      @volumechange="sync" @error="error = true" @click="handleVideoClick"
    />
    <p v-if="error" class="canvas-player-status" role="status">无法播放此文件</p>
    <p v-else-if="loading && kind === 'video'" class="canvas-player-status" role="status">正在加载视频</p>
    <div v-else-if="kind === 'audio'" class="canvas-waveform nodrag nopan">
      <svg v-if="peaks.length" viewBox="0 0 264 68" preserveAspectRatio="none" aria-hidden="true">
        <line v-for="(peak, index) in peaks" :key="index" :x1="index * 3 + 1.5" :x2="index * 3 + 1.5" :y1="34 - peak / 2" :y2="34 + peak / 2"
          :class="{ 'is-played': index / peaks.length < progress }" />
      </svg>
      <span v-else class="canvas-waveform-baseline"></span>
      <span class="canvas-waveform-head" :style="{ left: progress * 100 + '%' }"></span>
      <input aria-label="播放进度" type="range" min="0" :max="duration || 1" step="any" :value="time" :disabled="!duration" @input="seek">
    </div>
    <div v-if="!error" class="canvas-player-controls nodrag nopan" @click.stop @keydown="kind === 'audio' && $event.stopPropagation()">
      <input v-if="kind === 'video'" class="video-progress" aria-label="播放进度" type="range" min="0" :max="duration || 1"
        step="any" :value="time" :style="{ '--video-progress': progress * 100 + '%' }" :disabled="!duration" @input="seek">
      <div class="canvas-player-actions">
        <button type="button" :aria-label="playing ? '暂停' : '播放'" :title="playing ? '暂停' : '播放'" @click="togglePlayback">
          <Pause v-if="playing" :size="17" /><Play v-else :size="17" />
        </button>
        <span>{{ formatTime(time) }} / {{ formatTime(duration) }}</span>
        <div class="canvas-player-volume">
          <button type="button" :aria-label="muted ? '取消静音' : '静音'" :title="muted ? '取消静音' : '静音'" @click="toggleMute">
            <VolumeX v-if="muted || !volume" :size="17" /><Volume2 v-else :size="17" />
          </button>
          <div class="canvas-volume-slider"><input type="range" min="0" max="1" step=".05" :value="muted ? 0 : volume" aria-label="音量" @input="changeVolume"></div>
        </div>
        <button v-if="kind === 'video'" type="button" :aria-label="isFullscreen ? '退出全屏' : '全屏'" :title="isFullscreen ? '退出全屏' : '全屏'" @click="fullscreen">
          <Minimize v-if="isFullscreen" :size="17" /><Maximize v-else :size="17" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.canvas-player { position: relative; }
.canvas-player.is-video {
  display: grid; grid-template-rows: minmax(0, 1fr) auto; gap: 8px;
  width: min(100%, 1440px); height: 100%; min-height: 0; margin-inline: auto;
}
.canvas-player video { display: block; width: 100%; height: 100%; object-fit: contain; cursor: pointer; }
.canvas-player:fullscreen { width: 100%; padding: 12px; background: #000; }
.canvas-player audio { display: none; }
.canvas-player-controls { min-height: 28px; color: var(--color-muted); font-size: var(--font-size-caption); font-variant-numeric: tabular-nums; }
.canvas-player-actions { display: flex; align-items: center; gap: 6px; }
.canvas-player-controls button { display: grid; place-items: center; width: 26px; height: 26px; border-radius: 4px; cursor: pointer; }
.canvas-player-controls button:hover { background: var(--gold-tint); color: var(--color-gold-soft); }
.canvas-player-controls input { accent-color: var(--color-gold); cursor: pointer; }
.is-video .canvas-player-controls {
  width: 100%; padding: 8px 12px 6px; border: 1px solid var(--border-control);
  border-radius: 8px; background: var(--color-surface); color: var(--color-text);
}
.is-video .canvas-player-actions { min-height: 40px; gap: 10px; }
.is-video .canvas-player-controls button { width: 36px; height: 36px; border-radius: 5px; }
.video-progress { display: block; width: 100%; height: 18px; appearance: none; background: transparent; }
.video-progress::-webkit-slider-runnable-track {
  height: 4px; border-radius: 4px;
  background: linear-gradient(to right, var(--color-gold) var(--video-progress), var(--border-control) var(--video-progress));
}
.video-progress::-webkit-slider-thumb { width: 12px; height: 12px; margin-top: -4px; appearance: none; border-radius: 50%; background: var(--color-gold); }
.video-progress::-moz-range-track { height: 4px; border-radius: 4px; background: var(--border-control); }
.video-progress::-moz-range-progress { height: 4px; border-radius: 4px; background: var(--color-gold); }
.video-progress::-moz-range-thumb { width: 12px; height: 12px; border: 0; border-radius: 50%; background: var(--color-gold); }
.video-progress:disabled { opacity: .5; cursor: default; }
.canvas-player-volume { position: relative; display: flex; align-items: center; gap: 4px; margin-left: auto; }
.canvas-volume-slider { display: flex; align-items: center; }
.is-audio .canvas-volume-slider {
  display: none; position: absolute; z-index: 1; right: 0; bottom: 100%; padding: 7px;
  border: 1px solid var(--border-control); border-radius: 5px; background: var(--color-surface);
}
.is-audio .canvas-player-volume:is(:hover, :focus-within) .canvas-volume-slider { display: flex; }
.canvas-volume-slider input { width: 75px; }
.canvas-waveform { position: relative; height: 76px; border-radius: 4px; background: var(--color-canvas); }
.canvas-waveform svg { width: 100%; height: 100%; stroke: var(--color-muted); stroke-width: 1.6; }
.canvas-waveform .is-played { stroke: var(--color-gold); }
.canvas-waveform-head, .canvas-waveform-baseline { position: absolute; pointer-events: none; }
.canvas-waveform-head { inset-block: 6px; width: 1px; background: var(--color-gold); }
.canvas-waveform-baseline { inset: 50% 0 auto; border-top: 1px solid var(--border-control); }
.canvas-waveform input { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; }
.canvas-waveform:focus-within { outline: 1px solid var(--color-gold); }
.canvas-player-status {
  position: absolute; inset: 0; display: grid; place-items: center; margin: 0;
  color: var(--color-muted); font-size: var(--font-size-body); pointer-events: none;
}
.is-audio:has(.canvas-player-status) { min-height: 76px; }
@media (max-width: 380px) {
  .is-video .canvas-player-actions { gap: 4px; }
  .is-video .canvas-volume-slider input { width: 54px; }
}
</style>
