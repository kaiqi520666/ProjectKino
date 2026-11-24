<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  Ban,
  Check,
  Copy,
  Download,
  ExternalLink,
  Link2,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Ticket,
  X,
} from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import UiDataTable, { type DataTableColumn } from '@/components/ui/UiDataTable.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import {
  createAdminRedeemBatch,
  disableAdminRedeemBatch,
  listAdminRedeemCodes,
  listAdminRedeemCodeUses,
  updateAdminRedeemCodeStatus,
  updateAdminRedeemPurchaseUrl,
  type AdminRedeemBatchCreateResult,
  type AdminRedeemCodeItem,
  type AdminRedeemCodeStatus,
  type AdminRedeemCodeUseItem,
  type AdminRedeemStats,
} from '@/features/admin/api'
import { extractErrorMessage, formatCredits, formatDateTime } from '@/features/admin/format'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

const loading = ref(false)
const items = ref<AdminRedeemCodeItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const stats = ref<AdminRedeemStats>({
  totalCodes: 0,
  activeCodes: 0,
  usedCountTotal: 0,
  redeemedCreditsTotal: '0',
})
const batches = ref<string[]>([])

const statusFilter = ref<'' | AdminRedeemCodeStatus>('')
const batchFilter = ref('')
const keyword = ref('')

const purchaseUrl = ref('')
const savedPurchaseUrl = ref('')
const savingUrl = ref(false)

const copiedCodeId = ref<string | null>(null)
const togglingId = ref<string | null>(null)
const batchDisabling = ref(false)

// 生成弹窗状态
const createOpen = ref(false)
const creating = ref(false)
const generatedResult = ref<AdminRedeemBatchCreateResult | null>(null)
const copiedBatch = ref(false)
const createForm = reactive({
  credits: '100',
  count: '20',
  prefix: '',
  batchName: '',
  maxUses: '1',
  expiresAtLocal: '',
})

// 核销记录弹窗状态
const usesOpen = ref(false)
const usesLoading = ref(false)
const activeCodeItem = ref<AdminRedeemCodeItem | null>(null)
const usesList = ref<AdminRedeemCodeUseItem[]>([])

const statusTabs: ReadonlyArray<{ value: '' | AdminRedeemCodeStatus; label: string }> = [
  { value: '', label: '全部' },
  { value: 'active', label: '可用' },
  { value: 'exhausted', label: '已兑完' },
  { value: 'expired', label: '已过期' },
  { value: 'disabled', label: '已作废' },
]

const STATUS_LABELS: Record<AdminRedeemCodeStatus, string> = {
  active: '可用',
  exhausted: '已兑完',
  expired: '已过期',
  disabled: '已作废',
}

const batchSelectOptions = computed(() => [
  { value: 'all', label: '全部批次' },
  ...batches.value.map((b) => ({ value: b, label: b })),
])

const batchSelectModel = computed({
  get: () => batchFilter.value || 'all',
  set: (val: string) => {
    batchFilter.value = val === 'all' ? '' : val
    void loadCodes(true)
  },
})

const canSavePurchaseUrl = computed(
  () => purchaseUrl.value.trim() !== savedPurchaseUrl.value && !savingUrl.value,
)

const columns: DataTableColumn[] = [
  { key: 'code', label: '兑换码', width: '240px' },
  { key: 'batchName', label: '批次' },
  { key: 'credits', label: '面额', align: 'right', width: '100px' },
  { key: 'usage', label: '进度', align: 'right', width: '88px' },
  { key: 'status', label: '状态', width: '88px' },
  { key: 'expiresAt', label: '过期时间', width: '154px' },
  { key: 'createdAt', label: '创建时间', width: '154px' },
  { key: 'actions', label: '操作', align: 'right', width: '132px' },
]

const usesColumns: DataTableColumn[] = [
  { key: 'email', label: '用户邮箱' },
  { key: 'nickname', label: '昵称', width: '140px' },
  { key: 'credits', label: '到账积分', align: 'right', width: '110px' },
  { key: 'createdAt', label: '兑换时间', width: '164px' },
]

