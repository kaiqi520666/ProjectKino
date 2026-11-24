<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  Bell,
  Copy,
  Eye,
  Maximize2,
  Minimize2,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-vue-next'
import MarkdownPreview from '@/components/ui/MarkdownPreview.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDataTable, { type DataTableColumn } from '@/components/ui/UiDataTable.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiSegmented, { type UiSegmentedOption } from '@/components/ui/UiSegmented.vue'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import {
  createAdminAnnouncement,
  deleteAdminAnnouncement,
  listAdminAnnouncements,
  updateAdminAnnouncement,
  type AdminAnnouncementItem,
} from '@/features/announcements/api'
import { extractErrorMessage, formatDateTime } from '@/features/admin/format'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

const loading = ref(false)
const items = ref<AdminAnnouncementItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')

const dialogOpen = ref(false)
const saving = ref(false)
const deletingId = ref<number | null>(null)
const editing = ref<AdminAnnouncementItem | null>(null)
const editorView = ref<'edit' | 'split' | 'preview'>('split')
const editorViewOptions: readonly UiSegmentedOption[] = [
  { value: 'edit', label: '编辑' },
  { value: 'split', label: '分栏' },
  { value: 'preview', label: '预览', icon: Eye },
]
const editorViewModel = computed({
  get: () => editorView.value,
  set: (val: string) => {
    editorView.value = val as 'edit' | 'split' | 'preview'
  },
})
const expanded = ref(false)

const form = reactive({
  title: '',
  content: '',
})

const columns: DataTableColumn[] = [
  { key: 'title', label: '标题' },
  { key: 'publishedAt', label: '发布时间', width: '168px' },
  { key: 'updatedAt', label: '更新时间', width: '168px' },
  { key: 'actions', label: '操作', align: 'right', width: '132px' },
]

function isConflictError(err: unknown): boolean {
  const status = (err as { response?: { status?: number } })?.response?.status
  return status === 409
}

