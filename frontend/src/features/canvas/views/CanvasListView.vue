<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { CalendarDays, LayoutDashboard, Plus, Save, Trash2 } from 'lucide-vue-next'
import EmptyState from '@/components/business/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiInput from '@/components/ui/UiInput.vue'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import { formatDateTime } from '@/lib/format'
import { useUiStore } from '@/stores/ui'
import { apiErrorMessage } from '../api'
import type { CanvasDocument } from '../canvas-model'
import { useCanvasStore } from '../canvas-store'

const router = useRouter()
const store = useCanvasStore()
const ui = useUiStore()
const createOpen = ref(false)
const creating = ref(false)
const draftName = ref('')
const draftDescription = ref('')
const deleteOpen = ref(false)
const deleting = ref(false)
const canvasToDelete = ref<CanvasDocument>()

onMounted(async () => {
  try {
    await store.fetchCanvases()
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  }
})

function openCreate() {
  draftName.value = ''
  draftDescription.value = ''
  createOpen.value = true
}

async function createCanvas() {
  const name = draftName.value.trim()
  if (!name || creating.value) return
  creating.value = true
  try {
    const created = await store.createCanvas(name, draftDescription.value.trim())
    createOpen.value = false
    void router.push({ name: 'canvas-editor', params: { canvasId: created.id } })
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    creating.value = false
  }
}

function confirmDelete(canvas: CanvasDocument) {
  canvasToDelete.value = canvas
  deleteOpen.value = true
}

async function deleteCanvas() {
  const target = canvasToDelete.value
  if (!target || deleting.value) return
  deleting.value = true
  try {
    await store.deleteCanvas(target.id)
    deleteOpen.value = false
    canvasToDelete.value = undefined
    ui.notify(`已删除画布「${target.name}」`, 'success')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <section class="canvas-page" aria-labelledby="canvas-page-title">
    <WorkspacePageHeader title="画布" title-id="canvas-page-title" :badge="store.canvases.length">
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

    <p v-if="store.canvasesLoading && !store.canvases.length" class="canvas-list-status">正在加载画布…</p>

    <EmptyState
      v-else-if="!store.canvases.length"
      title="还没有画布"
      description="创建一张自由画布，串联文本、图片与视频生成节点。"
    >
      <UiButton variant="primary" size="sm" @click="openCreate">
        <template #leading><Plus :size="15" aria-hidden="true" /></template>
        新建画布
      </UiButton>
    </EmptyState>

    <ul v-else class="canvas-grid" aria-label="画布列表">
      <li v-for="canvas in store.canvases" :key="canvas.id" class="canvas-card-item">
        <RouterLink class="canvas-card" :to="{ name: 'canvas-editor', params: { canvasId: canvas.id } }">
          <div class="canvas-card-cover">
            <img v-if="canvas.cover" :src="canvas.cover" alt="" />
            <LayoutDashboard v-else :size="32" :stroke-width="1.3" aria-hidden="true" />
            <span class="canvas-card-badge">{{ canvas.nodeCount }} 个节点</span>
          </div>
          <div class="canvas-card-body">
            <h3>{{ canvas.name }}</h3>
            <p>{{ canvas.description || '自由组合文本、图片与视频节点' }}</p>
            <div class="canvas-card-meta">
              <span><CalendarDays :size="14" aria-hidden="true" />{{ formatDateTime(canvas.updatedAt) }}</span>
            </div>
          </div>
        </RouterLink>
        <button
          type="button"
          class="canvas-card-delete"
          :aria-label="`删除画布 ${canvas.name}`"
          title="删除画布"
          @click.stop.prevent="confirmDelete(canvas)"
        >
          <Trash2 :size="14" aria-hidden="true" />
        </button>
      </li>
    </ul>

    <UiDialog v-model:open="createOpen" title="新建画布" description="先为你的创作空间设置一个名称。">
      <form id="canvas-create-form" class="canvas-create-form" @submit.prevent="createCanvas">
        <UiInput v-model="draftName" label="画布名称" placeholder="例如：第一集分镜灵感" required autofocus />
        <UiInput v-model="draftDescription" label="简介（可选）" placeholder="记录这张画布的用途或主题" />
      </form>
      <template #footer>
        <UiButton variant="ghost" :disabled="creating" @click="createOpen = false">取消</UiButton>
        <UiButton type="submit" form="canvas-create-form" variant="primary" :disabled="!draftName.trim() || creating" :loading="creating">
          <template #leading><Save :size="15" aria-hidden="true" /></template>
          创建画布
        </UiButton>
      </template>
    </UiDialog>

    <UiDialog
      v-model:open="deleteOpen"
      title="删除画布"
      :description="canvasToDelete ? `确认删除画布「${canvasToDelete.name}」吗？删除后将无法在列表中继续编辑。` : ''"
    >
      <template #footer>
        <UiButton variant="ghost" :disabled="deleting" @click="deleteOpen = false">取消</UiButton>
        <UiButton variant="danger" :disabled="deleting" :loading="deleting" @click="deleteCanvas">
          确认删除
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
.canvas-list-status { padding: 36px 0; text-align: center; color: var(--color-muted); font-size: var(--font-size-body); }
.canvas-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr)); gap: 16px; margin: 0; padding: 0; list-style: none; }
.canvas-card-item { position: relative; min-width: 0; }
.canvas-card { display: block; overflow: hidden; min-width: 0; border: 1px solid var(--border-subtle); border-radius: 8px; background: var(--color-surface); color: inherit; text-decoration: none; transition: border-color .15s; }
.canvas-card:hover { border-color: var(--focus-ring); }
.canvas-card-delete { position: absolute; top: 8px; right: 8px; z-index: 2; display: grid; place-items: center; width: 30px; height: 30px; border: 1px solid rgb(255 255 255 / 14%); border-radius: 6px; background: rgb(9 10 13 / 78%); color: var(--color-muted); opacity: 0; cursor: pointer; transition: opacity .15s, color .15s, border-color .15s; }
.canvas-card-item:hover .canvas-card-delete, .canvas-card-delete:focus-visible { opacity: 1; }
.canvas-card-delete:hover { color: var(--color-error); border-color: rgb(239 146 146 / 45%); }
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
  .canvas-card-delete { opacity: 1; }
}
</style>
