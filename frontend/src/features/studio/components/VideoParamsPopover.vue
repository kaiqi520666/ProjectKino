<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronDown, RotateCcw, SlidersHorizontal } from 'lucide-vue-next'
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from 'reka-ui'
import type { ModelCatalogItemOut } from '../api-types'

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

const resolution = defineModel<'480p' | '720p' | '1080p'>('resolution', { default: '720p' })
const ratio = defineModel<string>('ratio', { default: '16:9' })
const duration = defineModel<number>('duration', { default: 10 })
const durationMode = defineModel<'keep' | 'override'>('durationMode', { default: 'keep' })

const emit = defineEmits<{
  durationCommit: [seconds: number]
}>()

const open = ref(false)

const resolutionOptions = computed<('480p' | '720p' | '1080p')[]>(() => {
  const raw = props.model?.capabilities?.resolutions
  const valid = Array.isArray(raw)
    ? raw.map(String).filter((v): v is '480p' | '720p' | '1080p' => v === '480p' || v === '720p' || v === '1080p')
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

const isCustomRatio = computed(() => ratio.value !== props.defaultRatio)

const summaryText = computed(() => {
  const durLabel = props.mode === 'batch' && durationMode.value === 'keep'
    ? '原时长'
    : `${duration.value}s`
  return `${resolution.value} · ${ratio.value} · ${durLabel}`
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
      <button type="button" class="vp-trigger" :disabled="disabled" aria-label="生成参数设置">
        <SlidersHorizontal :size="13" class="vp-trigger-icon" aria-hidden="true" />
        <span class="vp-trigger-summary">{{ summaryText }}</span>
        <ChevronDown :size="13" class="vp-trigger-chevron" aria-hidden="true" />
      </button>
    </PopoverTrigger>

    <PopoverPortal>
      <PopoverContent
        class="vp-popover"
        side="top"
        align="end"
        :side-offset="8"
        :collision-padding="12"
      >
        <div class="vp-head">
          <strong>生成参数</strong>
          <button
            v-if="isCustomRatio && ratioOptions.includes(defaultRatio)"
            type="button"
            class="vp-reset-btn"
            @click="resetRatio"
          >
            <RotateCcw :size="11" />
            <span>恢复项目比例</span>
          </button>
        </div>

        <div class="vp-section">
          <div class="vp-label-row">
            <span>分辨率</span>
            <small>{{ resolution }}</small>
          </div>
          <div class="vp-chips">
            <button
              v-for="res in resolutionOptions"
              :key="res"
              type="button"
              class="vp-chip"
              :class="{ 'is-active': resolution === res }"
              @click="resolution = res"
            >
              {{ res }}
            </button>
          </div>
        </div>

        <div class="vp-section">
          <div class="vp-label-row">
            <span>画面比例</span>
            <small>项目默认 {{ defaultRatio }}</small>
          </div>
          <div class="vp-chips">
            <button
              v-for="r in ratioOptions"
              :key="r"
              type="button"
              class="vp-chip"
              :class="{ 'is-active': ratio === r }"
              @click="ratio = r"
            >
              {{ r }}
            </button>
          </div>
        </div>

        <div class="vp-section">
          <div class="vp-label-row">
            <span>生成时长</span>
            <small v-if="mode === 'single' || durationMode === 'override'" class="vp-dur-readout">
              {{ duration }} 秒
            </small>
            <small v-else>保持各片段原时长</small>
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
  gap: 7px;
  min-height: 34px;
  padding: 0 11px;
  border-radius: var(--radius-control);
  border: 1px solid var(--border-control);
  background: rgb(255 255 255 / 3%);
  color: var(--color-text);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  transition: border-color 0.14s, background 0.14s;
}

.vp-trigger:hover:not(:disabled),
.vp-trigger[data-state="open"] {
  border-color: rgb(240 184 75 / 55%);
  background: rgb(240 184 75 / 6%);
}

.vp-trigger:disabled {
  opacity: 0.45;
}

.vp-trigger-icon {
  color: var(--color-gold-soft);
  flex-shrink: 0;
}

.vp-trigger-summary {
  color: #e2e3e9;
  font-weight: 500;
}

.vp-trigger-chevron {
  color: var(--color-muted);
  flex-shrink: 0;
}
</style>

<style>
.vp-popover {
  z-index: 86;
  width: min(328px, calc(100vw - 24px));
  padding: 14px 16px 16px;
  border-radius: 12px;
  border: 1px solid rgb(255 255 255 / 14%);
  background: #14151b;
  box-shadow: 0 20px 56px rgb(0 0 0 / 62%);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.vp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-subtle);
}

.vp-head strong {
  font-size: 13px;
  font-weight: 600;
  color: #f3f3f6;
}

.vp-reset-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 7px;
  border-radius: 5px;
  border: 1px solid var(--border-subtle);
  background: rgb(255 255 255 / 3%);
  color: var(--color-muted);
  font-size: 11px;
}

.vp-reset-btn:hover {
  color: var(--color-gold-soft);
  border-color: rgb(240 184 75 / 38%);
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
  font-size: 12px;
  color: #c3c5cf;
  font-weight: 500;
}

.vp-label-row small {
  font-size: 11px;
  font-weight: 400;
  color: var(--color-muted);
}

.vp-dur-readout {
  color: var(--color-gold-soft) !important;
  font-weight: 600 !important;
  font-variant-numeric: tabular-nums;
}

.vp-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.vp-chip {
  min-width: 52px;
  height: 30px;
  padding: 0 10px;
  border-radius: 7px;
  border: 1px solid var(--border-control);
  background: rgb(255 255 255 / 2.5%);
  color: var(--color-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  transition: background 0.12s, border-color 0.12s, color 0.12s;
}

.vp-chip:hover {
  background: var(--surface-hover);
  color: var(--color-text);
}

.vp-chip.is-active {
  background: var(--gold-tint);
  border-color: rgb(240 184 75 / 50%);
  color: var(--color-gold-soft);
  font-weight: 500;
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
  font-weight: 500;
}

.vp-mode-btn.is-active {
  background: #28261f;
  color: var(--color-gold-soft);
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
