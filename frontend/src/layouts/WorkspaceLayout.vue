<script setup lang="ts">
import { computed, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ExternalLink, Headphones, RefreshCw, Tags, Ticket, Wallet } from 'lucide-vue-next'
import UiAlert from '@/components/ui/UiAlert.vue'
import UiBadge from '@/components/ui/UiBadge.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDataTable, { type DataTableColumn } from '@/components/ui/UiDataTable.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import WorkspaceHeader from '@/components/workspace/WorkspaceHeader.vue'
import WorkspaceSidebar from '@/components/workspace/WorkspaceSidebar.vue'
import type { WorkspaceBreadcrumb, WorkspaceUser } from '@/components/workspace/workspace-navigation'
import RedeemCodeDialog from '@/features/account/components/RedeemCodeDialog.vue'
import { fetchCreditBills, type CreditBillItem } from '@/features/account/credits-api'
import { formatCreditReason } from '@/features/account/credits-helpers'
import AnnouncementsDialog from '@/features/announcements/components/AnnouncementsDialog.vue'
import { useAnnouncementStore } from '@/features/announcements/announcement-store'
import { useArtStylesStore } from '@/features/art-styles/art-styles-store'
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
const announcements = useAnnouncementStore()
const artStylesStore = useArtStylesStore()

const mobileOpen = ref(false)
const panel = ref<'prices' | 'support' | 'recharge' | null>(null)
const announcementsOpen = ref(false)
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

const textPriceColumns: DataTableColumn[] = [
  { key: 'displayName', label: '模型', width: '260px' },
  { key: 'input', label: '输入（积分/百万 Token）', align: 'right' },
  { key: 'cached', label: '缓存命中（积分/百万 Token）', align: 'right' },
  { key: 'output', label: '输出（积分/百万 Token）', align: 'right' },
]

const imagePriceColumns: DataTableColumn[] = [
  { key: 'displayName', label: '模型', width: '260px' },
  { key: 'prices', label: '各分辨率档位单价（积分/张）' },
]

const videoPriceColumns: DataTableColumn[] = [
  { key: 'category', label: '系列', width: '132px' },
  { key: 'displayName', label: '模型', width: '250px' },
  { key: 'spec', label: '分辨率 / 时长', width: '180px' },
  { key: 'prices', label: '计费方式与价格' },
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

function openPanel(next: 'prices' | 'support' | 'recharge') {
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
  void artStylesStore.ensureLoaded()
  if (auth.isAdmin) await refreshAdminReviewBadge()
})

