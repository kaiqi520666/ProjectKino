<script setup lang="ts">
import { computed, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell, ExternalLink, Headphones, RefreshCw, Tags, Ticket, Wallet } from 'lucide-vue-next'
import UiAlert from '@/components/ui/UiAlert.vue'
import UiDataTable, { type DataTableColumn } from '@/components/ui/UiDataTable.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import WorkspaceHeader from '@/components/workspace/WorkspaceHeader.vue'
import WorkspaceSidebar from '@/components/workspace/WorkspaceSidebar.vue'
import type { WorkspaceBreadcrumb, WorkspaceUser } from '@/components/workspace/workspace-navigation'
import RedeemCodeDialog from '@/features/account/components/RedeemCodeDialog.vue'
import { fetchCreditBills, type CreditBillItem } from '@/features/account/credits-api'
import { formatCreditReason } from '@/features/account/credits-helpers'
import { getAdminOverview } from '@/features/admin/api'
import { LEDGER_OP_LABELS } from '@/features/admin/format'
import { useCanvasStore } from '@/features/canvas/canvas-store'
import { useUserAssetsStore } from '@/features/assets/user-assets-store'
import { useModelCatalog } from '@/features/studio/composables/useModelCatalog'
import { useStudioStore } from '@/features/studio/studio-store'
import {
  extractErrorMessage,
  formatCredits,
  formatDateTime,
  formatSignedCredits,
} from '@/lib/format'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import '@/styles/workspace.css'
import '@/styles/admin.css'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const studio = useStudioStore()
const canvas = useCanvasStore()
const userAssets = useUserAssetsStore()

const mobileOpen = ref(false)
const panel = ref<'prices' | 'support' | 'announcements' | 'recharge' | null>(null)
const adminReviewCount = ref(0)
const adminArchivedCount = ref(0)

const {
  catalog,
  loading: catalogLoading,
  error: catalogError,
  refresh: refreshCatalog,
  clearCatalog,
} = useModelCatalog()
const rechargeLoading = ref(false)
const rechargeRecords = ref<CreditBillItem[]>([])
const rechargeTotal = ref(0)
const rechargePage = ref(1)
const rechargePageSize = ref(15)
const redeemDialogOpen = ref(false)

const rechargeColumns: DataTableColumn[] = [
  { key: 'createdAt', label: '时间', width: '164px' },
  { key: 'operation', label: '类型', width: '96px' },
  { key: 'amount', label: '到账积分', align: 'right', width: '110px' },
  { key: 'balanceAfter', label: '入账后余额', align: 'right', width: '120px' },
  { key: 'reason', label: '说明' },
]

const isAdminRoute = computed(() => route.matched.some((r) => Boolean(r.meta.requiresAdmin)))
const canRenderView = computed(() => auth.isAuthenticated && (!isAdminRoute.value || auth.isAdmin))
const user = computed<WorkspaceUser | null>(() =>
  auth.user ? { name: auth.user.nickname || auth.user.email } : null,
)
const breadcrumbs = computed<WorkspaceBreadcrumb[]>(() => {
  const title = String(route.meta.title || '创作首页')
  if (isAdminRoute.value) {
    return [{ label: '后台', to: '/admin' }, { label: title }]
  }
  if (route.meta.workspaceNav === 'account') {
    return [{ label: '我的', to: '/account/credits' }, { label: title }]
  }
  return [{ label: title }]
})

async function refreshAdminReviewBadge() {
  if (!auth.isAdmin) return
  try {
    const overview = await getAdminOverview()
    adminReviewCount.value = overview.reviewJobs
    adminArchivedCount.value = overview.archivedProjects
  } catch {
    // Ignore transient badge error.
  }
}

provide('refreshAdminReviewBadge', refreshAdminReviewBadge)
const panels = {
  prices: { title: '模型价格表', description: '', icon: Tags, message: '' },
  support: { title: '联系客服', description: '', icon: Headphones, message: '客服联系方式尚未配置。' },
  announcements: { title: '系统公告', description: '', icon: Bell, message: '暂无新公告。' },
  recharge: { title: '积分充值', description: '', icon: Wallet, message: '' },
}
const currentPanel = computed(() => panels[panel.value || 'prices'])
const panelOpen = computed({
  get: () => panel.value !== null,
  set: (open: boolean) => { if (!open) panel.value = null },
})
const dialogSize = computed(() => (panel.value === 'prices' || panel.value === 'recharge' ? 'landscape' : undefined))
const previousTitle = document.title
const formattedMultiplier = computed(() => {
  const val = Number(auth.user?.usageMultiplier ?? 1)
  return Number.isFinite(val) ? `${val.toFixed(2)}×` : '1.00×'
})

