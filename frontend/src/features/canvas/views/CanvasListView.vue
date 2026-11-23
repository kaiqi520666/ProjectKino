<script setup lang="ts">
import { onMounted, ref, useTemplateRef } from 'vue'
import { useRouter } from 'vue-router'
import {
  CalendarDays,
  FolderOpen,
  Image as ImageIcon,
  LayoutDashboard,
  Pencil,
  Plus,
  Save,
  Trash2,
  Upload,
  X,
} from 'lucide-vue-next'
import EmptyState from '@/components/business/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiTextarea from '@/components/ui/UiTextarea.vue'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import AssetLibraryDialog from '@/features/assets/AssetLibraryDialog.vue'
import type { AssetLibraryItem } from '@/features/assets/asset-library-types'
import { formatDateTime } from '@/lib/format'
import { useUiStore } from '@/stores/ui'
import { apiErrorMessage, uploadFileToOss } from '../api'
import type { CanvasDocument } from '../canvas-model'
import { useCanvasStore } from '../canvas-store'

const router = useRouter()
const store = useCanvasStore()
const ui = useUiStore()

const createOpen = ref(false)
const creating = ref(false)
const draftName = ref('')
const draftDescription = ref('')

const editOpen = ref(false)
const editing = ref(false)
const uploadingCover = ref(false)
const coverLibraryOpen = ref(false)
const canvasToEdit = ref<CanvasDocument>()
const editName = ref('')
const editDescription = ref('')
const editCover = ref<string | null>(null)
const editCoverKey = ref<string | null>(null)
const coverFileInput = useTemplateRef<HTMLInputElement>('coverFileInput')

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

function openEdit(canvas: CanvasDocument) {
  canvasToEdit.value = canvas
  editName.value = canvas.name
  editDescription.value = canvas.description || ''
  editCover.value = canvas.cover ?? null
  editCoverKey.value = canvas.coverKey ?? null
  editOpen.value = true
}

function handleSelectCover(item: AssetLibraryItem) {
  if (!item.mediaUrl) return
  editCover.value = item.mediaUrl
  editCoverKey.value = item.mediaKey ?? null
}

async function handleUploadCover(event: Event) {
  const input = event.currentTarget as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!file.type.startsWith('image/')) {
    ui.notify('请选择图片文件', 'error')
    return
  }
  uploadingCover.value = true
  try {
    const uploaded = await uploadFileToOss(file, 'image')
    editCover.value = uploaded.url
    editCoverKey.value = uploaded.key
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    uploadingCover.value = false
  }
}

function clearCover() {
  editCover.value = null
  editCoverKey.value = null
}

