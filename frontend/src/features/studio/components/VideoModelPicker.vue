<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, ChevronDown, Clock3, Film, Layers, Maximize2, Search, Sparkles, X } from 'lucide-vue-next'
import {
  DialogClose,
  DialogContent,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
  DialogTrigger,
} from 'reka-ui'
import type { ModelCatalogItemOut } from '../api-types'

const props = withDefaults(
  defineProps<{
    models: readonly ModelCatalogItemOut[]
    clipDuration?: number
    minMaxDuration?: number
    projectRatio?: string
    referenceCount?: number
    promptLength?: number
    disabled?: boolean
    placeholder?: string
  }>(),
  {
    disabled: false,
    placeholder: '选择视频模型',
  },
)

const modelValue = defineModel<string>({ default: '' })

const open = ref(false)
const activeCategory = ref('all')
const activeBilling = ref<'all' | 'call' | 'second'>('all')
const keyword = ref('')

const categories = computed(() => {
  const counts = new Map<string, number>()
  for (const m of props.models) {
    const cat = (m.category || '').trim()
    if (cat) counts.set(cat, (counts.get(cat) ?? 0) + 1)
  }
  return [...counts.entries()].map(([name, count]) => ({ name, count }))
})

const selectedModel = computed(
  () => props.models.find((m) => m.id === modelValue.value) ?? props.models[0] ?? null,
)