async function loadPrices() {
  const data = await refreshCatalog()
  if (!data && catalogError.value) {
    ui.notify(catalogError.value, 'error')
  }
}

async function loadRechargeRecords(resetPage = false) {
  if (resetPage) rechargePage.value = 1
  rechargeLoading.value = true
  try {
    await auth.refreshBalance()
    const res = await fetchCreditBills({
      category: 'income',
      status: 'credited',
      limit: rechargePageSize.value,
      offset: (rechargePage.value - 1) * rechargePageSize.value,
    })
    rechargeRecords.value = res.items
    rechargeTotal.value = res.total
  } catch (err) {
    ui.notify(extractErrorMessage(err, '加载充值记录失败'), 'error')
  } finally {
    rechargeLoading.value = false
  }
}

function goToCreditBills() {
  panel.value = null
  void router.push({ name: 'account-credits' })
}

function openPanel(next: 'prices' | 'support' | 'announcements' | 'recharge') {
  panel.value = next
  if (next === 'prices') loadPrices()
  if (next === 'recharge') loadRechargeRecords(true)
}

watch(() => route.fullPath, () => {
  mobileOpen.value = false
  const title = String(route.meta.title || '工作台')
  document.title = isAdminRoute.value ? `后台 · ${title} | 帧剧 FrameDrama` : `${title} | 帧剧 FrameDrama`
}, { immediate: true })

onMounted(async () => {
  if (auth.isAdmin) await refreshAdminReviewBadge()
})

async function handleLogout() {
  await auth.logout()
  studio.clearProjects()
  canvas.clearAll()
  userAssets.clear()
  clearCatalog()
  await router.replace('/login')
}

onUnmounted(() => { document.title = previousTitle })
</script>

