<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Activity, AlertTriangle, Check, Copy, Eye, Image as ImageIcon, Play, RefreshCw, RotateCcw, Search, Wrench, X } from 'lucide-vue-next'
import ImagePreview from '@/components/ui/ImagePreview.vue'
import UiDataTable, { type DataTableColumn } from '@/components/ui/UiDataTable.vue'
import UiDateRangePicker from '@/components/ui/UiDateRangePicker.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import VideoPreview from '@/components/ui/VideoPreview.vue'
import {
  createDateRangePreset,
  isDateRangeEqual,
  toUtcIsoBounds,
  type DateRangeValue,
} from '@/components/ui/date-range'
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

const VALID_STATUSES = new Set(['queued', 'running', 'polling', 'succeeded', 'failed', 'review'])

function resolveRouteStatus(raw: unknown): string {
  return typeof raw === 'string' && VALID_STATUSES.has(raw) ? raw : 'all'
}

const initialStatus = resolveRouteStatus(route.query.status)

const loading = ref(false)
const jobs = ref<AdminJobItem[]>([])
const total = ref(0)
const reviewCount = ref(0)
const page = ref(1)
const pageSize = ref(30)

const filters = reactive<{
  q: string
  status: string
  jobType: string
  dateRange: DateRangeValue
}>({
  q: '',
  status: initialStatus,
  jobType: 'all',
  dateRange: initialStatus === 'review' ? { start: null, end: null } : createDateRangePreset('today'),
})

const jobColumns: DataTableColumn[] = [
  { key: 'createdAt', label: '创建时间', width: '164px' },
  { key: 'jobType', label: '任务类型', width: '140px' },
  { key: 'status', label: '状态', width: '190px' },
  { key: 'owner', label: '用户 / 项目' },
  { key: 'reservation', label: '积分', width: '120px' },
  { key: 'upstream', label: '上游 ID / 异常' },
  { key: 'actions', label: '操作', width: '180px' },
]

const statusOptions = computed(() => [
  { value: 'all', label: '全部状态' },
  { value: 'review', label: reviewCount.value > 0 ? `待核对 (${reviewCount.value})` : '待核对' },
  { value: 'running', label: '执行中' },
  { value: 'polling', label: '轮询中' },
  { value: 'queued', label: '排队中' },
  { value: 'succeeded', label: '成功' },
  { value: 'failed', label: '失败' },
])

const jobTypeOptions = [
  { value: 'all', label: '全部任务类型' },
  ...Object.entries(JOB_TYPE_LABELS).map(([value, label]) => ({ value, label })),
]

const hasNonDefaultFilters = computed(() => {
  const today = createDateRangePreset('today')
  return (
    filters.q.trim() !== ''
    || filters.status !== 'all'
    || filters.jobType !== 'all'
    || !isDateRangeEqual(filters.dateRange, today)
  )
})

const detailDialogOpen = ref(false)
const detailJob = ref<AdminJobItem | null>(null)

const imagePreviewOpen = ref(false)
const imagePreviewSrc = ref('')
const imagePreviewTitle = ref('')

const videoPreviewOpen = ref(false)
const videoPreviewSrc = ref('')
const videoPreviewTitle = ref('')

const refundDialogOpen = ref(false)
const refundSubmitting = ref(false)
const refundJob = ref<AdminJobItem | null>(null)
const refundReason = ref('')

const rescueDialogOpen = ref(false)
const rescueSubmitting = ref(false)
const rescueJob = ref<AdminJobItem | null>(null)
const rescueForm = reactive({
  mediaUrl: '',
  note: '',
})

let searchTimer: ReturnType<typeof setTimeout> | null = null
let activeRequestId = 0

function clearSearchTimer() {
  if (searchTimer !== null) {
    clearTimeout(searchTimer)
    searchTimer = null
  }
}

async function loadJobs(resetPage = false) {
  if (resetPage) page.value = 1
  const requestId = ++activeRequestId
  loading.value = true
  try {
    const bounds = toUtcIsoBounds(filters.dateRange)
    const res = await listAdminJobs({
      status: filters.status === 'all' ? undefined : filters.status,
      jobType: filters.jobType === 'all' ? undefined : filters.jobType,
      q: filters.q.trim() || undefined,
      createdFrom: bounds.createdFrom,
      createdTo: bounds.createdTo,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    })
    if (requestId !== activeRequestId) return
    jobs.value = res.items
    total.value = res.total
    reviewCount.value = res.reviewCount
    await refreshReviewBadge?.()
  } catch (err) {
    if (requestId !== activeRequestId) return
    ui.notify(extractErrorMessage(err, '加载任务列表失败'), 'error')
  } finally {
    if (requestId === activeRequestId) {
      loading.value = false
    }
  }
}

