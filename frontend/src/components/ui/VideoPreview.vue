<script setup lang="ts">
import { ref } from 'vue'
import MediaPlayer from './MediaPlayer.vue'
import MediaPreviewDialog from './MediaPreviewDialog.vue'

defineProps<{ src: string; title: string; poster?: string; autoplay?: boolean }>()
const open = defineModel<boolean>('open', { default: false })
const player = ref<InstanceType<typeof MediaPlayer>>()
</script>

<template>
  <MediaPreviewDialog v-model:open="open" :title="title" @keydown="player?.handlePreviewKey($event)">
    <template v-if="$slots.trigger" #trigger><slot name="trigger" /></template>
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
