<script setup lang="ts">
import { computed, onMounted, ref, useTemplateRef } from 'vue'
import {
  Image as ImageIcon,
  Palette,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Star,
  Trash2,
  Upload,
} from 'lucide-vue-next'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDataTable, { type DataTableColumn } from '@/components/ui/UiDataTable.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiSegmented, { type UiSegmentedOption } from '@/components/ui/UiSegmented.vue'
import UiSwitch from '@/components/ui/UiSwitch.vue'
import UiTextarea from '@/components/ui/UiTextarea.vue'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import {
  createAdminArtStyle,
  deleteAdminArtStyle,
  listAdminArtStyles,
  updateAdminArtStyle,
  uploadArtStyleImageToOss,
  type AdminArtStyleItem,
} from '@/features/art-styles/api'
import { useArtStylesStore } from '@/features/art-styles/art-styles-store'
import { extractErrorMessage } from '@/features/admin/format'
import { useUiStore } from '@/stores/ui'

type StatusFilter = 'all' | 'enabled' | 'disabled'

const ui = useUiStore()
const artStylesStore = useArtStylesStore()

const loading = ref(false)
const items = ref<AdminArtStyleItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const statusFilter = ref<StatusFilter>('all')

const editorOpen = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)
const uploading = ref(false)
const togglingId = ref<number | null>(null)
const deletingId = ref<number | null>(null)
const uploadMetaText = ref('')
const fileInput = useTemplateRef<HTMLInputElement>('fileInput')

const previewOpen = ref(false)
const previewItem = ref<AdminArtStyleItem | null>(null)

const form = ref({
  code: '',
  label: '',
  prompt: '',
  imageKey: '',
  imageUrl: '',
  sortOrder: '100',
  isEnabled: true,
  isDefault: false,
})

const isEditing = computed(() => editingId.value !== null)

const statusOptions: readonly UiSegmentedOption[] = [
  { value: 'all', label: '全部' },
  { value: 'enabled', label: '启用中' },
  { value: 'disabled', label: '已停用' },
]

const statusFilterModel = computed({
  get: () => statusFilter.value,
  set: (val: string) => {
    const next = val as StatusFilter
    if (statusFilter.value === next) return
    statusFilter.value = next
    void loadStyles(true)
  },
})

