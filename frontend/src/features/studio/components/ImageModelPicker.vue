<script setup lang="ts">
import { computed } from 'vue'
import { Check, ChevronDown, ImageIcon } from 'lucide-vue-next'
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from 'reka-ui'
import type { ModelCatalogItemOut } from '../api-types'

const props = withDefaults(
  defineProps<{
    models: ModelCatalogItemOut[]
    tier?: 'web' | '1k' | '2k' | '4k'
    disabled?: boolean
    placeholder?: string
    triggerDataPopup?: string
  }>(),
  {
    tier: '1k',
    disabled: false,
    placeholder: '选择图片模型',
    triggerDataPopup: undefined,
  },
)

const modelValue = defineModel<string>({ default: '' })
const open = defineModel<boolean>('open', { default: false })

const selectedModel = computed(
  () => props.models.find((m) => m.id === modelValue.value) ?? props.models[0] ?? null,
)

const groupedModels = computed(() => {
  const map = new Map<string, ModelCatalogItemOut[]>()
  for (const m of props.models) {
    const key = m.category || '图片模型'
    const bucket = map.get(key)
    if (bucket) bucket.push(m)
    else map.set(key, [m])
  }
  return [...map.entries()].map(([category, items]) => ({ category, items }))
})

function formatNum(val: string | number): string {
  const num = Number(val)
  if (!Number.isFinite(num)) return String(val)
  return Number(num.toFixed(2)).toString()
}

function tierPriceText(m: ModelCatalogItemOut): string {
  const row = m.imagePrices.find((p) => p.tier === props.tier) ?? m.imagePrices[0]
  if (!row) return ''
  return `${formatNum(row.creditPrice)}`
}

function modelDescription(m: ModelCatalogItemOut): string {
  const desc = m.capabilities?.description
  return typeof desc === 'string' ? desc.trim() : ''
}

function modelVariant(m: ModelCatalogItemOut): 'flare' | 'sunburst' | '' {
  const v = m.capabilities?.variant
  if (v === 'flare' || v === 'sunburst') return v
  if (m.id.includes('sunburst')) return 'sunburst'
  if (m.id.includes('flare')) return 'flare'
  return ''
}

function selectModel(m: ModelCatalogItemOut) {
  modelValue.value = m.id
  open.value = false
}
</script>

<template>
  <PopoverRoot v-model:open="open">
    <PopoverTrigger as-child :disabled="disabled">
      <button type="button" :data-canvas-popup="triggerDataPopup" class="imp-trigger" :disabled="disabled" :aria-label="placeholder">
        <ImageIcon :size="14" class="imp-trigger-icon" aria-hidden="true" />
        <span class="imp-trigger-name">{{ selectedModel?.displayName || placeholder }}</span>
        <ChevronDown :size="13" class="imp-trigger-chevron" aria-hidden="true" />
      </button>
    </PopoverTrigger>

    <PopoverPortal>
      <PopoverContent
        class="imp-popover"
        side="top"
        align="start"
        :side-offset="8"
        :collision-padding="12"
      >
        <div class="imp-head">
          <strong>选择图片模型</strong>
          <span class="imp-head-tier">当前按 {{ tier.toUpperCase() }} 档计价</span>
        </div>

        <div class="imp-groups">
          <div v-for="group in groupedModels" :key="group.category" class="imp-group">
            <div class="imp-group-label">{{ group.category }}</div>
            <div class="imp-list">
              <button
                v-for="m in group.items"
                :key="m.id"
                type="button"
                class="imp-card"
                :class="{ 'is-selected': m.id === modelValue }"
                @click="selectModel(m)"
              >
                <div class="imp-card-main">
                  <div class="imp-card-title-row">
                    <strong class="imp-card-name">{{ m.displayName }}</strong>
                    <span
                      v-if="modelVariant(m) === 'flare'"
                      class="imp-tag is-flare"
                    >
                      Flare
                    </span>
                    <span
                      v-else-if="modelVariant(m) === 'sunburst'"
                      class="imp-tag is-sunburst"
                    >
                      Sunburst
                    </span>
                    <span v-if="m.isDefault" class="imp-tag is-default">默认</span>
                    <span v-if="m.id === modelValue" class="imp-check" aria-hidden="true">
                      <Check :size="12" :stroke-width="2.6" />
                    </span>
                  </div>
                  <p v-if="modelDescription(m)" class="imp-card-desc">{{ modelDescription(m) }}</p>
                </div>

                <div v-if="tierPriceText(m)" class="imp-card-price">
                  <strong>{{ tierPriceText(m) }}</strong>
                  <span>积分/张</span>
                </div>
              </button>
            </div>
          </div>
        </div>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>

