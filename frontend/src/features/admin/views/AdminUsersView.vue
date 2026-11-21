<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Coins, FileText, RefreshCw, Search, Shield, Users } from 'lucide-vue-next'
import UiDataTable, { type DataTableColumn } from '@/components/ui/UiDataTable.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import {
  adjustAdminUserCredits,
  getAdminUserLedgers,
  listAdminUsers,
  updateAdminUser,
  type AdminUserItem,
  type CreditLedgerItem,
} from '@/features/admin/api'
import {
  extractErrorMessage,
  formatCredits,
  formatDateTime,
  formatSignedCredits,
  formatTokenUsage,
  LEDGER_OP_LABELS,
  ROLE_LABELS,
} from '@/features/admin/format'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const auth = useAuthStore()

const loading = ref(false)
const users = ref<AdminUserItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(30)

const filters = reactive({
  q: '',
  role: 'all',
  status: 'all',
})

const userColumns: DataTableColumn[] = [
  { key: 'id', label: 'ID', width: '76px' },
  { key: 'account', label: '账号 / 昵称' },
  { key: 'role', label: '角色' },
  { key: 'status', label: '状态' },
  { key: 'balance', label: '可用余额', align: 'right' },
  { key: 'frozen', label: '冻结积分', align: 'right' },
  { key: 'usageMultiplier', label: '倍率', align: 'right' },
  { key: 'stats', label: '项目 / 任务', align: 'right' },
  { key: 'createdAt', label: '注册时间' },
  { key: 'actions', label: '操作' },
]

const ledgerColumns: DataTableColumn[] = [
  { key: 'createdAt', label: '时间' },
  { key: 'operation', label: '类型' },
  { key: 'balanceChange', label: '余额变动', align: 'right' },
  { key: 'balanceRange', label: '余额变化' },
  { key: 'frozenChange', label: '冻结变动', align: 'right' },
  { key: 'reason', label: '说明 / Token 用量' },
]

const roleFilterOptions = [
  { value: 'all', label: '全部角色' },
  { value: 'user', label: '普通用户' },
  { value: 'operator', label: '运营' },
  { value: 'admin', label: '管理员' },
]

const statusFilterOptions = [
  { value: 'all', label: '全部状态' },
  { value: 'active', label: '正常' },
  { value: 'disabled', label: '已禁用' },
]

const roleEditOptions = [
  { value: 'user', label: '普通用户' },
  { value: 'operator', label: '运营' },
  { value: 'admin', label: '管理员' },
]

const statusEditOptions = [
  { value: 'active', label: '正常' },
  { value: 'disabled', label: '禁用' },
]

// Credit adjustment dialog
const creditDialogOpen = ref(false)
const creditSubmitting = ref(false)
const creditTarget = ref<AdminUserItem | null>(null)
const creditForm = reactive({
  amount: '',
  reason: '',
})

// Role / status / multiplier edit dialog
const editDialogOpen = ref(false)
const editSubmitting = ref(false)
const editTarget = ref<AdminUserItem | null>(null)
const editForm = reactive<{
  nickname: string
  role: 'user' | 'operator' | 'admin'
  status: 'active' | 'disabled'
  usageMultiplier: string
}>({
  nickname: '',
  role: 'user',
  status: 'active',
  usageMultiplier: '1.00',
})

// Ledger inspection dialog
const ledgerDialogOpen = ref(false)
const ledgerLoading = ref(false)
const ledgerTarget = ref<AdminUserItem | null>(null)
const ledgerItems = ref<CreditLedgerItem[]>([])
const ledgerTotal = ref(0)
const ledgerPage = ref(1)
const ledgerPageSize = ref(20)

async function loadUsers(resetPage = false) {
  if (resetPage) page.value = 1
  loading.value = true
  try {
    const res = await listAdminUsers({
      q: filters.q.trim() || undefined,
      role: filters.role === 'all' ? undefined : filters.role,
      status: filters.status === 'all' ? undefined : filters.status,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value,
    })
    users.value = res.items
    total.value = res.total
  } catch (err) {
    ui.notify(extractErrorMessage(err, '加载用户列表失败'), 'error')
  } finally {
    loading.value = false
  }
}

