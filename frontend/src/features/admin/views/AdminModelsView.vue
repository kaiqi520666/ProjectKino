<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { CloudDownload, Pencil, Plus, RefreshCw, Server, Trash2 } from 'lucide-vue-next'
import UiDataTable, { type DataTableColumn } from '@/components/ui/UiDataTable.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import {
  createAdminModel,
  deleteAdminModel,
  listAdminModels,
  listAdminModelSyncLogs,
  listAdminProviders,
  reorderAdminModels,
  syncAdminModels,
  updateAdminModel,
  updateAdminProvider,
  type AdminImagePrice,
  type AdminModelItem,
  type AdminModelSyncLog,
  type AdminProvider,
} from '@/features/admin/api'
import { extractErrorMessage, formatCredits, formatDateTime } from '@/features/admin/format'
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

const ALL_RESOLUTIONS = ['480p', '720p', '1080p'] as const
const ALL_RATIOS = ['16:9', '9:16', '1:1', '4:3', '3:4', '21:9'] as const
const ALL_IMAGE_RATIOS = ['16:9', '9:16', '1:1', '4:3', '3:4', '3:2', '2:3', '5:4', '4:5', '21:9', '9:21', 'auto'] as const
const ALL_TIERS = ['web', '1k', '2k', '4k'] as const
const VIDEO_CATEGORY_PRESETS = ['Seedance 2.0', 'Seedance 2.5', 'Seedance 2.5 Flash', 'Wan 3.0'] as const
const IMAGE_CATEGORY_PRESETS = ['GPT Image 2', 'GPT Image 2.5', 'GPT Image 2.6'] as const
const IMAGE_SERIES_OPTIONS = [
  { value: '', label: '标准（无变体）' },
  { value: 'flare', label: 'Flare 极速' },
  { value: 'sunburst', label: 'Sunburst 精修' },
] as const
const IMAGE_QUALITY_OPTIONS = [
  { value: 'medium', label: 'medium' },
  { value: 'high', label: 'high' },
  { value: 'xhigh', label: 'xhigh' },
  { value: 'max', label: 'max' },
] as const

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

const enabledOptions = [
  { value: 'true', label: '启用' },
  { value: 'false', label: '停用' },
]

const defaultOptions = [
  { value: 'true', label: '设为默认' },
  { value: 'false', label: '非默认' },
]

const mediaTypeCreateOptions = [
  { value: 'video', label: '生视频' },
  { value: 'image', label: '生图' },
  { value: 'text', label: '文本' },
]

const tierOptions = [
  { value: 'web', label: 'web' },
  { value: '1k', label: '1k' },
  { value: '2k', label: '2k' },
  { value: '4k', label: '4k' },
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

const providerSelectOptions = computed(() =>
  providers.value.map((p) => ({ value: p.key, label: `${p.displayName} (${p.key})` })),
)

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

const currentCategoryPresets = computed(() =>
  modelForm.mediaType === 'image' ? IMAGE_CATEGORY_PRESETS : VIDEO_CATEGORY_PRESETS,
)

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

// Provider edit modal
const providerDialogOpen = ref(false)
const providerSubmitting = ref(false)
const providerTarget = ref<AdminProvider | null>(null)
const providerForm = reactive({
  displayName: '',
  baseUrl: '',
  apiKey: '',
  enabled: 'true',
})

// Model create/edit modal
const modelDialogOpen = ref(false)
const modelSubmitting = ref(false)
const modelIsCreate = ref(false)
const modelTarget = ref<AdminModelItem | null>(null)
const modelForm = reactive({
  id: '',
  providerKey: 'cc',
  mediaType: 'video' as 'text' | 'image' | 'video',
  category: 'Seedance 2.0',
  displayName: '',
  description: '',
  upstreamModelId: '',
  enabled: 'true',
  isDefault: 'false',
  sort: '100',
  // Video capabilities
  resolutions: ['720p'] as string[],
  ratios: ['16:9', '9:16', '1:1', '4:3', '3:4', '21:9'] as string[],
  minDuration: '4',
  maxDuration: '15',
  maxPromptChars: '5000',
  maxReferenceImages: '9',
  maxReferenceVideos: '3',
  maxReferenceAudios: '3',
  // Video price (simplified single unit + price)
  videoUnit: 'call' as 'call' | 'second',
  videoCreditPrice: '15',
  // Text price
  textInputPrice: '0',
  textCachedPrice: '0',
  textOutputPrice: '0',
  // Image config & prices
  imageSeries: '' as '' | 'flare' | 'sunburst',
  imageQuality: 'high',
  imageRatios: [...ALL_IMAGE_RATIOS] as string[],
  imagePrices: [] as AdminImagePrice[],
})

// Delete confirmation modal
const deleteDialogOpen = ref(false)
const deleteSubmitting = ref(false)
const deleteTarget = ref<AdminModelItem | null>(null)

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
  providerForm.displayName = p.displayName
  providerForm.baseUrl = p.baseUrl
  providerForm.apiKey = ''
  providerForm.enabled = p.enabled ? 'true' : 'false'
  providerDialogOpen.value = true
}

