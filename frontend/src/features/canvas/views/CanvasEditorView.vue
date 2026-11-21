<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import CanvasEditorSurface from '../components/CanvasEditorSurface.vue'
import { useCanvasStore } from '../canvas-store'

const props = defineProps<{ canvasId: string }>()
const router = useRouter()
const store = useCanvasStore()
const canvas = computed(() => store.canvases.find(item => item.id === props.canvasId))

watch(canvas, value => {
  if (!value) void router.replace({ name: 'canvas' })
}, { immediate: true })
</script>

<template>
  <CanvasEditorSurface v-if="canvas" :key="canvas.id" :canvas="canvas" />
</template>