async function handleLogout() {
  await auth.logout()
  announcements.clearSession()
  artStylesStore.clear()
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
        :unread-announcements="announcements.unreadCount"
        @menu="mobileOpen = true"
        @prices="openPanel('prices')"
        @support="openPanel('support')"
        @announcements="announcementsOpen = true"
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
          <UiButton variant="secondary" size="sm" :disabled="catalogLoading" @click="loadPrices">
            <template #leading><RefreshCw :size="13" :class="{ 'ui-spin': catalogLoading }" aria-hidden="true" /></template>
            刷新价格
          </UiButton>
        </div>
        <div v-if="catalogLoading && !catalog" class="ws-live-empty">正在加载最新模型价格...</div>
        <div v-else-if="catalog" class="ws-price-sections">
          <div class="ws-price-group">
            <h4>文本模型（按真实 Token 后扣）</h4>
            <UiDataTable
              :columns="textPriceColumns"
              :rows="catalog.text"
              row-key="id"
              :loading="catalogLoading"
              empty-text="暂无可用文本模型"
            >
              <template #cell-displayName="{ row }">
                <div class="ws-model-cell">
                  <strong>{{ row.displayName }}</strong>
                  <UiBadge v-if="row.isDefault" tone="gold">默认</UiBadge>
                </div>
              </template>
              <template #cell-input="{ row }">
                <span class="ws-mono">{{ formatCredits(row.textPrice?.inputPricePerMillion) }}</span>
              </template>
              <template #cell-cached="{ row }">
                <span class="ws-mono">{{ formatCredits(row.textPrice?.cachedInputPricePerMillion) }}</span>
              </template>
              <template #cell-output="{ row }">
                <span class="ws-mono">{{ formatCredits(row.textPrice?.outputPricePerMillion) }}</span>
              </template>
            </UiDataTable>
          </div>

          <div class="ws-price-group">
            <h4>生图模型（预冻结，失败自动退还）</h4>
            <UiDataTable
              :columns="imagePriceColumns"
              :rows="catalog.image"
              row-key="id"
              :loading="catalogLoading"
              empty-text="暂无可用生图模型"
            >
              <template #cell-displayName="{ row }">
                <div class="ws-model-cell">
                  <strong>{{ row.displayName }}</strong>
                  <UiBadge v-if="row.isDefault" tone="gold">默认</UiBadge>
                </div>
              </template>
              <template #cell-prices="{ row }">
                <div class="ws-chip-row">
                  <UiBadge v-for="p in row.imagePrices" :key="p.tier" variant="chip">
                    {{ p.tier.toUpperCase() }}: {{ formatCredits(p.creditPrice) }}
                  </UiBadge>
                </div>
              </template>
            </UiDataTable>
          </div>

          <div class="ws-price-group">
            <h4>生视频模型（预冻结，失败自动退还）</h4>
            <UiDataTable
              :columns="videoPriceColumns"
              :rows="catalog.video"
              row-key="id"
              :loading="catalogLoading"
              empty-text="暂无可用生视频模型"
            >
              <template #cell-category="{ row }">
                <UiBadge v-if="row.category" tone="gold">{{ row.category }}</UiBadge>
                <span v-else class="ws-muted">-</span>
              </template>
              <template #cell-displayName="{ row }">
                <div class="ws-model-cell">
                  <strong>{{ row.displayName }}</strong>
                  <UiBadge v-if="row.isDefault" tone="gold">默认</UiBadge>
                </div>
              </template>
              <template #cell-spec="{ row }">
                <span class="ws-mono">
                  {{ Array.isArray(row.capabilities?.resolutions) ? row.capabilities.resolutions.join('/') : '720p' }}
                  · {{ row.capabilities?.minDuration ?? 4 }}–{{ row.capabilities?.maxDuration ?? 15 }}s
                </span>
              </template>
              <template #cell-prices="{ row }">
                <div class="ws-chip-row">
                  <UiBadge v-for="p in row.videoPrices" :key="p.ruleKey" variant="chip">
                    {{ formatCredits(p.creditPrice) }} 积分 / {{ p.unit === 'second' ? '秒' : '条' }}
                  </UiBadge>
                </div>
              </template>
            </UiDataTable>
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
            <UiButton variant="primary" size="sm" @click="redeemDialogOpen = true">
              <template #leading><Ticket :size="13" aria-hidden="true" /></template>
              兑换积分
            </UiButton>
            <UiButton
              v-if="auth.redeemPurchaseUrl"
              variant="outline"
              size="sm"
              :href="auth.redeemPurchaseUrl"
              target="_blank"
            >
              购买兑换码
              <template #trailing><ExternalLink :size="12" aria-hidden="true" /></template>
            </UiButton>
          </div>
          <div class="ws-live-bar-actions">
            <UiButton variant="secondary" size="sm" @click="goToCreditBills">
              消费账单
            </UiButton>
            <UiButton variant="secondary" size="sm" :disabled="rechargeLoading" @click="loadRechargeRecords()">
              <template #leading><RefreshCw :size="13" :class="{ 'ui-spin': rechargeLoading }" aria-hidden="true" /></template>
              刷新
            </UiButton>
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
          paginated
          :total="rechargeTotal"
          @change="loadRechargeRecords()"
        >
          <template #cell-createdAt="{ row }">
            <span class="ws-mono">{{ formatDateTime(row.createdAt) }}</span>
          </template>
          <template #cell-operation="{ row }">
            <UiBadge tone="gold">{{ LEDGER_OP_LABELS[row.operation] || row.operation }}</UiBadge>
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

    <AnnouncementsDialog v-model:open="announcementsOpen" />
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
.ws-model-cell { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
.ws-chip-row { display: inline-flex; align-items: center; gap: 6px; flex-wrap: nowrap; }
.ws-mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.ws-muted { color: var(--color-muted); }
.is-pos { color: var(--color-success); font-weight: 600; }
.is-neg { color: var(--color-error); font-weight: 600; }
@media (max-width: 640px) { .ws-balance-cards { grid-template-columns: minmax(0, 1fr); } }
</style>
