<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { CloudDownload, Pencil, Plus, RefreshCw, Server, Trash2 } from 'lucide-vue-next'
import UiDataTable, { type DataTableColumn } from '@/components/ui/UiDataTable.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import {
  deleteAdminModel,
  listAdminModels,
  listAdminModelSyncLogs,
  listAdminProviders,
  reorderAdminModels,
  syncAdminModels,
  updateAdminModel,
  type AdminModelItem,
  type AdminModelSyncLog,
  type AdminProvider,
} from '@/features/admin/api'
import AdminModelFormDialog from '@/features/admin/components/AdminModelFormDialog.vue'
import AdminProviderEditDialog from '@/features/admin/components/AdminProviderEditDialog.vue'
import { extractErrorMessage, formatCredits, formatDateTime } from '@/lib/format'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

const activeSection = ref<'models' | 'logs'>('models')
const loading = ref(false)
const syncing = ref(false)
const reordering = ref(false)
const togglingId = ref<string | null>(null)
const providers = ref<AdminProvider[]>([])
const models = ref<AdminModelItem[]>([])

// Sync logs state
const logsLoading = ref(false)
const syncLogs = ref<AdminModelSyncLog[]>([])
const syncLogsTotal = ref(0)
const logsPage = ref(1)
const logsPageSize = ref(20)

// Filters
const mediaFilter = ref<'all' | 'text' | 'image' | 'video'>('video')
const categoryFilter = ref('all')
const billingFilter = ref<'all' | 'call' | 'second'>('all')
const upstreamFilter = ref<'all' | 'online' | 'offline'>('all')

const mediaLabels: Record<string, string> = {
  text: '文本',
  image: '生图',
  video: '生视频',
}

const providerColumns: DataTableColumn[] = [
  { key: 'provider', label: '供应商' },
  { key: 'adapter', label: '适配器' },
  { key: 'baseUrl', label: '接口地址' },
  { key: 'apiKey', label: 'API Key' },
  { key: 'enabled', label: '状态' },
  { key: 'actions', label: '操作' },
]

const modelColumns: DataTableColumn[] = [
  { key: 'model', label: '模型名称 / 系列' },
  { key: 'upstreamModelId', label: '上游模型名' },
  { key: 'specs', label: '分辨率 / 时长 / 比例' },
  { key: 'limits', label: '素材 / 提示词上限' },
  { key: 'price', label: '计费 / 售价' },
  { key: 'enabled', label: '后台开关' },
  { key: 'upstream', label: '上游状态' },
  { key: 'actions', label: '操作' },
]

const logColumns: DataTableColumn[] = [
  { key: 'createdAt', label: '变动时间' },
  { key: 'providerKey', label: '供应商' },
  { key: 'model', label: '本地模型 / 上游名' },
  { key: 'eventType', label: '状态变动' },
  { key: 'summary', label: '详情' },
]

const billingFilterOptions = [
  { value: 'all', label: '全部计费' },
  { value: 'call', label: '按条' },
  { value: 'second', label: '按秒' },
]

const upstreamFilterOptions = [
  { value: 'all', label: '全部状态' },
  { value: 'online', label: '上游在线' },
  { value: 'offline', label: '上游已下架' },
]

const categoryFilterOptions = computed(() => {
  const seen = new Set<string>()
  for (const m of models.value) {
    if (mediaFilter.value !== 'all' && m.mediaType !== mediaFilter.value) continue
    if (m.category) seen.add(m.category)
  }
  return [
    { value: 'all', label: '全部系列' },
    ...[...seen].map((c) => ({ value: c, label: c })),
  ]
})

function primaryVideoPrice(m: AdminModelItem) {
  return m.videoPrices.find((p) => p.ruleKey === 'default') ?? m.videoPrices[0] ?? null
}

const filteredModels = computed(() => {
  return models.value.filter((m) => {
    if (mediaFilter.value !== 'all' && m.mediaType !== mediaFilter.value) return false
    if (categoryFilter.value !== 'all' && m.category !== categoryFilter.value) return false
    if (billingFilter.value !== 'all') {
      const vp = primaryVideoPrice(m)
      if (!vp || vp.unit !== billingFilter.value) return false
    }
    if (upstreamFilter.value === 'online' && !m.upstreamAvailable) return false
    if (upstreamFilter.value === 'offline' && m.upstreamAvailable) return false
    return true
  })
})

