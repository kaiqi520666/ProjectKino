<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { KeyRound, LogOut, RefreshCw, Save, UserRound, Wallet } from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import UiDataTable, { type DataTableColumn } from '@/components/ui/UiDataTable.vue'
import UiInput from '@/components/ui/UiInput.vue'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import type { CreditLedgerItem } from '@/features/admin/api'
import { LEDGER_OP_LABELS } from '@/features/admin/format'
import { useUserAssetsStore } from '@/features/assets/user-assets-store'
import { useCanvasStore } from '@/features/canvas/canvas-store'
import { useModelCatalog } from '@/features/studio/composables/useModelCatalog'
import { useStudioStore } from '@/features/studio/studio-store'
import {
  extractErrorMessage,
  formatCredits,
  formatDateTime,
  formatSignedCredits,
  formatTokenUsage,
} from '@/lib/format'
import { http, unwrap } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const studio = useStudioStore()
const canvas = useCanvasStore()
const userAssets = useUserAssetsStore()
const { clearCatalog } = useModelCatalog()

const nickname = ref(auth.user?.nickname ?? '')
const savingProfile = ref(false)

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const savingPassword = ref(false)

const ledgersLoading = ref(false)
const ledgers = ref<CreditLedgerItem[]>([])
const ledgersTotal = ref(0)
const ledgerPage = ref(1)
const ledgerPageSize = ref(15)

const ledgerColumns: DataTableColumn[] = [
  { key: 'createdAt', label: '时间' },
  { key: 'operation', label: '类型' },
  { key: 'balanceChange', label: '变动', align: 'right' },
  { key: 'balanceRange', label: '变动前后' },
  { key: 'reason', label: '说明 / Token 用量' },
]

const roleLabel = computed(() => {
  if (auth.user?.role === 'admin') return '管理员'
  if (auth.user?.role === 'operator') return '运营'
  return '创作者'
})

const canSaveProfile = computed(() => {
  const clean = nickname.value.trim()
  return !!clean && clean !== (auth.user?.nickname ?? '') && !savingProfile.value
})

const passwordMismatch = computed(
  () => !!confirmPassword.value && confirmPassword.value !== newPassword.value,
)

const canSavePassword = computed(
  () =>
    !!currentPassword.value
    && newPassword.value.length >= 6
    && confirmPassword.value === newPassword.value
    && !savingPassword.value,
)

watch(
  () => auth.user?.nickname,
  (val) => {
    if (val !== undefined && !savingProfile.value) nickname.value = val
  },
)

async function saveProfile() {
  if (!canSaveProfile.value) return
  savingProfile.value = true
  try {
    await auth.updateProfile(nickname.value)
    ui.notify('昵称已更新', 'success')
  } catch (error) {
    ui.notify(extractErrorMessage(error, '更新昵称失败'), 'error')
  } finally {
    savingProfile.value = false
  }
}

async function savePassword() {
  if (!canSavePassword.value) return
  savingPassword.value = true
  try {
    await auth.changePassword(currentPassword.value, newPassword.value)
    currentPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    ui.notify('密码已更新，其他设备会话已失效', 'success')
  } catch (error) {
    ui.notify(extractErrorMessage(error, '修改密码失败'), 'error')
  } finally {
    savingPassword.value = false
  }
}

async function loadLedgers(resetPage = false) {
  if (resetPage) ledgerPage.value = 1
  ledgersLoading.value = true
  try {
    await auth.refreshBalance()
    const res = await unwrap<{ items: CreditLedgerItem[]; total: number }>(
      http.get('/credits/ledgers', {
        params: {
          limit: ledgerPageSize.value,
          offset: (ledgerPage.value - 1) * ledgerPageSize.value,
        },
      }),
    )
    ledgers.value = res.items
    ledgersTotal.value = res.total
  } catch (error) {
    ui.notify(extractErrorMessage(error, '加载积分流水失败'), 'error')
  } finally {
    ledgersLoading.value = false
  }
}

async function handleLogout() {
  await auth.logout()
  studio.clearProjects()
  canvas.clearAll()
  userAssets.clear()
  clearCatalog()
  await router.replace('/login')
}

onMounted(() => {
  void loadLedgers(true)
})
</script>

