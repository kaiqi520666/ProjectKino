<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { CalendarDays, LayoutDashboard, Plus, Save } from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiInput from '@/components/ui/UiInput.vue'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import { useCanvasStore } from '../canvas-store'

const router = useRouter()
const store = useCanvasStore()
const createOpen = ref(false)
const draftName = ref('')

function openCreate() {
  draftName.value = ''
  createOpen.value = true
}

function createCanvas() {
  const name = draftName.value.trim()
  if (!name) return

  const id = store.createCanvas(name)
  createOpen.value = false
  void router.push({ name: 'canvas-editor', params: { canvasId: id } })
}
</script>

<template>
  <section class="canvas-page" aria-labelledby="canvas-page-title">
    <WorkspacePageHeader eyebrow="创作工具" title="画布" title-id="canvas-page-title" :badge="store.canvases.length">
      <template #icon><LayoutDashboard :size="19" :stroke-width="1.7" /></template>
      <template #actions>
        <UiButton variant="primary" size="sm" @click="openCreate">
          <template #leading><Plus :size="15" aria-hidden="true" /></template>
          新建画布
        </UiButton>
      </template>
    </WorkspacePageHeader>

    <div class="canvas-list-heading">
      <div class="canvas-list-title">
        <LayoutDashboard :size="16" aria-hidden="true" />
        <h2>我的画布</h2>
        <span>{{ store.canvases.length }}</span>
      </div>
      <span class="canvas-list-hint">最近编辑</span>
    </div>

    <ul class="canvas-grid" aria-label="画布列表">
      <li v-for="canvas in store.canvases" :key="canvas.id">
        <RouterLink class="canvas-card" :to="{ name: 'canvas-editor', params: { canvasId: canvas.id } }">
          <div class="canvas-card-cover">
            <img v-if="canvas.cover" :src="canvas.cover" alt="" />
            <LayoutDashboard v-else :size="32" :stroke-width="1.3" aria-hidden="true" />
            <span class="canvas-card-badge">{{ canvas.nodes.length }} 个节点</span>
          </div>
          <div class="canvas-card-body">
            <h3>{{ canvas.name }}</h3>
            <p>{{ canvas.description }}</p>
            <div class="canvas-card-meta">
              <span><CalendarDays :size="14" aria-hidden="true" />{{ canvas.updatedAt }}</span>
            </div>
          </div>
        </RouterLink>
      </li>
    </ul>

    <UiDialog v-model:open="createOpen" title="新建画布" description="先为你的创作空间设置一个名称。">
      <form id="canvas-create-form" class="canvas-create-form" @submit.prevent="createCanvas">
        <UiInput v-model="draftName" label="画布名称" placeholder="例如：第一集分镜灵感" required autofocus />
      </form>
      <template #footer>
        <UiButton variant="ghost" @click="createOpen = false">取消</UiButton>
        <UiButton type="submit" form="canvas-create-form" variant="primary" :disabled="!draftName.trim()">
          <template #leading><Save :size="15" aria-hidden="true" /></template>
          创建画布
        </UiButton>
      </template>
    </UiDialog>
  </section>
</template>

<style scoped>
.canvas-page { width: 100%; padding: 20px 24px 40px; }
.canvas-list-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 20px 0 12px; }
.canvas-list-title { display: flex; align-items: center; gap: 8px; }
.canvas-list-title svg { color: var(--color-gold-soft); }
.canvas-list-title h2 { margin: 0; font-size: var(--font-size-body); font-weight: 600; }
.canvas-list-title span { color: var(--color-muted); font-size: var(--font-size-caption); }
.canvas-list-hint { color: var(--color-muted); font-size: var(--font-size-caption); }
.canvas-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr)); gap: 16px; margin: 0; padding: 0; list-style: none; }
.canvas-card { display: block; overflow: hidden; min-width: 0; border: 1px solid var(--border-subtle); border-radius: 8px; background: var(--color-surface); color: inherit; text-decoration: none; }
.canvas-card:hover { border-color: var(--focus-ring); }
.canvas-card-cover { position: relative; display: grid; place-items: center; overflow: hidden; aspect-ratio: 16 / 8; background: var(--color-elevated); color: var(--color-muted); }
.canvas-card-cover::after { position: absolute; inset: 0; background: linear-gradient(180deg, transparent 42%, rgb(5 6 8 / 45%)); content: ''; pointer-events: none; }
.canvas-card-cover img { width: 100%; height: 100%; object-fit: cover; }
.canvas-card-badge { position: absolute; right: 10px; bottom: 8px; z-index: 1; padding: 2px 7px; border: 1px solid rgb(255 217 138 / 28%); border-radius: 5px; background: rgb(9 10 13 / 76%); color: var(--color-gold-soft); font-size: 11px; }
.canvas-card-body { padding: 14px; }
.canvas-card-body h3 { margin: 0; overflow: hidden; color: var(--color-text); font-size: var(--font-size-body); font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.canvas-card-body p { display: -webkit-box; overflow: hidden; min-height: 44px; margin: 6px 0 14px; color: var(--color-muted); font-size: var(--font-size-caption); line-height: 1.6; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.canvas-card-meta { display: flex; flex-wrap: wrap; gap: 8px 14px; padding-top: 10px; border-top: 1px solid var(--border-subtle); color: var(--color-muted); font-size: 11px; }
.canvas-card-meta span { display: inline-flex; align-items: center; gap: 5px; }
.canvas-create-form { display: grid; gap: 12px; }
@media (max-width: 640px) {
  .canvas-page { padding: 18px 16px 32px; }
  .canvas-list-heading { margin-top: 16px; }
}
</style>