function handleStatusChange(status: string | undefined) {
  const next = status || 'all'
  filters.status = next
  void router.replace({
    path: '/admin/jobs',
    query: next === 'all' ? {} : { status: next },
  })
  void loadJobs(true)
}

function jumpToReview() {
  filters.dateRange = { start: null, end: null }
  handleStatusChange('review')
}

function submitSearch() {
  clearSearchTimer()
  void loadJobs(true)
}

function clearSearch() {
  filters.q = ''
  submitSearch()
}

function resetFilters() {
  clearSearchTimer()
  filters.q = ''
  filters.status = 'all'
  filters.jobType = 'all'
  filters.dateRange = createDateRangePreset('today')
  void router.replace({ path: '/admin/jobs', query: {} })
  void loadJobs(true)
}

watch(
  () => filters.q,
  () => {
    clearSearchTimer()
    searchTimer = setTimeout(() => {
      searchTimer = null
      void loadJobs(true)
    }, 300)
  },
)

watch(
  () => route.query.status,
  (val) => {
    const next = resolveRouteStatus(val)
    if (next !== filters.status) {
      filters.status = next
      if (next === 'review') {
        filters.dateRange = { start: null, end: null }
      }
      void loadJobs(true)
    }
  },
)

onBeforeUnmount(() => {
  clearSearchTimer()
})

function canRefund(job: AdminJobItem): boolean {
  return (
    (job.jobType === 'asset_image' || job.jobType === 'clip_video')
    && job.reservationStatus === 'frozen'
  )
}

function canRescue(job: AdminJobItem): boolean {
  return (
    (job.jobType === 'asset_image' || job.jobType === 'clip_video')
    && (job.status === 'review' || job.status === 'failed')
  )
}

function openDetail(job: AdminJobItem) {
  detailJob.value = job
  detailDialogOpen.value = true
}

interface JobPreviewMedia {
  kind: 'image' | 'video'
  src: string
  title: string
}

function readMediaUrl(
  payload: Record<string, unknown> | null | undefined,
  keys: readonly string[],
): string | null {
  if (!payload) return null
  for (const key of keys) {
    const value = payload[key]
    if (typeof value === 'string' && /^https?:\/\//i.test(value.trim())) {
      return value.trim()
    }
  }
  return null
}

function getJobPreviewMedia(job: AdminJobItem): JobPreviewMedia | null {
  if (job.status !== 'succeeded' || !job.resultPayload) return null
  const label = JOB_TYPE_LABELS[job.jobType] || job.jobType
  const title = [label, job.projectName].filter(Boolean).join(' · ')

  const videoUrl = readMediaUrl(job.resultPayload, ['videoUrl', 'composedVideoUrl'])
  if (videoUrl) return { kind: 'video', src: videoUrl, title }

  const imageUrl = readMediaUrl(job.resultPayload, ['imageUrl'])
  if (imageUrl) return { kind: 'image', src: imageUrl, title }

  return null
}

function openMediaPreview(job: AdminJobItem) {
  const media = getJobPreviewMedia(job)
  if (!media) return
  if (media.kind === 'image') {
    imagePreviewSrc.value = media.src
    imagePreviewTitle.value = media.title
    imagePreviewOpen.value = true
  } else {
    videoPreviewSrc.value = media.src
    videoPreviewTitle.value = media.title
    videoPreviewOpen.value = true
  }
}

const detailPreviewMedia = computed(() => (detailJob.value ? getJobPreviewMedia(detailJob.value) : null))

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
  if (status === 'released' || status === 'refunded') return 'admin-badge--info'
  return ''
}

function statusSubText(job: AdminJobItem): string {
  if (job.status === 'succeeded') return ''
  const parts: string[] = []
  if (job.progress > 0 && job.progress < 100) parts.push(`${job.progress}%`)
  if (job.stepLabel) parts.push(job.stepLabel)
  return parts.join(' · ')
}