// Dialog state
const providerDialogOpen = ref(false)
const providerTarget = ref<AdminProvider | null>(null)
const modelDialogOpen = ref(false)
const modelTarget = ref<AdminModelItem | null>(null)
const deleteDialogOpen = ref(false)
const deleteSubmitting = ref(false)
const deleteTarget = ref<AdminModelItem | null>(null)

const createDefaultMediaType = computed<'text' | 'image' | 'video'>(() =>
  mediaFilter.value === 'image' || mediaFilter.value === 'text' ? mediaFilter.value : 'video',
)

async function loadAll() {
  loading.value = true
  try {
    const [pList, mList] = await Promise.all([listAdminProviders(), listAdminModels()])
    providers.value = pList
    models.value = mList
  } catch (err) {
    ui.notify(extractErrorMessage(err, '加载供应商与模型失败'), 'error')
  } finally {
    loading.value = false
  }
}

async function loadSyncLogs(resetPage = false) {
  if (resetPage) logsPage.value = 1
  logsLoading.value = true
  try {
    const res = await listAdminModelSyncLogs({
      limit: logsPageSize.value,
      offset: (logsPage.value - 1) * logsPageSize.value,
    })
    syncLogs.value = res.items
    syncLogsTotal.value = res.total
  } catch (err) {
    ui.notify(extractErrorMessage(err, '加载变动记录失败'), 'error')
  } finally {
    logsLoading.value = false
  }
}

async function handleSyncUpstream() {
  syncing.value = true
  try {
    const res = await syncAdminModels('cc')
    if (res.skipped) {
      ui.notify(`同步已跳过：${res.reason || '上游暂不可用'}`, 'error')
    } else {
      const changed = (res.offline || 0) + (res.restored || 0)
      ui.notify(
        changed > 0
          ? `已检测 ${res.checked} 个模型：下架 ${res.offline} 个，恢复 ${res.restored} 个`
          : `已检测 ${res.checked} 个模型，上游状态无变动`,
        changed > 0 ? 'info' : 'success',
      )
      await Promise.all([loadAll(), loadSyncLogs(true)])
    }
  } catch (err) {
    ui.notify(extractErrorMessage(err, '同步上游失败'), 'error')
  } finally {
    syncing.value = false
  }
}

function openProviderEdit(p: AdminProvider) {
  providerTarget.value = p
  providerDialogOpen.value = true
}

function openCreateModel() {
  modelTarget.value = null
  modelDialogOpen.value = true
}

function openModelEdit(m: AdminModelItem) {
  modelTarget.value = m
  modelDialogOpen.value = true
}

async function toggleModelEnabled(m: AdminModelItem) {
  if (m.isDefault && m.enabled) {
    ui.notify('默认模型不能直接停用，请先将其他模型设为默认', 'error')
    return
  }
  togglingId.value = m.id
  try {
    await updateAdminModel(m.id, { enabled: !m.enabled })
    m.enabled = !m.enabled
    ui.notify(`已${m.enabled ? '启用' : '停用'} ${m.displayName}`, 'success')
  } catch (err) {
    ui.notify(extractErrorMessage(err, '切换状态失败'), 'error')
  } finally {
    togglingId.value = null
  }
}

async function handleModelReorder(payload: { fromIndex: number; toIndex: number }) {
  if (reordering.value) return
  const visible = [...filteredModels.value]
  if (
    payload.fromIndex < 0
    || payload.toIndex < 0
    || payload.fromIndex >= visible.length
    || payload.toIndex >= visible.length
    || payload.fromIndex === payload.toIndex
  ) {
    return
  }

  const prevSnapshot = models.value.map((m) => ({ ...m }))
  const [moved] = visible.splice(payload.fromIndex, 1)
  if (!moved) return
  visible.splice(payload.toIndex, 0, moved)

  const sortPool = visible.map((m) => m.sort).sort((a, b) => a - b)
  const optimisticSorts = new Map<string, number>()
  let lastSort = -Infinity
  for (let i = 0; i < visible.length; i += 1) {
    const item = visible[i]!
    let nextSort = sortPool[i] ?? i
    if (nextSort <= lastSort) nextSort = lastSort + 1
    lastSort = nextSort
    optimisticSorts.set(item.id, nextSort)
  }
  models.value = models.value
    .map((m) => (optimisticSorts.has(m.id) ? { ...m, sort: optimisticSorts.get(m.id)! } : m))
    .sort((a, b) => a.mediaType.localeCompare(b.mediaType) || a.sort - b.sort || a.id.localeCompare(b.id))

  reordering.value = true
  try {
    const res = await reorderAdminModels(visible.map((m) => m.id))
    models.value = models.value
      .map((m) => (res.sorts[m.id] !== undefined ? { ...m, sort: res.sorts[m.id]! } : m))
      .sort((a, b) => a.mediaType.localeCompare(b.mediaType) || a.sort - b.sort || a.id.localeCompare(b.id))
  } catch (err) {
    models.value = prevSnapshot
    ui.notify(extractErrorMessage(err, '保存排序失败'), 'error')
  } finally {
    reordering.value = false
  }
}