async function loadCodes(resetPage = false) {
  if (resetPage) page.value = 1
  loading.value = true
  try {
    const res = await listAdminRedeemCodes({
      status: statusFilter.value || undefined,
      batch_name: batchFilter.value || undefined,
      keyword: keyword.value.trim() || undefined,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    })
    items.value = res.items
    total.value = res.total
    stats.value = res.stats
    batches.value = res.batches
    purchaseUrl.value = res.purchaseUrl || ''
    savedPurchaseUrl.value = res.purchaseUrl || ''
  } catch (err) {
    ui.notify(extractErrorMessage(err, '加载兑换码列表失败'), 'error')
  } finally {
    loading.value = false
  }
}

async function savePurchaseUrl() {
  const cleaned = purchaseUrl.value.trim()
  if (cleaned && !cleaned.startsWith('http://') && !cleaned.startsWith('https://')) {
    ui.notify('购买链接必须以 http:// 或 https:// 开头', 'error')
    return
  }
  savingUrl.value = true
  try {
    const res = await updateAdminRedeemPurchaseUrl(cleaned)
    purchaseUrl.value = res.purchaseUrl
    savedPurchaseUrl.value = res.purchaseUrl
    ui.notify(res.purchaseUrl ? '购买链接已保存' : '已关闭购买链接入口', 'success')
  } catch (err) {
    ui.notify(extractErrorMessage(err, '保存购买链接失败'), 'error')
  } finally {
    savingUrl.value = false
  }
}

function openCreateDialog() {
  generatedResult.value = null
  copiedBatch.value = false
  createOpen.value = true
}

async function submitCreateBatch() {
  const creditsNum = Number(createForm.credits)
  if (!Number.isFinite(creditsNum) || creditsNum <= 0) {
    ui.notify('面额积分必须大于 0', 'error')
    return
  }
  const countNum = Math.round(Number(createForm.count))
  if (!Number.isFinite(countNum) || countNum < 1 || countNum > 500) {
    ui.notify('生成数量需在 1–500 之间', 'error')
    return
  }
  const maxUsesNum = Math.max(1, Math.round(Number(createForm.maxUses) || 1))
  let expiresIso: string | null = null
  if (createForm.expiresAtLocal.trim()) {
    const dt = new Date(createForm.expiresAtLocal)
    if (Number.isNaN(dt.getTime())) {
      ui.notify('过期时间格式无效', 'error')
      return
    }
    expiresIso = dt.toISOString()
  }

  creating.value = true
  try {
    const res = await createAdminRedeemBatch({
      credits: String(creditsNum),
      count: countNum,
      prefix: createForm.prefix.trim(),
      batchName: createForm.batchName.trim(),
      maxUses: maxUsesNum,
      expiresAt: expiresIso,
    })
    generatedResult.value = res
    ui.notify(`已生成 ${res.count} 个兑换码`, 'success')
    void loadCodes(true)
  } catch (err) {
    ui.notify(extractErrorMessage(err, '生成兑换码失败'), 'error')
  } finally {
    creating.value = false
  }
}

async function copySingleCode(item: AdminRedeemCodeItem) {
  try {
    await navigator.clipboard.writeText(item.code)
    copiedCodeId.value = item.id
    setTimeout(() => {
      if (copiedCodeId.value === item.id) copiedCodeId.value = null
    }, 1500)
  } catch {
    ui.notify('复制失败', 'error')
  }
}

async function copyAllGenerated() {
  if (!generatedResult.value) return
  try {
    await navigator.clipboard.writeText(generatedResult.value.codes.join('\n'))
    copiedBatch.value = true
    ui.notify(`已复制 ${generatedResult.value.codes.length} 个兑换码`, 'success')
    setTimeout(() => {
      copiedBatch.value = false
    }, 1800)
  } catch {
    ui.notify('复制失败', 'error')
  }
}

