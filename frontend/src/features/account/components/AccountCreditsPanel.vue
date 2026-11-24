<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  ArrowDownLeft,
  ChevronDown,
  ChevronUp,
  Clapperboard,
  Clock,
  Coins,
  Download,
  ExternalLink,
  FileText,
  Film,
  Image as ImageIcon,
  LayoutDashboard,
  Lock,
  RefreshCw,
  RotateCcw,
  Search,
  Ticket,
  Wallet,
  X,
} from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import UiDataTable, { type DataTableColumn } from '@/components/ui/UiDataTable.vue'
import UiDateRangePicker from '@/components/ui/UiDateRangePicker.vue'
import {
  createDateRangePreset,
  isDateRangeEqual,
  toUtcIsoBounds,
  type DateRangeValue,
} from '@/components/ui/date-range'
import UiSelect from '@/components/ui/UiSelect.vue'
import { JOB_STATUS_LABELS, JOB_TYPE_LABELS } from '@/features/admin/format'
import {
  extractErrorMessage,
  formatCredits,
  formatDateTime,
  formatSignedCredits,
} from '@/lib/format'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import {
  fetchCreditBills,
  fetchCreditSummary,
  fetchEnrichedCreditLedgers,
  type CreditBillCategory,
  type CreditBillItem,
  type CreditBillStatus,
  type CreditLedgerOperation,
  type CreditSummary,
  type EnrichedCreditLedgerItem,
} from '../credits-api'
import {
  BILL_CATEGORY_LABELS,
  BILL_STATUS_LABELS,
  buildBillsCsv,
  buildLedgersCsv,
  computeBreakdownSegments,
  formatCreditReason,
  formatLedgerChangeDisplay,
  formatRateSpec,
  LEDGER_OP_LABELS_ACCOUNT,
} from '../credits-helpers'
import CreditDetailDialog, { type CreditDetailPayload } from './CreditDetailDialog.vue'
import RedeemCodeDialog from './RedeemCodeDialog.vue'

type ViewMode = 'bills' | 'ledgers'

const auth = useAuthStore()
const ui = useUiStore()

const viewMode = ref<ViewMode>('bills')
const dateRange = ref<DateRangeValue>(createDateRangePreset('today'))
const keyword = ref('')
const billCategory = ref<'' | CreditBillCategory>('')
const billStatus = ref<'' | CreditBillStatus>('')
const ledgerOperation = ref<'' | CreditLedgerOperation>('')

const summaryLoading = ref(false)
const summary = ref<CreditSummary | null>(null)
const frozenExpanded = ref(false)

const billsLoading = ref(false)
const bills = ref<CreditBillItem[]>([])
const billsTotal = ref(0)
const billsPage = ref(1)
const billsPageSize = ref(15)

const ledgersLoading = ref(false)
const ledgers = ref<EnrichedCreditLedgerItem[]>([])
const ledgersTotal = ref(0)
const ledgersPage = ref(1)
const ledgersPageSize = ref(15)

const exporting = ref(false)
const detailOpen = ref(false)
const activeDetail = ref<CreditDetailPayload | null>(null)
const redeemOpen = ref(false)

let searchTimer: ReturnType<typeof setTimeout> | null = null

const categoryTabs: ReadonlyArray<{ value: '' | CreditBillCategory; label: string }> = [
  { value: '', label: '全部' },
  { value: 'video', label: '视频' },
  { value: 'image', label: '图片' },
  { value: 'text', label: '文本' },
  { value: 'income', label: '入账' },
]

const billStatusOptions = [
  { value: 'all', label: '全部状态' },
  { value: 'charged', label: '已扣费' },
  { value: 'frozen', label: '冻结中' },
  { value: 'refunded', label: '已退还' },
  { value: 'credited', label: '已入账' },
]

const ledgerOperationOptions = [
  { value: 'all', label: '全部操作' },
  { value: 'llm_consume', label: '文本扣费' },
  { value: 'freeze', label: '任务预扣' },
  { value: 'settle', label: '消费结算' },
  { value: 'release', label: '失败退还' },
  { value: 'redeem', label: '兑换码' },
  { value: 'grant', label: '积分赠送' },
  { value: 'adjust', label: '账户调账' },
]

const billStatusSelect = computed({
  get: () => billStatus.value || 'all',
  set: (val: string) => {
    billStatus.value = val === 'all' ? '' : (val as CreditBillStatus)
    void loadBills(true)
  },
})

const ledgerOpSelect = computed({
  get: () => ledgerOperation.value || 'all',
  set: (val: string) => {
    ledgerOperation.value = val === 'all' ? '' : (val as CreditLedgerOperation)
    void loadLedgers(true)
  },
})

const billColumns: DataTableColumn[] = [
  { key: 'createdAt', label: '时间', width: '154px' },
  { key: 'title', label: '消费项目与来源' },
  { key: 'model', label: '模型与规格' },
  { key: 'status', label: '状态', width: '84px' },
  { key: 'amount', label: '实付积分', align: 'right', width: '116px' },
  { key: 'action', label: '', align: 'right', width: '66px' },
]

