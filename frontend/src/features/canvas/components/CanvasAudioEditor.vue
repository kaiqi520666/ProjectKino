<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import type { CanvasMedia } from '../canvas-model'

const props = defineProps<{ mode: 'trim' | 'clip' | 'speed'; media: CanvasMedia }>()
const emit = defineEmits<{ close: []; replace: [file: File] }>()
const open = ref(true)
const begin = ref(0)
const end = ref(0)
const duration = ref(0)
const rate = ref(1.25)
const busy = ref(false)
const error = ref('')
const title = computed(() => props.mode === 'speed' ? '调整音频倍速' : props.mode === 'clip' ? '提取音频片段' : '裁剪音频')
const valid = computed(() => duration.value > 0 && (props.mode === 'speed' || (begin.value >= 0 && end.value <= duration.value && end.value > begin.value)))
let closed = false
onBeforeUnmount(() => { closed = true })

function readDuration(event: Event) {
  const media = event.target as HTMLAudioElement
  if (!Number.isFinite(media.duration)) return
  duration.value = end.value = media.duration
  if (props.mode === 'speed') media.playbackRate = rate.value
}

function changeRate(event: Event) {
  const audio = (event.currentTarget as HTMLElement).closest('.canvas-audio-editor')?.querySelector('audio')
  if (audio) audio.playbackRate = rate.value
}

function pcmWave(buffer: AudioBuffer, startFrame: number, endFrame: number, speed: number) {
  const channels = Array.from({ length: buffer.numberOfChannels }, (_, index) => buffer.getChannelData(index))
  const frames = Math.max(1, Math.floor((endFrame - startFrame) / speed))
  const block = channels.length * 2
  const bytes = new ArrayBuffer(44 + frames * block)
  const file = new DataView(bytes)
  function ascii(offset: number, value: string) {
    for (let i = 0; i < value.length; i++) file.setUint8(offset + i, value.charCodeAt(i))
  }
  ascii(0, 'RIFF')
  file.setUint32(4, bytes.byteLength - 8, true)
  ascii(8, 'WAVE')
  ascii(12, 'fmt ')
  file.setUint32(16, 16, true)
  file.setUint16(20, 1, true)
  file.setUint16(22, channels.length, true)
  file.setUint32(24, buffer.sampleRate, true)
  file.setUint32(28, buffer.sampleRate * block, true)
  file.setUint16(32, block, true)
  file.setUint16(34, 16, true)
  ascii(36, 'data')
  file.setUint32(40, frames * block, true)
  for (let i = 0; i < frames; i++) {
    const position = startFrame + i * speed
    const left = Math.floor(position)
    const right = Math.min(left + 1, endFrame - 1)
    for (const [channel, samples] of channels.entries()) {
      const value = (samples[left] ?? 0) * (1 - (position - left)) + (samples[right] ?? 0) * (position - left)
      const clipped = Math.max(-1, Math.min(1, value))
      file.setInt16(44 + i * block + channel * 2, clipped * (clipped < 0 ? 32768 : 32767), true)
    }
  }
  return bytes
}

async function save() {
  if (!valid.value || busy.value) return
  busy.value = true
  error.value = ''
  const context = new AudioContext()
  try {
    const response = await fetch(props.media.url)
    if (!response.ok) throw new Error()
    const audio = await context.decodeAudioData(await response.arrayBuffer())
    const start = props.mode !== 'speed' ? Math.floor(begin.value * audio.sampleRate) : 0
    const stop = props.mode !== 'speed' ? Math.min(audio.length, Math.floor(end.value * audio.sampleRate)) : audio.length
    if (stop <= start) throw new Error()
    const bytes = pcmWave(audio, start, stop, props.mode === 'speed' ? rate.value : 1)
    if (closed) return
    emit('replace', new File([bytes], props.media.name.replace(/\.[^.]+$/, '') + '.wav', { type: 'audio/wav' }))
    emit('close')
  } catch {
    error.value = '无法处理这段音频'
  } finally {
    await context.close()
    busy.value = false
  }
}
</script>

<template>
  <UiDialog v-model:open="open" :title="title" @update:open="!$event && emit('close')">
    <div class="canvas-audio-editor">
      <audio :src="media.url" controls preload="metadata" @loadedmetadata="readDuration" @error="error = '无法读取这段音频'" />
      <div v-if="mode !== 'speed'" class="canvas-audio-range">
        <label>开始（秒）<input v-model.number="begin" type="number" min="0" :max="duration" step="0.01" :disabled="!duration || busy" /></label>
        <label>结束（秒）<input v-model.number="end" type="number" :min="begin" :max="duration" step="0.01" :disabled="!duration || busy" /></label>
      </div>
      <label v-else>播放倍速
        <select v-model.number="rate" @change="changeRate"><option v-for="value in [0.5, 0.75, 1, 1.25, 1.5, 2]" :key="value" :value="value">{{ value }}×</option></select>
      </label>
      <p v-if="error" role="alert">{{ error }}</p>
    </div>
    <template #footer>
      <UiButton variant="ghost" @click="emit('close')">取消</UiButton>
      <UiButton variant="primary" :disabled="!valid || busy" @click="save">{{ busy ? '正在处理' : '应用' }}</UiButton>
    </template>
  </UiDialog>
</template>

<style scoped>
.canvas-audio-editor { display: grid; gap: 14px; }
.canvas-audio-editor audio { width: 100%; }
.canvas-audio-range { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.canvas-audio-editor label { display: grid; gap: 6px; font-size: var(--font-size-body); }
.canvas-audio-editor :is(input, select) { padding: 7px; border: 1px solid var(--border-control); border-radius: 5px; background: var(--color-elevated); }
</style>