function downloadGenerated(format: 'txt' | 'csv') {
  if (!generatedResult.value) return
  const { codes, credits, batchName } = generatedResult.value
  const stamp = new Date().toISOString().slice(0, 10)
  let content = ''
  let mime = 'text/plain;charset=utf-8;'
  if (format === 'txt') {
    content = codes.join('\n')
  } else {
    mime = 'text/csv;charset=utf-8;'
    const rows = codes.map((c) => `${c},${formatCredits(credits)},${batchName || ''}`)
    content = `\uFEFF兑换码,面额积分,批次\n${rows.join('\n')}`
  }
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `redeem-codes-${stamp}.${format}`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

async function toggleCodeStatus(item: AdminRedeemCodeItem) {
  const nextStatus = item.rawStatus === 'disabled' ? 'active' : 'disabled'
  togglingId.value = item.id
  try {
    await updateAdminRedeemCodeStatus(item.id, nextStatus)
    ui.notify(nextStatus === 'disabled' ? '已作废' : '已重新启用', 'success')
    await loadCodes(false)
  } catch (err) {
    ui.notify(extractErrorMessage(err, '更新状态失败'), 'error')
  } finally {
    togglingId.value = null
  }
}

async function handleBatchDisable() {
  const target = batchFilter.value.trim()
  if (!target) return
  if (!window.confirm(`确认作废批次「${target}」下所有未兑换的兑换码？`)) return
  batchDisabling.value = true
  try {
    const res = await disableAdminRedeemBatch(target)
    ui.notify(`已作废 ${res.disabledCount} 个未兑换卡密`, 'success')
    await loadCodes(false)
  } catch (err) {
    ui.notify(extractErrorMessage(err, '批量作废失败'), 'error')
  } finally {
    batchDisabling.value = false
  }
}

async function openUsesDialog(item: AdminRedeemCodeItem) {
  activeCodeItem.value = item
  usesList.value = []
  usesOpen.value = true
  usesLoading.value = true
  try {
    const res = await listAdminRedeemCodeUses(item.id)
    usesList.value = res.items
  } catch (err) {
    ui.notify(extractErrorMessage(err, '加载核销记录失败'), 'error')
  } finally {
    usesLoading.value = false
  }
}

function selectStatus(val: '' | AdminRedeemCodeStatus) {
  if (statusFilter.value === val) return
  statusFilter.value = val
  void loadCodes(true)
}

onMounted(() => {
  void loadCodes(true)
})
</script>

<template>
  <section class="admin-section admin-page-shell">
    <WorkspacePageHeader title="兑换码">
      <template #icon><Ticket :size="19" :stroke-width="1.7" /></template>
      <template #actions>
        <UiButton variant="outline" size="sm" :disabled="loading" @click="loadCodes(false)">
          <template #leading><RefreshCw :size="13" :class="{ 'ui-spin': loading }" aria-hidden="true" /></template>
          刷新
        </UiButton>
        <UiButton variant="primary" size="sm" @click="openCreateDialog">
          <template #leading><Plus :size="14" aria-hidden="true" /></template>
          生成兑换码
        </UiButton>
      </template>
    </WorkspacePageHeader>

    <!-- 汇总统计 -->
    <div class="admin-kpi-grid">
      <div class="admin-kpi-card">
        <span>总兑换码</span>
        <strong>{{ stats.totalCodes }}</strong>
      </div>
      <div class="admin-kpi-card">
        <span>当前可用</span>
        <strong class="is-gold">{{ stats.activeCodes }}</strong>
      </div>
      <div class="admin-kpi-card">
        <span>已核销次数</span>
        <strong>{{ stats.usedCountTotal }}</strong>
      </div>
      <div class="admin-kpi-card">
        <span>已发放积分</span>
        <strong class="is-gold">{{ formatCredits(stats.redeemedCreditsTotal) }}</strong>
      </div>
    </div>

    <!-- 外部购买链接配置条 -->
    <form class="redeem-url-bar" @submit.prevent="savePurchaseUrl">
      <span class="redeem-url-label">
        <Link2 :size="14" aria-hidden="true" />
        购买兑换码链接
      </span>
      <input
        v-model="purchaseUrl"
        type="url"
        class="redeem-url-input"
        placeholder="输入外部购买链接（如发卡网地址 https://...），留空则隐藏前台入口"
      />
      <a
        v-if="savedPurchaseUrl"
        :href="savedPurchaseUrl"
        target="_blank"
        rel="noopener noreferrer"
        class="redeem-url-preview"
      >
        <span>打开</span>
        <ExternalLink :size="12" aria-hidden="true" />
      </a>
      <UiButton type="submit" variant="primary" size="sm" :disabled="!canSavePurchaseUrl" :loading="savingUrl">
        <template #leading><Save :size="13" aria-hidden="true" /></template>
        保存
      </UiButton>
    </form>

    <!-- 筛选条 -->
    <div class="redeem-toolbar">
      <div class="admin-chip-group">
        <button
          v-for="tab in statusTabs"
          :key="tab.value || 'all'"
          type="button"
          class="admin-chip"
          :class="{ 'is-active': statusFilter === tab.value }"
          @click="selectStatus(tab.value)"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="redeem-toolbar-right">
        <div v-if="batches.length" class="redeem-batch-select">
          <UiSelect v-model="batchSelectModel" :options="batchSelectOptions" placeholder="全部批次" />
        </div>

        <label class="redeem-search">
          <Search :size="13" aria-hidden="true" />
          <input
            v-model="keyword"
            type="text"
            placeholder="搜索兑换码或批次"
            @keyup.enter="loadCodes(true)"
          />
          <button
            v-if="keyword"
            type="button"
            class="redeem-search-clear"
            aria-label="清空"
            @click="keyword = ''; loadCodes(true)"
          >
            <X :size="12" aria-hidden="true" />
          </button>
        </label>

        <UiButton
          v-if="batchFilter"
          variant="outline"
          size="sm"
          :loading="batchDisabling"
          @click="handleBatchDisable"
        >
          <template #leading><Ban :size="13" aria-hidden="true" /></template>
          作废本批次
        </UiButton>
      </div>
    </div>

    <!-- 卡密数据表 -->
    <UiDataTable
      v-model:page="page"
      v-model:page-size="pageSize"
      :columns="columns"
      :rows="items"
      row-key="id"
      :loading="loading"
      empty-text="暂无兑换码"
      compact
      paginated
      :total="total"
      :page-size-options="[20, 50, 100]"
      @change="loadCodes(false)"
    >
      <template #cell-code="{ row }">
        <button
          type="button"
          class="redeem-code-copy"
          :title="'点击复制 ' + row.code"
          @click="copySingleCode(row)"
        >
          <code class="admin-mono">{{ row.code }}</code>
          <Check v-if="copiedCodeId === row.id" :size="12" class="is-copied" aria-hidden="true" />
          <Copy v-else :size="12" aria-hidden="true" />
        </button>
      </template>

      <template #cell-batchName="{ row }">
        <span>{{ row.batchName || '-' }}</span>
      </template>

      <template #cell-credits="{ row }">
        <strong class="admin-mono is-gold">+{{ formatCredits(row.credits) }}</strong>
      </template>

      <template #cell-usage="{ row }">
        <span class="admin-mono">{{ row.usedCount }} / {{ row.maxUses }}</span>
      </template>

      <template #cell-status="{ row }">
        <span class="redeem-status-pill" :class="`is-${row.status}`">
          {{ STATUS_LABELS[row.status as AdminRedeemCodeStatus] || row.status }}
        </span>
      </template>

      <template #cell-expiresAt="{ row }">
        <span class="admin-mono admin-muted">{{ row.expiresAt ? formatDateTime(row.expiresAt) : '永久' }}</span>
      </template>

      <template #cell-createdAt="{ row }">
        <span class="admin-mono admin-muted">{{ formatDateTime(row.createdAt) }}</span>
      </template>

      <template #cell-actions="{ row }">
        <div class="redeem-row-actions">
          <button
            v-if="row.usedCount > 0"
            type="button"
            class="redeem-link-btn"
            @click="openUsesDialog(row)"
          >
            记录
          </button>
          <button
            v-if="row.status !== 'exhausted'"
            type="button"
            class="redeem-link-btn"
            :class="row.rawStatus === 'disabled' ? 'is-enable' : 'is-danger'"
            :disabled="togglingId === row.id"
            @click="toggleCodeStatus(row)"
          >
            <RotateCcw v-if="row.rawStatus === 'disabled'" :size="12" aria-hidden="true" />
            {{ row.rawStatus === 'disabled' ? '启用' : '作废' }}
          </button>
        </div>
      </template>
    </UiDataTable>

    <!-- 批量生成弹窗 -->
    <UiDialog v-model:open="createOpen" :title="generatedResult ? '生成结果' : '批量生成兑换码'" size="wide">
      <form v-if="!generatedResult" class="redeem-create-form" @submit.prevent="submitCreateBatch">
        <div class="redeem-create-grid">
          <UiInput
            v-model="createForm.credits"
            type="number"
            label="面额积分"
            placeholder="例如 100"
            required
          />
          <UiInput
            v-model="createForm.count"
            type="number"
            label="生成数量（1–500）"
            placeholder="10"
            required
          />
          <UiInput
            v-model="createForm.prefix"
            label="卡密前缀（可选）"
            placeholder="例如 KINO"
          />
          <UiInput
            v-model="createForm.batchName"
            label="批次备注（可选）"
            placeholder="例如 发卡网-100积分"
          />
          <UiInput
            v-model="createForm.maxUses"
            type="number"
            label="单码可用次数"
            placeholder="1"
            required
          />
          <div class="redeem-date-field">
            <label class="ui-label" for="redeem-expires-input">过期时间（可选）</label>
            <input
              id="redeem-expires-input"
              v-model="createForm.expiresAtLocal"
              type="datetime-local"
              class="redeem-datetime-input"
            />
          </div>
        </div>

        <div class="redeem-dialog-foot">
          <UiButton type="button" variant="outline" size="sm" :disabled="creating" @click="createOpen = false">
            取消
          </UiButton>
          <UiButton type="submit" variant="primary" size="sm" :loading="creating">
            <template #leading><Plus :size="14" aria-hidden="true" /></template>
            立即生成
          </UiButton>
        </div>
      </form>

      <div v-else class="redeem-result-box">
        <div class="redeem-result-meta">
          <span>数量：<strong>{{ generatedResult.count }}</strong></span>
          <span>面额：<strong class="is-gold">+{{ formatCredits(generatedResult.credits) }} 积分</strong></span>
          <span v-if="generatedResult.batchName">批次：<strong>{{ generatedResult.batchName }}</strong></span>
        </div>

        <textarea
          class="redeem-result-textarea admin-mono"
          readonly
          :rows="Math.min(14, Math.max(6, generatedResult.codes.length))"
          :value="generatedResult.codes.join('\n')"
        ></textarea>

        <div class="redeem-dialog-foot is-split">
          <div class="redeem-export-group">
            <UiButton variant="primary" size="sm" @click="copyAllGenerated">
              <template #leading>
                <Check v-if="copiedBatch" :size="13" aria-hidden="true" />
                <Copy v-else :size="13" aria-hidden="true" />
              </template>
              {{ copiedBatch ? '已复制' : '复制全部' }}
            </UiButton>
            <UiButton variant="outline" size="sm" @click="downloadGenerated('txt')">
              <template #leading><Download :size="13" aria-hidden="true" /></template>
              导出 TXT
            </UiButton>
            <UiButton variant="outline" size="sm" @click="downloadGenerated('csv')">
              <template #leading><Download :size="13" aria-hidden="true" /></template>
              导出 CSV
            </UiButton>
          </div>
          <div class="redeem-export-group">
            <UiButton variant="ghost" size="sm" @click="generatedResult = null">
              继续生成
            </UiButton>
            <UiButton variant="outline" size="sm" @click="createOpen = false">
              完成
            </UiButton>
          </div>
        </div>
      </div>
    </UiDialog>

    <!-- 核销记录弹窗 -->
    <UiDialog
      v-model:open="usesOpen"
      :title="activeCodeItem ? `核销记录 · ${activeCodeItem.code}` : '核销记录'"
      size="wide"
    >
      <UiDataTable
        :columns="usesColumns"
        :rows="usesList"
        row-key="id"
        :loading="usesLoading"
        empty-text="暂无核销记录"
        compact
      >
        <template #cell-credits="{ row }">
          <strong class="admin-mono is-gold">+{{ formatCredits(row.credits) }}</strong>
        </template>
        <template #cell-createdAt="{ row }">
          <span class="admin-mono admin-muted">{{ formatDateTime(row.createdAt) }}</span>
        </template>
      </UiDataTable>
    </UiDialog>
  </section>
</template>

<style scoped>
.is-gold {
  color: var(--color-gold-soft);
}

.admin-muted {
  color: var(--color-muted);
}

.redeem-url-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  background: var(--color-surface);
  flex-wrap: wrap;
}

