<script setup lang="ts">
import { inject, onMounted, reactive, ref } from 'vue'
import { FolderArchive, RefreshCw, RotateCcw, Search, Trash2 } from 'lucide-vue-next'
import UiDataTable, { type DataTableColumn } from '@/components/ui/UiDataTable.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import {
  listAdminProjects,
  purgeAdminProject,
  restoreAdminProject,
  type AdminProjectItem,
} from '@/features/admin/api'
import { extractErrorMessage, formatDateTime } from '@/features/admin/format'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const refreshReviewBadge = inject<() => Promise<void>>('refreshAdminReviewBadge')

const loading = ref(false)
const projects = ref<AdminProjectItem[]>([])
const total = ref(0)
const archivedCount = ref(0)
const page = ref(1)
const pageSize = ref(30)

const filters = reactive({
  status: 'all',
  q: '',
})

const projectColumns: DataTableColumn[] = [
  { key: 'name', label: '项目名称 / ID' },
  { key: 'owner', label: '所属用户' },
  { key: 'status', label: '状态' },
  { key: 'counts', label: '集数 / 资产 / 镜头' },
  { key: 'jobs', label: '历史任务' },
  { key: 'createdAt', label: '创建时间' },
  { key: 'updatedAt', label: '最近更新' },
  { key: 'actions', label: '操作' },
]

const purgeDialogOpen = ref(false)
const purgeSubmitting = ref(false)
const purgeTarget = ref<AdminProjectItem | null>(null)
const restoringId = ref<string | null>(null)

async function loadProjects(resetPage = false) {
  if (resetPage) page.value = 1
  loading.value = true
  try {
    const res = await listAdminProjects({
      status: filters.status === 'all' ? undefined : filters.status,
      q: filters.q.trim() || undefined,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    })
    projects.value = res.items
    total.value = res.total
    archivedCount.value = res.archivedCount
    await refreshReviewBadge?.()
  } catch (err) {
    ui.notify(extractErrorMessage(err, '加载项目列表失败'), 'error')
  } finally {
    loading.value = false
  }
}

function selectStatus(status: string) {
  filters.status = status
  loadProjects(true)
}

async function handleRestore(project: AdminProjectItem) {
  restoringId.value = project.id
  try {
    await restoreAdminProject(project.id)
    ui.notify(`已恢复项目「${project.name}」`, 'success')
    await loadProjects()
  } catch (err) {
    ui.notify(extractErrorMessage(err, '恢复项目失败'), 'error')
  } finally {
    restoringId.value = null
  }
}

function openPurge(project: AdminProjectItem) {
  purgeTarget.value = project
  purgeDialogOpen.value = true
}

async function confirmPurge() {
  if (!purgeTarget.value) return
  purgeSubmitting.value = true
  try {
    const res = await purgeAdminProject(purgeTarget.value.id)
    ui.notify(
      `已彻底清理「${purgeTarget.value.name}」，删除 ${res.deletedOssCount} 个 OSS 文件`,
      'success',
    )
    purgeDialogOpen.value = false
    await loadProjects()
  } catch (err) {
    ui.notify(extractErrorMessage(err, '彻底清理项目失败'), 'error')
  } finally {
    purgeSubmitting.value = false
  }
}

onMounted(() => loadProjects(true))
</script>