<template>
  <section class="account-page" aria-labelledby="account-page-title">
    <WorkspacePageHeader title="我的" title-id="account-page-title">
      <template #icon><UserRound :size="19" :stroke-width="1.7" /></template>
      <template #actions>
        <UiButton variant="outline" size="sm" @click="handleLogout">
          <template #leading><LogOut :size="14" aria-hidden="true" /></template>
          退出登录
        </UiButton>
      </template>
    </WorkspacePageHeader>

    <div class="account-grid">
      <article class="account-card">
        <header class="account-card-head">
          <h2><UserRound :size="15" aria-hidden="true" />基本资料</h2>
          <span class="account-role">{{ roleLabel }}</span>
        </header>
        <form class="account-form" @submit.prevent="saveProfile">
          <div class="account-readonly-row">
            <span class="ui-label">登录邮箱</span>
            <p class="account-email">{{ auth.user?.email || '-' }}</p>
          </div>
          <UiInput v-model="nickname" label="昵称" placeholder="输入昵称" required />
          <div class="account-form-actions">
            <UiButton type="submit" variant="primary" size="sm" :disabled="!canSaveProfile" :loading="savingProfile">
              <template #leading><Save :size="14" aria-hidden="true" /></template>
              保存
            </UiButton>
          </div>
        </form>
      </article>

      <article class="account-card">
        <header class="account-card-head">
          <h2><KeyRound :size="15" aria-hidden="true" />修改密码</h2>
        </header>
        <form class="account-form" @submit.prevent="savePassword">
          <UiInput
            v-model="currentPassword"
            type="password"
            label="当前密码"
            autocomplete="current-password"
            required
          />
          <UiInput
            v-model="newPassword"
            type="password"
            label="新密码（至少 6 位）"
            autocomplete="new-password"
            required
          />
          <UiInput
            v-model="confirmPassword"
            type="password"
            label="确认新密码"
            autocomplete="new-password"
            :error="passwordMismatch ? '两次输入的新密码不一致' : ''"
            required
          />
          <div class="account-form-actions">
            <UiButton type="submit" variant="primary" size="sm" :disabled="!canSavePassword" :loading="savingPassword">
              <template #leading><Save :size="14" aria-hidden="true" /></template>
              更新密码
            </UiButton>
          </div>
        </form>
      </article>
    </div>

    <article class="account-card account-credits-card">
      <header class="account-card-head">
        <h2><Wallet :size="15" aria-hidden="true" />积分与流水</h2>
        <UiButton variant="outline" size="sm" :disabled="ledgersLoading" @click="loadLedgers()">
          <template #leading><RefreshCw :size="13" :class="{ 'ui-spin': ledgersLoading }" aria-hidden="true" /></template>
          刷新
        </UiButton>
      </header>

      <div class="account-balance-grid">
        <div class="account-metric">
          <span>可用余额</span>
          <strong :class="{ 'is-neg': Number(auth.user?.balance || 0) < 0 }">
            {{ formatCredits(auth.user?.balance) }}
          </strong>
        </div>
        <div class="account-metric">
          <span>任务冻结中</span>
          <strong>{{ formatCredits(auth.user?.frozen) }}</strong>
        </div>
        <div class="account-metric">
          <span>费率倍率</span>
          <strong>{{ Number(auth.user?.usageMultiplier || 1).toFixed(2) }}×</strong>
        </div>
      </div>

      <UiDataTable
        v-model:page="ledgerPage"
        v-model:page-size="ledgerPageSize"
        :columns="ledgerColumns"
        :rows="ledgers"
        row-key="id"
        :loading="ledgersLoading"
        empty-title="暂无积分流水"
        compact
        paginated
        :total="ledgersTotal"
        @change="loadLedgers()"
      >
        <template #cell-createdAt="{ row }">
          <span class="account-mono">{{ formatDateTime(row.createdAt) }}</span>
        </template>
        <template #cell-operation="{ row }">
          <span class="account-tag">{{ LEDGER_OP_LABELS[row.operation] || row.operation }}</span>
        </template>
        <template #cell-balanceChange="{ row }">
          <span
            class="account-mono"
            :class="Number(row.balanceChange) > 0 ? 'is-pos' : Number(row.balanceChange) < 0 ? 'is-neg' : ''"
          >
            {{ formatSignedCredits(row.balanceChange) }}
          </span>
        </template>
        <template #cell-balanceRange="{ row }">
          <span class="account-mono">
            {{ formatCredits(row.balanceBefore) }} → {{ formatCredits(row.balanceAfter) }}
          </span>
        </template>
        <template #cell-reason="{ row }">
          <div>{{ row.reason || '-' }}</div>
          <div v-if="formatTokenUsage(row.tokenUsage)" class="account-token-sub account-mono">
            {{ formatTokenUsage(row.tokenUsage) }}
          </div>
        </template>
      </UiDataTable>
    </article>
  </section>
</template>

<style scoped>
.account-page {
  width: 100%;
  padding: 20px 24px 40px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.account-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.account-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px 20px;
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  background: var(--color-surface);
}

.account-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.account-card-head h2 {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
}

.account-card-head h2 svg {
  color: var(--color-gold-soft);
}

.account-role {
  padding: 2px 8px;
  border-radius: 99px;
  border: 1px solid rgb(240 184 75 / 28%);
  background: rgb(240 184 75 / 10%);
  color: var(--color-gold-soft);
  font-size: 11px;
}

.account-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
}

.account-readonly-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.account-email {
  margin: 0;
  padding: 9px 12px;
  border-radius: 7px;
  border: 1px solid var(--border-subtle);
  background: var(--color-canvas);
  color: var(--color-muted);
  font-size: 13px;
}

.account-form-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: auto;
  padding-top: 4px;
}

.account-balance-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.account-metric {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
  background: var(--color-canvas);
}

.account-metric span {
  font-size: 12px;
  color: var(--color-muted);
}

.account-metric strong {
  font-size: 20px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--color-text);
}

.account-mono {
  font-variant-numeric: tabular-nums;
}

.is-pos {
  color: var(--color-success);
}

.is-neg {
  color: var(--color-error);
}

.account-tag {
  display: inline-block;
  padding: 2px 7px;
  border-radius: 4px;
  background: var(--color-elevated);
  border: 1px solid var(--border-subtle);
  font-size: 11px;
  color: var(--color-text);
}

.account-token-sub {
  margin-top: 2px;
  font-size: 11px;
  color: var(--color-muted);
}

@media (max-width: 820px) {
  .account-grid,
  .account-balance-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .account-page {
    padding: 18px 16px 32px;
  }
}
</style>
