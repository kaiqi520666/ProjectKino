<script setup lang="ts">
import { computed, watch } from 'vue'
import { ChevronDown, RotateCcw, SlidersHorizontal } from 'lucide-vue-next'
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from 'reka-ui'
import type { ModelCatalogItemOut } from '../api-types'

type VideoResolution = '480p' | '720p' | '1080p'

const RESOLUTION_SPEC: Record<VideoResolution, string> = {
  '480p': '流畅试稿',
  '720p': '标准高清',
  '1080p': '全高清',
}

const props = withDefaults(
  defineProps<{
    model?: ModelCatalogItemOut | null
    defaultRatio?: string
    mode?: 'single' | 'batch'
    disabled?: boolean
    align?: 'start' | 'center' | 'end'
    showDefaultRatioHint?: boolean
    triggerDataPopup?: string
  }>(),
  {
    model: null,
    defaultRatio: '16:9',
    mode: 'single',
    disabled: false,
    align: 'end',
    showDefaultRatioHint: true,
    triggerDataPopup: undefined,
  },
)

const resolution = defineModel<VideoResolution>('resolution', { default: '720p' })
const ratio = defineModel<string>('ratio', { default: '16:9' })
const duration = defineModel<number>('duration', { default: 10 })
const durationMode = defineModel<'keep' | 'override'>('durationMode', { default: 'keep' })
const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{
  durationCommit: [seconds: number]
}>()

const resolutionOptions = computed<VideoResolution[]>(() => {
  const raw = props.model?.capabilities?.resolutions
  const valid = Array.isArray(raw)
    ? raw
      .map((item) => String(item).trim().toLowerCase())
      .filter((v): v is VideoResolution => v === '480p' || v === '720p' || v === '1080p')
    : []
  return valid.length ? valid : ['720p']
})

const ratioOptions = computed<string[]>(() => {
  const raw = props.model?.capabilities?.ratios
  const valid = Array.isArray(raw) ? raw.map(String).filter(Boolean) : []
  return valid.length ? valid : ['16:9', '9:16', '1:1', '4:3', '3:4', '21:9']
})

const minDuration = computed(() => Math.max(1, Number(props.model?.capabilities?.minDuration || 4)))
const maxDuration = computed(() => Math.max(minDuration.value, Number(props.model?.capabilities?.maxDuration || 15)))

// 模型切换时自动吸附参数至合法范围
watch(
  [resolutionOptions, ratioOptions, minDuration, maxDuration],
  ([resList, ratioList, minD, maxD]) => {
    if (!resList.includes(resolution.value) && resList[0]) {
      resolution.value = resList[0]
    }
    if (!ratioList.includes(ratio.value)) {
      ratio.value = ratioList.includes(props.defaultRatio) ? props.defaultRatio : (ratioList[0] ?? '16:9')
    }
    if (duration.value < minD) {
      duration.value = minD
    } else if (duration.value > maxD) {
      duration.value = maxD
    }
  },
  { immediate: true },
)

function resolutionPrice(res: VideoResolution): string {
  const prices = props.model?.videoPrices ?? []
  const row =
    prices.find((p) => p.ruleKey.toLowerCase() === res)
    ?? prices.find((p) => p.ruleKey === 'default')
    ?? prices[0]
  if (!row) return ''
  const num = Number(row.creditPrice)
  if (!Number.isFinite(num)) return ''
  const formatted = Number(num.toFixed(2)).toString()
  return row.unit === 'call' ? `${formatted}分/条` : `${formatted}分/秒`
}

const isCustomRatio = computed(() => ratio.value !== props.defaultRatio)

const summaryText = computed(() => {
  const ratioLabel = ratio.value === 'auto' ? '自动' : ratio.value
  const durLabel = props.mode === 'batch' && durationMode.value === 'keep'
    ? '原时长'
    : `${duration.value}s`
  return `${resolution.value.toUpperCase()} · ${ratioLabel} · ${durLabel}`
})

function onRangeInput(event: Event) {
  const value = Number((event.target as HTMLInputElement).value)
  if (Number.isFinite(value)) {
    duration.value = Math.min(Math.max(Math.round(value), minDuration.value), maxDuration.value)
  }
}