const ledgerColumns: DataTableColumn[] = [
  { key: 'createdAt', label: '时间', width: '154px' },
  { key: 'operation', label: '操作类型', width: '96px' },
  { key: 'change', label: '资金变动', align: 'right', width: '132px' },
  { key: 'balanceRange', label: '变动后余冻', width: '156px' },
  { key: 'reason', label: '来源与说明' },
  { key: 'action', label: '', align: 'right', width: '66px' },
]

const activeBalance = computed(() => summary.value?.balance ?? auth.user?.balance ?? '0')
const activeFrozen = computed(() => summary.value?.frozen ?? auth.user?.frozen ?? '0')
const activeMultiplier = computed(() => Number(summary.value?.usageMultiplier ?? auth.user?.usageMultiplier ?? 1))
const redeemPurchaseUrl = computed(() => summary.value?.redeemPurchaseUrl || auth.redeemPurchaseUrl || '')
const isNegativeBalance = computed(() => Number(activeBalance.value) < 0)
const hasFrozenCredits = computed(
  () => Number(activeFrozen.value) > 0 || (summary.value?.activeFrozenItems.length ?? 0) > 0,
)

const breakdownSegments = computed(() => computeBreakdownSegments(summary.value?.breakdown))
const hasPeriodSpend = computed(() => Number(summary.value?.totalSpent ?? 0) > 0)

const periodLabel = computed(() => {
  const { start, end } = dateRange.value
  if (!start && !end) return '全部时间'
  if (isDateRangeEqual(dateRange.value, createDateRangePreset('today'))) return '今天'
  if (start && end) return start === end ? start : `${start} 至 ${end}`
  if (start) return `${start} 起`
  return `至 ${end}`
})

const hasActiveFilters = computed(() =>
  Boolean(
    !isDateRangeEqual(dateRange.value, createDateRangePreset('today'))
    || keyword.value.trim()
    || (viewMode.value === 'bills' ? (billCategory.value || billStatus.value) : ledgerOperation.value),
  ),
)

const isRefreshing = computed(
  () => summaryLoading.value || (viewMode.value === 'bills' ? billsLoading.value : ledgersLoading.value),
)

function currentDateBounds() {
  const bounds = toUtcIsoBounds(dateRange.value)
  return { startAt: bounds.createdFrom, endAt: bounds.createdTo }
}

async function loadSummary() {
  summaryLoading.value = true
  try {
    const bounds = currentDateBounds()
    const [res] = await Promise.all([
      fetchCreditSummary(bounds),
      auth.refreshBalance().catch(() => {}),
    ])
    summary.value = res
    if (res.activeFrozenItems.length === 0) {
      frozenExpanded.value = false
    }
  } catch (error) {
    ui.notify(extractErrorMessage(error, '加载积分概览失败'), 'error')
  } finally {
    summaryLoading.value = false
  }
}

async function loadBills(resetPage = false) {
  if (resetPage) billsPage.value = 1
  billsLoading.value = true
  try {
    const bounds = currentDateBounds()
    const res = await fetchCreditBills({
      category: billCategory.value || undefined,
      status: billStatus.value || undefined,
      startAt: bounds.startAt,
      endAt: bounds.endAt,
      keyword: keyword.value,
      limit: billsPageSize.value,
      offset: (billsPage.value - 1) * billsPageSize.value,
    })
    bills.value = res.items
    billsTotal.value = res.total
  } catch (error) {
    ui.notify(extractErrorMessage(error, '加载消费账单失败'), 'error')
  } finally {
    billsLoading.value = false
  }
}

async function loadLedgers(resetPage = false) {
  if (resetPage) ledgersPage.value = 1
  ledgersLoading.value = true
  try {
    const bounds = currentDateBounds()
    const res = await fetchEnrichedCreditLedgers({
      operation: ledgerOperation.value || undefined,
      startAt: bounds.startAt,
      endAt: bounds.endAt,
      keyword: keyword.value,
      limit: ledgersPageSize.value,
      offset: (ledgersPage.value - 1) * ledgersPageSize.value,
    })
    ledgers.value = res.items
    ledgersTotal.value = res.total
  } catch (error) {
    ui.notify(extractErrorMessage(error, '加载资金流水失败'), 'error')
  } finally {
    ledgersLoading.value = false
  }
}

async function refreshAll(resetPage = false) {
  await Promise.all([
    loadSummary(),
    viewMode.value === 'bills' ? loadBills(resetPage) : loadLedgers(resetPage),
  ])
}

function selectViewMode(next: ViewMode) {
  if (viewMode.value === next) return
  viewMode.value = next
  if (next === 'bills') void loadBills(true)
  else void loadLedgers(true)
}

function selectCategory(cat: '' | CreditBillCategory) {
  if (billCategory.value === cat) return
  billCategory.value = cat
  void loadBills(true)
}

function handleDateRangeChange() {
  void refreshAll(true)
}

function resetFilters() {
  dateRange.value = createDateRangePreset('today')
  keyword.value = ''
  billCategory.value = ''
  billStatus.value = ''
  ledgerOperation.value = ''
  void refreshAll(true)
}

function openBillDetail(item: CreditBillItem) {
  activeDetail.value = { kind: 'bill', item }
  detailOpen.value = true
}

