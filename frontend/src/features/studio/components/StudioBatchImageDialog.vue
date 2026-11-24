<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, Sparkles } from 'lucide-vue-next'
import UiAlert from '@/components/ui/UiAlert.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import type { ModelCatalogItemOut } from '../api-types'
import { assetKindIcons } from '../asset-icons'
import { assetDisplayName, assetKindOptions, findParentAsset, planAssetImageWaves } from '../studio-assets'
import type { StudioAsset, StudioAssetKind } from '../studio-assets'
import { resolveDefaultImageModel, resolveImageTierForModel, type ImageTier } from '../model-defaults'
import ImageModelPicker from './ImageModelPicker.vue'
import ImageParamsPopover from './ImageParamsPopover.vue'

const props = withDefaults(
  defineProps<{
    assets: StudioAsset[]
    activeCategory: StudioAssetKind
    activeAssetIds: ReadonlySet<string>
    imageModels: ModelCatalogItemOut[]
    defaultModelId?: string
    defaultTier?: ImageTier
    initialSelectedIds?: string[]
    submitting?: boolean
  }>(),
  {
    defaultModelId: undefined,
    defaultTier: undefined,
    initialSelectedIds: () => [],
    submitting: false,
  },
)

const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{
  submit: [payload: {
    assetIds: string[]
    wave2VariantIds: string[]
    modelId: string
    tier: 'web' | '1k' | '2k' | '4k'
    ratio?: string
  }]
}>()

const selectedIds = ref<string[]>([])
const selectedModelId = ref('')
const selectedTier = ref<'web' | '1k' | '2k' | '4k'>('1k')
const ratioMode = ref<'auto' | 'override'>('auto')
const overrideRatio = ref('16:9')
const rootsOnly = ref(false)

const modelCatalogList = computed<ModelCatalogItemOut[]>(() => props.imageModels)

const currentModel = computed(
  () => modelCatalogList.value.find((m) => m.id === selectedModelId.value) ?? modelCatalogList.value[0] ?? null,
)

function defaultAssetRatio(asset: StudioAsset) {
  return asset.kind === 'prop' ? '1:1' : '16:9'
}

function effectiveAssetRatio(asset: StudioAsset) {
  return ratioMode.value === 'override' ? overrideRatio.value : defaultAssetRatio(asset)
}

function isSelectable(asset: StudioAsset) {
  return !!asset.backendId && !!asset.prompt.trim() && !props.activeAssetIds.has(asset.backendId)
}

function disabledReason(asset: StudioAsset) {
  if (!asset.backendId) return '未保存'
  if (props.activeAssetIds.has(asset.backendId)) return '生图中'
  if (!asset.prompt.trim()) return '缺提示词'
  return ''
}

const selectableAssets = computed(() => props.assets.filter(isSelectable))
const missingSelectableAssets = computed(() => selectableAssets.value.filter((a) => !a.imageUrl))
const missingRootSelectableAssets = computed(() =>
  missingSelectableAssets.value.filter((a) => !a.parentAssetId),
)
const currentCategorySelectable = computed(() =>
  selectableAssets.value.filter((a) => a.kind === props.activeCategory),
)

const groups = computed(() =>
  assetKindOptions
    .map((item) => ({
      ...item,
      icon: assetKindIcons[item.value],
      assets: props.assets.filter((a) => a.kind === item.value),
    }))
    .filter((group) => group.assets.length > 0),
)

const selectedSet = computed(() => new Set(selectedIds.value))

const selectedAssets = computed(() =>
  props.assets.filter((a) => a.backendId && selectedSet.value.has(a.backendId) && isSelectable(a)),
)

const selectedVariantCount = computed(() =>
  selectedAssets.value.filter((a) => !!a.parentAssetId).length,
)

const selectedRootCount = computed(() =>
  selectedAssets.value.filter((a) => !a.parentAssetId).length,
)

const wavePlan = computed(() =>
  planAssetImageWaves(
    props.assets,
    selectedAssets.value.map((a) => a.backendId!),
    { rootsOnly: rootsOnly.value },
  ),
)

const effectiveIdSet = computed(
  () => new Set([...wavePlan.value.wave1Ids, ...wavePlan.value.wave2VariantIds]),
)

