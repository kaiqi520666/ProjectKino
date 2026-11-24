<script setup lang="ts">
import { inject, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Cloud,
  Coins,
  FolderKanban,
  LayoutDashboard,
  RefreshCw,
  Users,
  XCircle,
} from 'lucide-vue-next'
import UiDataTable, { type DataTableColumn } from '@/components/ui/UiDataTable.vue'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import { getAdminOverview, type AdminOverview } from '@/features/admin/api'
import { extractErrorMessage, formatCredits } from '@/features/admin/format'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const refreshReviewBadge = inject<() => Promise<void>>('refreshAdminReviewBadge')

const loading = ref(false)
const overview = ref<AdminOverview | null>(null)

const providerColumns: DataTableColumn[] = [
  { key: 'provider', label: '供应商' },
  { key: 'adapter', label: '适配器' },
  { key: 'baseUrl', label: '接口地址' },
  { key: 'apiKey', label: 'API Key' },
  { key: 'enabled', label: '状态' },
]

async function loadOverview() {
  loading.value = true
  try {
    overview.value = await getAdminOverview()
    await refreshReviewBadge?.()
  } catch (err) {
    ui.notify(extractErrorMessage(err, '加载后台概览失败'), 'error')
  } finally {
    loading.value = false
  }
}

onMounted(loadOverview)
</script>

<template>
  <section class="admin-section">
    <WorkspacePageHeader eyebrow="管理后台" title="概览">
      <template #icon><LayoutDashboard :size="19" :stroke-width="1.7" /></template>
      <template #actions>
        <button type="button" class="ui-button ui-button--secondary ui-button--sm" :disabled="loading" @click="loadOverview">
          <RefreshCw :size="14" :class="{ 'ui-spin': loading }" />
          <span>刷新</span>
        </button>
      </template>
    </WorkspacePageHeader>

    <div v-if="overview && overview.reviewJobs > 0" class="admin-review-banner">
      <div class="admin-review-banner-left" style="align-items: center;">
        <AlertTriangle :size="18" />
        <strong>待核对任务 {{ overview.reviewJobs }} 条</strong>
      </div>
      <RouterLink :to="{ path: '/admin/jobs', query: { status: 'review' } }" class="ui-button ui-button--danger ui-button--sm">
        前往处理
      </RouterLink>
    </div>

    <div v-if="loading && !overview" class="admin-loading">正在加载概览数据...</div>

    <template v-else-if="overview">
      <div class="admin-kpi-grid">
        <div class="admin-kpi-card">
          <div class="admin-kpi-top">
            <span>注册用户</span>
            <Users :size="16" />
          </div>
          <div class="admin-kpi-value">{{ overview.totalUsers }}</div>
          <div class="admin-kpi-meta">
            <span>正常 {{ overview.activeUsers }}</span>
            <span>管理员 {{ overview.adminCount }}</span>
            <span>运营 {{ overview.operatorCount }}</span>
          </div>
        </div>

        <div class="admin-kpi-card">
          <div class="admin-kpi-top">
            <span>短剧项目</span>
            <FolderKanban :size="16" />
          </div>
          <div class="admin-kpi-value">{{ overview.activeProjects }}</div>
          <div class="admin-kpi-meta">
            <span>进行中 {{ overview.activeProjects }}</span>
            <span>已软删留证 {{ overview.archivedProjects }}</span>
          </div>
        </div>

        <div class="admin-kpi-card" :class="{ 'admin-kpi-card--alert': overview.reviewJobs > 0 }">
          <div class="admin-kpi-top">
            <span>任务监控</span>
            <Activity :size="16" />
          </div>
          <div class="admin-kpi-value">{{ overview.runningJobs }}</div>
          <div class="admin-kpi-meta">
            <span>运行中 {{ overview.runningJobs }}</span>
            <span>待核对 {{ overview.reviewJobs }}</span>
            <span>24h 失败 {{ overview.failedJobs24h }}</span>
          </div>
        </div>

        <div class="admin-kpi-card">
          <div class="admin-kpi-top">
            <span>平台总积分</span>
            <Coins :size="16" />
          </div>
          <div class="admin-kpi-value">{{ formatCredits(overview.totalBalance) }}</div>
          <div class="admin-kpi-meta">
            <span>当前冻结 {{ formatCredits(overview.totalFrozen) }}</span>
          </div>
        </div>
      </div>

      <div class="admin-health-grid">
        <div class="admin-card">
          <div class="admin-card-head">
            <h3>阿里云 OSS</h3>
            <Cloud :size="16" />
          </div>
          <span
            class="admin-badge"
            :class="overview.ossConfigured ? 'admin-badge--success' : 'admin-badge--danger'"
          >
            <CheckCircle2 v-if="overview.ossConfigured" :size="13" />
            <XCircle v-else :size="13" />
            {{ overview.ossConfigured ? '已配置' : '未配置' }}
          </span>
        </div>

        <div class="admin-card">
          <div class="admin-card-head">
            <h3>AI 供应商连接状态</h3>
            <span>共 {{ overview.providers.length }} 个</span>
          </div>
          <UiDataTable :columns="providerColumns" :rows="overview.providers" row-key="key">
            <template #cell-provider="{ row }">
              <div class="admin-inline-meta">
                <strong>{{ row.displayName }}</strong>
                <span class="admin-inline-sep">·</span>
                <span class="admin-inline-sub admin-mono">{{ row.key }}</span>
              </div>
            </template>
            <template #cell-adapter="{ row }">
              <span class="admin-mono">{{ row.adapter }}</span>
            </template>
            <template #cell-baseUrl="{ row }">
              <span class="admin-mono">{{ row.baseUrl || '-' }}</span>
            </template>
            <template #cell-apiKey="{ row }">
              <span class="admin-badge" :class="row.hasApiKey ? 'admin-badge--success' : 'admin-badge--danger'">
                {{ row.hasApiKey ? '已配置' : '未配置' }}
              </span>
            </template>
            <template #cell-enabled="{ row }">
              <span class="admin-badge" :class="row.enabled ? 'admin-badge--gold' : ''">
                {{ row.enabled ? '启用中' : '已停用' }}
              </span>
            </template>
          </UiDataTable>
        </div>
      </div>
    </template>
  </section>
</template>