function prettyJson(obj: unknown): string {
  if (obj === null || obj === undefined) return 'null'
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

const READABLE_INPUT_FIELDS: ReadonlyArray<{
  key: string
  label: string
  alwaysExtract?: boolean
}> = [
  { key: 'prompt', label: '提示词 (Prompt)', alwaysExtract: true },
  { key: 'text', label: '输入文本' },
  { key: 'feedback', label: '修改意见' },
]

const detailInputView = computed(() => {
  const payload = detailJob.value?.inputPayload ?? {}
  const textBlocks: Array<{ key: string; label: string; content: string }> = []
  const extractedKeys = new Set<string>()

  for (const field of READABLE_INPUT_FIELDS) {
    const raw = payload[field.key]
    if (typeof raw !== 'string') continue
    const trimmed = raw.trim()
    if (!trimmed) continue
    if (field.alwaysExtract || raw.includes('\n') || raw.includes('\\n') || raw.length > 80) {
      const normalized = raw.replace(/\r\n/g, '\n').replace(/\\n/g, '\n')
      textBlocks.push({ key: field.key, label: field.label, content: normalized })
      extractedKeys.add(field.key)
    }
  }

  const restPayload: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(payload)) {
    if (!extractedKeys.has(key)) restPayload[key] = value
  }

  return {
    textBlocks,
    restPayload,
    hasRestPayload: Object.keys(restPayload).length > 0,
  }
})

const copiedKey = ref<string | null>(null)
let copyTimer: ReturnType<typeof setTimeout> | null = null

function clearCopyTimer() {
  if (copyTimer !== null) {
    clearTimeout(copyTimer)
    copyTimer = null
  }
}

async function copyText(key: string, text: string) {
  if (typeof navigator === 'undefined' || !navigator.clipboard) return
  try {
    await navigator.clipboard.writeText(text)
    copiedKey.value = key
    clearCopyTimer()
    copyTimer = setTimeout(() => {
      copiedKey.value = null
      copyTimer = null
    }, 1800)
  } catch {
    ui.notify('复制失败，请手动选中复制', 'error')
  }
}