const effectiveAssets = computed(() =>
  selectedAssets.value.filter((a) => a.backendId && effectiveIdSet.value.has(a.backendId)),
)

const newCount = computed(() => effectiveAssets.value.filter((a) => !a.imageUrl).length)
const redrawCount = computed(() => effectiveAssets.value.filter((a) => !!a.imageUrl).length)

function hasReadyParentImage(asset: StudioAsset): boolean {
  if (!asset.parentAssetId) return false
  const parent = findParentAsset(props.assets, asset)
  return !!parent?.imageUrl && /^https?:\/\//i.test(parent.imageUrl)
}

function isWave2Variant(asset: StudioAsset): boolean {
  return !!asset.backendId && wavePlan.value.wave2VariantIds.includes(asset.backendId)
}

const unitPrice = computed(() => {
  const price = currentModel.value?.imagePrices.find((p) => p.tier === selectedTier.value)
  if (!price) return null
  const num = Number(price.creditPrice)
  return Number.isFinite(num) ? num : null
})

const totalEstimatedAmount = computed(() => {
  if (unitPrice.value === null || !effectiveAssets.value.length) return ''
  const total = unitPrice.value * effectiveAssets.value.length
  return String(Number(total.toFixed(2)))
})

const totalEstimatedText = computed(() => (totalEstimatedAmount.value ? `${totalEstimatedAmount.value} 积分` : ''))

watch(open, (isOpen) => {
  if (!isOpen) return
  ratioMode.value = 'auto'
  overrideRatio.value = '16:9'
  rootsOnly.value = false
  const resolvedModel = resolveDefaultImageModel(modelCatalogList.value, props.defaultModelId)
  selectedModelId.value = resolvedModel?.id || ''
  selectedTier.value = resolveImageTierForModel(resolvedModel, props.defaultTier)
  if (props.initialSelectedIds.length) {
    const allowed = new Set(selectableAssets.value.map((a) => a.backendId!))
    selectedIds.value = props.initialSelectedIds.filter((id) => allowed.has(id)).slice(0, 30)
  } else {
    selectedIds.value = missingSelectableAssets.value.map((a) => a.backendId!).slice(0, 30)
  }
})

function toggleAsset(asset: StudioAsset) {
  if (!isSelectable(asset) || !asset.backendId) return
  const id = asset.backendId
  if (selectedSet.value.has(id)) {
    selectedIds.value = selectedIds.value.filter((item) => item !== id)
  } else {
    if (selectedIds.value.length >= 30) return
    selectedIds.value = [...selectedIds.value, id]
  }
}

function selectMissing() {
  selectedIds.value = missingSelectableAssets.value.map((a) => a.backendId!).slice(0, 30)
}

function selectMissingRoots() {
  selectedIds.value = missingRootSelectableAssets.value.map((a) => a.backendId!).slice(0, 30)
}

function addMissingParents() {
  const allowed = new Set(selectableAssets.value.map((a) => a.backendId!))
  const next = [...selectedIds.value]
  for (const pid of wavePlan.value.missingParentIds) {
    if (next.length >= 30) break
    if (allowed.has(pid) && !next.includes(pid)) next.unshift(pid)
  }
  selectedIds.value = next
}

function selectCurrentCategory() {
  selectedIds.value = currentCategorySelectable.value.map((a) => a.backendId!).slice(0, 30)
}

function selectAllAssets() {
  selectedIds.value = selectableAssets.value.map((a) => a.backendId!).slice(0, 30)
}

function clearSelection() {
  selectedIds.value = []
}

function confirmSubmit() {
  const { wave1Ids, wave2VariantIds } = wavePlan.value
  if (!wave1Ids.length || !currentModel.value || props.submitting) return
  emit('submit', {
    assetIds: wave1Ids,
    wave2VariantIds,
    modelId: currentModel.value.id,
    tier: selectedTier.value,
    ratio: ratioMode.value === 'override' ? overrideRatio.value : undefined,
  })
}
</script>

