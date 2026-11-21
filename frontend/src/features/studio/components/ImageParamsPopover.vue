<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronDown, RotateCcw, SlidersHorizontal } from 'lucide-vue-next'
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from 'reka-ui'
import type { ModelCatalogItemOut } from '../api-types'

const ALL_TIERS = ['web', '1k', '2k', '4k'] as const
type ImageTier = (typeof ALL_TIERS)[number]

const TIER_META: Record<ImageTier, { label: string; spec: string }> = {
  web: { label: 'Web', spec: '极速试稿' },
  '1k': { label: '1K', spec: '1024px' },
  '2k': { label: '2K', spec: '2048px' },
  '4k': { label: '4K', spec: '2880px' },
}

const DEFAULT_RATIOS = ['16:9', '9:16', '1:1', '4:3', '3:4', '3:2', '2:3', '5:4', '4:5', '21:9', '9:21', 'auto']

const props = withDefaults(
  defineProps<{
    model?: ModelCatalogItemOut | null
    defaultRatio?: string
    mode?: 'single' | 'batch'
    disabled?: boolean
  }>(),
  {
    model: null,
    defaultRatio: '16:9',
    mode: 'single',
    disabled: false,
  },
)

const tier = defineModel<ImageTier>('tier', { default: '1k' })
const ratio = defineModel<string>('ratio', { default: '16:9' })
const ratioMode = defineModel<'auto' | 'override'>('ratioMode', { default: 'auto' })

const open = ref(false)

const tierOptions = computed<ImageTier[]>(() => {
  const raw = props.model?.capabilities?.tiers
  const valid = Array.isArray(raw)
    ? raw.map(String).filter((v): v is ImageTier => (ALL_TIERS as readonly string[]).includes(v))
    : []
  return valid.length ? valid : ['web', '1k', '2k', '4k']
})

const ratioOptions = computed<string[]>(() => {
  const raw = props.model?.capabilities?.ratios
  const valid = Array.isArray(raw) ? raw.map(String).filter(Boolean) : []
  return valid.length ? valid : DEFAULT_RATIOS
})

watch(
  [tierOptions, ratioOptions],
  ([tiers, ratios]) => {
    if (!tiers.includes(tier.value)) {
      tier.value = tiers.includes('1k') ? '1k' : (tiers[0] ?? '1k')
    }
    if (!ratios.includes(ratio.value)) {
      ratio.value = ratios.includes(props.defaultRatio) ? props.defaultRatio : (ratios[0] ?? '16:9')
    }
  },
  { immediate: true },
)

function tierPrice(t: ImageTier): string {
  const row = props.model?.imagePrices.find((p) => p.tier === t)
  if (!row) return ''
  const num = Number(row.creditPrice)
  return Number.isFinite(num) ? `${Number(num.toFixed(2))}分` : ''
}

const isCustomRatio = computed(() => props.mode === 'single' && ratio.value !== props.defaultRatio)

const summaryText = computed(() => {
  const tierLabel = TIER_META[tier.value]?.label ?? tier.value.toUpperCase()
  const ratioLabel = props.mode === 'batch' && ratioMode.value === 'auto'
    ? '默认比例'
    : (ratio.value === 'auto' ? '自动' : ratio.value)
  return `${tierLabel} · ${ratioLabel}`
})

function resetRatio() {
  if (ratioOptions.value.includes(props.defaultRatio)) {
    ratio.value = props.defaultRatio
  } else if (ratioOptions.value[0]) {
    ratio.value = ratioOptions.value[0]
  }
}
</script>