function onRangeChange() {
  emit('durationCommit', duration.value)
}

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
      <button type="button" :data-canvas-popup="triggerDataPopup" class="vp-trigger" :disabled="disabled" aria-label="视频生成参数">
        <SlidersHorizontal :size="13" class="vp-trigger-icon" aria-hidden="true" />
        <span class="vp-trigger-summary">{{ summaryText }}</span>
        <ChevronDown :size="13" class="vp-trigger-chevron" aria-hidden="true" />
      </button>
    </PopoverTrigger>

    <PopoverPortal>
      <PopoverContent
        class="vp-popover"
        side="top"
        :align="align"
        :side-offset="8"
        :collision-padding="12"
      >
        <div class="vp-head">
          <strong>视频参数</strong>
          <button
            v-if="showDefaultRatioHint && isCustomRatio && ratioOptions.includes(defaultRatio)"
            type="button"
            class="vp-reset-btn"
            @click="resetRatio"
          >
            <RotateCcw :size="11" aria-hidden="true" />
            <span>恢复默认 ({{ defaultRatio }})</span>
          </button>
        </div>

        <div class="vp-section">
          <div class="vp-label-row">
            <span class="vp-label">分辨率</span>
            <span class="vp-hint">{{ resolution.toUpperCase() }}</span>
          </div>
          <div class="vp-res-grid">
            <button
              v-for="res in resolutionOptions"
              :key="res"
              type="button"
              class="vp-res-chip"
              :class="{ 'is-active': resolution === res }"
              @click="resolution = res"
            >
              <strong>{{ res.toUpperCase() }}</strong>
              <span class="vp-res-sub">{{ resolutionPrice(res) || RESOLUTION_SPEC[res] }}</span>
            </button>
          </div>
        </div>

        <div class="vp-section">
          <div class="vp-label-row">
            <span class="vp-label">画面比例</span>
            <span v-if="showDefaultRatioHint" class="vp-hint">默认 {{ defaultRatio }}</span>
          </div>
          <div class="vp-ratio-grid">
            <button
              v-for="r in ratioOptions"
              :key="r"
              type="button"
              class="vp-ratio-chip"
              :class="{ 'is-active': ratio === r }"
              @click="ratio = r"
            >
              {{ r === 'auto' ? '自动' : r }}
            </button>
          </div>
        </div>

        <div class="vp-section">
          <div class="vp-label-row">
            <span class="vp-label">生成时长</span>
            <span v-if="mode === 'single' || durationMode === 'override'" class="vp-dur-readout">
              {{ duration }} 秒
            </span>
            <span v-else class="vp-hint">保持各片段原时长</span>
          </div>

          <div v-if="mode === 'batch'" class="vp-mode-switch">
            <button
              type="button"
              class="vp-mode-btn"
              :class="{ 'is-active': durationMode === 'keep' }"
              @click="durationMode = 'keep'"
            >
              保持各片段原时长
            </button>
            <button
              type="button"
              class="vp-mode-btn"
              :class="{ 'is-active': durationMode === 'override' }"
              @click="durationMode = 'override'"
            >
              统一指定时长
            </button>
          </div>

          <div v-if="mode === 'single' || durationMode === 'override'" class="vp-slider-box">
            <input
              type="range"
              class="ui-range"
              :min="minDuration"
              :max="maxDuration"
              step="1"
              :value="duration"
              @input="onRangeInput"
              @change="onRangeChange"
            />
            <div class="vp-slider-ticks">
              <span>{{ minDuration }}s</span>
              <span>{{ maxDuration }}s</span>
            </div>
          </div>
        </div>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>

<style scoped>
.vp-trigger {
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

.vp-trigger:hover:not(:disabled),
.vp-trigger[data-state="open"] {
  border-color: rgb(240 184 75 / 55%);
  background: rgb(255 255 255 / 4%);
}

.vp-trigger:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.vp-trigger-icon {
  color: var(--color-gold-soft);
  flex-shrink: 0;
}

.vp-trigger-summary {
  font-weight: 500;
}

.vp-trigger-chevron {
  color: var(--color-muted);
  flex-shrink: 0;
}
</style>

<style>
.vp-popover {
  z-index: 110;
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

.vp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.vp-head strong {
  font-size: 13.5px;
  font-weight: 600;
  color: #f3f4f6;
}

.vp-reset-btn {
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

.vp-reset-btn:hover {
  background: rgb(240 184 75 / 16%);
}

.vp-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.vp-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.vp-label {
  font-size: 12px;
  font-weight: 500;
  color: #d4d6de;
}

.vp-hint {
  font-size: 11px;
  color: var(--color-muted);
  font-variant-numeric: tabular-nums;
}

.vp-dur-readout {
  font-size: 12px;
  color: var(--color-gold-soft);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.vp-res-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(72px, 1fr));
  gap: 6px;
}

.vp-res-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: 7px 6px;
  border-radius: 8px;
  border: 1px solid var(--border-control);
  background: rgb(255 255 255 / 2%);
  color: var(--color-muted);
  cursor: pointer;
  transition: border-color 0.15s, background-color 0.15s, color 0.15s;
}

.vp-res-chip strong {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--color-text);
  line-height: 1.1;
}

.vp-res-sub {
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.vp-res-chip:hover {
  border-color: rgb(240 184 75 / 45%);
}

.vp-res-chip.is-active {
  border-color: rgb(240 184 75 / 72%);
  background: var(--gold-tint);
  color: var(--color-gold-soft);
}

.vp-res-chip.is-active strong {
  color: var(--color-gold-soft);
}

.vp-ratio-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
}

.vp-ratio-chip {
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

.vp-ratio-chip:hover {
  border-color: rgb(240 184 75 / 45%);
  color: var(--color-text);
}

.vp-ratio-chip.is-active {
  border-color: rgb(240 184 75 / 72%);
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-weight: 600;
}

.vp-mode-switch {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px;
  padding: 3px;
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
  background: rgb(255 255 255 / 2.5%);
}

.vp-mode-btn {
  height: 28px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--color-muted);
  font-size: 12px;
  cursor: pointer;
  transition: background-color 0.15s, color 0.15s;
}

.vp-mode-btn.is-active {
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-weight: 600;
}

.vp-slider-box {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 2px;
}

.vp-slider-ticks {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #767884;
  font-variant-numeric: tabular-nums;
}
</style>
