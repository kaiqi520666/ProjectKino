<script setup lang="ts">
import { inject, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Activity, Eye, RefreshCw, RotateCcw, Wrench } from 'lucide-vue-next'
import UiDataTable, { type DataTableColumn } from '@/components/ui/UiDataTable.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import {
  listAdminJobs,
  refundAdminJob,
  rescueAdminJobMedia,
  type AdminJobItem,
} from '@/features/admin/api'
import {
  extractErrorMessage,
  formatCredits,
  formatDateTime,
  JOB_STATUS_LABELS,
  JOB_TYPE_LABELS,
  RESERVATION_STATUS_LABELS,
} from '@/features/admin/format'
import { useUiStore } from '@/stores/ui'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const refreshReviewBadge = inject<() => Promise<void>>('refreshAdminReviewBadge')

const loading = ref(false)
const jobs = ref<AdminJobItem[]>([])
const total = ref(0)
const reviewCount = ref(0)
const page = ref(1)
const pageSize = ref(30)

const filters = reactive({
  status: typeof route.query.status === 'string' && route.query.status ? route.query.status : 'all',
  jobType: 'all',
})

const jobColumns: DataTableColumn[] = [
  { key: 'createdAt', label: '创建时间' },
  { key: 'jobType', label: '任务类型' },
  { key: 'status', label: '状态 / 进度' },
  { key: 'owner', label: '用户 / 项目' },
  { key: 'reservation', label: '预扣款项' },
  { key: 'upstream', label: '上游 ID / 错误摘要' },
  { key: 'actions', label: '操作' },
]

const statusPills = [
  { value: 'all', label: '全部任务' },
  { value: 'review', label: '待核对', danger: true },
  { value: 'running', label: '执行中' },
  { value: 'polling', label: '轮询中' },
  { value: 'queued', label: '排队中' },
  { value: 'succeeded', label: '成功' },
  { value: 'failed', label: '失败' },
]

const jobTypeOptions = [
  { value: 'all', label: '全部任务类型' },
  { value: 'asset_image', label: '生成资产图' },
  { value: 'clip_video', label: '生成分镜视频' },
  { value: 'compose_episode', label: '合成本集视频' },
  { value: 'compose_project', label: '合成全片' },
  { value: 'parse_novel', label: '解析小说' },
  { value: 'extract_assets', label: '提取资产' },
  { value: 'generate_episodes', label: '生成分集' },
  { value: 'generate_storyboard', label: '生成分镜' },
  { value: 'regenerate_episode_storyboard', label: '重写单集分镜' },
]

// Detail dialog
const detailDialogOpen = ref(false)
const detailJob = ref<AdminJobItem | null>(null)

// Refund dialog
const refundDialogOpen = ref(false)
const refundSubmitting = ref(false)
const refundJob = ref<AdminJobItem | null>(null)
const refundReason = ref('')

// Rescue media dialog
const rescueDialogOpen = ref(false)
const rescueSubmitting = ref(false)
const rescueJob = ref<AdminJobItem | null>(null)
const rescueForm = reactive({
  mediaUrl: '',
  note: '',
})

async function loadJobs(resetPage = false) {
  if (resetPage) page.value = 1
  loading.value = true
  try {
    const res = await listAdminJobs({
      status: filters.status === 'all' ? undefined : filters.status,
      jobType: filters.jobType === 'all' ? undefined : filters.jobType,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    })
    jobs.value = res.items
    total.value = res.total
    reviewCount.value = res.reviewCount
    await refreshReviewBadge?.()
  } catch (err) {
    ui.notify(extractErrorMessage(err, '加载任务列表失败'), 'error')
  } finally {
    loading.value = false
  }
}

function selectStatus(status: string) {
  filters.status = status
  router.replace({
    path: '/admin/jobs',
    query: status === 'all' ? {} : { status },
  })
  loadJobs(true)
}

watch(
  () => route.query.status,
  (val) => {
    const next = typeof val === 'string' && val ? val : 'all'
    if (next !== filters.status) {
      filters.status = next
      loadJobs(true)
    }
  },
)