const filteredModels = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  return props.models.filter((m) => {
    if (activeCategory.value !== 'all' && (m.category || '').trim() !== activeCategory.value) {
      return false
    }
    if (activeBilling.value !== 'all') {
      const vp = primaryPrice(m)
      if (!vp || vp.unit !== activeBilling.value) return false
    }
    if (q) {
      const hay = `${m.displayName} ${m.id} ${m.category || ''} ${modelDescription(m)}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
})

watch(open, (isOpen) => {
  if (!isOpen) return
  keyword.value = ''
  if (activeCategory.value !== 'all' && !categories.value.some((c) => c.name === activeCategory.value)) {
    activeCategory.value = 'all'
  }
})

function primaryPrice(m: ModelCatalogItemOut) {
  return m.videoPrices.find((p) => p.ruleKey === 'default') ?? m.videoPrices[0] ?? null
}

function formatNum(val: string | number): string {
  const num = Number(val)
  if (!Number.isFinite(num)) return String(val)
  return Number(num.toFixed(2)).toString()
}

function modelDescription(m: ModelCatalogItemOut): string {
  const desc = m.capabilities?.description
  return typeof desc === 'string' ? desc.trim() : ''
}

function modelResolutionsText(m: ModelCatalogItemOut): string {
  const raw = m.capabilities?.resolutions
  return Array.isArray(raw) && raw.length ? raw.map(String).join(' / ') : '720p'
}

function modelDurationText(m: ModelCatalogItemOut): string {
  const minD = Number(m.capabilities?.minDuration || 4)
  const maxD = Number(m.capabilities?.maxDuration || 15)
  return `${minD}–${maxD}s`
}

function modelRatiosText(m: ModelCatalogItemOut): string {
  const raw = m.capabilities?.ratios
  if (!Array.isArray(raw) || raw.length === 0 || raw.length >= 6) return '全比例'
  return `仅 ${raw.map(String).join('/')}`
}

function modelMediaText(m: ModelCatalogItemOut): string {
  const caps = m.capabilities || {}
  const img = Number(caps.maxReferenceImages ?? 9)
  const vid = Number(caps.maxReferenceVideos ?? 3)
  const aud = Number(caps.maxReferenceAudios ?? 3)
  const parts: string[] = [`图≤${img}`]
  if (vid > 0) parts.push(`视≤${vid}`)
  if (aud > 0) parts.push(`音≤${aud}`)
  if (vid === 0) parts.push('无视频参考')
  return parts.join(' · ')
}

function estimatedClipCost(m: ModelCatalogItemOut): string {
  if (props.clipDuration === undefined) return ''
  const vp = primaryPrice(m)
  if (!vp || vp.unit !== 'second') return ''
  const unit = Number(vp.creditPrice)
  if (!Number.isFinite(unit)) return ''
  return `本段约 ${formatNum(unit * props.clipDuration)} 积分`
}

function hardBlockReason(m: ModelCatalogItemOut): string {
  const caps = m.capabilities || {}
  if (props.minMaxDuration !== undefined) {
    const maxD = Number(caps.maxDuration || 15)
    if (maxD < props.minMaxDuration) {
      return `最长支持 ${maxD}s，不满足 ${props.minMaxDuration}s 片段要求`
    }
  }
  if (props.referenceCount !== undefined) {
    const maxImg = Number(caps.maxReferenceImages ?? 9)
    if (props.referenceCount > maxImg) {
      return `参考图 ${props.referenceCount} 张，超出上限 ${maxImg} 张`
    }
  }
  if (props.promptLength !== undefined) {
    const maxPrompt = Number(caps.maxPromptChars ?? 5000)
    if (props.promptLength > maxPrompt) {
      return `提示词 ${props.promptLength} 字，超出上限 ${maxPrompt} 字`
    }
  }
  return ''
}

function autoAdaptHint(m: ModelCatalogItemOut): string {
  const caps = m.capabilities || {}
  const hints: string[] = []
  if (props.clipDuration !== undefined) {
    const minD = Number(caps.minDuration || 4)
    const maxD = Number(caps.maxDuration || 15)
    if (props.clipDuration < minD || props.clipDuration > maxD) {
      hints.push(`切换后时长自动适配至 ${minD}–${maxD}s`)
    }
  }
  if (props.projectRatio) {
    const ratios = Array.isArray(caps.ratios) ? caps.ratios.map(String) : []
    if (ratios.length > 0 && !ratios.includes(props.projectRatio)) {
      hints.push(`切换后比例自动适配至 ${ratios[0]}`)
    }
  }
  return hints.join('；')
}

function selectModel(m: ModelCatalogItemOut) {
  if (hardBlockReason(m)) return
  modelValue.value = m.id
  open.value = false
}
</script>

<template>
  <DialogRoot v-model:open="open">
    <DialogTrigger as-child :disabled="disabled">
      <button type="button" class="vmp-trigger" :disabled="disabled" :aria-label="placeholder">
        <Film :size="15" class="vmp-trigger-icon" aria-hidden="true" />
        <span class="vmp-trigger-name">{{ selectedModel?.displayName || placeholder }}</span>
        <ChevronDown :size="14" class="vmp-trigger-chevron" aria-hidden="true" />
      </button>
    </DialogTrigger>

    <DialogPortal>
      <DialogOverlay class="vmp-overlay" />
      <DialogContent class="vmp-modal" :aria-describedby="undefined">
        <header class="vmp-modal-header">
          <div class="vmp-modal-title-group">
            <span class="vmp-modal-icon" aria-hidden="true"><Sparkles :size="18" /></span>
            <div>
              <DialogTitle class="vmp-modal-title">选择视频模型</DialogTitle>
              <div class="vmp-modal-sub">
                <span>共 {{ models.length }} 款可用</span>
                <template v-if="clipDuration !== undefined">
                  <span>·</span>
                  <span>当前片段 {{ clipDuration }}s</span>
                </template>
                <template v-if="projectRatio">
                  <span>·</span>
                  <span>画幅 {{ projectRatio }}</span>
                </template>
              </div>
            </div>
          </div>

          <div class="vmp-modal-header-right">
            <div class="vmp-search">
              <Search :size="14" class="vmp-search-icon" aria-hidden="true" />
              <input
                v-model="keyword"
                type="search"
                class="vmp-search-input"
                placeholder="搜索模型名称或特点..."
              />
            </div>
            <DialogClose class="ui-icon-button" aria-label="关闭模型选择"><X :size="18" /></DialogClose>
          </div>
        </header>

        <div class="vmp-filter-bar">
          <div class="vmp-tabs" role="tablist" aria-label="模型系列">
            <button
              type="button"
              class="vmp-tab"
              :class="{ 'is-active': activeCategory === 'all' }"
              @click="activeCategory = 'all'"
            >
              <span>全部系列</span>
              <span class="vmp-tab-count">{{ models.length }}</span>
            </button>
            <button
              v-for="cat in categories"
              :key="cat.name"
              type="button"
              class="vmp-tab"
              :class="{ 'is-active': activeCategory === cat.name }"
              @click="activeCategory = cat.name"
            >
              <span>{{ cat.name }}</span>
              <span class="vmp-tab-count">{{ cat.count }}</span>
            </button>
          </div>

          <div class="vmp-billing-switch" role="group" aria-label="计费方式">
            <button
              v-for="opt in ([
                { value: 'all', label: '全部计费' },
                { value: 'call', label: '按条计费' },
                { value: 'second', label: '按秒计费' },
              ] as const)"
              :key="opt.value"
              type="button"
              class="vmp-billing-btn"
              :class="{ 'is-active': activeBilling === opt.value }"
              @click="activeBilling = opt.value"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>

        <div class="vmp-body">
          <div v-if="filteredModels.length === 0" class="vmp-empty">当前筛选条件下暂无可用模型</div>
          <div v-else class="vmp-grid">
            <button
              v-for="m in filteredModels"
              :key="m.id"
              type="button"
              class="vmp-card"
              :class="{
                'is-selected': m.id === modelValue,
                'is-disabled': !!hardBlockReason(m),
              }"
              :disabled="!!hardBlockReason(m)"
              @click="selectModel(m)"
            >
              <div class="vmp-card-head">
                <div class="vmp-card-identity">
                  <strong class="vmp-card-name">{{ m.displayName }}</strong>
                  <div class="vmp-card-badges">
                    <span v-if="m.category" class="vmp-cat-tag">{{ m.category }}</span>
                    <span v-if="m.isDefault" class="vmp-default-tag">15s 默认</span>
                    <span v-if="m.isDefaultLong" class="vmp-default-tag">30s 默认</span>
                    <span v-if="m.id === modelValue" class="vmp-selected-tag">
                      <Check :size="11" :stroke-width="2.6" />
                      <span>已选</span>
                    </span>
                  </div>
                </div>

                <div v-if="primaryPrice(m)" class="vmp-card-pricing">
                  <div class="vmp-price-main">
                    <span class="vmp-price-num">{{ formatNum(primaryPrice(m)!.creditPrice) }}</span>
                    <span class="vmp-price-unit">积分 / {{ primaryPrice(m)!.unit === 'call' ? '条' : '秒' }}</span>
                  </div>
                  <div class="vmp-price-meta">
                    <span
                      class="vmp-unit-pill"
                      :class="primaryPrice(m)!.unit === 'call' ? 'is-call' : 'is-second'"
                    >
                      {{ primaryPrice(m)!.unit === 'call' ? '按条一口价' : '按秒计费' }}
                    </span>
                    <span v-if="estimatedClipCost(m)" class="vmp-est-cost">{{ estimatedClipCost(m) }}</span>
                  </div>
                </div>
              </div>

              <p v-if="modelDescription(m)" class="vmp-card-desc">{{ modelDescription(m) }}</p>

              <div class="vmp-card-specs">
                <span class="vmp-spec-pill">
                  <Maximize2 :size="11" aria-hidden="true" />
                  <span>{{ modelResolutionsText(m) }}</span>
                </span>
                <span class="vmp-spec-pill">
                  <Clock3 :size="11" aria-hidden="true" />
                  <span>{{ modelDurationText(m) }}</span>
                </span>
                <span class="vmp-spec-pill">{{ modelRatiosText(m) }}</span>
                <span class="vmp-spec-pill">
                  <Layers :size="11" aria-hidden="true" />
                  <span>{{ modelMediaText(m) }}</span>
                </span>
              </div>

              <div v-if="hardBlockReason(m)" class="vmp-card-warn">
                {{ hardBlockReason(m) }}
              </div>
              <div v-else-if="autoAdaptHint(m)" class="vmp-card-hint">
                {{ autoAdaptHint(m) }}
              </div>
            </button>
          </div>
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.vmp-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  max-width: 100%;
  padding: 0 12px;
  border-radius: var(--radius-control);
  border: 1px solid var(--border-control);
  background: rgb(255 255 255 / 3.5%);
  color: var(--color-text);
  font-size: 13px;
  transition: border-color 0.15s, background 0.15s;
}

.vmp-trigger:hover:not(:disabled),
.vmp-trigger[data-state="open"] {
  border-color: rgb(240 184 75 / 55%);
  background: rgb(240 184 75 / 7%);
}

.vmp-trigger:disabled {
  opacity: 0.45;
}

.vmp-trigger-icon {
  color: var(--color-gold-soft);
  flex-shrink: 0;
}

.vmp-trigger-name {
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.vmp-trigger-chevron {
  color: var(--color-muted);
  flex-shrink: 0;
}
</style>

<style>
.vmp-overlay {
  position: fixed;
  inset: 0;
  z-index: 110;
  background: rgb(5 6 9 / 76%);
  backdrop-filter: blur(8px);
  animation: ui-fade-in 0.15s ease-out;
}

.vmp-modal {
  position: fixed;
  top: 50%;
  left: 50%;
  z-index: 111;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  width: min(980px, calc(100vw - 32px));
  max-height: min(760px, calc(100dvh - 48px));
  border-radius: 16px;
  border: 1px solid rgb(255 255 255 / 14%);
  background: #121318;
  box-shadow: 0 28px 90px rgb(0 0 0 / 68%);
  overflow: hidden;
  animation: ui-fade-in 0.15s ease-out;
}

.vmp-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 18px 24px;
  border-bottom: 1px solid var(--border-subtle);
  background: linear-gradient(180deg, rgb(255 255 255 / 3%), transparent);
}

.vmp-modal-title-group {
  display: flex;
  align-items: center;
  gap: 13px;
}

.vmp-modal-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 11px;
  border: 1px solid rgb(240 184 75 / 30%);
  background: linear-gradient(145deg, rgb(240 184 75 / 16%), rgb(240 184 75 / 5%));
  color: var(--color-gold-soft);
  flex-shrink: 0;
}

.vmp-modal-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #f4f4f6;
  line-height: 1.25;
}

.vmp-modal-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
  font-size: 12px;
  color: var(--color-muted);
  font-variant-numeric: tabular-nums;
}

.vmp-modal-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.vmp-search {
  position: relative;
  width: 230px;
}

.vmp-search-icon {
  position: absolute;
  left: 11px;
  top: 50%;
  transform: translateY(-50%);
  color: #747683;
  pointer-events: none;
}

.vmp-search-input {
  width: 100%;
  height: 36px;
  padding: 0 12px 0 33px;
  border-radius: 9px;
  border: 1px solid var(--border-control);
  background: rgb(255 255 255 / 3%);
  color: var(--color-text);
  font-size: 13px;
  transition: border-color 0.14s, box-shadow 0.14s;
}

.vmp-search-input::placeholder {
  color: #6f727d;
}

.vmp-search-input:focus {
  outline: none;
  border-color: rgb(240 184 75 / 60%);
  box-shadow: 0 0 0 3px var(--focus-ring);
}

.vmp-filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border-subtle);
  background: #0f1014;
}

.vmp-tabs {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.vmp-tab {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  padding: 0 14px;
  border-radius: 9px;
  border: 1px solid var(--border-subtle);
  background: rgb(255 255 255 / 2.5%);
  color: #a4a6b2;
  font-size: 13px;
  font-weight: 500;
  transition: background 0.14s, border-color 0.14s, color 0.14s;
}

.vmp-tab:hover {
  background: var(--surface-hover);
  border-color: var(--border-control);
  color: var(--color-text);
}

.vmp-tab.is-active {
  background: var(--gold-tint);
  border-color: rgb(240 184 75 / 45%);
  color: var(--color-gold-soft);
}

.vmp-tab-count {
  min-width: 20px;
  height: 18px;
  padding: 0 5px;
  border-radius: 99px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgb(255 255 255 / 7%);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: inherit;
}

.vmp-billing-switch {
  display: inline-flex;
  padding: 3px;
  border-radius: 9px;
  border: 1px solid var(--border-subtle);
  background: rgb(255 255 255 / 2.5%);
}

.vmp-billing-btn {
  height: 28px;
  padding: 0 12px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 500;
  transition: background 0.14s, color 0.14s;
}

.vmp-billing-btn:hover {
  color: var(--color-text);
}

.vmp-billing-btn.is-active {
  background: #28261f;
  color: var(--color-gold-soft);
  box-shadow: 0 1px 4px rgb(0 0 0 / 28%);
}

.vmp-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 18px 24px 24px;
}

.vmp-empty {
  padding: 56px 20px;
  text-align: center;
  color: var(--color-muted);
  font-size: 14px;
}

.vmp-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.vmp-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
  padding: 16px 18px;
  border-radius: 12px;
  border: 1px solid var(--border-subtle);
  background: linear-gradient(180deg, rgb(255 255 255 / 3%), rgb(255 255 255 / 1.5%));
  color: var(--color-text);
  text-align: left;
  transition: border-color 0.15s, background 0.15s, transform 0.15s, box-shadow 0.15s;
}

.vmp-card:hover:not(:disabled) {
  border-color: rgb(240 184 75 / 42%);
  background: linear-gradient(180deg, rgb(240 184 75 / 6%), rgb(255 255 255 / 2.5%));
  transform: translateY(-1px);
  box-shadow: 0 10px 26px rgb(0 0 0 / 28%);
}

.vmp-card.is-selected {
  border-color: rgb(240 184 75 / 72%);
  background: linear-gradient(180deg, rgb(240 184 75 / 13%), rgb(240 184 75 / 4%));
  box-shadow: 0 0 0 1px rgb(240 184 75 / 24%), 0 12px 30px rgb(0 0 0 / 32%);
}

.vmp-card.is-disabled {
  opacity: 0.44;
  cursor: not-allowed;
}

.vmp-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.vmp-card-identity {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.vmp-card-name {
  font-size: 15px;
  font-weight: 600;
  color: #f4f4f6;
  line-height: 1.3;
}

.vmp-card-badges {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.vmp-cat-tag {
  padding: 2px 7px;
  border-radius: 5px;
  background: rgb(143 185 233 / 11%);
  border: 1px solid rgb(143 185 233 / 24%);
  color: var(--color-info);
  font-size: 11px;
}

.vmp-default-tag {
  padding: 2px 7px;
  border-radius: 5px;
  background: var(--gold-tint);
  border: 1px solid rgb(240 184 75 / 32%);
  color: var(--color-gold-soft);
  font-size: 11px;
}

.vmp-selected-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 7px;
  border-radius: 5px;
  background: rgb(128 201 161 / 14%);
  border: 1px solid rgb(128 201 161 / 36%);
  color: var(--color-success);
  font-size: 11px;
  font-weight: 500;
}

.vmp-card-pricing {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 5px;
  flex-shrink: 0;
}

.vmp-price-main {
  display: inline-flex;
  align-items: baseline;
  gap: 3px;
}

.vmp-price-num {
  font-size: 19px;
  font-weight: 700;
  line-height: 1.1;
  color: var(--color-gold-soft);
  font-variant-numeric: tabular-nums;
}

.vmp-price-unit {
  font-size: 11px;
  color: var(--color-muted);
}

.vmp-price-meta {
  display: flex;
  align-items: center;
  gap: 6px;
}

.vmp-unit-pill {
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 500;
}

.vmp-unit-pill.is-call {
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  border: 1px solid rgb(240 184 75 / 28%);
}

.vmp-unit-pill.is-second {
  background: rgb(143 185 233 / 12%);
  color: var(--color-info);
  border: 1px solid rgb(143 185 233 / 28%);
}

.vmp-est-cost {
  font-size: 11px;
  color: #a9abb6;
  font-variant-numeric: tabular-nums;
}

.vmp-card-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: #afb1bc;
}

.vmp-card-specs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: auto;
  padding-top: 2px;
}

.vmp-spec-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 6px;
  border: 1px solid var(--border-subtle);
  background: rgb(255 255 255 / 3%);
  color: #9b9da8;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.vmp-card-warn {
  padding: 5px 9px;
  border-radius: 6px;
  background: rgb(239 146 146 / 10%);
  border: 1px solid rgb(239 146 146 / 28%);
  color: var(--color-error);
  font-size: 11px;
}

.vmp-card-hint {
  padding: 4px 8px;
  border-radius: 6px;
  background: rgb(240 184 75 / 8%);
  border: 1px solid rgb(240 184 75 / 22%);
  color: var(--color-gold-soft);
  font-size: 11px;
}

@media (max-width: 780px) {
  .vmp-modal {
    width: calc(100vw - 20px);
    max-height: calc(100dvh - 24px);
  }

  .vmp-modal-header,
  .vmp-filter-bar,
  .vmp-body {
    padding-inline: 16px;
  }

  .vmp-search {
    width: 170px;
  }

  .vmp-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