function openCreditDialog(user: AdminUserItem) {
  creditTarget.value = user
  creditForm.amount = '100'
  creditForm.reason = ''
  creditDialogOpen.value = true
}

async function submitCreditAdjust() {
  if (!creditTarget.value) return
  const parsed = Number(creditForm.amount)
  if (!Number.isFinite(parsed) || parsed === 0) {
    ui.notify('请输入非零的积分变动数值', 'error')
    return
  }
  if (!creditForm.reason.trim()) {
    ui.notify('请填写调账原因', 'error')
    return
  }
  creditSubmitting.value = true
  try {
    await adjustAdminUserCredits(creditTarget.value.id, {
      amount: String(creditForm.amount).trim(),
      reason: creditForm.reason.trim(),
    })
    ui.notify(`已为 ${creditTarget.value.email} 调整积分 ${formatSignedCredits(parsed)}`, 'success')
    creditDialogOpen.value = false
    await loadUsers()
    if (creditTarget.value.id === auth.user?.id) {
      await auth.refreshBalance()
    }
  } catch (err) {
    ui.notify(extractErrorMessage(err, '调账失败'), 'error')
  } finally {
    creditSubmitting.value = false
  }
}

function openEditDialog(user: AdminUserItem) {
  editTarget.value = user
  editForm.nickname = user.nickname
  editForm.role = user.role
  editForm.status = user.status
  editForm.usageMultiplier = user.usageMultiplier
  editDialogOpen.value = true
}

async function submitUserEdit() {
  if (!editTarget.value) return
  const mult = Number(editForm.usageMultiplier)
  if (!Number.isFinite(mult) || mult <= 0 || mult > 100) {
    ui.notify('费率倍率必须在 0 ~ 100 之间', 'error')
    return
  }
  editSubmitting.value = true
  try {
    await updateAdminUser(editTarget.value.id, {
      nickname: editForm.nickname.trim(),
      role: editForm.role,
      status: editForm.status,
      usageMultiplier: String(editForm.usageMultiplier).trim(),
    })
    ui.notify(`已更新用户 ${editTarget.value.email}`, 'success')
    editDialogOpen.value = false
    await loadUsers()
  } catch (err) {
    ui.notify(extractErrorMessage(err, '更新用户信息失败'), 'error')
  } finally {
    editSubmitting.value = false
  }
}

async function loadUserLedgers() {
  if (!ledgerTarget.value) return
  ledgerLoading.value = true
  try {
    const res = await getAdminUserLedgers(ledgerTarget.value.id, {
      limit: ledgerPageSize.value,
      offset: (ledgerPage.value - 1) * ledgerPageSize.value,
    })
    ledgerTarget.value = res.user
    ledgerItems.value = res.items
    ledgerTotal.value = res.total
  } catch (err) {
    ui.notify(extractErrorMessage(err, '加载积分流水失败'), 'error')
  } finally {
    ledgerLoading.value = false
  }
}

async function openLedgerDialog(user: AdminUserItem) {
  ledgerTarget.value = user
  ledgerItems.value = []
  ledgerTotal.value = 0
  ledgerPage.value = 1
  ledgerDialogOpen.value = true
  await loadUserLedgers()
}

function roleBadgeClass(role: string) {
  if (role === 'admin') return 'admin-badge--gold'
  if (role === 'operator') return 'admin-badge--info'
  return ''
}

onMounted(() => loadUsers(true))
</script>

