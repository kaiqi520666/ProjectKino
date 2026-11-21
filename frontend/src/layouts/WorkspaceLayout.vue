<script setup lang="ts">
import { computed, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell, Headphones, RefreshCw, Tags, Wallet } from 'lucide-vue-next'
import UiAlert from '@/components/ui/UiAlert.vue'
import UiDataTable, { type DataTableColumn } from '@/components/ui/UiDataTable.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import WorkspaceHeader from '@/components/workspace/WorkspaceHeader.vue'
import WorkspaceSidebar from '@/components/workspace/WorkspaceSidebar.vue'
import type { WorkspaceBreadcrumb, WorkspaceUser } from '@/components/workspace/workspace-navigation'
import { getAdminOverview, type CreditLedgerItem } from '@/features/admin/api'
import {
  extractErrorMessage,
  formatCredits,
  formatDateTime,
  formatSignedCredits,
  formatTokenUsage,
  LEDGER_OP_LABELS,
} from '@/features/admin/format'
import { getModelCatalog } from '@/features/studio/api'
import type { ModelCatalogOut } from '@/features/studio/api-types'
import { useStudioStore } from '@/features/studio/studio-store'
import { http, unwrap } from '@/lib/http'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import '@/styles/workspace.css'
import '@/styles/admin.css'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const studio = useStudioStore()

const mobileOpen = ref(false)
const panel = ref<'prices' | 'support' | 'announcements' | 'recharge' | null>(null)
const adminReviewCount = ref(0)
const adminArchivedCount = ref(0)

const catalogLoading = ref(false)
const catalog = ref<ModelCatalogOut | null>(null)
const ledgersLoading = ref(false)
const ledgers = ref<CreditLedgerItem[]>([])
const ledgersTotal = ref(0)
const ledgerPage = ref(1)
const ledgerPageSize = ref(20)

const ledgerColumns: DataTableColumn[] = [
  { key: 'createdAt', label: '时间' },
  { key: 'operation', label: '类型' },
  { key: 'balanceChange', label: '变动', align: 'right' },
  { key: 'balanceRange', label: '变动前后' },
  { key: 'reason', label: '说明 / Token 用量' },
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
  prices: { title: '模型价格表', description: '实时展示当前账号生效的模型与计费标准（已包含个人费率倍率）', icon: Tags, message: '' },
  support: { title: '联系客服', description: '帧剧客户支持', icon: Headphones, message: '客服联系方式尚未配置。' },
  announcements: { title: '系统公告', description: '平台消息', icon: Bell, message: '暂无新公告。' },
  recharge: { title: '积分账户与流水明细', description: '查看可用余额、冻结额度与近期消费/充值记录', icon: Wallet, message: '' },
}
const currentPanel = computed(() => panels[panel.value || 'prices'])
const panelOpen = computed({
  get: () => panel.value !== null,
  set: (open: boolean) => { if (!open) panel.value = null },
})
const dialogSize = computed(() => (panel.value === 'prices' || panel.value === 'recharge' ? 'landscape' : undefined))
const previousTitle = document.title

async function loadPrices() {
  catalogLoading.value = true
  try {
    catalog.value = await getModelCatalog()
  } catch (err) {
    ui.notify(extractErrorMessage(err, '加载模型价格失败'), 'error')
  } finally {
    catalogLoading.value = false
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
  } catch (err) {
    ui.notify(extractErrorMessage(err, '加载积分流水失败'), 'error')
  } finally {
    ledgersLoading.value = false
  }
}

function openPanel(next: 'prices' | 'support' | 'announcements' | 'recharge') {
  panel.value = next
  if (next === 'prices') loadPrices()
  if (next === 'recharge') loadLedgers(true)
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
        <div class="ws-live-bar">
          <span class="ws-live-note">
            当前账号费率倍率：<strong>{{ auth.user?.usageMultiplier || '1.00' }}x</strong>；FFmpeg 合成本集 / 全片视频免费。
          </span>
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

      <!-- 个人积分账户与流水明细 -->
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
            <strong>{{ auth.user?.usageMultiplier || '1.00' }}x</strong>
          </div>
        </div>
        <div class="ws-live-bar">
          <span class="ws-live-note">
            在线自助充值暂未开放，如需充值请联系管理员。
          </span>
          <button type="button" class="ui-button ui-button--secondary ui-button--sm" :disabled="ledgersLoading" @click="loadLedgers()">
            <RefreshCw :size="13" :class="{ 'ui-spin': ledgersLoading }" />
            <span>刷新</span>
          </button>
        </div>
        <UiDataTable
          v-model:page="ledgerPage"
          v-model:page-size="ledgerPageSize"
          :columns="ledgerColumns"
          :rows="ledgers"
          row-key="id"
          :loading="ledgersLoading"
          loading-text="正在加载积分流水..."
          empty-text="暂无积分变动记录"
          compact
          paginated
          :total="ledgersTotal"
          @change="loadLedgers()"
        >
          <template #cell-createdAt="{ row }">
            <span class="ws-mono">{{ formatDateTime(row.createdAt) }}</span>
          </template>
          <template #cell-operation="{ row }">
            <span class="ws-tag">{{ LEDGER_OP_LABELS[row.operation] || row.operation }}</span>
          </template>
          <template #cell-balanceChange="{ row }">
            <span
              class="ws-mono"
              :class="Number(row.balanceChange) > 0 ? 'is-pos' : Number(row.balanceChange) < 0 ? 'is-neg' : ''"
            >
              {{ formatSignedCredits(row.balanceChange) }}
            </span>
          </template>
          <template #cell-balanceRange="{ row }">
            <span class="ws-mono">{{ formatCredits(row.balanceBefore) }} → {{ formatCredits(row.balanceAfter) }}</span>
          </template>
          <template #cell-reason="{ row }">
            <div>{{ row.reason || '-' }}</div>
            <div v-if="formatTokenUsage(row.tokenUsage)" class="ws-token-sub ws-mono">
              {{ formatTokenUsage(row.tokenUsage) }}
            </div>
          </template>
        </UiDataTable>
      </div>

      <!-- 客服 / 公告 -->
      <div v-else class="workspace-service-panel">
        <component :is="currentPanel.icon" :size="30" :stroke-width="1.4" aria-hidden="true" />
        <UiAlert tone="info" :title="currentPanel.message" />
      </div>
    </UiDialog>
  </div>
</template>

<style scoped>
.ws-live-panel { display: flex; flex-direction: column; gap: 14px; }
.ws-live-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
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