async function submitProviderEdit() {
  if (!providerTarget.value) return
  if (!providerForm.displayName.trim() || !providerForm.baseUrl.trim()) {
    ui.notify('供应商名称和接口地址不能为空', 'error')
    return
  }
  providerSubmitting.value = true
  try {
    await updateAdminProvider(providerTarget.value.key, {
      displayName: providerForm.displayName.trim(),
      baseUrl: providerForm.baseUrl.trim(),
      apiKey: providerForm.apiKey.trim() || undefined,
      enabled: providerForm.enabled === 'true',
    })
    ui.notify(`已更新供应商 ${providerTarget.value.displayName}`, 'success')
    providerDialogOpen.value = false
    await loadAll()
  } catch (err) {
    ui.notify(extractErrorMessage(err, '保存供应商失败'), 'error')
  } finally {
    providerSubmitting.value = false
  }
}

function openCreateModel() {
  const createImage = mediaFilter.value === 'image'
  modelIsCreate.value = true
  modelTarget.value = null
  modelForm.id = ''
  modelForm.providerKey = createImage ? 'cangyuan' : 'cc'
  modelForm.mediaType = createImage ? 'image' : 'video'
  modelForm.category = createImage ? 'GPT Image 2.6' : 'Seedance 2.0'
  modelForm.displayName = ''
  modelForm.description = ''
  modelForm.upstreamModelId = createImage ? 'gpt-image-2.6-x' : ''
  modelForm.enabled = 'true'
  modelForm.isDefault = 'false'
  modelForm.sort = '50'
  modelForm.resolutions = ['720p']
  modelForm.ratios = [...ALL_RATIOS]
  modelForm.minDuration = '4'
  modelForm.maxDuration = '15'
  modelForm.maxPromptChars = '5000'
  modelForm.maxReferenceImages = '9'
  modelForm.maxReferenceVideos = '3'
  modelForm.maxReferenceAudios = '3'
  modelForm.videoUnit = 'call'
  modelForm.videoCreditPrice = '15'
  modelForm.textInputPrice = '0'
  modelForm.textCachedPrice = '0'
  modelForm.textOutputPrice = '0'
  modelForm.imageSeries = createImage ? 'flare' : ''
  modelForm.imageQuality = 'high'
  modelForm.imageRatios = [...ALL_IMAGE_RATIOS]
  modelForm.imagePrices = [
    { tier: 'web', creditPrice: '2' },
    { tier: '1k', creditPrice: '3.5' },
    { tier: '2k', creditPrice: '6' },
    { tier: '4k', creditPrice: '10' },
  ]
  modelDialogOpen.value = true
}