<template>
  <section class="admin-section">
    <WorkspacePageHeader eyebrow="管理后台" title="用户与积分" :badge="total">
      <template #icon><Users :size="19" :stroke-width="1.7" /></template>
      <template #actions>
        <button type="button" class="ui-button ui-button--secondary ui-button--sm" :disabled="loading" @click="loadUsers()">
          <RefreshCw :size="14" :class="{ 'ui-spin': loading }" />
          <span>刷新</span>
        </button>
      </template>
    </WorkspacePageHeader>

    <form class="admin-toolbar" @submit.prevent="loadUsers(true)">
      <div class="admin-filters">
        <div class="ui-input-wrap has-leading admin-search-input">
          <Search :size="15" class="ui-input-icon" />
          <input
            v-model="filters.q"
            class="ui-input"
            type="search"
            placeholder="搜索邮箱或昵称..."
          />
        </div>
        <div class="admin-filter-select">
          <UiSelect v-model="filters.role" :options="roleFilterOptions" placeholder="筛选角色" @update:model-value="loadUsers(true)" />
        </div>
        <div class="admin-filter-select">
          <UiSelect v-model="filters.status" :options="statusFilterOptions" placeholder="筛选状态" @update:model-value="loadUsers(true)" />
        </div>
        <button type="submit" class="ui-button ui-button--primary ui-button--sm">查询</button>
      </div>
    </form>

    <UiDataTable
      v-model:page="page"
      v-model:page-size="pageSize"
      :columns="userColumns"
      :rows="users"
      row-key="id"
      :loading="loading"
      loading-text="正在加载用户列表..."
      empty-text="没有匹配的用户记录"
      paginated
      :total="total"
      @change="loadUsers()"
    >
      <template #cell-id="{ row }">
        <span class="admin-mono">#{{ row.id }}</span>
      </template>
      <template #cell-account="{ row }">
        <div class="admin-cell-primary">{{ row.email }}</div>
        <div class="admin-cell-sub">{{ row.nickname || '未设昵称' }}</div>
      </template>
      <template #cell-role="{ row }">
        <span class="admin-badge" :class="roleBadgeClass(row.role)">
          {{ ROLE_LABELS[row.role] || row.role }}
        </span>
      </template>
      <template #cell-status="{ row }">
        <span class="admin-badge" :class="row.status === 'active' ? 'admin-badge--success' : 'admin-badge--danger'">
          {{ row.status === 'active' ? '正常' : '已禁用' }}
        </span>
      </template>
      <template #cell-balance="{ row }">
        <span class="admin-num" :class="{ 'admin-num--neg': Number(row.balance) < 0 }">
          {{ formatCredits(row.balance) }}
        </span>
      </template>
      <template #cell-frozen="{ row }">
        <span class="admin-num">{{ formatCredits(row.frozen) }}</span>
      </template>
      <template #cell-usageMultiplier="{ row }">
        <span class="admin-mono">{{ row.usageMultiplier }}x</span>
      </template>
      <template #cell-stats="{ row }">
        <span class="admin-num">{{ row.projectCount }} / {{ row.jobCount }}</span>
      </template>
      <template #cell-createdAt="{ row }">
        <span class="admin-mono">{{ formatDateTime(row.createdAt) }}</span>
      </template>
      <template #cell-actions="{ row }">
        <div class="admin-actions">
          <button type="button" class="ui-button ui-button--outline ui-button--sm" @click="openCreditDialog(row)">
            <Coins :size="13" />
            <span>充/扣积分</span>
          </button>
          <button type="button" class="ui-button ui-button--secondary ui-button--sm" @click="openEditDialog(row)">
            <Shield :size="13" />
            <span>改权限</span>
          </button>
          <button type="button" class="ui-button ui-button--ghost ui-button--sm" @click="openLedgerDialog(row)">
            <FileText :size="13" />
            <span>查流水</span>
          </button>
        </div>
      </template>
    </UiDataTable>

    <!-- 充/扣积分弹窗 -->
    <UiDialog
      v-model:open="creditDialogOpen"
      title="人工充/扣积分"
      :description="creditTarget ? `${creditTarget.email} · 余额 ${formatCredits(creditTarget.balance)} · 冻结 ${formatCredits(creditTarget.frozen)}` : ''"
    >
      <div class="admin-form-stack">
        <div class="ui-field">
          <label class="ui-label">变动积分 <span class="ui-required">*</span></label>
          <input
            v-model="creditForm.amount"
            class="ui-input"
            type="number"
            step="0.01"
            placeholder="正数充值，负数扣减"
          />
        </div>
        <div class="ui-field">
          <label class="ui-label">原因 <span class="ui-required">*</span></label>
          <input
            v-model="creditForm.reason"
            class="ui-input"
            type="text"
            placeholder="如：充值入账 / 异常补偿"
          />
        </div>
      </div>
      <template #footer>
        <button type="button" class="ui-button ui-button--secondary" @click="creditDialogOpen = false">取消</button>
        <button type="button" class="ui-button ui-button--primary" :disabled="creditSubmitting" @click="submitCreditAdjust">
          {{ creditSubmitting ? '提交中...' : '确认调账' }}
        </button>
      </template>
    </UiDialog>

    <!-- 修改权限/状态弹窗 -->
    <UiDialog
      v-model:open="editDialogOpen"
      title="编辑用户权限与配置"
      :description="editTarget ? `用户 #${editTarget.id} · ${editTarget.email}` : ''"
    >
      <div class="admin-form-stack">
        <div class="ui-field">
          <label class="ui-label">昵称</label>
          <input v-model="editForm.nickname" class="ui-input" type="text" placeholder="用户显示昵称" />
        </div>
        <UiSelect v-model="editForm.role" label="角色权限" :options="roleEditOptions" />
        <UiSelect v-model="editForm.status" label="账号状态" :options="statusEditOptions" />
        <div class="ui-field">
          <label class="ui-label">计费倍率</label>
          <input v-model="editForm.usageMultiplier" class="ui-input" type="number" step="0.05" min="0.01" max="100" />
        </div>
      </div>
      <template #footer>
        <button type="button" class="ui-button ui-button--secondary" @click="editDialogOpen = false">取消</button>
        <button type="button" class="ui-button ui-button--primary" :disabled="editSubmitting" @click="submitUserEdit">
          {{ editSubmitting ? '保存中...' : '保存修改' }}
        </button>
      </template>
    </UiDialog>

    <!-- 积分流水审计弹窗 -->
    <UiDialog
      v-model:open="ledgerDialogOpen"
      size="landscape"
      :title="ledgerTarget ? `积分流水 · ${ledgerTarget.email}` : '积分流水'"
      :description="ledgerTarget ? `余额 ${formatCredits(ledgerTarget.balance)} · 冻结 ${formatCredits(ledgerTarget.frozen)} · 共 ${ledgerTotal} 条` : ''"
    >
      <UiDataTable
        v-model:page="ledgerPage"
        v-model:page-size="ledgerPageSize"
        :columns="ledgerColumns"
        :rows="ledgerItems"
        row-key="id"
        :loading="ledgerLoading"
        loading-text="正在加载流水记录..."
        empty-text="暂无积分流水"
        compact
        paginated
        :total="ledgerTotal"
        @change="loadUserLedgers()"
      >
        <template #cell-createdAt="{ row }">
          <span class="admin-mono">{{ formatDateTime(row.createdAt) }}</span>
        </template>
        <template #cell-operation="{ row }">
          <span class="admin-badge">{{ LEDGER_OP_LABELS[row.operation] || row.operation }}</span>
        </template>
        <template #cell-balanceChange="{ row }">
          <span
            class="admin-num"
            :class="Number(row.balanceChange) > 0 ? 'admin-num--pos' : Number(row.balanceChange) < 0 ? 'admin-num--neg' : ''"
          >
            {{ formatSignedCredits(row.balanceChange) }}
          </span>
        </template>
        <template #cell-balanceRange="{ row }">
          <span class="admin-mono">{{ formatCredits(row.balanceBefore) }} → {{ formatCredits(row.balanceAfter) }}</span>
        </template>
        <template #cell-frozenChange="{ row }">
          <span class="admin-mono">{{ formatSignedCredits(row.frozenChange) }}</span>
        </template>
        <template #cell-reason="{ row }">
          <div>{{ row.reason || '-' }}</div>
          <div v-if="formatTokenUsage(row.tokenUsage)" class="admin-cell-sub admin-mono">
            {{ formatTokenUsage(row.tokenUsage) }}
          </div>
        </template>
      </UiDataTable>
    </UiDialog>
  </section>
</template>