function canRefund(job: AdminJobItem): boolean {
  return (
    (job.jobType === 'asset_image' || job.jobType === 'clip_video') &&
    job.reservationStatus === 'frozen'
  )
}

function canRescue(job: AdminJobItem): boolean {
  return (
    (job.jobType === 'asset_image' || job.jobType === 'clip_video') &&
    (job.status === 'review' || job.status === 'failed')
  )
}

function openDetail(job: AdminJobItem) {
  detailJob.value = job
  detailDialogOpen.value = true
}

function openRefund(job: AdminJobItem) {
  refundJob.value = job
  refundReason.value = '人工核对上游未出片，退还冻结积分'
  refundDialogOpen.value = true
}

async function submitRefund() {
  if (!refundJob.value) return
  if (!refundReason.value.trim()) {
    ui.notify('请填写退款原因', 'error')
    return
  }
  refundSubmitting.value = true
  try {
    const res = await refundAdminJob(refundJob.value.id, refundReason.value.trim())
    ui.notify(`已退还 ${formatCredits(res.refundedAmount)} 积分并将任务标记为失败`, 'success')
    refundDialogOpen.value = false
    await loadJobs()
  } catch (err) {
    ui.notify(extractErrorMessage(err, '退款操作失败'), 'error')
  } finally {
    refundSubmitting.value = false
  }
}

function openRescue(job: AdminJobItem) {
  rescueJob.value = job
  rescueForm.mediaUrl = ''
  rescueForm.note = ''
  rescueDialogOpen.value = true
}

async function submitRescue() {
  if (!rescueJob.value) return
  const url = rescueForm.mediaUrl.trim()
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    ui.notify('请输入有效的 http(s) 上游媒体直链', 'error')
    return
  }
  rescueSubmitting.value = true
  try {
    const res = await rescueAdminJobMedia(rescueJob.value.id, {
      mediaUrl: url,
      note: rescueForm.note.trim() || undefined,
    })
    ui.notify(
      res.settledReservation
        ? '已转存 OSS、回填成片并自动结算冻结积分'
        : '已转存 OSS 并回填成片',
      'success',
    )
    rescueDialogOpen.value = false
    await loadJobs()
  } catch (err) {
    ui.notify(extractErrorMessage(err, '补录成片失败'), 'error')
  } finally {
    rescueSubmitting.value = false
  }
}

function statusBadgeClass(status: string) {
  if (status === 'succeeded') return 'admin-badge--success'
  if (status === 'failed' || status === 'review') return 'admin-badge--danger'
  if (status === 'running' || status === 'polling') return 'admin-badge--gold'
  return ''
}

function reservationBadgeClass(status?: string | null) {
  if (status === 'frozen') return 'admin-badge--gold'
  if (status === 'settled') return 'admin-badge--success'
  if (status === 'refunded') return 'admin-badge--info'
  return ''
}