async function saveEdit() {
  const target = canvasToEdit.value
  const name = editName.value.trim()
  if (!target || !name || editing.value || uploadingCover.value) return
  editing.value = true
  try {
    await store.updateCanvasMeta(target, {
      name,
      description: editDescription.value,
      cover: editCover.value,
      coverKey: editCoverKey.value,
    })
    editOpen.value = false
    canvasToEdit.value = undefined
    ui.notify('画布信息已更新', 'success')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    editing.value = false
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
            <p>{{ canvas.description || '暂无简介' }}</p>
            <div class="canvas-card-meta">
              <span><CalendarDays :size="14" aria-hidden="true" />{{ formatDateTime(canvas.updatedAt) }}</span>
            </div>
          </div>
        </RouterLink>
        <div class="canvas-card-actions">
          <button
            type="button"
            class="canvas-card-action"
            :aria-label="`编辑画布 ${canvas.name}`"
            title="编辑"
            @click.stop.prevent="openEdit(canvas)"
          >
            <Pencil :size="13" aria-hidden="true" />
          </button>
          <button
            type="button"
            class="canvas-card-action canvas-card-action--danger"
            :aria-label="`删除画布 ${canvas.name}`"
            title="删除"
            @click.stop.prevent="confirmDelete(canvas)"
          >
            <Trash2 :size="13" aria-hidden="true" />
          </button>
        </div>
      </li>
    </ul>

    <UiDialog v-model:open="createOpen" title="新建画布">
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

    <UiDialog v-model:open="editOpen" title="编辑画布">
      <form id="canvas-edit-form" class="canvas-create-form" @submit.prevent="saveEdit">
        <UiInput v-model="editName" label="名称" required autofocus />
        <UiTextarea v-model="editDescription" label="简介" :rows="2" />
        <div class="canvas-cover-field">
          <span class="ui-label">封面图</span>
          <input ref="coverFileInput" type="file" accept="image/*" hidden @change="handleUploadCover" />
          <div class="canvas-cover-preview">
            <img v-if="editCover" :src="editCover" alt="" />
            <div v-else class="canvas-cover-empty">
              <ImageIcon :size="22" :stroke-width="1.5" aria-hidden="true" />
              <span>暂无封面</span>
            </div>
            <button
              v-if="editCover"
              type="button"
              class="canvas-cover-clear"
              title="移除封面"
              aria-label="移除封面"
              @click="clearCover"
            >
              <X :size="13" aria-hidden="true" />
            </button>
          </div>
          <div class="canvas-cover-actions">
            <UiButton
              type="button"
              variant="outline"
              size="sm"
              :loading="uploadingCover"
              @click="coverFileInput?.click()"
            >
              <template #leading><Upload :size="14" aria-hidden="true" /></template>
              本地上传
            </UiButton>
            <UiButton
              type="button"
              variant="outline"
              size="sm"
              :disabled="uploadingCover"
              @click="coverLibraryOpen = true"
            >
              <template #leading><FolderOpen :size="14" aria-hidden="true" /></template>
              素材库
            </UiButton>
          </div>
        </div>
      </form>
      <template #footer>
        <UiButton variant="ghost" :disabled="editing" @click="editOpen = false">取消</UiButton>
        <UiButton
          type="submit"
          form="canvas-edit-form"
          variant="primary"
          :disabled="!editName.trim() || editing || uploadingCover"
          :loading="editing"
        >
          <template #leading><Save :size="15" aria-hidden="true" /></template>
          保存
        </UiButton>
      </template>
    </UiDialog>

    <AssetLibraryDialog
      v-model:open="coverLibraryOpen"
      title="素材库"
      mode="single"
      :allowed-kinds="['image']"
      require-http-url
      @select="handleSelectCover"
    />

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
.canvas-list-status { padding: 36px 0; text-align: center; color: var(--color-muted); font-size: var(--font-size-body); }
.canvas-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr)); gap: 16px; margin: 20px 0 0; padding: 0; list-style: none; }
.canvas-card-item { position: relative; min-width: 0; }
.canvas-card { display: block; overflow: hidden; min-width: 0; border: 1px solid var(--border-subtle); border-radius: 8px; background: var(--color-surface); color: inherit; text-decoration: none; transition: border-color .15s; }
.canvas-card:hover { border-color: var(--focus-ring); }
.canvas-card-actions { position: absolute; top: 8px; right: 8px; z-index: 2; display: inline-flex; gap: 5px; opacity: 0; transition: opacity .15s; }
.canvas-card-item:hover .canvas-card-actions,
.canvas-card-item:focus-within .canvas-card-actions { opacity: 1; }
.canvas-card-action { display: grid; place-items: center; width: 28px; height: 28px; border: 1px solid rgb(255 255 255 / 14%); border-radius: 6px; background: rgb(9 10 13 / 80%); color: #e5e2dc; cursor: pointer; backdrop-filter: blur(6px); transition: color .15s, border-color .15s; }
.canvas-card-action:hover { color: var(--color-gold-soft); border-color: rgb(240 184 75 / 45%); }
.canvas-card-action--danger:hover { color: var(--color-error); border-color: rgb(239 146 146 / 45%); }
.canvas-card-cover { position: relative; display: grid; place-items: center; overflow: hidden; aspect-ratio: 16 / 8; background: var(--color-elevated); color: var(--color-muted); }
.canvas-card-cover::after { position: absolute; inset: 0; background: linear-gradient(180deg, transparent 42%, rgb(5 6 8 / 45%)); content: ''; pointer-events: none; }
.canvas-card-cover img { width: 100%; height: 100%; object-fit: cover; object-position: center 20%; }
.canvas-card-badge { position: absolute; right: 10px; bottom: 8px; z-index: 1; padding: 2px 7px; border: 1px solid rgb(255 217 138 / 28%); border-radius: 5px; background: rgb(9 10 13 / 76%); color: var(--color-gold-soft); font-size: 11px; }
.canvas-card-body { padding: 14px; }
.canvas-card-body h3 { margin: 0; overflow: hidden; color: var(--color-text); font-size: var(--font-size-body); font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.canvas-card-body p { display: -webkit-box; overflow: hidden; min-height: 44px; margin: 6px 0 14px; color: var(--color-muted); font-size: var(--font-size-caption); line-height: 1.6; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.canvas-card-meta { display: flex; flex-wrap: wrap; gap: 8px 14px; padding-top: 10px; border-top: 1px solid var(--border-subtle); color: var(--color-muted); font-size: 11px; }
.canvas-card-meta span { display: inline-flex; align-items: center; gap: 5px; }
.canvas-create-form { display: grid; gap: 14px; }
.canvas-cover-field { display: flex; flex-direction: column; gap: 8px; }
.canvas-cover-preview { position: relative; display: grid; place-items: center; width: 100%; aspect-ratio: 16 / 8; overflow: hidden; border: 1px solid var(--border-subtle); border-radius: 8px; background: var(--color-canvas); }
.canvas-cover-preview img { width: 100%; height: 100%; object-fit: contain; display: block; }
.canvas-cover-empty { display: grid; justify-items: center; gap: 6px; color: var(--color-muted); font-size: 12px; }
.canvas-cover-clear { position: absolute; top: 8px; right: 8px; display: grid; place-items: center; width: 26px; height: 26px; border: 1px solid rgb(255 255 255 / 16%); border-radius: 6px; background: rgb(10 11 14 / 80%); color: #f3f1ec; cursor: pointer; }
.canvas-cover-clear:hover { color: var(--color-error); border-color: rgb(239 146 146 / 50%); }
.canvas-cover-actions { display: flex; gap: 8px; }
@media (max-width: 640px) {
  .canvas-page { padding: 18px 16px 32px; }
  .canvas-card-actions { opacity: 1; }
}
</style>