function openLedgerDetail(item: EnrichedCreditLedgerItem) {
  activeDetail.value = { kind: 'ledger', item }
  detailOpen.value = true
}

function categoryIcon(category: CreditBillCategory) {
  if (category === 'video') return Film
  if (category === 'image') return ImageIcon
  if (category === 'text') return FileText
  return ArrowDownLeft
}

async function exportCsv() {
  if (exporting.value) return
  exporting.value = true
  try {
    const bounds = currentDateBounds()
    const stamp = new Date().toISOString().slice(0, 10)
    let csv = ''
    let filename = ''
    if (viewMode.value === 'bills') {
      const res = await fetchCreditBills({
        category: billCategory.value || undefined,
        status: billStatus.value || undefined,
        startAt: bounds.startAt,
        endAt: bounds.endAt,
        keyword: keyword.value,
        limit: 100,
        offset: 0,
      })
      if (!res.items.length) {
        ui.notify('当前筛选条件下没有可导出的消费账单', 'info')
        return
      }
      csv = buildBillsCsv(res.items)
      filename = `credit-bills-${stamp}.csv`
      if (res.total > res.items.length) {
        ui.notify(`已导出最近 ${res.items.length} 条消费账单（共 ${res.total} 条，建议缩小时间范围分批导出）`, 'info')
      }
    } else {
      const res = await fetchEnrichedCreditLedgers({
        operation: ledgerOperation.value || undefined,
        startAt: bounds.startAt,
        endAt: bounds.endAt,
        keyword: keyword.value,
        limit: 100,
        offset: 0,
      })
      if (!res.items.length) {
        ui.notify('当前筛选条件下没有可导出的资金流水', 'info')
        return
      }
      csv = buildLedgersCsv(res.items)
      filename = `credit-ledgers-${stamp}.csv`
      if (res.total > res.items.length) {
        ui.notify(`已导出最近 ${res.items.length} 条资金流水（共 ${res.total} 条，建议缩小时间范围分批导出）`, 'info')
      }
    }
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } catch (error) {
    ui.notify(extractErrorMessage(error, '导出 CSV 失败'), 'error')
  } finally {
    exporting.value = false
  }
}

watch(keyword, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    if (viewMode.value === 'bills') void loadBills(true)
    else void loadLedgers(true)
  }, 320)
})

onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer)
})

onMounted(() => {
  void refreshAll(true)
})
</script>