function prettyJson(obj: unknown): string {
  if (obj === null || obj === undefined) return 'null'
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

onMounted(() => loadJobs(true))
</script>

<template>
  <section class="admin-section">
    <WorkspacePageHeader eyebrow="管理后台" title="任务与核对" :badge="total">
      <template #icon><Activity :size="19" :stroke-width="1.7" /></template>
      <template #actions>
        <button type="button" class="ui-button ui-button--secondary ui-button--sm" :disabled="loading" @click="loadJobs()">
          <RefreshCw :size="14" :class="{ 'ui-spin': loading }" />
          <span>刷新</span>
        </button>
      </template>
    </WorkspacePageHeader>

    <div class="admin-toolbar">
      <div class="admin-pill-bar">
        <button
          v-for="pill in statusPills"
          :key="pill.value"
          type="button"
          class="admin-pill"
          :class="{
            'is-active': filters.status === pill.value,
            'admin-pill--danger': pill.danger,
            'has-count': pill.value === 'review' && reviewCount > 0,
          }"
          @click="selectStatus(pill.value)"
        >
          <span>{{ pill.label }}</span>
          <span v-if="pill.value === 'review' && reviewCount > 0" class="admin-mono">({{ reviewCount }})</span>
        </button>
      </div>
      <div style="width: 190px;">
        <UiSelect v-model="filters.jobType" :options="jobTypeOptions" placeholder="任务类型" @update:model-value="loadJobs(true)" />
      </div>
    </div>

    <UiDataTable
      v-model:page="page"
      v-model:page-size="pageSize"
      :columns="jobColumns"
      :rows="jobs"
      row-key="id"
      :loading="loading"
      loading-text="正在加载任务列表..."
      empty-text="当前筛选条件下暂无任务"
      paginated
      :total="total"
      @change="loadJobs()"
    >
      <template #cell-createdAt="{ row }">
        <span class="admin-mono">{{ formatDateTime(row.createdAt) }}</span>
      </template>
      <template #cell-jobType="{ row }">
        <div class="admin-cell-primary">{{ JOB_TYPE_LABELS[row.jobType] || row.jobType }}</div>
        <div class="admin-cell-sub admin-mono">{{ row.jobType }}</div>
      </template>
      <template #cell-status="{ row }">
        <span class="admin-badge" :class="statusBadgeClass(row.status)">
          {{ JOB_STATUS_LABELS[row.status] || row.status }}
        </span>
        <div class="admin-cell-sub">{{ row.progress }}% · {{ row.stepLabel || '-' }}</div>
      </template>
      <template #cell-owner="{ row }">
        <div class="admin-cell-primary">{{ row.userEmail }}</div>
        <div class="admin-cell-sub">{{ row.projectName || '无项目关联' }}</div>
      </template>
      <template #cell-reservation="{ row }">
        <template v-if="row.reservationAmount">
          <div class="admin-num">{{ formatCredits(row.reservationAmount) }} 积分</div>
          <span class="admin-badge" :class="reservationBadgeClass(row.reservationStatus)" style="margin-top: 3px;">
            {{ RESERVATION_STATUS_LABELS[row.reservationStatus || ''] || row.reservationStatus }}
          </span>
        </template>
        <span v-else class="admin-cell-sub">-</span>
      </template>
      <template #cell-upstream="{ row }">
        <div v-if="row.providerTaskId" class="admin-mono" :title="row.providerTaskId">
          {{ row.providerTaskId.slice(0, 22) }}{{ row.providerTaskId.length > 22 ? '…' : '' }}
        </div>
        <div v-if="row.errorMessage" class="admin-error-snippet" :title="row.errorMessage">
          {{ row.errorCode ? `[${row.errorCode}] ` : '' }}{{ row.errorMessage }}
        </div>
        <span v-if="!row.providerTaskId && !row.errorMessage" class="admin-cell-sub">-</span>
      </template>
      <template #cell-actions="{ row }">
        <div class="admin-actions">
          <button type="button" class="ui-button ui-button--ghost ui-button--sm" @click="openDetail(row)">
            <Eye :size="13" />
            <span>详情</span>
          </button>
          <button
            v-if="canRescue(row)"
            type="button"
            class="ui-button ui-button--outline ui-button--sm"
            @click="openRescue(row)"
          >
            <Wrench :size="13" />
            <span>补录成片</span>
          </button>
          <button
            v-if="canRefund(row)"
            type="button"
            class="ui-button ui-button--danger ui-button--sm"
            @click="openRefund(row)"
          >
            <RotateCcw :size="13" />
            <span>退还积分</span>
          </button>
        </div>
      </template>
    </UiDataTable>

    <!-- 任务详情弹窗 -->
    <UiDialog
      v-model:open="detailDialogOpen"
      size="landscape"
      :title="detailJob ? `任务详情 · ${JOB_TYPE_LABELS[detailJob.jobType] || detailJob.jobType}` : '任务详情'"
      :description="detailJob ? `Job ID: ${detailJob.id}` : ''"
    >
      <template v-if="detailJob">
        <dl class="admin-detail-grid">
          <div class="admin-detail-item">
            <dt>所属用户 / 项目</dt>
            <dd>{{ detailJob.userEmail }} · #{{ detailJob.userId }} · {{ detailJob.projectName || '-' }}</dd>
          </div>
          <div class="admin-detail-item">
            <dt>状态与步骤</dt>
            <dd>{{ JOB_STATUS_LABELS[detailJob.status] || detailJob.status }} · {{ detailJob.progress }}% · {{ detailJob.stepLabel || '-' }}</dd>
          </div>
          <div class="admin-detail-item">
            <dt>上游任务 ID</dt>
            <dd class="admin-mono">{{ detailJob.providerTaskId || '-' }}</dd>
          </div>
          <div class="admin-detail-item">
            <dt>预扣单</dt>
            <dd class="admin-mono">
              {{ detailJob.reservationAmount ? `${formatCredits(detailJob.reservationAmount)} · ${RESERVATION_STATUS_LABELS[detailJob.reservationStatus || ''] || detailJob.reservationStatus}` : '-' }}
            </dd>
          </div>
          <div class="admin-detail-item">
            <dt>创建 / 开始 / 结束时间</dt>
            <dd class="admin-mono">
              {{ formatDateTime(detailJob.createdAt) }} / {{ formatDateTime(detailJob.startedAt) }} / {{ formatDateTime(detailJob.finishedAt) }}
            </dd>
          </div>
          <div class="admin-detail-item">
            <dt>错误信息</dt>
            <dd :style="detailJob.errorMessage ? 'color: var(--color-error)' : ''">
              {{ detailJob.errorCode ? `[${detailJob.errorCode}] ` : '' }}{{ detailJob.errorMessage || '无' }}
            </dd>
          </div>
        </dl>

        <div class="admin-form-stack">
          <div v-if="detailJob.usageSummary">
            <div class="ui-label">用量摘要</div>
            <pre class="admin-json-block">{{ prettyJson(detailJob.usageSummary) }}</pre>
          </div>
          <div>
            <div class="ui-label">输入参数</div>
            <pre class="admin-json-block">{{ prettyJson(detailJob.inputPayload) }}</pre>
          </div>
          <div>
            <div class="ui-label">执行结果</div>
            <pre class="admin-json-block">{{ prettyJson(detailJob.resultPayload) }}</pre>
          </div>
        </div>
      </template>
    </UiDialog>

    <!-- 退还冻结积分弹窗 -->
    <UiDialog
      v-model:open="refundDialogOpen"
      title="退还冻结积分"
      :description="refundJob ? `退还 ${formatCredits(refundJob.reservationAmount)} 积分给 ${refundJob.userEmail}` : ''"
    >
      <div class="admin-form-stack">
        <div class="ui-field">
          <label class="ui-label">退款说明 <span class="ui-required">*</span></label>
          <input v-model="refundReason" class="ui-input" type="text" placeholder="记录核对结果" />
        </div>
      </div>
      <template #footer>
        <button type="button" class="ui-button ui-button--secondary" @click="refundDialogOpen = false">取消</button>
        <button type="button" class="ui-button ui-button--danger" :disabled="refundSubmitting" @click="submitRefund">
          {{ refundSubmitting ? '处理中...' : '确认退还积分' }}
        </button>
      </template>
    </UiDialog>

    <!-- 补录上游成片弹窗 -->
    <UiDialog
      v-model:open="rescueDialogOpen"
      size="wide"
      title="补录成片"
      :description="rescueJob ? `${JOB_TYPE_LABELS[rescueJob.jobType] || rescueJob.jobType} · ${rescueJob.userEmail}` : ''"
    >
      <div class="admin-form-stack">
        <div class="ui-field">
          <label class="ui-label">上游媒体链接 <span class="ui-required">*</span></label>
          <input
            v-model="rescueForm.mediaUrl"
            class="ui-input"
            type="url"
            placeholder="https://..."
          />
        </div>
        <div class="ui-field">
          <label class="ui-label">备注</label>
          <input
            v-model="rescueForm.note"
            class="ui-input"
            type="text"
            placeholder="可选"
          />
        </div>
      </div>
      <template #footer>
        <button type="button" class="ui-button ui-button--secondary" @click="rescueDialogOpen = false">取消</button>
        <button type="button" class="ui-button ui-button--primary" :disabled="rescueSubmitting" @click="submitRescue">
          {{ rescueSubmitting ? '转存并回填中...' : '转存 OSS 并完成结算' }}
        </button>
      </template>
    </UiDialog>
  </section>
</template>