<style scoped>
.imp-trigger {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: var(--control-height-sm);
  max-width: 240px;
  padding: 0 10px 0 11px;
  border-radius: var(--radius-control-sm);
  border: 1px solid var(--border-control);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 13px;
  cursor: pointer;
  transition: border-color 0.15s, background-color 0.15s;
}

.imp-trigger:hover:not(:disabled) {
  border-color: rgb(240 184 75 / 55%);
  background: rgb(255 255 255 / 4%);
}

.imp-trigger:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.imp-trigger-icon {
  color: var(--color-gold-soft);
  flex-shrink: 0;
}

.imp-trigger-name {
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.imp-trigger-chevron {
  color: var(--color-muted);
  flex-shrink: 0;
}
</style>

<style>
.imp-popover {
  z-index: 110;
  width: min(470px, calc(100vw - 24px));
  max-height: min(520px, calc(100dvh - 80px));
  display: flex;
  flex-direction: column;
  border-radius: 14px;
  border: 1px solid rgb(255 255 255 / 14%);
  background: #13141a;
  box-shadow: 0 22px 64px rgb(0 0 0 / 68%);
  overflow: hidden;
  animation: ui-fade-in 0.12s ease-out;
}

.imp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 13px 16px;
  border-bottom: 1px solid var(--border-subtle);
  background: rgb(255 255 255 / 2%);
}

.imp-head strong {
  font-size: 14px;
  font-weight: 600;
  color: #f3f4f6;
}

.imp-head-tier {
  font-size: 11px;
  color: var(--color-muted);
  font-variant-numeric: tabular-nums;
}

.imp-groups {
  overflow-y: auto;
  padding: 12px 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.imp-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.imp-group-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-muted);
  letter-spacing: 0.03em;
  padding: 0 2px;
}

.imp-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.imp-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border-subtle);
  background: rgb(255 255 255 / 2%);
  color: var(--color-text);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, background-color 0.15s;
}

.imp-card:hover {
  border-color: rgb(240 184 75 / 45%);
  background: rgb(255 255 255 / 4%);
}

.imp-card.is-selected {
  border-color: rgb(240 184 75 / 68%);
  background: linear-gradient(180deg, rgb(240 184 75 / 10%), rgb(240 184 75 / 4%));
}

.imp-card-main {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
  flex: 1;
}

.imp-card-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.imp-card-name {
  font-size: 13px;
  font-weight: 600;
  color: #f4f4f6;
}

.imp-tag {
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  line-height: 1.5;
}

.imp-tag.is-flare {
  background: rgb(56 189 248 / 14%);
  color: #7dd3fc;
}

.imp-tag.is-sunburst {
  background: rgb(240 184 75 / 16%);
  color: var(--color-gold-soft);
}

.imp-tag.is-default {
  background: rgb(255 255 255 / 8%);
  color: var(--color-muted);
}

.imp-check {
  display: inline-flex;
  align-items: center;
  color: var(--color-gold);
}

.imp-card-desc {
  margin: 0;
  font-size: 11.5px;
  color: var(--color-muted);
  line-height: 1.45;
}

.imp-card-price {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

.imp-card-price strong {
  font-size: 16px;
  font-weight: 700;
  color: var(--color-gold-soft);
  line-height: 1.1;
}

.imp-card-price span {
  font-size: 10px;
  color: var(--color-muted);
}
</style>