const columns: DataTableColumn[] = [
  { key: 'preview', label: '封面', width: '92px' },
  { key: 'label', label: '画风名称', width: '188px' },
  { key: 'code', label: '标识', width: '168px' },
  { key: 'prompt', label: '提示词' },
  { key: 'sortOrder', label: '排序', align: 'right', width: '76px' },
  { key: 'projectCount', label: '项目数', align: 'right', width: '80px' },
  { key: 'status', label: '状态', width: '88px' },
  { key: 'actions', label: '操作', align: 'right', width: '230px' },
]

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(2)} MB`
}

async function loadStyles(resetPage = false) {
  if (resetPage) page.value = 1
  loading.value = true
  try {
    const res = await listAdminArtStyles({
      keyword: keyword.value.trim() || undefined,
      status: statusFilter.value,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    })
    items.value = res.items
    total.value = res.total
  } catch (err) {
    ui.notify(extractErrorMessage(err, '加载画风列表失败'), 'error')
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  editingId.value = null
  uploadMetaText.value = ''
  const maxSort = items.value.reduce((acc, item) => Math.max(acc, item.sortOrder), 0)
  form.value = {
    code: '',
    label: '',
    prompt: '',
    imageKey: '',
    imageUrl: '',
    sortOrder: String(maxSort > 0 ? maxSort + 10 : 10),
    isEnabled: true,
    isDefault: items.value.length === 0,
  }
  editorOpen.value = true
}

function openEditDialog(row: AdminArtStyleItem) {
  editingId.value = row.id
  uploadMetaText.value = ''
  form.value = {
    code: row.code,
    label: row.label,
    prompt: row.prompt,
    imageKey: row.imageKey,
    imageUrl: row.imageUrl,
    sortOrder: String(row.sortOrder),
    isEnabled: row.isEnabled,
    isDefault: row.isDefault,
  }
  editorOpen.value = true
}

function openPreview(row: AdminArtStyleItem) {
  previewItem.value = row
  previewOpen.value = true
}

function triggerFilePick() {
  fileInput.value?.click()
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const raw = input.files?.[0]
  input.value = ''
  if (!raw) return
  if (!raw.type.startsWith('image/')) {
    ui.notify('请选择图片文件', 'error')
    return
  }
  if (raw.size > 20 * 1024 * 1024) {
    ui.notify('原图体积不能超过 20 MB', 'error')
    return
  }

  uploading.value = true
  try {
    const uploaded = await uploadArtStyleImageToOss(raw, form.value.code)
    form.value.imageKey = uploaded.key
    form.value.imageUrl = uploaded.url
    uploadMetaText.value = `WebP · ${formatBytes(uploaded.size)}`
    ui.notify('封面已压缩并上传至 OSS', 'success')
  } catch (err) {
    ui.notify(extractErrorMessage(err, '上传封面失败'), 'error')
  } finally {
    uploading.value = false
  }
}

async function submitEditor() {
  const code = form.value.code.trim().toLowerCase()
  const label = form.value.label.trim()
  const prompt = form.value.prompt.trim()
  const sortOrder = Math.max(0, Math.round(Number(form.value.sortOrder) || 0))

  if (!isEditing.value && !/^[a-z0-9]+(?:-[a-z0-9]+)*$/u.test(code)) {
    ui.notify('标识仅支持小写字母、数字和连字符（如 ink-painting）', 'error')
    return
  }
  if (!label) {
    ui.notify('请输入画风名称', 'error')
    return
  }
  if (!prompt) {
    ui.notify('请输入画风提示词', 'error')
    return
  }
  if (!form.value.imageKey || !form.value.imageUrl) {
    ui.notify('请先上传画风封面图', 'error')
    return
  }

  saving.value = true
  try {
    if (editingId.value === null) {
      await createAdminArtStyle({
        code,
        label,
        prompt,
        imageKey: form.value.imageKey,
        imageUrl: form.value.imageUrl,
        sortOrder,
        isEnabled: form.value.isDefault ? true : form.value.isEnabled,
        isDefault: form.value.isDefault,
      })
      ui.notify('画风已新增', 'success')
    } else {
      await updateAdminArtStyle(editingId.value, {
        label,
        prompt,
        imageKey: form.value.imageKey,
        imageUrl: form.value.imageUrl,
        sortOrder,
        isEnabled: form.value.isDefault ? true : form.value.isEnabled,
        isDefault: form.value.isDefault ? true : undefined,
      })
      ui.notify('画风已更新', 'success')
    }
    editorOpen.value = false
    await Promise.all([loadStyles(false), artStylesStore.refresh()])
  } catch (err) {
    ui.notify(extractErrorMessage(err, '保存画风失败'), 'error')
  } finally {
    saving.value = false
  }
}

async function setAsDefault(row: AdminArtStyleItem) {
  if (row.isDefault || togglingId.value !== null) return
  togglingId.value = row.id
  try {
    await updateAdminArtStyle(row.id, { isDefault: true, isEnabled: true })
    ui.notify(`已将「${row.label}」设为默认画风`, 'success')
    await Promise.all([loadStyles(false), artStylesStore.refresh()])
  } catch (err) {
    ui.notify(extractErrorMessage(err, '设置默认画风失败'), 'error')
  } finally {
    togglingId.value = null
  }
}

async function toggleEnabled(row: AdminArtStyleItem) {
  if (togglingId.value !== null) return
  togglingId.value = row.id
  try {
    await updateAdminArtStyle(row.id, { isEnabled: !row.isEnabled })
    ui.notify(row.isEnabled ? `已停用「${row.label}」` : `已启用「${row.label}」`, 'success')
    await Promise.all([loadStyles(false), artStylesStore.refresh()])
  } catch (err) {
    ui.notify(extractErrorMessage(err, '切换状态失败'), 'error')
  } finally {
    togglingId.value = null
  }
}

async function handleDelete(row: AdminArtStyleItem) {
  if (deletingId.value !== null) return
  if (!window.confirm(`确认删除画风「${row.label}」？此操作不可撤销，并会同步删除 OSS 封面文件。`)) {
    return
  }
  deletingId.value = row.id
  try {
    await deleteAdminArtStyle(row.id)
    ui.notify('画风已删除', 'success')
    await Promise.all([loadStyles(false), artStylesStore.refresh()])
  } catch (err) {
    ui.notify(extractErrorMessage(err, '删除画风失败'), 'error')
  } finally {
    deletingId.value = null
  }
}

onMounted(() => {
  void loadStyles(true)
})
</script>

<template>
  <section class="admin-section admin-page-shell">
    <WorkspacePageHeader title="画风管理">
      <template #icon><Palette :size="19" :stroke-width="1.7" /></template>
      <template #actions>
        <UiButton variant="outline" size="sm" :disabled="loading" @click="loadStyles(false)">
          <template #leading><RefreshCw :size="13" :class="{ 'ui-spin': loading }" aria-hidden="true" /></template>
          刷新
        </UiButton>
        <UiButton variant="primary" size="sm" @click="openCreateDialog">
          <template #leading><Plus :size="14" aria-hidden="true" /></template>
          新增画风
        </UiButton>
      </template>
    </WorkspacePageHeader>

    <div class="art-admin-toolbar">
      <UiSegmented v-model="statusFilterModel" :options="statusOptions" variant="pills" aria-label="按状态筛选" />
      <div class="art-admin-search">
        <UiInput
          v-model="keyword"
          size="sm"
          clearable
          placeholder="搜索名称、标识或提示词"
          @keyup.enter="loadStyles(true)"
          @clear="loadStyles(true)"
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
      empty-text="暂无画风配置"
      paginated
      :total="total"
      :page-size-options="[20, 50, 100]"
      @change="loadStyles(false)"
    >
      <template #cell-preview="{ row }">
        <button
          type="button"
          class="art-admin-thumb"
          :title="`预览 ${row.label}`"
          @click="openPreview(row)"
        >
          <img :src="row.imageUrl" :alt="row.label" loading="lazy" decoding="async" />
        </button>
      </template>

      <template #cell-label="{ row }">
        <div class="admin-inline-meta">
          <strong>{{ row.label }}</strong>
          <UiBadge v-if="row.isDefault" tone="gold">默认</UiBadge>
        </div>
      </template>

      <template #cell-code="{ row }">
        <code class="admin-mono admin-muted">{{ row.code }}</code>
      </template>

      <template #cell-prompt="{ row }">
        <span class="art-admin-prompt" :title="row.prompt">{{ row.prompt }}</span>
      </template>

      <template #cell-sortOrder="{ row }">
        <span class="admin-mono">{{ row.sortOrder }}</span>
      </template>

      <template #cell-projectCount="{ row }">
        <span class="admin-mono admin-muted">{{ row.projectCount }}</span>
      </template>

      <template #cell-status="{ row }">
        <UiBadge :tone="row.isEnabled ? 'success' : 'neutral'">
          {{ row.isEnabled ? '启用中' : '已停用' }}
        </UiBadge>
      </template>

      <template #cell-actions="{ row }">
        <div class="art-admin-actions">
          <UiButton variant="ghost" size="xs" @click="openEditDialog(row)">
            <template #leading><Pencil :size="12" aria-hidden="true" /></template>
            编辑
          </UiButton>
          <UiButton
            v-if="!row.isDefault"
            variant="ghost"
            size="xs"
            :disabled="togglingId === row.id"
            @click="setAsDefault(row)"
          >
            <template #leading><Star :size="12" aria-hidden="true" /></template>
            设默认
          </UiButton>
          <UiButton
            v-if="!row.isDefault"
            variant="outline"
            size="xs"
            :disabled="togglingId === row.id"
            @click="toggleEnabled(row)"
          >
            {{ row.isEnabled ? '停用' : '启用' }}
          </UiButton>
          <UiButton
            v-if="!row.isDefault"
            variant="danger"
            size="xs"
            :disabled="deletingId === row.id || row.projectCount > 0"
            :title="row.projectCount > 0 ? '已有项目引用，不可删除' : '删除画风'"
            @click="handleDelete(row)"
          >
            <template #leading><Trash2 :size="12" aria-hidden="true" /></template>
            删除
          </UiButton>
        </div>
      </template>
    </UiDataTable>

    <!-- 新增 / 编辑画风弹窗 -->
    <UiDialog v-model:open="editorOpen" :title="isEditing ? '编辑画风' : '新增画风'" size="wide">
      <form class="art-admin-form" @submit.prevent="submitEditor">
        <div class="art-admin-cover-row">
          <div class="art-admin-cover-box">
            <img v-if="form.imageUrl" :src="form.imageUrl" :alt="form.label || '画风封面'" />
            <div v-else class="art-admin-cover-empty">
              <ImageIcon :size="20" aria-hidden="true" />
              <span>16:9 封面预览</span>
            </div>
          </div>
          <div class="art-admin-cover-ctrl">
            <input
              ref="fileInput"
              type="file"
              accept="image/*"
              class="sr-only"
              @change="handleFileChange"
            />
            <UiButton
              type="button"
              variant="outline"
              size="sm"
              :loading="uploading"
              @click="triggerFilePick"
            >
              <template v-if="!uploading" #leading><Upload :size="13" aria-hidden="true" /></template>
              {{ form.imageUrl ? '替换封面' : '上传封面' }}
            </UiButton>
            <UiBadge v-if="uploadMetaText" tone="gold">{{ uploadMetaText }}</UiBadge>
          </div>
        </div>

        <div class="art-admin-grid">
          <UiInput
            v-model="form.label"
            label="画风名称"
            placeholder="例如 国风水墨画"
            required
          />
          <UiInput
            v-model="form.code"
            label="唯一标识（code）"
            placeholder="例如 ink-painting"
            :disabled="isEditing"
            required
          />
          <UiInput
            v-model="form.sortOrder"
            type="number"
            label="排序权重（越小越靠前）"
            placeholder="100"
          />
        </div>

        <UiTextarea
          v-model="form.prompt"
          label="画风提示词"
          placeholder="描述纯视觉媒介、笔法、光影与色彩质感"
          :rows="4"
          required
        />

        <div class="art-admin-switches">
          <UiSwitch
            v-model="form.isEnabled"
            label="启用画风"
            :disabled="form.isDefault"
          />
          <UiSwitch
            v-model="form.isDefault"
            label="设为默认画风"
          />
        </div>

        <div class="art-admin-foot">
          <UiButton type="button" variant="outline" size="sm" :disabled="saving" @click="editorOpen = false">
            取消
          </UiButton>
          <UiButton type="submit" variant="primary" size="sm" :loading="saving" :disabled="uploading">
            {{ isEditing ? '保存修改' : '确认新增' }}
          </UiButton>
        </div>
      </form>
    </UiDialog>

    <!-- 封面大图预览弹窗 -->
    <UiDialog v-model:open="previewOpen" :title="previewItem ? `${previewItem.label} (${previewItem.code})` : '画风预览'" size="wide">
      <div v-if="previewItem" class="art-admin-preview">
        <img :src="previewItem.imageUrl" :alt="previewItem.label" />
        <p class="art-admin-preview-prompt">{{ previewItem.prompt }}</p>
      </div>
    </UiDialog>
  </section>
</template>

<style scoped>
.art-admin-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px 12px;
}

.art-admin-search {
  width: 224px;
}

.art-admin-thumb {
  display: block;
  width: 64px;
  aspect-ratio: 16 / 9;
  padding: 0;
  overflow: hidden;
  border: 1px solid var(--border-control);
  border-radius: var(--radius-control-xs);
  background: var(--color-canvas);
  cursor: pointer;
}

.art-admin-thumb img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.art-admin-thumb:hover {
  border-color: var(--color-gold);
}

.art-admin-prompt {
  display: block;
  max-width: 360px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-muted);
}

.art-admin-actions {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}

.art-admin-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.art-admin-cover-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.art-admin-cover-box {
  width: 220px;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border: 1px solid var(--border-control);
  border-radius: var(--radius-control-sm);
  background: var(--color-canvas);
  flex-shrink: 0;
}

.art-admin-cover-box img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.art-admin-cover-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  height: 100%;
  color: var(--color-muted);
  font-size: 12px;
}

.art-admin-cover-ctrl {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.art-admin-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.art-admin-switches {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 10px 14px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-control-sm);
  background: var(--color-canvas);
}

.art-admin-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.art-admin-preview {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.art-admin-preview img {
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  border-radius: var(--radius-control-sm);
  border: 1px solid var(--border-subtle);
}

.art-admin-preview-prompt {
  margin: 0;
  color: var(--color-muted);
  font-size: 13px;
  line-height: 1.7;
}

.admin-muted {
  color: var(--color-muted);
}

@media (max-width: 720px) {
  .art-admin-grid,
  .art-admin-switches {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