<template>
  <section class="admin-section">
    <WorkspacePageHeader eyebrow="管理后台" title="项目与清理" :badge="total">
      <template #icon><FolderArchive :size="19" :stroke-width="1.7" /></template>
      <template #actions>
        <button type="button" class="ui-button ui-button--secondary ui-button--sm" :disabled="loading" @click="loadProjects()">
          <RefreshCw :size="14" :class="{ 'ui-spin': loading }" />
          <span>刷新</span>
        </button>
      </template>
    </WorkspacePageHeader>

    <form class="admin-toolbar" @submit.prevent="loadProjects(true)">
      <div class="admin-pill-bar">
        <button
          type="button"
          class="admin-pill"
          :class="{ 'is-active': filters.status === 'all' }"
          @click="selectStatus('all')"
        >
          全部项目
        </button>
        <button
          type="button"
          class="admin-pill"
          :class="{ 'is-active': filters.status === 'active' }"
          @click="selectStatus('active')"
        >
          进行中
        </button>
        <button
          type="button"
          class="admin-pill"
          :class="{ 'is-active': filters.status === 'archived' }"
          @click="selectStatus('archived')"
        >
          <span>已软删留证</span>
          <span v-if="archivedCount > 0" class="admin-mono">({{ archivedCount }})</span>
        </button>
      </div>

      <div class="admin-actions">
        <div class="ui-input-wrap has-leading admin-search-input">
          <Search :size="14" class="ui-input-icon" />
          <input v-model="filters.q" class="ui-input ui-input--sm" type="search" placeholder="搜索项目名或所属邮箱..." />
        </div>
        <button type="submit" class="ui-button ui-button--primary ui-button--sm">查询</button>
      </div>
    </form>

    <UiDataTable
      v-model:page="page"
      v-model:page-size="pageSize"
      :columns="projectColumns"
      :rows="projects"
      row-key="id"
      :loading="loading"
      loading-text="正在加载项目列表..."
      empty-text="当前筛选条件下暂无项目"
      paginated
      :total="total"
      @change="loadProjects()"
    >
      <template #cell-name="{ row }">
        <span class="admin-cell-primary" :title="`${row.name} (${row.id})`">{{ row.name }}</span>
      </template>
      <template #cell-owner="{ row }">
        <div class="admin-inline-meta" :title="`${row.userEmail} (#${row.userId})`">
          <span class="admin-cell-primary">{{ row.userEmail }}</span>
          <span class="admin-inline-sep" aria-hidden="true">·</span>
          <span class="admin-inline-sub admin-mono">#{{ row.userId }}</span>
        </div>
      </template>
      <template #cell-status="{ row }">
        <span class="admin-badge" :class="row.status === 'active' ? 'admin-badge--success' : 'admin-badge--danger'">
          {{ row.status === 'active' ? '进行中' : '已软删留证' }}
        </span>
      </template>
      <template #cell-counts="{ row }">
        <span class="admin-num">{{ row.episodeCount }} 集 / {{ row.assetCount }} 资产 / {{ row.clipCount }} 镜头</span>
      </template>
      <template #cell-jobs="{ row }">
        <span class="admin-num">{{ row.jobCount }}</span>
        <span v-if="row.activeJobCount > 0" class="admin-badge admin-badge--gold" style="margin-left: 6px;">
          运行中 {{ row.activeJobCount }}
        </span>
      </template>
      <template #cell-createdAt="{ row }">
        <span class="admin-mono">{{ formatDateTime(row.createdAt) }}</span>
      </template>
      <template #cell-updatedAt="{ row }">
        <span class="admin-mono">{{ formatDateTime(row.updatedAt) }}</span>
      </template>
      <template #cell-actions="{ row }">
        <div v-if="row.status === 'archived'" class="admin-actions">
          <button
            type="button"
            class="ui-button ui-button--secondary ui-button--xs"
            :disabled="restoringId === row.id"
            @click="handleRestore(row)"
          >
            <RotateCcw :size="12" />
            <span>{{ restoringId === row.id ? '恢复中...' : '恢复项目' }}</span>
          </button>
          <button
            type="button"
            class="ui-button ui-button--danger ui-button--xs"
            :disabled="row.activeJobCount > 0"
            :title="row.activeJobCount > 0 ? '项目仍有运行中任务，暂不可清理' : '彻底删除项目与 OSS 文件'"
            @click="openPurge(row)"
          >
            <Trash2 :size="12" />
            <span>彻底清理</span>
          </button>
        </div>
        <span v-else class="admin-cell-sub">正常使用中</span>
      </template>
    </UiDataTable>

    <UiDialog
      v-model:open="purgeDialogOpen"
      title="确认彻底清理"
      :description="purgeTarget ? `${purgeTarget.name} · ${purgeTarget.userEmail}` : ''"
    >
      <p style="margin: 0; font-size: 13px; color: var(--color-muted); line-height: 1.7;">
        不可撤销：将删除项目记录与 OSS 文件，保留积分流水和任务审计记录。
      </p>
      <template #footer>
        <button type="button" class="ui-button ui-button--secondary" @click="purgeDialogOpen = false">取消</button>
        <button type="button" class="ui-button ui-button--danger" :disabled="purgeSubmitting" @click="confirmPurge">
          {{ purgeSubmitting ? '清理中...' : '确认彻底清理' }}
        </button>
      </template>
    </UiDialog>
  </section>
</template>