onBeforeUnmount(() => {
  clearCopyTimer()
})

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

    <div v-if="reviewCount > 0 && filters.status !== 'review'" class="admin-review-banner">
      <div class="admin-review-banner-left">
        <AlertTriangle :size="18" aria-hidden="true" />
        <div>
          <strong>当前有 {{ reviewCount }} 条待核对任务</strong>
          <p>上游状态超时或存在异常，建议尽快人工核对补录成片或退还冻结积分。</p>
        </div>
      </div>
      <button type="button" class="ui-button ui-button--danger ui-button--sm" @click="jumpToReview">
        查看待核对
      </button>
    </div>

    <form class="admin-jobs-toolbar" @submit.prevent="submitSearch">
      <div class="admin-jobs-search-wrap">
        <Search :size="15" class="admin-jobs-search-icon" aria-hidden="true" />
        <input
          v-model="filters.q"
          class="ui-input admin-jobs-search-input"
          type="text"
          placeholder="搜索用户名或邮箱"
          aria-label="搜索用户名或邮箱"
        />
        <button
          v-if="filters.q"
          type="button"
          class="admin-jobs-search-clear"
          aria-label="清空搜索"
          @click="clearSearch"
        >
          <X :size="13" aria-hidden="true" />
        </button>
      </div>

      <div class="admin-jobs-select">
        <UiSelect
          :model-value="filters.status"
          :options="statusOptions"
          placeholder="任务状态"
          @update:model-value="handleStatusChange"
        />
      </div>

      <div class="admin-jobs-select admin-jobs-select--type">
        <UiSelect
          v-model="filters.jobType"
          :options="jobTypeOptions"
          placeholder="任务类型"
          @update:model-value="loadJobs(true)"
        />
      </div>

      <UiDateRangePicker
        v-model="filters.dateRange"
        inline-presets
        @change="loadJobs(true)"
      />

      <button
        v-if="hasNonDefaultFilters"
        type="button"
        class="ui-button ui-button--ghost ui-button--sm admin-jobs-reset"
        @click="resetFilters"
      >
        重置
      </button>
    </form>

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
        <span class="admin-mono admin-jobs-time">{{ formatDateTime(row.createdAt) }}</span>
      </template>

      <template #cell-jobType="{ row }">
        <span class="admin-cell-primary">{{ JOB_TYPE_LABELS[row.jobType] || row.jobType }}</span>
      </template>

      <template #cell-status="{ row }">
        <span class="admin-badge" :class="statusBadgeClass(row.status)">
          {{ JOB_STATUS_LABELS[row.status] || row.status }}
        </span>
        <div v-if="statusSubText(row)" class="admin-cell-sub admin-jobs-step" :title="statusSubText(row)">
          {{ statusSubText(row) }}
        </div>
      </template>

      <template #cell-owner="{ row }">
        <div class="admin-jobs-owner">
          <span class="admin-cell-primary">{{ row.userNickname || row.userEmail }}</span>
          <span
            v-if="row.userNickname && row.userNickname !== row.userEmail"
            class="admin-jobs-email"
            :title="row.userEmail"
          >
            {{ row.userEmail }}
          </span>
        </div>
        <div v-if="row.projectName" class="admin-cell-sub">{{ row.projectName }}</div>
      </template>

      <template #cell-reservation="{ row }">
        <template v-if="row.reservationAmount">
          <div class="admin-jobs-credit">
            <span class="admin-num">{{ formatCredits(row.reservationAmount) }} 积分</span>
            <span class="admin-badge" :class="reservationBadgeClass(row.reservationStatus)">
              {{ RESERVATION_STATUS_LABELS[row.reservationStatus || ''] || row.reservationStatus }}
            </span>
          </div>
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
          <button
            v-if="getJobPreviewMedia(row)"
            type="button"
            class="ui-button ui-button--outline ui-button--sm"
            :aria-label="getJobPreviewMedia(row)?.kind === 'video' ? '预览视频' : '预览图片'"
            @click="openMediaPreview(row)"
          >
            <Play v-if="getJobPreviewMedia(row)?.kind === 'video'" :size="13" aria-hidden="true" />
            <ImageIcon v-else :size="13" aria-hidden="true" />
            <span>预览</span>
          </button>
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
            <dd>
              {{ detailJob.userNickname || detailJob.userEmail }}
              <template v-if="detailJob.userNickname && detailJob.userNickname !== detailJob.userEmail">
                ({{ detailJob.userEmail }})
              </template>
              · #{{ detailJob.userId }}
              <template v-if="detailJob.projectName"> · {{ detailJob.projectName }}</template>
            </dd>
          </div>
          <div class="admin-detail-item">
            <dt>任务类型 / 状态</dt>
            <dd>
              {{ JOB_TYPE_LABELS[detailJob.jobType] || detailJob.jobType }}
              (<span class="admin-mono">{{ detailJob.jobType }}</span>)
              · {{ JOB_STATUS_LABELS[detailJob.status] || detailJob.status }} · {{ detailJob.progress }}%
              <template v-if="detailJob.stepLabel"> · {{ detailJob.stepLabel }}</template>
            </dd>
          </div>
          <div class="admin-detail-item">
            <dt>上游任务 ID</dt>
            <dd class="admin-mono">{{ detailJob.providerTaskId || '-' }}</dd>
          </div>
          <div class="admin-detail-item">
            <dt>预扣单</dt>
            <dd class="admin-mono">
              {{ detailJob.reservationAmount ? `${formatCredits(detailJob.reservationAmount)} 积分 · ${RESERVATION_STATUS_LABELS[detailJob.reservationStatus || ''] || detailJob.reservationStatus}` : '-' }}
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
          <div v-for="block in detailInputView.textBlocks" :key="block.key">
            <div class="admin-block-head">
              <span class="ui-label">{{ block.label }}</span>
              <button
                type="button"
                class="admin-copy-btn"
                @click="copyText(block.key, block.content)"
              >
                <Check v-if="copiedKey === block.key" :size="12" aria-hidden="true" />
                <Copy v-else :size="12" aria-hidden="true" />
                <span>{{ copiedKey === block.key ? '已复制' : '复制' }}</span>
              </button>
            </div>
            <pre class="admin-prompt-block">{{ block.content }}</pre>
          </div>
          <div v-if="detailInputView.hasRestPayload || !detailInputView.textBlocks.length">
            <div class="admin-block-head">
              <span class="ui-label">{{ detailInputView.textBlocks.length ? '其他输入参数' : '输入参数' }}</span>
              <button
                type="button"
                class="admin-copy-btn"
                @click="copyText('inputPayload', prettyJson(detailJob.inputPayload))"
              >
                <Check v-if="copiedKey === 'inputPayload'" :size="12" aria-hidden="true" />
                <Copy v-else :size="12" aria-hidden="true" />
                <span>{{ copiedKey === 'inputPayload' ? '已复制' : '复制完整 JSON' }}</span>
              </button>
            </div>
            <pre class="admin-json-block">{{ prettyJson(detailInputView.textBlocks.length ? detailInputView.restPayload : detailJob.inputPayload) }}</pre>
          </div>
          <div>
            <div class="admin-block-head">
              <span class="ui-label">执行结果</span>
              <button
                v-if="detailPreviewMedia"
                type="button"
                class="admin-copy-btn admin-copy-btn--gold"
                @click="detailJob && openMediaPreview(detailJob)"
              >
                <Play v-if="detailPreviewMedia.kind === 'video'" :size="12" aria-hidden="true" />
                <ImageIcon v-else :size="12" aria-hidden="true" />
                <span>{{ detailPreviewMedia.kind === 'video' ? '预览视频' : '预览图片' }}</span>
              </button>
            </div>
            <pre class="admin-json-block">{{ prettyJson(detailJob.resultPayload) }}</pre>
          </div>
        </div>
      </template>
    </UiDialog>

    <ImagePreview
      v-model:open="imagePreviewOpen"
      :src="imagePreviewSrc"
      :title="imagePreviewTitle"
    />
    <VideoPreview
      v-model:open="videoPreviewOpen"
      :src="videoPreviewSrc"
      :title="videoPreviewTitle"
      autoplay
    />

    <UiDialog
      v-model:open="refundDialogOpen"
      title="退还冻结积分"
      :description="refundJob ? `退还 ${formatCredits(refundJob.reservationAmount)} 积分给 ${refundJob.userNickname || refundJob.userEmail}` : ''"
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

    <UiDialog
      v-model:open="rescueDialogOpen"
      size="wide"
      title="补录成片"
      :description="rescueJob ? `${JOB_TYPE_LABELS[rescueJob.jobType] || rescueJob.jobType} · ${rescueJob.userNickname || rescueJob.userEmail}` : ''"
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