function openDeleteModel(m: AdminModelItem) {
  deleteTarget.value = m
  deleteDialogOpen.value = true
}

async function confirmDeleteModel() {
  if (!deleteTarget.value) return
  deleteSubmitting.value = true
  try {
    await deleteAdminModel(deleteTarget.value.id)
    ui.notify(`已删除模型 ${deleteTarget.value.displayName}`, 'success')
    deleteDialogOpen.value = false
    await loadAll()
  } catch (err) {
    ui.notify(extractErrorMessage(err, '删除模型失败'), 'error')
  } finally {
    deleteSubmitting.value = false
  }
}

function formatSpecs(m: AdminModelItem): string {
  const caps = m.capabilities || {}
  if (m.mediaType === 'image') {
    const tiers = Array.isArray(caps.tiers) && caps.tiers.length
      ? caps.tiers.map((t) => String(t).toUpperCase()).join('/')
      : 'WEB/1K/2K/4K'
    const series = m.configuration?.series ?? caps.variant
    const seriesLabel = series === 'flare' ? 'Flare' : series === 'sunburst' ? 'Sunburst' : '标准'
    const ratios = Array.isArray(caps.ratios) ? caps.ratios : []
    const ratioText = ratios.length >= 10 || ratios.length === 0 ? '全比例' : ratios.join('/')
    return `${tiers} · ${seriesLabel} · ${ratioText}`
  }
  if (m.mediaType !== 'video') return mediaLabels[m.mediaType] || m.mediaType
  const res = Array.isArray(caps.resolutions) ? caps.resolutions.join('/') : '720p'
  const minD = caps.minDuration ?? 4
  const maxD = caps.maxDuration ?? 15
  const ratios = Array.isArray(caps.ratios) ? caps.ratios : []
  const ratioText = ratios.length >= 6 ? '全比例' : ratios.length ? ratios.join('/') : '全比例'
  return `${res} · ${minD}–${maxD}s · ${ratioText}`
}

function formatLimits(m: AdminModelItem): string {
  const caps = m.capabilities || {}
  if (m.mediaType === 'image') {
    const img = caps.maxReferenceImages ?? 9
    return caps.supportsMask ? `参考图≤${img} · 支持蒙版` : `参考图≤${img}`
  }
  if (m.mediaType !== 'video') return '-'
  const img = caps.maxReferenceImages ?? 9
  const vid = caps.maxReferenceVideos ?? 3
  const aud = caps.maxReferenceAudios ?? 3
  const prompt = caps.maxPromptChars ?? 5000
  return `图${img} / 视${vid} / 音${aud} · ${prompt}字`
}

function switchSection(section: 'models' | 'logs') {
  activeSection.value = section
  if (section === 'logs') loadSyncLogs(true)
}

onMounted(loadAll)
</script>