async function load(resetPage = false) {
  if (resetPage) page.value = 1
  loading.value = true
  try {
    const res = await listAdminAnnouncements({
      keyword: keyword.value.trim() || undefined,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    })
    if (!res.items.length && page.value > 1) {
      page.value -= 1
      await load(false)
      return
    }
    items.value = res.items
    total.value = res.total
  } catch (err) {
    ui.notify(extractErrorMessage(err, '加载公告列表失败'), 'error')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  form.title = ''
  form.content = ''
  editorView.value = 'split'
  expanded.value = false
  dialogOpen.value = true
}

function openEdit(item: AdminAnnouncementItem) {
  editing.value = item
  form.title = item.title
  form.content = item.content
  editorView.value = 'split'
  expanded.value = false
  dialogOpen.value = true
}

async function copyContent() {
  if (!form.content) return
  try {
    await navigator.clipboard.writeText(form.content)
    ui.notify('已复制正文', 'success')
  } catch {
    ui.notify('复制失败', 'error')
  }
}

async function save() {
  if (saving.value) return
  const title = form.title.trim()
  const content = form.content
  if (!title || !content.trim()) {
    ui.notify('请填写公告标题和正文', 'error')
    return
  }
  if (content.length > 100_000) {
    ui.notify('公告正文不能超过 100000 字符', 'error')
    return
  }

  saving.value = true
  try {
    if (editing.value) {
      await updateAdminAnnouncement(editing.value.id, {
        title,
        content,
        version: editing.value.version,
      })
    } else {
      await createAdminAnnouncement({ title, content })
    }
    dialogOpen.value = false
    ui.notify('保存成功', 'success')
    await load(false)
  } catch (err) {
    ui.notify(extractErrorMessage(err, '保存公告失败'), 'error')
    if (isConflictError(err)) {
      await load(false)
    }
  } finally {
    saving.value = false
  }
}

async function remove(item: AdminAnnouncementItem) {
  if (deletingId.value !== null || saving.value) return
  if (!window.confirm(`确定删除公告「${item.title}」？`)) return
  deletingId.value = item.id
  try {
    await deleteAdminAnnouncement(item.id, item.version)
    ui.notify('已删除', 'success')
    await load(false)
  } catch (err) {
    ui.notify(extractErrorMessage(err, '删除公告失败'), 'error')
    if (isConflictError(err)) {
      await load(false)
    }
  } finally {
    deletingId.value = null
  }
}

onMounted(() => {
  void load(true)
})
</script>

<template>
  <section class="admin-section admin-page-shell">
    <WorkspacePageHeader title="系统公告">
      <template #icon><Bell :size="19" :stroke-width="1.7" /></template>
      <template #actions>
        <UiButton variant="outline" size="sm" :disabled="loading" @click="load(false)">
          <template #leading><RefreshCw :size="13" :class="{ 'ui-spin': loading }" aria-hidden="true" /></template>
          刷新
        </UiButton>
        <UiButton variant="primary" size="sm" @click="openCreate">
          <template #leading><Plus :size="14" aria-hidden="true" /></template>
          新增公告
        </UiButton>
      </template>
    </WorkspacePageHeader>

    <div class="ann-admin-toolbar">
      <div class="ann-admin-search-wrap">
        <UiInput
          v-model="keyword"
          size="sm"
          clearable
          placeholder="搜索公告标题或正文"
          @keyup.enter="load(true)"
          @clear="load(true)"
        >
          <template #leading><Search :size="13" aria-hidden="true" /></template>
        </UiInput>
      </div>
    </div>

    <UiDataTable
      v-model:page="page"
      v-model:page-size="pageSize"
      :columns="columns"
      :rows="items"
      row-key="id"
      :loading="loading"
      empty-text="暂无公告"
      paginated
      :total="total"
      :page-size-options="[20, 50]"
      @change="load(false)"
    >
      <template #cell-title="{ row }">
        <span class="ann-admin-title">{{ row.title }}</span>
      </template>

      <template #cell-publishedAt="{ row }">
        <span class="admin-mono admin-muted">{{ formatDateTime(row.publishedAt) }}</span>
      </template>

      <template #cell-updatedAt="{ row }">
        <span class="admin-mono admin-muted">{{ formatDateTime(row.updatedAt) }}</span>
      </template>

      <template #cell-actions="{ row }">
        <div class="ann-admin-actions">
          <UiButton
            variant="ghost"
            size="xs"
            :disabled="saving || deletingId !== null"
            @click="openEdit(row)"
          >
            <template #leading><Pencil :size="12" aria-hidden="true" /></template>
            编辑
          </UiButton>
          <UiButton
            variant="danger"
            size="xs"
            :disabled="saving || deletingId !== null"
            @click="remove(row)"
          >
            <template #leading><Trash2 :size="12" aria-hidden="true" /></template>
            删除
          </UiButton>
        </div>
      </template>
    </UiDataTable>

    <UiDialog
      v-model:open="dialogOpen"
      :title="editing ? '编辑公告' : '新增公告'"
      :size="expanded ? 'editor' : 'landscape'"
    >
      <form class="ann-editor-form" @submit.prevent="save">
        <UiInput
          v-model="form.title"
          label="标题"
          placeholder="输入公告标题"
          maxlength="200"
          required
        />

        <div class="ann-md-field">
          <div class="ann-md-bar">
            <span class="ui-label">正文（Markdown）<span class="ui-required">*</span></span>
            <div class="ann-md-controls">
              <UiSegmented v-model="editorViewModel" :options="editorViewOptions" size="xs" aria-label="编辑视图" />
              <UiButton variant="secondary" size="xs" title="复制正文" aria-label="复制正文" @click="copyContent">
                <template #leading><Copy :size="12" aria-hidden="true" /></template>
              </UiButton>
              <UiButton
                variant="secondary"
                size="xs"
                :title="expanded ? '还原大小' : '放大编辑区'"
                :aria-label="expanded ? '还原大小' : '放大编辑区'"
                @click="expanded = !expanded"
              >
                <template #leading>
                  <Minimize2 v-if="expanded" :size="12" aria-hidden="true" />
                  <Maximize2 v-else :size="12" aria-hidden="true" />
                </template>
              </UiButton>
            </div>
          </div>

          <div class="ann-md-panes" :class="[`is-${editorView}`, { 'is-expanded': expanded }]">
            <textarea
              v-if="editorView !== 'preview'"
              v-model="form.content"
              class="ann-md-textarea admin-mono"
              placeholder="支持标题、列表、粗体、链接、代码块等 Markdown 语法"
              maxlength="100000"
              required
            ></textarea>
            <div v-if="editorView !== 'edit'" class="ann-md-preview-pane">
              <MarkdownPreview v-if="form.content.trim()" :content="form.content" />
              <span v-else class="ann-md-empty">预览区</span>
            </div>
          </div>
        </div>

        <div class="ann-editor-foot">
          <UiButton type="button" variant="outline" size="sm" :disabled="saving" @click="dialogOpen = false">
            取消
          </UiButton>
          <UiButton type="submit" variant="primary" size="sm" :loading="saving">
            保存
          </UiButton>
        </div>
      </form>
    </UiDialog>
  </section>
</template>

<style scoped>
.admin-muted {
  color: var(--color-muted);
}

.ann-admin-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.ann-admin-search-wrap {
  width: 240px;
}

.ann-admin-title {
  font-weight: 500;
  color: var(--color-text);
}

.ann-admin-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.ann-editor-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.ann-md-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ann-md-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.ann-md-controls {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.ann-md-panes {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 12px;
  height: 380px;
}

.ann-md-panes.is-split {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.ann-md-panes.is-expanded {
  height: min(64dvh, 620px);
}

.ann-md-textarea,
.ann-md-preview-pane {
  width: 100%;
  height: 100%;
  padding: 12px 14px;
  border: 1px solid var(--border-control);
  border-radius: 8px;
  background: var(--color-canvas);
  overflow-y: auto;
}

.ann-md-textarea {
  color: var(--color-text);
  font-size: 13px;
  line-height: 1.65;
  resize: none;
  outline: none;
}

.ann-md-textarea:focus {
  border-color: rgb(240 184 75 / 55%);
}

.ann-md-empty {
  font-size: 12.5px;
  color: var(--color-muted);
}

.ann-editor-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 760px) {
  .ann-md-panes.is-split {
    grid-template-columns: minmax(0, 1fr);
    height: 480px;
  }
}
</style>