<template>
  <article class="credits-panel">
    <!-- 顶部标题 -->
    <header class="credits-panel-head">
      <div class="credits-panel-title">
        <h2><Wallet :size="16" aria-hidden="true" />积分与账单</h2>
      </div>
      <div class="credits-panel-head-actions">
        <UiButton variant="outline" size="sm" :loading="exporting" :disabled="exporting || isRefreshing" @click="exportCsv">
          <template v-if="!exporting" #leading><Download :size="13" aria-hidden="true" /></template>
          导出 CSV
        </UiButton>
        <UiButton variant="outline" size="sm" :disabled="isRefreshing" @click="refreshAll(false)">
          <template #leading><RefreshCw :size="13" :class="{ 'ui-spin': isRefreshing }" aria-hidden="true" /></template>
          刷新
        </UiButton>
      </div>
    </header>

    <!-- 第 1 层：双卡资产与消耗概览 -->
    <div class="credits-overview-grid">
      <!-- 左侧：账户资产卡片 -->
      <section class="credits-asset-card" aria-label="账户积分余额">
        <div class="credits-asset-top">
          <span class="credits-eyebrow"><Coins :size="13" aria-hidden="true" />可用积分余额</span>
          <span
            class="credits-multiplier-pill"
            :class="{ 'is-discount': activeMultiplier < 1 }"
            title="当前账号生效的计费费率倍率"
          >
            {{ activeMultiplier < 1 ? `专属 ${(activeMultiplier * 10).toFixed(1).replace(/\.0$/, '')} 折` : `费率 ${activeMultiplier.toFixed(2)}×` }}
          </span>
        </div>
        <div class="credits-balance-row">
          <div class="credits-balance-hero" :class="{ 'is-neg': isNegativeBalance }">
            <strong>{{ formatCredits(activeBalance) }}</strong>
            <span>积分</span>
          </div>
          <div class="credits-balance-actions">
            <UiButton variant="primary" size="sm" @click="redeemOpen = true">
              <template #leading><Ticket :size="13" aria-hidden="true" /></template>
              兑换积分
            </UiButton>
            <a
              v-if="redeemPurchaseUrl"
              :href="redeemPurchaseUrl"
              target="_blank"
              rel="noopener noreferrer"
              class="credits-buy-btn"
            >
              <span>购买兑换码</span>
              <ExternalLink :size="12" aria-hidden="true" />
            </a>
          </div>
        </div>
        <p v-if="isNegativeBalance" class="credits-neg-warn">
          余额已为负数（文本按实际 Token 事后扣费），请补充积分后再继续生成。
        </p>
        <div class="credits-asset-footer">
          <div class="credits-frozen-summary">
            <Lock :size="13" aria-hidden="true" />
            <span>任务冻结中</span>
            <strong :class="{ 'is-active': Number(activeFrozen) > 0 }">{{ formatCredits(activeFrozen) }}</strong>
          </div>
          <button
            v-if="hasFrozenCredits"
            type="button"
            class="credits-frozen-toggle"
            :aria-expanded="frozenExpanded"
            @click="frozenExpanded = !frozenExpanded"
          >
            <span>{{ frozenExpanded ? '收起冻结明细' : `查看冻结明细 (${summary?.activeFrozenItems.length ?? 0})` }}</span>
            <ChevronUp v-if="frozenExpanded" :size="13" aria-hidden="true" />
            <ChevronDown v-else :size="13" aria-hidden="true" />
          </button>
        </div>
      </section>

      <!-- 右侧：周期消耗与分类占比 -->
      <section class="credits-spend-card" aria-label="周期消费分布">
        <div class="credits-spend-top">
          <span class="credits-eyebrow">消费概览</span>
          <span class="credits-period-tag">{{ periodLabel }}</span>
        </div>

        <div class="credits-spend-kpis">
          <div class="credits-kpi">
            <span>实际消耗</span>
            <strong class="is-spend">{{ formatCredits(summary?.totalSpent ?? 0) }}</strong>
          </div>
          <div class="credits-kpi">
            <span>累计入账</span>
            <strong class="is-income">+{{ formatCredits(summary?.totalGranted ?? 0) }}</strong>
          </div>
          <div class="credits-kpi">
            <span>失败退还</span>
            <strong>{{ formatCredits(summary?.totalRefunded ?? 0) }}</strong>
          </div>
          <div class="credits-kpi">
            <span>账单笔数</span>
            <strong>{{ summary?.billCount ?? 0 }}</strong>
          </div>
        </div>

        <div class="credits-breakdown">
          <div class="credits-breakdown-bar" role="img" aria-label="按类别消费占比">
            <template v-if="hasPeriodSpend">
              <span
                v-for="seg in breakdownSegments"
                :key="seg.key"
                v-show="seg.percent > 0"
                class="credits-breakdown-fill"
                :class="`is-${seg.key}`"
                :style="{ width: `${Math.max(seg.percent, 2)}%` }"
                :title="`${seg.label}：${formatCredits(seg.amount)} 积分 (${seg.percent}%)`"
              ></span>
            </template>
            <span v-else class="credits-breakdown-empty"></span>
          </div>
          <ul class="credits-breakdown-legend">
            <li v-for="seg in breakdownSegments" :key="seg.key">
              <span class="credits-legend-dot" :class="`is-${seg.key}`" aria-hidden="true"></span>
              <span class="credits-legend-label">{{ seg.label }}</span>
              <strong class="credits-legend-val">{{ formatCredits(seg.amount) }}</strong>
              <small v-if="hasPeriodSpend">{{ seg.percent }}%</small>
            </li>
          </ul>
        </div>
      </section>
    </div>

    <!-- 展开式：当前冻结中任务明细 -->
    <section
      v-if="frozenExpanded && summary?.activeFrozenItems.length"
      class="credits-frozen-panel"
      aria-label="当前冻结中任务明细"
    >
      <header class="credits-frozen-panel-head">
        <span><Clock :size="13" aria-hidden="true" />以下任务正在后台执行或待核对，完成后自动结算，失败将全额退还至可用余额：</span>
      </header>
      <ul class="credits-frozen-list">
        <li v-for="item in summary.activeFrozenItems" :key="item.reservationId">
          <span class="credits-cat-icon" :class="`is-${item.businessType}`" aria-hidden="true">
            <Film v-if="item.businessType === 'video'" :size="13" />
            <ImageIcon v-else :size="13" />
          </span>
          <div class="credits-frozen-info">
            <div class="credits-frozen-title-row">
              <strong>{{ (item.jobType && JOB_TYPE_LABELS[item.jobType]) || (item.businessType === 'video' ? '视频生成' : '图片生成') }}</strong>
              <span v-if="item.jobStatus" class="credits-mini-tag" :class="{ 'is-review': item.jobStatus === 'review' }">
                {{ JOB_STATUS_LABELS[item.jobStatus] || item.jobStatus }}
              </span>
              <RouterLink
                v-if="item.projectId"
                class="credits-source-chip"
                :to="{ name: 'studio-storyboard', params: { projectId: item.projectId } }"
              >
                <Clapperboard :size="11" aria-hidden="true" />{{ item.projectName || '短剧项目' }}
              </RouterLink>
              <RouterLink
                v-else-if="item.canvasId"
                class="credits-source-chip"
                :to="{ name: 'canvas-editor', params: { canvasId: item.canvasId } }"
              >
                <LayoutDashboard :size="11" aria-hidden="true" />{{ item.canvasName || '画布' }}
              </RouterLink>
            </div>
            <div class="credits-frozen-sub">
              <span>{{ item.modelName || item.modelId }}</span>
              <span v-if="formatRateSpec(item.rateSnapshot)">· {{ formatRateSpec(item.rateSnapshot) }}</span>
              <span>· {{ formatDateTime(item.createdAt) }}</span>
            </div>
          </div>
          <span class="credits-frozen-amount">冻结 {{ formatCredits(item.amount) }}</span>
        </li>
      </ul>
    </section>

    <!-- 第 2 层：双视角切换 + 筛选栏 -->
    <div class="credits-toolbar">
      <div class="credits-view-switch" role="tablist" aria-label="账务视角切换">
        <button
          type="button"
          role="tab"
          class="credits-view-tab"
          :class="{ 'is-active': viewMode === 'bills' }"
          :aria-selected="viewMode === 'bills'"
          @click="selectViewMode('bills')"
        >
          消费账单
          <span v-if="viewMode === 'bills'" class="credits-view-count">{{ billsTotal }}</span>
        </button>
        <button
          type="button"
          role="tab"
          class="credits-view-tab"
          :class="{ 'is-active': viewMode === 'ledgers' }"
          :aria-selected="viewMode === 'ledgers'"
          @click="selectViewMode('ledgers')"
        >
          资金流水
          <span v-if="viewMode === 'ledgers'" class="credits-view-count">{{ ledgersTotal }}</span>
        </button>
      </div>

      <div class="credits-filter-row">
        <UiDateRangePicker
          v-model="dateRange"
          placeholder="全部时间"
          @change="handleDateRangeChange"
        />

        <template v-if="viewMode === 'bills'">
          <div class="credits-cat-pills" role="group" aria-label="按消费类别筛选">
            <button
              v-for="tab in categoryTabs"
              :key="tab.value || 'all'"
              type="button"
              class="credits-cat-pill"
              :class="{ 'is-active': billCategory === tab.value }"
              @click="selectCategory(tab.value)"
            >
              {{ tab.label }}
            </button>
          </div>
          <div class="credits-select-wrap">
            <UiSelect v-model="billStatusSelect" :options="billStatusOptions" placeholder="状态" />
          </div>
        </template>

        <div v-else class="credits-select-wrap">
          <UiSelect v-model="ledgerOpSelect" :options="ledgerOperationOptions" placeholder="操作类型" />
        </div>

        <label class="credits-search">
          <Search :size="13" aria-hidden="true" />
          <input
            v-model="keyword"
            type="text"
            placeholder="搜项目、模型或说明"
            aria-label="搜索账单或流水"
          />
          <button
            v-if="keyword"
            type="button"
            class="credits-search-clear"
            aria-label="清空搜索"
            @click="keyword = ''"
          >
            <X :size="12" aria-hidden="true" />
          </button>
        </label>

        <UiButton v-if="hasActiveFilters" variant="ghost" size="sm" @click="resetFilters">
          <template #leading><RotateCcw :size="12" aria-hidden="true" /></template>
          重置
        </UiButton>
      </div>
    </div>

    <!-- 第 3 层：双视角数据表 -->
    <UiDataTable
      v-if="viewMode === 'bills'"
      v-model:page="billsPage"
      v-model:page-size="billsPageSize"
      :columns="billColumns"
      :rows="bills"
      row-key="id"
      :loading="billsLoading"
      empty-text="当前条件下暂无消费账单"
      compact
      paginated
      :total="billsTotal"
      :page-size-options="[15, 30, 50]"
      @change="loadBills()"
    >
      <template #cell-createdAt="{ row }">
        <span class="credits-mono credits-muted">{{ formatDateTime(row.createdAt) }}</span>
      </template>

      <template #cell-title="{ row }">
        <div class="credits-bill-title-cell">
          <span class="credits-cat-icon" :class="`is-${row.category}`" aria-hidden="true">
            <component :is="categoryIcon(row.category)" :size="13" />
          </span>
          <div class="credits-bill-title-text">
            <div class="credits-bill-title-line">
              <button type="button" class="credits-row-link" @click="openBillDetail(row)">
                {{ row.title }}
              </button>
              <RouterLink
                v-if="row.projectId"
                class="credits-source-chip"
                :to="{ name: 'studio-storyboard', params: { projectId: row.projectId } }"
              >
                <Clapperboard :size="11" aria-hidden="true" />{{ row.projectName || '短剧项目' }}
              </RouterLink>
              <RouterLink
                v-else-if="row.canvasId"
                class="credits-source-chip"
                :to="{ name: 'canvas-editor', params: { canvasId: row.canvasId } }"
              >
                <LayoutDashboard :size="11" aria-hidden="true" />{{ row.canvasName || '画布' }}
              </RouterLink>
            </div>
            <div
              v-if="formatCreditReason(row.reason) && formatCreditReason(row.reason) !== row.title"
              class="credits-row-sub"
            >
              {{ formatCreditReason(row.reason) }}
            </div>
          </div>
        </div>
      </template>

      <template #cell-model="{ row }">
        <div class="credits-model-cell">
          <span v-if="row.modelName || row.modelId" class="credits-model-name">
            {{ row.modelName || row.modelId }}
          </span>
          <span v-else class="credits-muted">{{ BILL_CATEGORY_LABELS[row.category] }}</span>
          <div v-if="formatRateSpec(row.rateSnapshot, row.tokenUsage)" class="credits-row-sub credits-mono">
            {{ formatRateSpec(row.rateSnapshot, row.tokenUsage) }}
          </div>
        </div>
      </template>

      <template #cell-status="{ row }">
        <span class="credits-status-pill" :class="`is-${row.status}`">
          {{ BILL_STATUS_LABELS[row.status] }}
        </span>
      </template>

      <template #cell-amount="{ row }">
        <div class="credits-amount-cell credits-mono">
          <template v-if="row.status === 'refunded'">
            <span class="credits-amount-strike">-{{ formatCredits(row.originalAmount) }}</span>
            <strong class="is-refunded">0</strong>
          </template>
          <template v-else-if="row.status === 'frozen'">
            <strong class="is-frozen">冻结 {{ formatCredits(row.originalAmount) }}</strong>
          </template>
          <template v-else>
            <strong :class="Number(row.amount) > 0 ? 'is-pos' : Number(row.amount) < 0 ? 'is-neg' : ''">
              {{ formatSignedCredits(row.amount) }}
            </strong>
          </template>
        </div>
      </template>

      <template #cell-action="{ row }">
        <button type="button" class="credits-detail-btn" @click="openBillDetail(row)">
          详情
        </button>
      </template>
    </UiDataTable>

    <UiDataTable
      v-else
      v-model:page="ledgersPage"
      v-model:page-size="ledgersPageSize"
      :columns="ledgerColumns"
      :rows="ledgers"
      row-key="id"
      :loading="ledgersLoading"
      empty-text="当前条件下暂无资金流水"
      compact
      paginated
      :total="ledgersTotal"
      :page-size-options="[15, 30, 50]"
      @change="loadLedgers()"
    >
      <template #cell-createdAt="{ row }">
        <span class="credits-mono credits-muted">{{ formatDateTime(row.createdAt) }}</span>
      </template>

      <template #cell-operation="{ row }">
        <span class="credits-op-tag" :class="`is-${row.operation}`">
          {{ LEDGER_OP_LABELS_ACCOUNT[row.operation] || row.operation }}
        </span>
      </template>

      <template #cell-change="{ row }">
        <div class="credits-amount-cell credits-mono">
          <strong :class="`is-${formatLedgerChangeDisplay(row).tone}`">
            {{ formatLedgerChangeDisplay(row).primary }}
          </strong>
          <span v-if="formatLedgerChangeDisplay(row).secondary" class="credits-row-sub">
            {{ formatLedgerChangeDisplay(row).secondary }}
          </span>
        </div>
      </template>

      <template #cell-balanceRange="{ row }">
        <div class="credits-mono">
          <div>可用 {{ formatCredits(row.balanceAfter) }}</div>
          <div v-if="Number(row.frozenAfter) > 0 || Number(row.frozenChange) !== 0" class="credits-row-sub">
            冻结 {{ formatCredits(row.frozenBefore) }} → {{ formatCredits(row.frozenAfter) }}
          </div>
          <div v-else class="credits-row-sub">
            前 {{ formatCredits(row.balanceBefore) }}
          </div>
        </div>
      </template>

      <template #cell-reason="{ row }">
        <div class="credits-bill-title-line">
          <span>{{ formatCreditReason(row.reason) || '-' }}</span>
          <RouterLink
            v-if="row.projectId"
            class="credits-source-chip"
            :to="{ name: 'studio-storyboard', params: { projectId: row.projectId } }"
          >
            <Clapperboard :size="11" aria-hidden="true" />{{ row.projectName || '短剧项目' }}
          </RouterLink>
          <RouterLink
            v-else-if="row.canvasId"
            class="credits-source-chip"
            :to="{ name: 'canvas-editor', params: { canvasId: row.canvasId } }"
          >
            <LayoutDashboard :size="11" aria-hidden="true" />{{ row.canvasName || '画布' }}
          </RouterLink>
        </div>
        <div v-if="row.modelName || formatRateSpec(row.rateSnapshot, row.tokenUsage)" class="credits-row-sub credits-mono">
          <template v-if="row.modelName">{{ row.modelName }}</template>
          <template v-if="row.modelName && formatRateSpec(row.rateSnapshot, row.tokenUsage)"> · </template>
          {{ formatRateSpec(row.rateSnapshot, row.tokenUsage) }}
        </div>
      </template>

      <template #cell-action="{ row }">
        <button type="button" class="credits-detail-btn" @click="openLedgerDetail(row)">
          详情
        </button>
      </template>
    </UiDataTable>

    <CreditDetailDialog v-model:open="detailOpen" :detail="activeDetail" />
    <RedeemCodeDialog v-model:open="redeemOpen" :purchase-url="redeemPurchaseUrl" @redeemed="refreshAll(true)" />
  </article>