.redeem-url-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text);
  white-space: nowrap;
}

.redeem-url-input {
  flex: 1 1 280px;
  min-width: 220px;
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--border-control);
  border-radius: 7px;
  background: var(--color-canvas);
  color: var(--color-text);
  font-size: 13px;
  outline: none;
}

.redeem-url-input:focus {
  border-color: rgb(240 184 75 / 55%);
}

.redeem-url-preview {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12.5px;
  color: var(--color-gold-soft);
  text-decoration: none;
  padding: 0 6px;
}

.redeem-url-preview:hover {
  text-decoration: underline;
}

.redeem-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.redeem-toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.redeem-batch-select {
  min-width: 150px;
}

.redeem-search {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--border-control);
  border-radius: 7px;
  background: var(--color-surface);
  color: var(--color-muted);
}

.redeem-search input {
  width: 170px;
  border: none;
  background: transparent;
  color: var(--color-text);
  font-size: 12.5px;
  outline: none;
}

.redeem-search-clear {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--color-muted);
  cursor: pointer;
  padding: 0;
}

.redeem-code-copy {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 3px 7px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text);
  cursor: pointer;
  transition: background-color 0.14s ease, border-color 0.14s ease;
}

.redeem-code-copy:hover {
  background: rgb(255 255 255 / 4%);
  border-color: var(--border-subtle);
}

