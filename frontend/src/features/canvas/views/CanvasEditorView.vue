<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import EmptyState from '@/components/business/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { apiErrorMessage } from '../api'
import CanvasEditorSurface from '../components/CanvasEditorSurface.vue'
import { useCanvasStore } from '../canvas-store'

const props = defineProps<{ canvasId: string }>()
const router = useRouter()
const store = useCanvasStore()

const loading = ref(false)
const loadError = ref('')

const canvas = computed(() => {
  const found = store.getCanvas(props.canvasId)
  return found?.loaded ? found : undefined
})

async function loadCanvas(id: string) {
  loading.value = true
  loadError.value = ''
  try {
    await Promise.all([
      store.fetchCanvasDetail(id),
      store.assetsLoaded ? Promise.resolve() : store.fetchAssets().catch(() => {}),
    ])
  } catch (error) {
    loadError.value = apiErrorMessage(error)
  } finally {
    loading.value = false
  }
}

watch(
  () => props.canvasId,
  (id) => {
    if (id) void loadCanvas(id)
  },
  { immediate: true },
)
</script>

<template>
  <CanvasEditorSurface v-if="canvas" :key="canvas.id" :canvas="canvas" />
  <main v-else class="canvas-editor-state">
    <p v-if="loading" class="canvas-editor-loading">正在加载画布…</p>
    <EmptyState
      v-else
      title="无法打开画布"
      :description="loadError || '该画布不存在或已被删除。'"
    >
      <div class="canvas-editor-state-actions">
        <UiButton variant="secondary" size="sm" @click="router.push({ name: 'canvas' })">返回画布列表</UiButton>
        <UiButton variant="primary" size="sm" @click="loadCanvas(canvasId)">重新加载</UiButton>
      </div>
    </EmptyState>
  </main>
</template>

<style scoped>
.canvas-editor-state {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100dvh;
  padding: 24px;
  background: var(--color-canvas);
  color: var(--color-text);
}

.canvas-editor-loading {
  color: var(--color-muted);
  font-size: var(--font-size-body);
}

.canvas-editor-state-actions {
  display: flex;
  gap: 10px;
}
</style>