<template>
  <div class="workspace-shell">
    <a class="workspace-skip-link" href="#workspace-main">跳到主要内容</a>
    <div class="workspace-desktop-sidebar">
      <WorkspaceSidebar
        :admin-review-count="adminReviewCount"
        :admin-archived-count="adminArchivedCount"
      />
    </div>
    <div class="workspace-body">
      <WorkspaceHeader
        :breadcrumbs="breadcrumbs"
        :balance="auth.numericBalance"
        :user="user"
        :is-admin="auth.isAdmin"
        :preview="false"
        @menu="mobileOpen = true"
        @prices="openPanel('prices')"
        @support="openPanel('support')"
        @announcements="openPanel('announcements')"
        @recharge="openPanel('recharge')"
        @account="router.push('/account')"
        @admin="router.push('/admin')"
        @login="router.push({ path: '/login', query: { next: route.fullPath } })"
        @logout="handleLogout"
        @home="router.push('/')"
      />
      <main id="workspace-main" class="workspace-main" :class="{ 'admin-page-shell': isAdminRoute }" tabindex="-1">
        <RouterView v-if="canRenderView" />
      </main>
    </div>
    <UiDialog v-model:open="mobileOpen" title="帧剧工作台" description="短剧 · 画布 · 素材">
      <div class="workspace-mobile-navigation">
        <WorkspaceSidebar
          :admin-review-count="adminReviewCount"
          :admin-archived-count="adminArchivedCount"
          @navigate="mobileOpen = false"
        />
      </div>
    </UiDialog>
    <UiDialog v-model:open="panelOpen" :size="dialogSize" :title="currentPanel.title" :description="currentPanel.description">
      <!-- 实时模型价格表 -->
      <div v-if="panel === 'prices'" class="ws-live-panel">
        <div class="ws-live-bar ws-live-bar--end">
          <button type="button" class="ui-button ui-button--secondary ui-button--sm" :disabled="catalogLoading" @click="loadPrices">
            <RefreshCw :size="13" :class="{ 'ui-spin': catalogLoading }" />
            <span>刷新价格</span>
          </button>
        </div>
        <div v-if="catalogLoading && !catalog" class="ws-live-empty">正在加载最新模型价格...</div>
        <div v-else-if="catalog" class="ws-price-sections">
          <div class="ws-price-group">
            <h4>文本模型（按真实 Token 后扣）</h4>
            <table class="ws-table">
              <thead>
                <tr>
                  <th>模型</th>
                  <th>输入（积分/百万 Token）</th>
                  <th>缓存命中（积分/百万 Token）</th>
                  <th>输出（积分/百万 Token）</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in catalog.text" :key="m.id">
                  <td><strong>{{ m.displayName }}</strong> <small v-if="m.isDefault" class="ws-tag">默认</small></td>
                  <td class="ws-mono">{{ formatCredits(m.textPrice?.inputPricePerMillion) }}</td>
                  <td class="ws-mono">{{ formatCredits(m.textPrice?.cachedInputPricePerMillion) }}</td>
                  <td class="ws-mono">{{ formatCredits(m.textPrice?.outputPricePerMillion) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="ws-price-group">
            <h4>生图模型（预冻结，失败自动退还）</h4>
            <table class="ws-table">
              <thead>
                <tr>
                  <th>模型</th>
                  <th>各分辨率档位单价（积分/张）</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in catalog.image" :key="m.id">
                  <td><strong>{{ m.displayName }}</strong> <small v-if="m.isDefault" class="ws-tag">默认</small></td>
                  <td class="ws-mono">
                    <span v-for="p in m.imagePrices" :key="p.tier" class="ws-price-chip">
                      {{ p.tier.toUpperCase() }}: {{ formatCredits(p.creditPrice) }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="ws-price-group">
            <h4>生视频模型（预冻结，失败自动退还）</h4>
            <table class="ws-table">
              <thead>
                <tr>
                  <th>系列</th>
                  <th>模型</th>
                  <th>分辨率 / 时长</th>
                  <th>计费方式与价格</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in catalog.video" :key="m.id">
                  <td><span v-if="m.category" class="ws-tag">{{ m.category }}</span><span v-else>-</span></td>
                  <td><strong>{{ m.displayName }}</strong> <small v-if="m.isDefault" class="ws-tag">默认</small></td>
                  <td class="ws-mono">
                    {{ Array.isArray(m.capabilities?.resolutions) ? m.capabilities.resolutions.join('/') : '720p' }}
                    · {{ m.capabilities?.minDuration ?? 4 }}–{{ m.capabilities?.maxDuration ?? 15 }}s
                  </td>
                  <td class="ws-mono">
                    <span v-for="p in m.videoPrices" :key="p.ruleKey" class="ws-price-chip">
                      {{ formatCredits(p.creditPrice) }} 积分 / {{ p.unit === 'second' ? '秒' : '条' }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- 积分充值与入账记录 -->
      <div v-else-if="panel === 'recharge'" class="ws-live-panel">
        <div class="ws-balance-cards">
          <div class="ws-balance-card">
            <span>可用积分余额</span>
            <strong :class="{ 'is-neg': Number(auth.user?.balance || 0) < 0 }">{{ formatCredits(auth.user?.balance) }}</strong>
          </div>
          <div class="ws-balance-card">
            <span>任务冻结中</span>
            <strong>{{ formatCredits(auth.user?.frozen) }}</strong>
          </div>
          <div class="ws-balance-card">
            <span>账户费率倍率</span>
            <strong>{{ formattedMultiplier }}</strong>
          </div>
        </div>
        <div class="ws-live-bar">
          <div class="ws-live-bar-actions">
            <button type="button" class="ui-button ui-button--primary ui-button--sm" @click="redeemDialogOpen = true">
              <Ticket :size="13" />
              <span>兑换积分</span>
            </button>
            <a
              v-if="auth.redeemPurchaseUrl"
              :href="auth.redeemPurchaseUrl"
              target="_blank"
              rel="noopener noreferrer"
              class="ui-button ui-button--secondary ui-button--sm"
            >
              <span>购买兑换码</span>
              <ExternalLink :size="12" />
            </a>
          </div>
          <div class="ws-live-bar-actions">
            <button type="button" class="ui-button ui-button--secondary ui-button--sm" @click="goToCreditBills">
              <span>消费账单</span>
            </button>
            <button type="button" class="ui-button ui-button--secondary ui-button--sm" :disabled="rechargeLoading" @click="loadRechargeRecords()">
              <RefreshCw :size="13" :class="{ 'ui-spin': rechargeLoading }" />
              <span>刷新</span>
            </button>
          </div>
        </div>
        <UiDataTable
          v-model:page="rechargePage"
          v-model:page-size="rechargePageSize"
          :columns="rechargeColumns"
          :rows="rechargeRecords"
          row-key="id"
          :loading="rechargeLoading"
          empty-text="暂无充值与入账记录"
          compact
          paginated
          :total="rechargeTotal"
          @change="loadRechargeRecords()"
        >
          <template #cell-createdAt="{ row }">
            <span class="ws-mono">{{ formatDateTime(row.createdAt) }}</span>
          </template>
          <template #cell-operation="{ row }">
            <span class="ws-tag">{{ LEDGER_OP_LABELS[row.operation] || row.operation }}</span>
          </template>
          <template #cell-amount="{ row }">
            <span class="ws-mono is-pos">{{ formatSignedCredits(row.amount) }}</span>
          </template>
          <template #cell-balanceAfter="{ row }">
            <span class="ws-mono">{{ formatCredits(row.balanceAfter) }}</span>
          </template>
          <template #cell-reason="{ row }">
            <span>{{ formatCreditReason(row.reason) || row.title || '-' }}</span>
          </template>
        </UiDataTable>
      </div>

      <!-- 客服 / 公告 -->
      <div v-else class="workspace-service-panel">
        <component :is="currentPanel.icon" :size="30" :stroke-width="1.4" aria-hidden="true" />
        <UiAlert tone="info" :title="currentPanel.message" />
      </div>
    </UiDialog>

    <RedeemCodeDialog
      v-model:open="redeemDialogOpen"
      :purchase-url="auth.redeemPurchaseUrl"
      @redeemed="loadRechargeRecords(true)"
    />
  </div>
</template>

<style scoped>
.ws-live-panel { display: flex; flex-direction: column; gap: 14px; }
.ws-live-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.ws-live-bar--end { justify-content: flex-end; }
.ws-live-bar-actions { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ws-live-note { font-size: 12px; color: var(--color-muted); }
.ws-live-note strong { color: var(--color-gold-soft); }
.ws-live-empty { padding: 32px 16px; text-align: center; color: var(--color-muted); font-size: 13px; }
.ws-balance-cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.ws-balance-card { padding: 12px 16px; border-radius: 10px; border: 1px solid var(--border-subtle); background: rgb(255 255 255 / 2.5%); display: flex; flex-direction: column; gap: 6px; }
.ws-balance-card span { font-size: 12px; color: var(--color-muted); }
.ws-balance-card strong { font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; color: var(--color-text); }
.ws-balance-card strong.is-neg { color: var(--color-error); }
.ws-price-sections { display: flex; flex-direction: column; gap: 16px; }
.ws-price-group h4 { margin: 0 0 8px; font-size: 13px; color: var(--color-gold-soft); font-weight: 600; }
.ws-table-wrap { overflow-x: auto; border: 1px solid var(--border-subtle); border-radius: 8px; }
.ws-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.ws-table th { padding: 9px 12px; text-align: left; font-size: 12px; font-weight: 500; color: var(--color-muted); background: rgb(255 255 255 / 2.5%); border-bottom: 1px solid var(--border-subtle); white-space: nowrap; }
.ws-table td { padding: 9px 12px; border-bottom: 1px solid var(--border-subtle); vertical-align: middle; }
.ws-table tbody tr:last-child td { border-bottom: 0; }
.ws-mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; font-variant-numeric: tabular-nums; }
.ws-tag { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 11px; background: var(--gold-tint); color: var(--color-gold-soft); border: 1px solid rgb(240 184 75 / 28%); }
.ws-price-chip { display: inline-block; margin: 2px 8px 2px 0; padding: 2px 7px; border-radius: 5px; background: rgb(255 255 255 / 4%); border: 1px solid var(--border-subtle); }
.ws-token-sub { margin-top: 2px; font-size: 11px; color: var(--color-muted); }
.is-pos { color: var(--color-success); font-weight: 600; }
.is-neg { color: var(--color-error); font-weight: 600; }
@media (max-width: 640px) { .ws-balance-cards { grid-template-columns: minmax(0, 1fr); } }
</style>