<template>
  <UiDialog
    v-model:open="open"
    title="批量生图 / 批量重绘"
    description="可自由勾选暂无图片的资产生成新图，或勾选已有图片的资产进行重绘（单次最多 30 项，后台并发执行不阻塞页面）。"
    size="landscape"
  >
    <div class="batch-dialog">
      <div class="batch-shortcuts">
        <div class="batch-shortcut-buttons">
          <UiButton variant="outline" size="sm" :disabled="!missingSelectableAssets.length" @click="selectMissing">
            全选缺图 ({{ missingSelectableAssets.length }})
          </UiButton>
          <UiButton
            v-if="missingRootSelectableAssets.length < missingSelectableAssets.length"
            variant="outline"
            size="sm"
            :disabled="!missingRootSelectableAssets.length"
            @click="selectMissingRoots"
          >
            仅选缺图主资产 ({{ missingRootSelectableAssets.length }})
          </UiButton>
          <UiButton variant="outline" size="sm" :disabled="!currentCategorySelectable.length" @click="selectCurrentCategory">
            全选当前分类 ({{ currentCategorySelectable.length }})
          </UiButton>
          <UiButton variant="outline" size="sm" :disabled="!selectableAssets.length" @click="selectAllAssets">
            全选全部 ({{ selectableAssets.length }})
          </UiButton>
          <UiButton variant="ghost" size="sm" :disabled="!selectedIds.length" @click="clearSelection">
            清空
          </UiButton>
        </div>
        <span class="batch-count-hint">已选 {{ selectedAssets.length }} / 30 项</span>
      </div>

      <UiAlert
        v-if="!rootsOnly && wavePlan.orphanVariantIds.length > 0"
        tone="warning"
        :title="`有 ${wavePlan.orphanVariantIds.length} 项已选变体的主资产尚未出图且未勾选`"
      >
        <div class="batch-orphan-alert">
          <span>建议连同对应主资产一起勾选，系统将自动先生成主图，再用主图垫图生成变体以锁住外观一致。</span>
          <UiButton
            v-if="wavePlan.missingParentIds.length"
            variant="outline"
            size="sm"
            @click="addMissingParents"
          >
            补选主资产 (+{{ wavePlan.missingParentIds.length }})
          </UiButton>
        </div>
      </UiAlert>

      <div class="batch-groups">
        <section v-for="group in groups" :key="group.value" class="batch-group">
          <h3 class="batch-group-title">
            <component :is="group.icon" :size="14" aria-hidden="true" />
            {{ group.label }}
            <span>{{ group.assets.length }}</span>
          </h3>
          <ul class="batch-asset-grid">
            <li v-for="asset in group.assets" :key="asset.id">
              <button
                type="button"
                class="batch-asset-item"
                :class="{
                  'is-selected': !!asset.backendId && selectedSet.has(asset.backendId),
                  'is-disabled': !isSelectable(asset),
                }"
                :disabled="!isSelectable(asset)"
                @click="toggleAsset(asset)"
              >
                <span class="batch-check" aria-hidden="true">
                  <Check v-if="asset.backendId && selectedSet.has(asset.backendId)" :size="12" :stroke-width="2.6" />
                </span>
                <span class="batch-thumb">
                  <img v-if="asset.imageUrl" :src="asset.imageUrl" alt="" />
                  <component :is="group.icon" v-else :size="18" aria-hidden="true" />
                </span>
                <span class="batch-info">
                  <strong :title="assetDisplayName(asset)">{{ assetDisplayName(asset) }}</strong>
                  <span class="batch-tags">
                    <span
                      class="batch-ratio"
                      :class="{ 'is-overridden': ratioMode === 'override' && effectiveAssetRatio(asset) !== defaultAssetRatio(asset) }"
                      :title="ratioMode === 'override' && effectiveAssetRatio(asset) !== defaultAssetRatio(asset) ? `原默认 ${defaultAssetRatio(asset)} → 统一 ${overrideRatio}` : undefined"
                    >
                      {{ effectiveAssetRatio(asset) === 'auto' ? '自动' : effectiveAssetRatio(asset) }}
                    </span>
                    <span v-if="isWave2Variant(asset)" class="batch-badge is-ref">第2阶段 · 垫图</span>
                    <span v-else-if="hasReadyParentImage(asset)" class="batch-badge is-ref">主图垫图</span>
                    <span v-if="disabledReason(asset)" class="batch-badge is-disabled">{{ disabledReason(asset) }}</span>
                    <span v-else-if="asset.imageUrl" class="batch-badge is-redraw">已有图 · 重绘</span>
                    <span v-else class="batch-badge is-missing">暂无图片</span>
                  </span>
                </span>
              </button>
            </li>
          </ul>
        </section>
      </div>

      <div v-if="selectedVariantCount > 0" class="batch-phase-bar">
        <label class="batch-phase-toggle">
          <input v-model="rootsOnly" type="checkbox" :disabled="selectedRootCount === 0 && !rootsOnly" />
          <span>仅先生成主图，确认后再生成变体</span>
        </label>
        <span class="batch-phase-desc">
          <template v-if="rootsOnly">
            本次仅生成 {{ wavePlan.wave1Ids.length }} 张主图（暂不生成 {{ selectedVariantCount }} 张变体）
          </template>
          <template v-else-if="wavePlan.wave2VariantIds.length > 0">
            自动两阶段：先生成主图 {{ wavePlan.wave1Ids.length }} 张 → 完成后自动以主图垫图生变体 {{ wavePlan.wave2VariantIds.length }} 张
          </template>
          <template v-else>
            所选变体的主图已就绪，将直接以主图垫图并发生成
          </template>
        </span>
      </div>

      <div class="batch-config-bar">
        <div class="batch-config-selects">
          <ImageModelPicker
            v-model="selectedModelId"
            :models="modelCatalogList"
            :tier="selectedTier"
          />
          <ImageParamsPopover
            v-model:tier="selectedTier"
            v-model:ratio="overrideRatio"
            v-model:ratio-mode="ratioMode"
            :model="currentModel"
            mode="batch"
          />
        </div>
        <div class="batch-summary">
          <p v-if="effectiveAssets.length" class="batch-summary-main">
            本次执行 <strong>{{ effectiveAssets.length }}</strong> 项（新生成 {{ newCount }} · 重绘 {{ redrawCount }}）<template v-if="totalEstimatedText">，预计共需 <strong>{{ totalEstimatedText }}</strong></template>
          </p>
          <p v-else class="batch-summary-main">请至少勾选 1 项可生成的资产</p>
          <p class="batch-summary-note">
            <template v-if="!rootsOnly && wavePlan.wave2VariantIds.length > 0">
              分两阶段预冻结：若某张主图失败，其名下变体将自动跳过且不扣积分。
            </template>
            <template v-else>
              每张独立核算：单张失败自动退还冻结积分，重绘失败保留原图。
            </template>
          </p>
        </div>
      </div>
    </div>

    <template #footer>
      <UiButton variant="ghost" size="sm" :disabled="submitting" @click="open = false">取消</UiButton>
      <div class="batch-cta-split" :class="{ 'is-solo': !totalEstimatedAmount || submitting }">
        <span v-if="totalEstimatedAmount && !submitting" class="batch-cta-cost">
          <Sparkles :size="13" class="batch-cta-cost-icon" aria-hidden="true" />
          <strong class="batch-cta-cost-num">{{ totalEstimatedAmount }}</strong>
          <span class="batch-cta-cost-unit">积分</span>
        </span>
        <UiButton
          class="batch-submit-btn"
          variant="primary"
          size="sm"
          :loading="submitting"
          :disabled="!effectiveAssets.length || !currentModel || submitting"
          @click="confirmSubmit"
        >
          <template v-if="!submitting" #leading><Sparkles :size="14" aria-hidden="true" /></template>
          {{
            rootsOnly
              ? `先生成主图 (${effectiveAssets.length})`
              : wavePlan.wave2VariantIds.length > 0
                ? `一键两阶段生图 (${effectiveAssets.length})`
                : `开始批量生图 (${effectiveAssets.length})`
          }}
        </UiButton>
      </div>
    </template>
  </UiDialog>