</template>

<style scoped>
.credits-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px 20px;
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  background: var(--color-surface);
}

.credits-panel-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.credits-panel-title {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 10px;
}

.credits-panel-title h2 {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
}

.credits-panel-subtitle {
  font-size: 12px;
  color: var(--color-muted);
}

.credits-panel-head-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.credits-overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.35fr);
  gap: 14px;
}

.credits-asset-card,
.credits-spend-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 15px 16px;
  border: 1px solid var(--border-subtle);
  border-radius: 9px;
  background: var(--color-canvas);
}

.credits-asset-card {
  background: linear-gradient(145deg, rgb(240 184 75 / 8%), var(--color-canvas) 64%);
  border-color: rgb(240 184 75 / 22%);
}

.credits-asset-top,
.credits-spend-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.credits-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-muted);
}

.credits-multiplier-pill,
.credits-period-tag {
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--border-control);
  background: rgb(255 255 255 / 4%);
  font-size: 11px;
  color: var(--color-muted);
  font-variant-numeric: tabular-nums;
}

.credits-multiplier-pill.is-discount {
  border-color: rgb(240 184 75 / 42%);
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-weight: 500;
}

.credits-balance-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.credits-balance-hero {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.credits-balance-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.credits-buy-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 30px;
  padding: 0 11px;
  border-radius: 7px;
  border: 1px solid rgb(240 184 75 / 32%);
  background: rgb(240 184 75 / 8%);
  color: var(--color-gold-soft);
  font-size: 12.5px;
  font-weight: 500;
  text-decoration: none;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.credits-buy-btn:hover {
  border-color: rgb(240 184 75 / 56%);
  background: rgb(240 184 75 / 15%);
}

.credits-balance-hero strong {
  font-size: 30px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.1;
  color: var(--color-gold-soft);
  font-variant-numeric: tabular-nums;
}

.credits-balance-hero span {
  font-size: 12px;
  color: var(--color-muted);
}

.credits-balance-hero.is-neg strong {
  color: var(--color-error);
}

.credits-neg-warn {
  margin: -4px 0 0;
  font-size: 12px;
  color: var(--color-error);
}

.credits-asset-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: auto;
  padding-top: 10px;
  border-top: 1px solid var(--border-subtle);
}

