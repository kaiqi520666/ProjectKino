<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ImageOff, ImagePlus, RotateCcw } from 'lucide-vue-next'
import UiSkeleton from './UiSkeleton.vue'
import { imageAspectRatios } from './image-types'
import type { ImageAspectRatio, ImageFit } from './image-types'

const props = withDefaults(defineProps<{
  src?: string
  alt: string
  aspectRatio?: ImageAspectRatio | number
  fit?: ImageFit
  position?: string
  loading?: 'lazy' | 'eager'
  checkerboard?: boolean
  retryable?: boolean
}>(), {
  aspectRatio: '16:9',
  fit: 'cover',
  position: 'center',
  loading: 'lazy',
  checkerboard: false,
  retryable: true,
})
const emit = defineEmits<{ load: [event: Event]; error: [event: Event]; retry: [] }>()
const source = computed(() => props.src?.trim() || '')
const state = ref<'empty' | 'loading' | 'loaded' | 'error'>('empty')
const attempt = ref(0)
const image = ref<HTMLImageElement>()
const ratio = computed(() => {
  const value = typeof props.aspectRatio === 'number'
    ? props.aspectRatio
    : imageAspectRatios[props.aspectRatio]
  return Number.isFinite(value) && value > 0 ? value : imageAspectRatios['16:9']
})

watch(source, () => {
  state.value = source.value ? 'loading' : 'empty'
  attempt.value = 0
}, { immediate: true, flush: 'sync' })

function onLoad(event: Event) {
  if (event.currentTarget !== image.value) return
  state.value = 'loaded'
  emit('load', event)
}

function onError(event: Event) {
  if (event.currentTarget !== image.value) return
  state.value = 'error'
  emit('error', event)
}

function retry() {
  if (state.value !== 'error' || !source.value) return
  attempt.value++
  state.value = 'loading'
  emit('retry')
}
</script>

<template>
  <div
    class="ui-image"
    :class="{ 'has-checkerboard': checkerboard }"
    :style="{ aspectRatio: ratio }"
    :data-state="state"
    :aria-busy="state === 'loading' || undefined"
  >
    <img
      v-if="source && state !== 'error'"
      :key="`${source}:${attempt}`"
      ref="image"
      class="ui-image-element"
      :src="source"
      :alt="alt"
      :loading="loading"
      decoding="async"
      :style="{ objectFit: fit, objectPosition: position }"
      @load="onLoad"
      @error="onError"
    />
    <UiSkeleton v-if="state === 'loading'" class="ui-image-skeleton" width="100%" height="100%" />
    <div v-else-if="state !== 'loaded'" class="ui-image-placeholder">
      <component :is="state === 'error' ? ImageOff : ImagePlus" :size="22" :stroke-width="1.5" aria-hidden="true" />
      <span>{{ state === 'error' ? '图片加载失败' : '暂无图片' }}</span>
      <span v-if="alt" class="sr-only">{{ alt }}</span>
      <button v-if="state === 'error' && retryable" type="button" class="ui-image-retry" @click="retry">
        <RotateCcw :size="13" aria-hidden="true" />重新加载
      </button>
    </div>
  </div>
</template>