</template>

<style scoped>
.batch-dialog {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
}
.batch-shortcuts {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.batch-shortcut-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.batch-count-hint {
  color: var(--color-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.batch-groups {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  overflow-y: auto;
  padding: 2px 4px 2px 0;
}
.batch-group-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 8px;
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 600;
}
.batch-group-title span {
  font-weight: 400;
}
.batch-asset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.batch-asset-item {
  display: grid;
  grid-template-columns: 18px 54px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border-control);
  border-radius: 8px;
  background: var(--color-surface);
  color: var(--color-text);
  text-align: left;
  cursor: pointer;
  transition: border-color .15s, background-color .15s;
}
.batch-asset-item:not(:disabled):hover {
  border-color: rgb(240 184 75 / 50%);
  background: var(--surface-hover);
}
.batch-asset-item.is-selected {
  border-color: var(--color-gold);
  background: var(--gold-tint);
}
.batch-asset-item.is-disabled {
  opacity: 0.48;
  cursor: not-allowed;
}
.batch-check {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border: 1px solid var(--border-control);
  border-radius: 4px;
  background: var(--color-canvas);
  color: var(--color-ink);
}
.batch-asset-item.is-selected .batch-check {
  border-color: var(--color-gold);
  background: var(--color-gold);
}
.batch-thumb {
  display: grid;
  place-items: center;
  width: 54px;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: 5px;
  background: var(--color-elevated);
  color: var(--color-muted);
}
.batch-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.batch-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.batch-info strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
}
.batch-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  font-size: 11px;
}
.batch-ratio {
  padding: 0 5px;
  border-radius: 4px;
  background: rgb(255 255 255 / 6%);
  color: var(--color-muted);
  font-variant-numeric: tabular-nums;
}
.batch-ratio.is-overridden {
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-weight: 600;
}
.batch-badge {
  padding: 0 5px;
  border-radius: 4px;
}
.batch-badge.is-missing {
  background: var(--gold-tint);
  color: var(--color-gold-soft);
}
.batch-badge.is-redraw {
  background: rgb(74 222 128 / 12%);
  color: var(--color-success);
}
.batch-badge.is-ref {
  background: color-mix(in srgb, var(--color-gold) 18%, transparent);
  color: var(--color-gold-soft);
}
.batch-badge.is-disabled {
  background: rgb(255 255 255 / 5%);
  color: var(--color-muted);
}
.batch-orphan-alert {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.batch-phase-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 14px;
  padding: 8px 12px;
  border: 1px solid rgb(240 184 75 / 26%);
  border-radius: 8px;
  background: rgb(240 184 75 / 6%);
  font-size: 12px;
}
.batch-phase-toggle {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--color-text);
  font-weight: 500;
  cursor: pointer;
  user-select: none;
}
.batch-phase-toggle input {
  width: 15px;
  height: 15px;
  accent-color: var(--color-gold);
  cursor: pointer;
}
.batch-phase-desc {
  color: var(--color-gold-soft);
}
.batch-config-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-top: auto;
  padding: 10px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--color-canvas);
}
.batch-config-selects {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.batch-summary {
  flex: 1 1 240px;
  text-align: right;
}
.batch-summary-main {
  margin: 0;
  font-size: 13px;
}
.batch-summary-main strong {
  color: var(--color-gold-soft);
}
.batch-summary-note {
  margin: 3px 0 0;
  color: var(--color-muted);
  font-size: 11px;
}
.batch-cta-split {
  display: inline-flex;
  align-items: stretch;
  height: var(--control-height-sm);
  border-radius: var(--radius-control-sm);
  overflow: hidden;
  border: 1px solid rgb(240 184 75 / 55%);
  box-shadow: 0 2px 10px rgb(240 184 75 / 12%);
}
.batch-cta-split.is-solo {
  border-color: transparent;
  box-shadow: none;
}
.batch-cta-cost {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0 12px;
  background: #13151c;
  color: var(--color-gold-soft);
  user-select: none;
}
.batch-cta-cost-icon {
  color: var(--color-gold);
  flex-shrink: 0;
}
.batch-cta-cost-num {
  font-size: 16px;
  font-weight: 700;
  color: #f8cc66;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  line-height: 1;
}
.batch-cta-cost-unit {
  font-size: 11px;
  font-weight: 500;
  color: rgb(248 204 102 / 82%);
  line-height: 1;
}
.batch-submit-btn.ui-button {
  min-height: 0;
  height: 100%;
  padding: 0 14px;
  border: 0;
  border-radius: 0;
}
.batch-cta-split.is-solo .batch-submit-btn.ui-button {
  border-radius: var(--radius-control-sm);
}
@media (max-width: 640px) {
  .batch-summary { text-align: left; }
}
</style>