function openModelEdit(m: AdminModelItem) {
  modelIsCreate.value = false
  modelTarget.value = m
  const caps = m.capabilities || {}
  const cfg = m.configuration || {}
  const vp = primaryVideoPrice(m)

  modelForm.id = m.id
  modelForm.providerKey = m.providerKey
  modelForm.mediaType = m.mediaType
  modelForm.category = m.category || ''
  modelForm.displayName = m.displayName
  modelForm.description = typeof caps.description === 'string' ? caps.description : ''
  modelForm.upstreamModelId = m.upstreamModelId
  modelForm.enabled = m.enabled ? 'true' : 'false'
  modelForm.isDefault = m.isDefault ? 'true' : 'false'
  modelForm.sort = String(m.sort)

  const resList = Array.isArray(caps.resolutions) && caps.resolutions.length
    ? caps.resolutions.map(String)
    : ['720p']
  const ratioList = Array.isArray(caps.ratios) && caps.ratios.length
    ? caps.ratios.map(String)
    : [...ALL_RATIOS]
  const imgRatioList = Array.isArray(caps.ratios) && caps.ratios.length
    ? caps.ratios.map(String)
    : [...ALL_IMAGE_RATIOS]

  modelForm.resolutions = resList
  modelForm.ratios = ratioList
  modelForm.minDuration = String(caps.minDuration ?? 4)
  modelForm.maxDuration = String(caps.maxDuration ?? 15)
  modelForm.maxPromptChars = String(caps.maxPromptChars ?? 5000)
  modelForm.maxReferenceImages = String(caps.maxReferenceImages ?? 9)
  modelForm.maxReferenceVideos = String(caps.maxReferenceVideos ?? 3)
  modelForm.maxReferenceAudios = String(caps.maxReferenceAudios ?? 3)
  modelForm.videoUnit = vp?.unit ?? 'call'
  modelForm.videoCreditPrice = vp?.creditPrice ?? '0'

  modelForm.textInputPrice = m.textPrice?.inputPricePerMillion ?? '0'
  modelForm.textCachedPrice = m.textPrice?.cachedInputPricePerMillion ?? '0'
  modelForm.textOutputPrice = m.textPrice?.outputPricePerMillion ?? '0'
  const rawSeries = cfg.series ?? caps.variant
  modelForm.imageSeries = rawSeries === 'flare' || rawSeries === 'sunburst' ? rawSeries : ''
  modelForm.imageQuality = typeof cfg.quality === 'string' && cfg.quality ? cfg.quality : 'high'
  modelForm.imageRatios = imgRatioList
  modelForm.imagePrices = m.imagePrices.map((x) => ({ ...x }))
  modelDialogOpen.value = true
}

function toggleResolution(res: string) {
  if (modelForm.resolutions.includes(res)) {
    if (modelForm.resolutions.length <= 1) return
    modelForm.resolutions = modelForm.resolutions.filter((r) => r !== res)
  } else {
    modelForm.resolutions = [...modelForm.resolutions, res]
  }
}

function toggleRatio(ratio: string) {
  if (modelForm.ratios.includes(ratio)) {
    if (modelForm.ratios.length <= 1) return
    modelForm.ratios = modelForm.ratios.filter((r) => r !== ratio)
  } else {
    modelForm.ratios = [...modelForm.ratios, ratio]
  }
}

function toggleImageRatio(ratio: string) {
  if (modelForm.imageRatios.includes(ratio)) {
    if (modelForm.imageRatios.length <= 1) return
    modelForm.imageRatios = modelForm.imageRatios.filter((r) => r !== ratio)
  } else {
    modelForm.imageRatios = [...modelForm.imageRatios, ratio]
  }
}

function addImagePriceRow() {
  const used = new Set(modelForm.imagePrices.map((x) => x.tier))
  const next = (['web', '1k', '2k', '4k'] as const).find((t) => !used.has(t))
  if (!next) {
    ui.notify('所有分辨率档位均已添加', 'info')
    return
  }
  modelForm.imagePrices.push({ tier: next, creditPrice: '0' })
}