.credits-frozen-summary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-muted);
}

.credits-frozen-summary strong {
  color: var(--color-text);
  font-variant-numeric: tabular-nums;
}

.credits-frozen-summary strong.is-active {
  color: var(--color-gold-soft);
}

.credits-frozen-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border: 1px solid rgb(240 184 75 / 34%);
  border-radius: 6px;
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-size: 11px;
  cursor: pointer;
}

.credits-frozen-toggle:hover {
  border-color: var(--color-gold);
}

.credits-spend-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.credits-kpi {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.credits-kpi span {
  font-size: 11px;
  color: var(--color-muted);
}

.credits-kpi strong {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
  font-variant-numeric: tabular-nums;
}

.credits-kpi strong.is-spend {
  color: #fca5a5;
}

.credits-kpi strong.is-income {
  color: var(--color-success);
}

.credits-breakdown {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: auto;
}

.credits-breakdown-bar {
  display: flex;
  height: 7px;
  gap: 2px;
  overflow: hidden;
  border-radius: 999px;
  background: rgb(255 255 255 / 6%);
}

.credits-breakdown-fill {
  height: 100%;
  transition: width 0.25s ease;
}

.credits-breakdown-fill.is-video {
  background: #f0b84b;
}

.credits-breakdown-fill.is-image {
  background: #60a5fa;
}

.credits-breakdown-fill.is-text {
  background: #a78bfa;
}

.credits-breakdown-empty {
  width: 100%;
  height: 100%;
  background: rgb(255 255 255 / 4%);
}

.credits-breakdown-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 12px;
}