<template>
  <section class="admin-section">
    <WorkspacePageHeader eyebrow="管理后台" title="供应商与定价" :badge="models.length">
      <template #icon><Server :size="19" :stroke-width="1.7" /></template>
      <template #actions>
        <button type="button" class="ui-button ui-button--outline ui-button--sm" :disabled="syncing" @click="handleSyncUpstream">
          <CloudDownload :size="14" :class="{ 'ui-spin': syncing }" />
          <span>{{ syncing ? '检测中...' : '检测上游' }}</span>
        </button>
        <button type="button" class="ui-button ui-button--primary ui-button--sm" @click="openCreateModel">
          <Plus :size="14" />
          <span>新建模型</span>
        </button>
        <button type="button" class="ui-button ui-button--secondary ui-button--sm" :disabled="loading" @click="loadAll">
          <RefreshCw :size="14" :class="{ 'ui-spin': loading }" />
          <span>刷新</span>
        </button>
      </template>
    </WorkspacePageHeader>

    <div class="admin-pill-bar">
      <button
        type="button"
        class="admin-pill"
        :class="{ 'is-active': activeSection === 'models' }"
        @click="switchSection('models')"
      >
        模型与定价
      </button>
      <button
        type="button"
        class="admin-pill"
        :class="{ 'is-active': activeSection === 'logs' }"
        @click="switchSection('logs')"
      >
        上游变动记录
      </button>
    </div>

    <template v-if="activeSection === 'models'">
      <div class="admin-card">
        <div class="admin-card-head">
          <h3>AI 供应商</h3>
          <span>共 {{ providers.length }} 个</span>
        </div>
        <UiDataTable :columns="providerColumns" :rows="providers" row-key="key" :loading="loading" compact>
          <template #cell-provider="{ row }">
            <div class="admin-cell-primary">{{ row.displayName }}</div>
            <div class="admin-cell-sub admin-mono">{{ row.key }}</div>
          </template>
          <template #cell-adapter="{ row }">
            <span class="admin-mono">{{ row.adapter }}</span>
          </template>
          <template #cell-baseUrl="{ row }">
            <span class="admin-mono">{{ row.baseUrl }}</span>
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
          <template #cell-actions="{ row }">
            <button type="button" class="ui-button ui-button--secondary ui-button--sm" @click="openProviderEdit(row)">
              <Pencil :size="13" />
              <span>编辑</span>
            </button>
          </template>
        </UiDataTable>
      </div>

      <div class="admin-card">
        <div class="admin-card-head">
          <div class="admin-pill-bar">
            <button
              v-for="tab in ([
                { value: 'video', label: '生视频' },
                { value: 'image', label: '生图' },
                { value: 'text', label: '文本' },
                { value: 'all', label: '全部' },
              ] as const)"
              :key="tab.value"
              type="button"
              class="admin-pill"
              :class="{ 'is-active': mediaFilter === tab.value }"
              @click="mediaFilter = tab.value"
            >
              {{ tab.label }}
            </button>
          </div>

          <div class="admin-actions">
            <div style="width: 150px;">
              <UiSelect v-model="categoryFilter" :options="categoryFilterOptions" placeholder="系列分类" />
            </div>
            <div v-if="mediaFilter === 'video' || mediaFilter === 'all'" style="width: 118px;">
              <UiSelect v-model="billingFilter" :options="billingFilterOptions" placeholder="计费方式" />
            </div>
            <div v-if="mediaFilter === 'video' || mediaFilter === 'all'" style="width: 122px;">
              <UiSelect v-model="upstreamFilter" :options="upstreamFilterOptions" placeholder="上游状态" />
            </div>
          </div>
        </div>

        <UiDataTable
          :columns="modelColumns"
          :rows="filteredModels"
          row-key="id"
          :loading="loading"
          draggable
          :drag-disabled="reordering"
          @reorder="handleModelReorder"
        >
          <template #cell-model="{ row }">
            <div class="admin-cell-primary" style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
              <span>{{ row.displayName }}</span>
              <span v-if="row.category" class="admin-badge admin-badge--info">{{ row.category }}</span>
              <span v-if="row.isDefault" class="admin-badge admin-badge--gold">{{ row.mediaType === 'video' ? '15s 默认' : '默认' }}</span>
              <span v-if="row.mediaType === 'video' && row.isDefaultLong" class="admin-badge admin-badge--gold">30s 默认</span>
            </div>
            <div class="admin-cell-sub admin-mono">{{ row.id }} · 排序 {{ row.sort }}</div>
          </template>
          <template #cell-upstreamModelId="{ row }">
            <span class="admin-mono">{{ row.upstreamModelId }}</span>
          </template>
          <template #cell-specs="{ row }">
            <span class="admin-mono">{{ formatSpecs(row) }}</span>
          </template>
          <template #cell-limits="{ row }">
            <span class="admin-mono">{{ formatLimits(row) }}</span>
          </template>
          <template #cell-price="{ row }">
            <template v-if="row.mediaType === 'video'">
              <template v-if="primaryVideoPrice(row)">
                <span class="admin-badge" :class="primaryVideoPrice(row)!.unit === 'call' ? 'admin-badge--gold' : 'admin-badge--info'">
                  {{ primaryVideoPrice(row)!.unit === 'call' ? '按条' : '按秒' }}
                </span>
                <span class="admin-mono" style="margin-left: 6px;">
                  {{ formatCredits(primaryVideoPrice(row)!.creditPrice) }} 积分
                </span>
              </template>
              <span v-else class="admin-cell-sub">未定价</span>
            </template>
            <template v-else-if="row.mediaType === 'image'">
              <span class="admin-mono">
                {{ row.imagePrices.map((p) => `${p.tier.toUpperCase()}:${formatCredits(p.creditPrice)}`).join(' · ') || '未定价' }}
              </span>
            </template>
            <template v-else-if="row.textPrice">
              <span class="admin-mono">
                入 {{ formatCredits(row.textPrice.inputPricePerMillion) }} / 出 {{ formatCredits(row.textPrice.outputPricePerMillion) }}
              </span>
            </template>
          </template>
          <template #cell-enabled="{ row }">
            <button
              type="button"
              class="admin-badge"
              :class="row.enabled ? 'admin-badge--success' : 'admin-badge--danger'"
              style="cursor: pointer;"
              :disabled="togglingId === row.id"
              @click="toggleModelEnabled(row)"
            >
              {{ row.enabled ? '已启用' : '已停用' }}
            </button>
          </template>
          <template #cell-upstream="{ row }">
            <span v-if="row.providerKey !== 'cc'" class="admin-badge admin-badge--muted">内置可用</span>
            <span v-else class="admin-badge" :class="row.upstreamAvailable ? 'admin-badge--success' : 'admin-badge--danger'">
              {{ row.upstreamAvailable ? '在线' : '已下架' }}
            </span>
          </template>
          <template #cell-actions="{ row }">
            <div class="admin-actions">
              <button type="button" class="ui-button ui-button--outline ui-button--sm" @click="openModelEdit(row)">
                <Pencil :size="13" />
                <span>配置</span>
              </button>
              <button
                type="button"
                class="ui-button ui-button--ghost ui-button--sm"
                :disabled="row.isDefault || row.isDefaultLong"
                @click="openDeleteModel(row)"
              >
                <Trash2 :size="13" />
              </button>
            </div>
          </template>
        </UiDataTable>
      </div>
    </template>

    <UiDataTable
      v-else
      v-model:page="logsPage"
      v-model:page-size="logsPageSize"
      :columns="logColumns"
      :rows="syncLogs"
      row-key="id"
      :loading="logsLoading"
      empty-text="暂无上游变动记录"
      paginated
      :total="syncLogsTotal"
      @change="loadSyncLogs()"
    >
      <template #cell-createdAt="{ row }">
        <span class="admin-mono">{{ formatDateTime(row.createdAt) }}</span>
      </template>
      <template #cell-providerKey="{ row }">
        <span class="admin-mono">{{ row.providerKey }}</span>
      </template>
      <template #cell-model="{ row }">
        <div class="admin-cell-primary admin-mono">{{ row.modelId }}</div>
        <div class="admin-cell-sub admin-mono">{{ row.upstreamModelId }}</div>
      </template>
      <template #cell-eventType="{ row }">
        <span class="admin-badge" :class="row.eventType === 'offline' ? 'admin-badge--danger' : 'admin-badge--success'">
          {{ row.eventType === 'offline' ? '上游已下架' : '上游已恢复' }}
        </span>
      </template>
      <template #cell-summary="{ row }">
        <span>{{ row.summary }}</span>
      </template>
    </UiDataTable>

    <AdminProviderEditDialog
      v-model:open="providerDialogOpen"
      :provider="providerTarget"
      @saved="loadAll"
    />

    <AdminModelFormDialog
      v-model:open="modelDialogOpen"
      :providers="providers"
      :target="modelTarget"
      :default-media-type="createDefaultMediaType"
      @saved="loadAll"
    />

    <UiDialog
      v-model:open="deleteDialogOpen"
      title="确认删除模型"
      :description="deleteTarget ? `${deleteTarget.displayName} (${deleteTarget.id})` : ''"
    >
      <p style="margin: 0; font-size: 13px; color: var(--color-muted);">
        删除后将不再监控该模型；若已有历史扣费记录则仅允许停用。
      </p>
      <template #footer>
        <button type="button" class="ui-button ui-button--secondary" @click="deleteDialogOpen = false">取消</button>
        <button type="button" class="ui-button ui-button--danger" :disabled="deleteSubmitting" @click="confirmDeleteModel">
          {{ deleteSubmitting ? '删除中...' : '确认删除' }}
        </button>
      </template>
    </UiDialog>
  </section>
</template>