<style scoped>
.admin-jobs-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-panel);
  background: var(--color-surface);
}

.admin-jobs-search-wrap {
  position: relative;
  width: min(240px, 100%);
  flex: 1 1 200px;
  max-width: 280px;
}

.admin-jobs-search-icon {
  position: absolute;
  top: 50%;
  left: 12px;
  transform: translateY(-50%);
  color: var(--color-muted);
  pointer-events: none;
}

.admin-jobs-search-input {
  width: 100%;
  padding-left: 34px;
  padding-right: 30px;
}

.admin-jobs-search-clear {
  position: absolute;
  top: 50%;
  right: 8px;
  transform: translateY(-50%);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--color-muted);
  cursor: pointer;
}

.admin-jobs-search-clear:hover {
  background: rgb(255 255 255 / 10%);
  color: var(--color-text);
}

.admin-jobs-select {
  width: 146px;
}

.admin-jobs-select--type {
  width: 168px;
}

.admin-jobs-reset {
  height: 42px;
}

.admin-jobs-time {
  white-space: nowrap;
}

.admin-jobs-step {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.admin-jobs-owner {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.admin-jobs-email {
  font-size: 12px;
  color: var(--color-muted);
}

.admin-jobs-credit {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.admin-block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.admin-copy-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border: 1px solid var(--border-control);
  border-radius: 6px;
  background: rgb(255 255 255 / 3%);
  color: var(--color-muted);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.14s, border-color 0.14s, color 0.14s;
}

.admin-copy-btn:hover {
  background: var(--surface-hover);
  border-color: rgb(255 255 255 / 22%);
  color: var(--color-text);
}

.admin-copy-btn--gold {
  border-color: rgb(240 184 75 / 36%);
  background: rgb(240 184 75 / 10%);
  color: var(--color-gold-soft);
}

.admin-copy-btn--gold:hover {
  border-color: rgb(240 184 75 / 55%);
  background: rgb(240 184 75 / 18%);
  color: var(--color-gold-soft);
}

.admin-prompt-block {
  margin: 6px 0 0;
  padding: 14px 16px;
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
  background: #0b0c10;
  color: #e2e4ec;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.75;
  overflow-y: auto;
  max-height: 340px;
  white-space: pre-wrap;
  word-break: break-word;
  user-select: text;
}
</style>