.redeem-code-copy .is-copied {
  color: #4ade80;
}

.redeem-status-pill {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
}

.redeem-status-pill.is-active {
  background: rgb(74 222 128 / 12%);
  color: #4ade80;
  border: 1px solid rgb(74 222 128 / 28%);
}

.redeem-status-pill.is-exhausted {
  background: rgb(148 163 184 / 12%);
  color: var(--color-muted);
  border: 1px solid var(--border-subtle);
}

.redeem-status-pill.is-expired {
  background: rgb(245 158 11 / 12%);
  color: #fbbf24;
  border: 1px solid rgb(245 158 11 / 28%);
}

.redeem-status-pill.is-disabled {
  background: rgb(248 113 113 / 12%);
  color: #f87171;
  border: 1px solid rgb(248 113 113 / 28%);
}

.redeem-row-actions {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.redeem-link-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: none;
  background: transparent;
  color: var(--color-gold-soft);
  font-size: 12.5px;
  cursor: pointer;
  padding: 0;
}

.redeem-link-btn:hover {
  text-decoration: underline;
}

.redeem-link-btn.is-danger {
  color: #f87171;
}

.redeem-link-btn.is-enable {
  color: #4ade80;
}

.redeem-create-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.redeem-create-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.redeem-date-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.redeem-datetime-input {
  height: 36px;
  padding: 0 10px;
  border: 1px solid var(--border-control);
  border-radius: 7px;
  background: var(--color-canvas);
  color: var(--color-text);
  font-size: 13px;
  color-scheme: dark;
}

.redeem-result-box {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.redeem-result-meta {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-wrap: wrap;
  font-size: 13px;
  color: var(--color-muted);
}

.redeem-result-meta strong {
  color: var(--color-text);
}

.redeem-result-textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--color-canvas);
  color: var(--color-text);
  font-size: 13px;
  line-height: 1.65;
  resize: vertical;
  outline: none;
}

.redeem-dialog-foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.redeem-dialog-foot.is-split {
  justify-content: space-between;
}

.redeem-export-group {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 640px) {
  .redeem-create-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