.credits-breakdown-legend li {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.credits-legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.credits-legend-dot.is-video { background: #f0b84b; }
.credits-legend-dot.is-image { background: #60a5fa; }
.credits-legend-dot.is-text { background: #a78bfa; }

.credits-legend-label {
  color: var(--color-muted);
}

.credits-legend-val {
  color: var(--color-text);
  font-variant-numeric: tabular-nums;
}

.credits-breakdown-legend small {
  color: var(--color-muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.credits-frozen-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid rgb(240 184 75 / 28%);
  border-radius: 9px;
  background: rgb(240 184 75 / 5%);
}

.credits-frozen-panel-head {
  font-size: 12px;
  color: var(--color-gold-soft);
}

.credits-frozen-panel-head span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.credits-frozen-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.credits-frozen-list li {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: var(--color-canvas);
}

.credits-frozen-info {
  min-width: 0;
}

.credits-frozen-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.credits-frozen-sub {
  margin-top: 2px;
  font-size: 11px;
  color: var(--color-muted);
  font-variant-numeric: tabular-nums;
}

.credits-frozen-amount {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-gold-soft);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.credits-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px 12px;
  padding-top: 4px;
  border-top: 1px solid var(--border-subtle);
}

.credits-view-switch {
  display: inline-flex;
  padding: 3px;
  border: 1px solid var(--border-control);
  border-radius: 8px;
  background: var(--color-canvas);
}

.credits-view-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 12px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 140ms ease, color 140ms ease;
}

.credits-view-tab:hover {
  color: var(--color-text);
}

.credits-view-tab.is-active {
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-weight: 600;
}

.credits-view-count {
  padding: 0 6px;
  border-radius: 999px;
  background: rgb(240 184 75 / 18%);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.credits-filter-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.credits-cat-pills {
  display: inline-flex;
  padding: 2px;
  border: 1px solid var(--border-control);
  border-radius: 7px;
  background: var(--color-canvas);
}

.credits-cat-pill {
  height: 26px;
  padding: 0 9px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--color-muted);
  font-size: 12px;
  cursor: pointer;
}

.credits-cat-pill:hover {
  color: var(--color-text);
}

.credits-cat-pill.is-active {
  background: rgb(255 255 255 / 10%);
  color: var(--color-text);
  font-weight: 500;
}

.credits-select-wrap {
  width: 112px;
}

.credits-select-wrap :deep(.ui-select) {
  min-height: 32px;
  height: 32px;
  font-size: 12px;
}

.credits-search {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  width: 184px;
  height: 32px;
  padding: 0 9px;
  border: 1px solid var(--border-control);
  border-radius: 7px;
  background: var(--color-canvas);
  color: var(--color-muted);
}

.credits-search:focus-within {
  border-color: rgb(240 184 75 / 50%);
  color: var(--color-text);
}

.credits-search input {
  width: 100%;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--color-text);
  font-size: 12px;
  outline: none;
}

.credits-search input::placeholder {
  color: var(--color-muted);
}

.credits-search-clear {
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  border: 0;
  background: transparent;
  color: var(--color-muted);
  cursor: pointer;
}

.credits-mono {
  font-variant-numeric: tabular-nums;
}

.credits-muted {
  color: var(--color-muted);
}

.credits-bill-title-cell {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  min-width: 0;
}

.credits-cat-icon {
  flex: none;
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  margin-top: 1px;
  border-radius: 6px;
  background: rgb(255 255 255 / 6%);
  color: var(--color-muted);
}

.credits-cat-icon.is-video {
  background: rgb(240 184 75 / 14%);
  color: var(--color-gold-soft);
}

.credits-cat-icon.is-image {
  background: rgb(96 165 250 / 14%);
  color: #93c5fd;
}

.credits-cat-icon.is-text {
  background: rgb(167 139 250 / 14%);
  color: #c4b5fd;
}

.credits-cat-icon.is-income {
  background: rgb(74 222 128 / 14%);
  color: var(--color-success);
}

.credits-bill-title-text {
  min-width: 0;
}

.credits-bill-title-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.credits-row-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--color-text);
  font-size: 13px;
  font-weight: 500;
  text-align: left;
  cursor: pointer;
}