function removeImagePriceRow(index: number) {
  modelForm.imagePrices.splice(index, 1)
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

  // 乐观更新本地排序与序号，松手瞬间生效
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

async function submitModelForm() {
  if (!modelForm.displayName.trim() || !modelForm.upstreamModelId.trim()) {
    ui.notify('模型名称和上游模型名不能为空', 'error')
    return
  }
  const sortNum = Number.parseInt(modelForm.sort, 10)
  if (!Number.isFinite(sortNum)) {
    ui.notify('排序必须为整数', 'error')
    return
  }

  let capabilities: Record<string, unknown> = modelTarget.value ? { ...modelTarget.value.capabilities } : {}
  let defaults: Record<string, unknown> = modelTarget.value ? { ...modelTarget.value.defaults } : {}
  let configuration: Record<string, unknown> = modelTarget.value?.configuration
    ? { ...modelTarget.value.configuration }
    : {}

  if (modelForm.mediaType === 'video') {
    const minD = Math.max(1, Number.parseInt(modelForm.minDuration, 10) || 4)
    const maxD = Math.max(minD, Number.parseInt(modelForm.maxDuration, 10) || 15)
    const maxPrompt = Math.max(100, Number.parseInt(modelForm.maxPromptChars, 10) || 5000)
    const maxImg = Math.max(0, Number.parseInt(modelForm.maxReferenceImages, 10) || 0)
    const maxVid = Math.max(0, Number.parseInt(modelForm.maxReferenceVideos, 10) || 0)
    const maxAud = Math.max(0, Number.parseInt(modelForm.maxReferenceAudios, 10) || 0)
    const orderedRes = ALL_RESOLUTIONS.filter((r) => modelForm.resolutions.includes(r))
    const orderedRatios = ALL_RATIOS.filter((r) => modelForm.ratios.includes(r))

    capabilities = {
      ...capabilities,
      description: modelForm.description.trim(),
      resolutions: orderedRes.length ? orderedRes : ['720p'],
      ratios: orderedRatios.length ? orderedRatios : [...ALL_RATIOS],
      minDuration: minD,
      maxDuration: maxD,
      maxPromptChars: maxPrompt,
      maxReferenceImages: maxImg,
      maxReferenceVideos: maxVid,
      maxReferenceAudios: maxAud,
    }
    defaults = { ...defaults, resolution: (orderedRes[0] ?? '720p') }
  } else if (modelForm.mediaType === 'image') {
    const orderedTiers = ALL_TIERS.filter((t) => modelForm.imagePrices.some((p) => p.tier === t))
    const orderedImgRatios = ALL_IMAGE_RATIOS.filter((r) => modelForm.imageRatios.includes(r))
    capabilities = {
      ...capabilities,
      description: modelForm.description.trim(),
      variant: modelForm.imageSeries,
      tiers: orderedTiers.length ? orderedTiers : ['web', '1k', '2k', '4k'],
      ratios: orderedImgRatios.length ? orderedImgRatios : [...ALL_IMAGE_RATIOS],
      aspectRatios: { character: '16:9', scene: '16:9', prop: '1:1' },
      maxReferenceImages: 9,
      supportsMask: true,
    }
    defaults = { ...defaults, tier: orderedTiers.includes('1k') ? '1k' : (orderedTiers[0] ?? '1k') }
    configuration = {
      ...configuration,
      quality: modelForm.imageQuality || 'high',
    }
    if (modelForm.imageSeries) {
      configuration.series = modelForm.imageSeries
    } else {
      delete configuration.series
    }
  }

  const priceFields: {
    textPrice?: { inputPricePerMillion: string; cachedInputPricePerMillion: string; outputPricePerMillion: string }
    imagePrices?: AdminImagePrice[]
    videoPrices?: { ruleKey: string; unit: 'call' | 'second'; creditPrice: string }[]
  } = {}

  if (modelForm.mediaType === 'text') {
    priceFields.textPrice = {
      inputPricePerMillion: String(modelForm.textInputPrice).trim() || '0',
      cachedInputPricePerMillion: String(modelForm.textCachedPrice).trim() || '0',
      outputPricePerMillion: String(modelForm.textOutputPrice).trim() || '0',
    }
  } else if (modelForm.mediaType === 'image') {
    priceFields.imagePrices = modelForm.imagePrices.map((row) => ({
      tier: row.tier,
      creditPrice: String(row.creditPrice).trim() || '0',
    }))
  } else {
    priceFields.videoPrices = [
      {
        ruleKey: 'default',
        unit: modelForm.videoUnit,
        creditPrice: String(modelForm.videoCreditPrice).trim() || '0',
      },
    ]
  }

  modelSubmitting.value = true
  try {
    if (modelIsCreate.value) {
      const modelId = modelForm.id.trim() || modelForm.upstreamModelId.trim()
      await createAdminModel({
        id: modelId,
        providerKey: modelForm.providerKey,
        mediaType: modelForm.mediaType,
        category: modelForm.category.trim(),
        displayName: modelForm.displayName.trim(),
        upstreamModelId: modelForm.upstreamModelId.trim(),
        enabled: modelForm.enabled === 'true',
        isDefault: modelForm.isDefault === 'true',
        sort: sortNum,
        capabilities,
        defaults,
        configuration,
        ...priceFields,
      })
      ui.notify(`已新增模型 ${modelForm.displayName.trim()}`, 'success')
    } else if (modelTarget.value) {
      await updateAdminModel(modelTarget.value.id, {
        category: modelForm.category.trim(),
        displayName: modelForm.displayName.trim(),
        upstreamModelId: modelForm.upstreamModelId.trim(),
        enabled: modelForm.enabled === 'true',
        isDefault: modelForm.isDefault === 'true',
        sort: sortNum,
        capabilities,
        defaults,
        configuration,
        ...priceFields,
      })
      ui.notify(`已保存 ${modelForm.displayName.trim()}`, 'success')
    }
    modelDialogOpen.value = false
    await loadAll()
  } catch (err) {
    ui.notify(extractErrorMessage(err, '保存模型失败'), 'error')
  } finally {
    modelSubmitting.value = false
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
      <!-- 供应商列表 -->
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

      <!-- 模型目录与定价 -->
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
              <span v-if="row.isDefault" class="admin-badge admin-badge--gold">默认</span>
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
                :disabled="row.isDefault"
                @click="openDeleteModel(row)"
              >
                <Trash2 :size="13" />
              </button>
            </div>
          </template>
        </UiDataTable>
      </div>
    </template>

    <!-- 上游变动记录 -->
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

    <!-- 编辑供应商弹窗 -->
    <UiDialog
      v-model:open="providerDialogOpen"
      title="编辑供应商"
      :description="providerTarget ? `${providerTarget.key} · ${providerTarget.adapter}` : ''"
    >
      <div class="admin-form-stack">
        <div class="ui-field">
          <label class="ui-label">名称 <span class="ui-required">*</span></label>
          <input v-model="providerForm.displayName" class="ui-input" type="text" />
        </div>
        <div class="ui-field">
          <label class="ui-label">接口地址 <span class="ui-required">*</span></label>
          <input v-model="providerForm.baseUrl" class="ui-input admin-mono" type="url" />
        </div>
        <div class="ui-field">
          <label class="ui-label">API Key</label>
          <input
            v-model="providerForm.apiKey"
            class="ui-input admin-mono"
            type="password"
            autocomplete="off"
            :placeholder="providerTarget?.hasApiKey ? '已配置，留空不修改' : '请输入 API Key'"
          />
        </div>
        <UiSelect v-model="providerForm.enabled" label="启用状态" :options="enabledOptions" />
      </div>
      <template #footer>
        <button type="button" class="ui-button ui-button--secondary" @click="providerDialogOpen = false">取消</button>
        <button type="button" class="ui-button ui-button--primary" :disabled="providerSubmitting" @click="submitProviderEdit">
          {{ providerSubmitting ? '保存中...' : '保存' }}
        </button>
      </template>
    </UiDialog>

    <!-- 新建 / 编辑模型弹窗 -->
    <UiDialog
      v-model:open="modelDialogOpen"
      size="wide"
      :title="modelIsCreate ? '新建模型' : `配置模型 · ${modelTarget?.id}`"
    >
      <div class="admin-form-stack">
        <div v-if="modelIsCreate" class="admin-form-grid-3">
          <div class="ui-field">
            <label class="ui-label">模型 ID <span class="ui-required">*</span></label>
            <input v-model="modelForm.id" class="ui-input admin-mono" type="text" placeholder="如 cc-sd2.5-flash-720" />
          </div>
          <UiSelect v-model="modelForm.providerKey" label="供应商" :options="providerSelectOptions" />
          <UiSelect v-model="modelForm.mediaType" label="类型" :options="mediaTypeCreateOptions" />
        </div>

        <div class="admin-settings-grid">
          <div class="ui-field">
            <label class="ui-label">前端名称 <span class="ui-required">*</span></label>
            <input v-model="modelForm.displayName" class="ui-input" type="text" placeholder="如 Seedance 2.5 Flash 720p" />
          </div>
          <div class="ui-field">
            <label class="ui-label">上游模型名 <span class="ui-required">*</span></label>
            <input v-model="modelForm.upstreamModelId" class="ui-input admin-mono" type="text" placeholder="如 cc-sd2.5-flash-720" />
          </div>
        </div>

        <div v-if="modelForm.mediaType === 'video' || modelForm.mediaType === 'image'" class="ui-field">
          <label class="ui-label">模型简介</label>
          <input v-model="modelForm.description" class="ui-input" type="text" placeholder="选填，一句话介绍特点，显示在前端模型卡片中" />
        </div>

        <div class="ui-field">
          <label class="ui-label">系列分类</label>
          <input v-model="modelForm.category" class="ui-input" type="text" placeholder="自定义或点下方快捷填入" />
          <div class="admin-chip-group">
            <button
              v-for="preset in currentCategoryPresets"
              :key="preset"
              type="button"
              class="admin-chip"
              :class="{ 'is-active': modelForm.category === preset }"
              @click="modelForm.category = preset"
            >
              {{ preset }}
            </button>
          </div>
        </div>

        <!-- 视频专属配置 -->
        <template v-if="modelForm.mediaType === 'video'">
          <div class="admin-settings-grid">
            <div class="ui-field">
              <label class="ui-label">计费方式</label>
              <div class="admin-chip-group">
                <button
                  type="button"
                  class="admin-chip"
                  :class="{ 'is-active': modelForm.videoUnit === 'call' }"
                  @click="modelForm.videoUnit = 'call'"
                >
                  按条
                </button>
                <button
                  type="button"
                  class="admin-chip"
                  :class="{ 'is-active': modelForm.videoUnit === 'second' }"
                  @click="modelForm.videoUnit = 'second'"
                >
                  按秒
                </button>
              </div>
            </div>
            <div class="ui-field">
              <label class="ui-label">售价（积分 / {{ modelForm.videoUnit === 'call' ? '条' : '秒' }}）</label>
              <input v-model="modelForm.videoCreditPrice" class="ui-input admin-mono" type="number" step="0.1" min="0" />
            </div>
          </div>

          <div class="ui-field">
            <label class="ui-label">支持分辨率（多选）</label>
            <div class="admin-chip-group">
              <button
                v-for="res in ALL_RESOLUTIONS"
                :key="res"
                type="button"
                class="admin-chip"
                :class="{ 'is-active': modelForm.resolutions.includes(res) }"
                @click="toggleResolution(res)"
              >
                {{ res }}
              </button>
            </div>
          </div>

          <div class="ui-field">
            <label class="ui-label">支持比例（多选）</label>
            <div class="admin-chip-group">
              <button
                v-for="ratio in ALL_RATIOS"
                :key="ratio"
                type="button"
                class="admin-chip"
                :class="{ 'is-active': modelForm.ratios.includes(ratio) }"
                @click="toggleRatio(ratio)"
              >
                {{ ratio }}
              </button>
            </div>
          </div>

          <div class="admin-form-grid-3">
            <div class="ui-field">
              <label class="ui-label">最短时长（秒）</label>
              <input v-model="modelForm.minDuration" class="ui-input admin-mono" type="number" min="1" max="60" />
            </div>
            <div class="ui-field">
              <label class="ui-label">最长时长（秒）</label>
              <input v-model="modelForm.maxDuration" class="ui-input admin-mono" type="number" min="1" max="120" />
            </div>
            <div class="ui-field">
              <label class="ui-label">提示词上限（字）</label>
              <input v-model="modelForm.maxPromptChars" class="ui-input admin-mono" type="number" min="100" max="50000" />
            </div>
          </div>

          <div class="admin-form-grid-3">
            <div class="ui-field">
              <label class="ui-label">参考图上限</label>
              <input v-model="modelForm.maxReferenceImages" class="ui-input admin-mono" type="number" min="0" max="50" />
            </div>
            <div class="ui-field">
              <label class="ui-label">参考视频上限</label>
              <input v-model="modelForm.maxReferenceVideos" class="ui-input admin-mono" type="number" min="0" max="20" />
            </div>
            <div class="ui-field">
              <label class="ui-label">参考音频上限</label>
              <input v-model="modelForm.maxReferenceAudios" class="ui-input admin-mono" type="number" min="0" max="20" />
            </div>
          </div>
        </template>

        <!-- 文本定价 -->
        <template v-else-if="modelForm.mediaType === 'text'">
          <div class="admin-form-grid-3">
            <div class="ui-field">
              <label class="ui-label">普通输入 / M</label>
              <input v-model="modelForm.textInputPrice" class="ui-input admin-mono" type="number" step="0.0001" min="0" />
            </div>
            <div class="ui-field">
              <label class="ui-label">缓存输入 / M</label>
              <input v-model="modelForm.textCachedPrice" class="ui-input admin-mono" type="number" step="0.0001" min="0" />
            </div>
            <div class="ui-field">
              <label class="ui-label">输出 / M</label>
              <input v-model="modelForm.textOutputPrice" class="ui-input admin-mono" type="number" step="0.0001" min="0" />
            </div>
          </div>
        </template>

        <!-- 图片档位与路由配置 -->
        <template v-else-if="modelForm.mediaType === 'image'">
          <div class="admin-settings-grid">
            <div class="ui-field">
              <label class="ui-label">变体通道（series）</label>
              <div class="admin-chip-group">
                <button
                  v-for="opt in IMAGE_SERIES_OPTIONS"
                  :key="opt.value"
                  type="button"
                  class="admin-chip"
                  :class="{ 'is-active': modelForm.imageSeries === opt.value }"
                  @click="modelForm.imageSeries = opt.value"
                >
                  {{ opt.label }}
                </button>
              </div>
            </div>
            <div class="ui-field">
              <label class="ui-label">非 Web 档画质（quality）</label>
              <div class="admin-chip-group">
                <button
                  v-for="q in IMAGE_QUALITY_OPTIONS"
                  :key="q.value"
                  type="button"
                  class="admin-chip"
                  :class="{ 'is-active': modelForm.imageQuality === q.value }"
                  @click="modelForm.imageQuality = q.value"
                >
                  {{ q.label }}
                </button>
              </div>
            </div>
          </div>

          <div class="ui-field">
            <label class="ui-label">支持比例（多选）</label>
            <div class="admin-chip-group">
              <button
                v-for="ratio in ALL_IMAGE_RATIOS"
                :key="ratio"
                type="button"
                class="admin-chip"
                :class="{ 'is-active': modelForm.imageRatios.includes(ratio) }"
                @click="toggleImageRatio(ratio)"
              >
                {{ ratio === 'auto' ? '自动' : ratio }}
              </button>
            </div>
          </div>

          <div class="admin-card-head" style="margin: 4px 0 0;">
            <span class="ui-label">图片档位单价 · 积分 / 张</span>
            <button type="button" class="ui-button ui-button--secondary ui-button--sm" @click="addImagePriceRow">
              <Plus :size="13" />
              <span>新增档位</span>
            </button>
          </div>
          <div v-for="(row, idx) in modelForm.imagePrices" :key="idx" class="admin-price-row">
            <UiSelect v-model="row.tier" :options="tierOptions" />
            <input v-model="row.creditPrice" class="ui-input admin-mono" type="number" step="0.01" min="0" placeholder="积分/张" />
            <span class="admin-cell-sub">积分 / 张</span>
            <button type="button" class="ui-icon-button" aria-label="删除档位" @click="removeImagePriceRow(idx)">
              <Trash2 :size="15" />
            </button>
          </div>
        </template>

        <div class="admin-form-grid-3">
          <UiSelect v-model="modelForm.enabled" label="后台开关" :options="enabledOptions" />
          <UiSelect v-model="modelForm.isDefault" label="是否默认" :options="defaultOptions" />
          <div class="ui-field">
            <label class="ui-label">排序</label>
            <input v-model="modelForm.sort" class="ui-input admin-mono" type="number" step="1" />
          </div>
        </div>
      </div>

      <template #footer>
        <button type="button" class="ui-button ui-button--secondary" @click="modelDialogOpen = false">取消</button>
        <button type="button" class="ui-button ui-button--primary" :disabled="modelSubmitting" @click="submitModelForm">
          {{ modelSubmitting ? '保存中...' : '保存' }}
        </button>
      </template>
    </UiDialog>

    <!-- 删除模型弹窗 -->
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