<template>
  <PopoverRoot v-model:open="open">
    <PopoverTrigger as-child :disabled="disabled">
      <button type="button" class="ip-trigger" :disabled="disabled" aria-label="图片生成参数">
        <SlidersHorizontal :size="13" class="ip-trigger-icon" aria-hidden="true" />
        <span class="ip-trigger-summary">{{ summaryText }}</span>
        <ChevronDown :size="13" class="ip-trigger-chevron" aria-hidden="true" />
      </button>
    </PopoverTrigger>

    <PopoverPortal>
      <PopoverContent
        class="ip-popover"
        side="top"
        align="end"
        :side-offset="8"
        :collision-padding="12"
      >
        <div class="ip-head">
          <strong>生图参数</strong>
          <button
            v-if="isCustomRatio && ratioOptions.includes(defaultRatio)"
            type="button"
            class="ip-reset-btn"
            @click="resetRatio"
          >
            <RotateCcw :size="11" aria-hidden="true" />
            <span>恢复默认 ({{ defaultRatio }})</span>
          </button>
        </div>

        <div class="ip-section">
          <div class="ip-label-row">
            <span class="ip-label">画质档位</span>
            <span class="ip-hint">默认推荐 1K</span>
          </div>
          <div class="ip-tier-grid">
            <button
              v-for="t in tierOptions"
              :key="t"
              type="button"
              class="ip-tier-chip"
              :class="{ 'is-active': tier === t }"
              @click="tier = t"
            >
              <strong>{{ TIER_META[t].label }}</strong>
              <span class="ip-tier-sub">{{ tierPrice(t) || TIER_META[t].spec }}</span>
            </button>
          </div>
        </div>

        <div class="ip-section">
          <div class="ip-label-row">
            <span class="ip-label">画面比例</span>
            <span v-if="mode === 'single'" class="ip-hint">默认 {{ defaultRatio }}</span>
            <span v-else class="ip-hint">角色/场景 16:9 · 物品 1:1</span>
          </div>

          <div v-if="mode === 'batch'" class="ip-mode-switch">
            <button
              type="button"
              class="ip-mode-btn"
              :class="{ 'is-active': ratioMode === 'auto' }"
              @click="ratioMode = 'auto'"
            >
              按资产默认比例
            </button>
            <button
              type="button"
              class="ip-mode-btn"
              :class="{ 'is-active': ratioMode === 'override' }"
              @click="ratioMode = 'override'"
            >
              统一指定比例
            </button>
          </div>

          <div v-if="mode === 'single' || ratioMode === 'override'" class="ip-ratio-grid">
            <button
              v-for="r in ratioOptions"
              :key="r"
              type="button"
              class="ip-ratio-chip"
              :class="{ 'is-active': ratio === r }"
              @click="ratio = r"
            >
              {{ r === 'auto' ? '自动' : r }}
            </button>
          </div>
        </div>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>

<style scoped>
.ip-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 11px;
  border-radius: 9px;
  border: 1px solid var(--border-control);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 12.5px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  cursor: pointer;
  transition: border-color 0.15s, background-color 0.15s;
}

.ip-trigger:hover:not(:disabled) {
  border-color: rgb(240 184 75 / 55%);
  background: rgb(255 255 255 / 4%);
}

.ip-trigger:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.ip-trigger-icon {
  color: var(--color-gold-soft);
  flex-shrink: 0;
}

.ip-trigger-summary {
  font-weight: 500;
}

.ip-trigger-chevron {
  color: var(--color-muted);
  flex-shrink: 0;
}
</style>

<style>
.ip-popover {
  z-index: 86;
  width: min(340px, calc(100vw - 24px));
  padding: 14px 16px 16px;
  border-radius: 14px;
  border: 1px solid rgb(255 255 255 / 14%);
  background: #13141a;
  box-shadow: 0 22px 60px rgb(0 0 0 / 65%);
  display: flex;
  flex-direction: column;
  gap: 14px;
  animation: ui-fade-in 0.12s ease-out;
}

.ip-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.ip-head strong {
  font-size: 13.5px;
  font-weight: 600;
  color: #f3f4f6;
}

.ip-reset-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 7px;
  border-radius: 6px;
  border: 1px solid rgb(240 184 75 / 30%);
  background: rgb(240 184 75 / 8%);
  color: var(--color-gold-soft);
  font-size: 11px;
  cursor: pointer;
}

.ip-reset-btn:hover {
  background: rgb(240 184 75 / 16%);
}

.ip-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ip-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.ip-label {
  font-size: 12px;
  font-weight: 500;
  color: #d4d6de;
}

.ip-hint {
  font-size: 11px;
  color: var(--color-muted);
  font-variant-numeric: tabular-nums;
}

.ip-tier-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
}

.ip-tier-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: 7px 4px;
  border-radius: 8px;
  border: 1px solid var(--border-control);
  background: rgb(255 255 255 / 2%);
  color: var(--color-muted);
  cursor: pointer;
  transition: border-color 0.15s, background-color 0.15s, color 0.15s;
}

.ip-tier-chip strong {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--color-text);
  line-height: 1.1;
}

.ip-tier-sub {
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.ip-tier-chip:hover {
  border-color: rgb(240 184 75 / 45%);
}

.ip-tier-chip.is-active {
  border-color: rgb(240 184 75 / 72%);
  background: var(--gold-tint);
  color: var(--color-gold-soft);
}

.ip-tier-chip.is-active strong {
  color: var(--color-gold-soft);
}

.ip-mode-switch {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px;
  padding: 3px;
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
  background: rgb(255 255 255 / 2.5%);
}

.ip-mode-btn {
  height: 28px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--color-muted);
  font-size: 12px;
  cursor: pointer;
  transition: background-color 0.15s, color 0.15s;
}

.ip-mode-btn.is-active {
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-weight: 600;
}

.ip-ratio-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
}

.ip-ratio-chip {
  height: 29px;
  border-radius: 7px;
  border: 1px solid var(--border-control);
  background: rgb(255 255 255 / 2%);
  color: var(--color-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  transition: border-color 0.15s, background-color 0.15s, color 0.15s;
}

.ip-ratio-chip:hover {
  border-color: rgb(240 184 75 / 45%);
  color: var(--color-text);
}

.ip-ratio-chip.is-active {
  border-color: rgb(240 184 75 / 72%);
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-weight: 600;
}
</style>