.credits-row-link:hover {
  color: var(--color-gold-soft);
}

.credits-source-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 160px;
  padding: 1px 6px;
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  background: rgb(255 255 255 / 3%);
  color: var(--color-muted);
  font-size: 11px;
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.credits-source-chip:hover {
  border-color: rgb(240 184 75 / 40%);
  color: var(--color-gold-soft);
}

.credits-row-sub {
  margin-top: 2px;
  font-size: 11px;
  color: var(--color-muted);
}

.credits-model-cell {
  min-width: 0;
}

.credits-model-name {
  font-size: 12px;
  color: var(--color-text);
}

.credits-status-pill,
.credits-op-tag,
.credits-mini-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 7px;
  border-radius: 999px;
  border: 1px solid var(--border-control);
  background: rgb(255 255 255 / 4%);
  font-size: 11px;
  color: var(--color-muted);
  white-space: nowrap;
}

.credits-status-pill.is-charged,
.credits-op-tag.is-llm_consume {
  border-color: rgb(248 113 113 / 28%);
  background: rgb(248 113 113 / 10%);
  color: #fca5a5;
}

.credits-status-pill.is-frozen,
.credits-op-tag.is-freeze,
.credits-mini-tag.is-review {
  border-color: rgb(240 184 75 / 36%);
  background: var(--gold-tint);
  color: var(--color-gold-soft);
}

.credits-status-pill.is-refunded,
.credits-op-tag.is-settle {
  border-color: rgb(96 165 250 / 32%);
  background: rgb(96 165 250 / 10%);
  color: #93c5fd;
}

.credits-status-pill.is-credited,
.credits-op-tag.is-grant,
.credits-op-tag.is-release {
  border-color: rgb(74 222 128 / 32%);
  background: rgb(74 222 128 / 10%);
  color: var(--color-success);
}

.credits-op-tag.is-adjust {
  border-color: rgb(167 139 250 / 34%);
  background: rgb(167 139 250 / 10%);
  color: #c4b5fd;
}

.credits-amount-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
}

.credits-amount-cell strong.is-pos {
  color: var(--color-success);
}

.credits-amount-cell strong.is-neg {
  color: #fca5a5;
}

.credits-amount-cell strong.is-frozen {
  color: var(--color-gold-soft);
}

.credits-amount-cell strong.is-refunded,
.credits-amount-cell strong.is-neutral {
  color: var(--color-muted);
}

.credits-amount-strike {
  font-size: 11px;
  color: var(--color-muted);
  text-decoration: line-through;
}

.credits-detail-btn {
  padding: 3px 8px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: var(--color-muted);
  font-size: 12px;
  cursor: pointer;
}

.credits-detail-btn:hover {
  border-color: var(--border-control);
  background: var(--surface-hover);
  color: var(--color-gold-soft);
}

.ui-spin {
  animation: credits-spin 1s linear infinite;
}

@keyframes credits-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 960px) {
  .credits-overview-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 640px) {
  .credits-panel {
    padding: 14px;
  }
  .credits-spend-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .credits-search {
    width: 100%;
  }
}
</style>
