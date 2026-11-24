<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Calendar, ChevronLeft, ChevronRight, X } from 'lucide-vue-next'
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from 'reka-ui'
import {
  buildCalendarMonthGrid,
  DEFAULT_DATE_RANGE_PRESETS,
  formatLocalDate,
  matchDateRangePreset,
  normalizeDateRange,
  parseLocalDate,
  type DateRangePresetOption,
  type DateRangeValue,
} from './date-range'

const props = withDefaults(
  defineProps<{
    presets?: readonly DateRangePresetOption[]
    inlinePresets?: boolean
    disableFuture?: boolean
    clearable?: boolean
    placeholder?: string
    size?: 'sm' | 'md'
  }>(),
  {
    presets: () => DEFAULT_DATE_RANGE_PRESETS,
    inlinePresets: false,
    disableFuture: true,
    clearable: true,
    placeholder: '全部时间',
    size: 'md',
  },
)

const model = defineModel<DateRangeValue>({
  default: () => ({ start: null, end: null }),
})

const emit = defineEmits<{
  change: [value: DateRangeValue]
}>()

const weekDays = ['一', '二', '三', '四', '五', '六', '日'] as const

const open = ref(false)
const anchorDate = ref<string | null>(null)
const hoverDate = ref<string | null>(null)

const initialAnchor = parseLocalDate(model.value.end ?? model.value.start) ?? new Date()
const viewYear = ref(initialAnchor.getFullYear())
const viewMonth = ref(initialAnchor.getMonth())

const activePresetId = computed(() => matchDateRangePreset(model.value, props.presets))
const hasValue = computed(() => Boolean(model.value.start || model.value.end))

const triggerText = computed(() => {
  const { start, end } = model.value
  if (!start && !end) return props.placeholder
  if (start && end) {
    return start === end ? start : `${start} 至 ${end}`
  }
  if (start) return `${start} 起`
  return `至 ${end}`
})

const monthLabel = computed(() => `${viewYear.value} 年 ${viewMonth.value + 1} 月`)

const calendarCells = computed(() => buildCalendarMonthGrid(viewYear.value, viewMonth.value))

const previewRange = computed<DateRangeValue>(() => {
  if (anchorDate.value) {
    if (hoverDate.value) {
      return normalizeDateRange(anchorDate.value, hoverDate.value)
    }
    return { start: anchorDate.value, end: anchorDate.value }
  }
  return model.value
})

const selectionHint = computed(() => {
  if (anchorDate.value) {
    return `${anchorDate.value} 至 请选择结束日期`
  }
  const { start, end } = model.value
  if (start && end) {
    return start === end ? `已选 ${start}` : `${start} 至 ${end}`
  }
  return '点击起止日期自定义范围'
})

watch(open, (isOpen) => {
  if (isOpen) {
    const focusDate = parseLocalDate(model.value.end ?? model.value.start) ?? new Date()
    viewYear.value = focusDate.getFullYear()
    viewMonth.value = focusDate.getMonth()
    anchorDate.value = null
    hoverDate.value = null
  } else {
    anchorDate.value = null
    hoverDate.value = null
  }
})

function commitRange(next: DateRangeValue) {
  model.value = next
  emit('change', next)
}

function applyPreset(preset: DateRangePresetOption) {
  commitRange(preset.resolve())
  open.value = false
}

function clearRange() {
  commitRange({ start: null, end: null })
  open.value = false
}

function shiftMonth(delta: number) {
  const shifted = new Date(viewYear.value, viewMonth.value + delta, 1)
  viewYear.value = shifted.getFullYear()
  viewMonth.value = shifted.getMonth()
}

function jumpToCurrentMonth() {
  const now = new Date()
  viewYear.value = now.getFullYear()
  viewMonth.value = now.getMonth()
}

function handleDayClick(iso: string, disabled: boolean) {
  if (disabled) return
  if (!anchorDate.value) {
    anchorDate.value = iso
    hoverDate.value = iso
    return
  }
  const normalized = normalizeDateRange(anchorDate.value, iso)
  anchorDate.value = null
  hoverDate.value = null
  commitRange(normalized)
  open.value = false
}

function isRangeEdge(iso: string): boolean {
  const { start, end } = previewRange.value
  return iso === start || iso === end
}

function isRangeStart(iso: string): boolean {
  const { start, end } = previewRange.value
  return Boolean(start && end && start !== end && iso === start)
}

function isRangeEnd(iso: string): boolean {
  const { start, end } = previewRange.value
  return Boolean(start && end && start !== end && iso === end)
}

function isInRange(iso: string): boolean {
  const { start, end } = previewRange.value
  if (!start || !end) return false
  return iso > start && iso < end
}

const isCurrentMonth = computed(() => {
  const now = new Date()
  return viewYear.value === now.getFullYear() && viewMonth.value === now.getMonth()
})

const canGoNextMonth = computed(() => {
  if (!props.disableFuture) return true
  const now = new Date()
  return viewYear.value < now.getFullYear()
    || (viewYear.value === now.getFullYear() && viewMonth.value < now.getMonth())
})

const todayIso = computed(() => formatLocalDate(new Date()))
</script>

<template>
  <div class="ui-date-range" :class="{ 'is-sm': size === 'sm' }">
    <div v-if="inlinePresets && presets.length" class="ui-date-presets" role="group" aria-label="快捷时间范围">
      <button
        v-for="preset in presets"
        :key="preset.id"
        type="button"
        class="ui-date-preset-btn"
        :class="{ 'is-active': activePresetId === preset.id }"
        :aria-pressed="activePresetId === preset.id"
        @click="applyPreset(preset)"
      >
        {{ preset.shortLabel || preset.label }}
      </button>
    </div>

    <PopoverRoot v-model:open="open">
      <PopoverTrigger as-child>
        <button
          type="button"
          class="ui-date-trigger"
          :class="{ 'is-open': open, 'has-value': hasValue }"
          aria-label="选择日期范围"
        >
          <Calendar :size="15" class="ui-date-trigger-icon" aria-hidden="true" />
          <span class="ui-date-trigger-text" :class="{ 'is-placeholder': !hasValue }">{{ triggerText }}</span>
          <span
            v-if="clearable && hasValue"
            role="button"
            tabindex="0"
            class="ui-date-clear"
            aria-label="清空日期范围"
            @click.stop.prevent="clearRange"
            @keydown.enter.stop.prevent="clearRange"
            @keydown.space.stop.prevent="clearRange"
          >
            <X :size="13" aria-hidden="true" />
          </span>
        </button>
      </PopoverTrigger>

      <PopoverPortal>
        <PopoverContent
          class="ui-popover ui-date-popover"
          align="start"
          :side-offset="6"
          :collision-padding="12"
        >
          <div class="ui-date-popover-body">
            <aside v-if="presets.length" class="ui-date-sidebar" aria-label="快捷范围">
              <button
                v-for="preset in presets"
                :key="preset.id"
                type="button"
                class="ui-date-side-btn"
                :class="{ 'is-active': activePresetId === preset.id }"
                @click="applyPreset(preset)"
              >
                {{ preset.label }}
              </button>
              <div class="ui-date-side-divider" aria-hidden="true" />
              <button
                type="button"
                class="ui-date-side-btn"
                :class="{ 'is-active': !hasValue }"
                @click="clearRange"
              >
                全部时间
              </button>
            </aside>

            <div class="ui-date-calendar">
              <div class="ui-date-cal-head">
                <button
                  type="button"
                  class="ui-date-nav-btn"
                  aria-label="上个月"
                  @click="shiftMonth(-1)"
                >
                  <ChevronLeft :size="15" aria-hidden="true" />
                </button>
                <div class="ui-date-cal-title">
                  <span>{{ monthLabel }}</span>
                  <button
                    v-if="!isCurrentMonth"
                    type="button"
                    class="ui-date-today-jump"
                    @click="jumpToCurrentMonth"
                  >
                    回到本月
                  </button>
                </div>
                <button
                  type="button"
                  class="ui-date-nav-btn"
                  :disabled="!canGoNextMonth"
                  aria-label="下个月"
                  @click="shiftMonth(1)"
                >
                  <ChevronRight :size="15" aria-hidden="true" />
                </button>
              </div>

              <div class="ui-date-weekdays" aria-hidden="true">
                <span v-for="wd in weekDays" :key="wd">{{ wd }}</span>
              </div>

              <div class="ui-date-grid" @mouseleave="hoverDate = null">
                <button
                  v-for="cell in calendarCells"
                  :key="cell.iso"
                  type="button"
                  class="ui-date-day"
                  :class="{
                    'is-outside': !cell.inMonth,
                    'is-today': cell.iso === todayIso,
                    'is-disabled': disableFuture && cell.isFuture,
                    'is-edge': isRangeEdge(cell.iso),
                    'is-range-start': isRangeStart(cell.iso),
                    'is-range-end': isRangeEnd(cell.iso),
                    'is-in-range': isInRange(cell.iso),
                  }"
                  :disabled="disableFuture && cell.isFuture"
                  :aria-label="cell.iso"
                  :aria-pressed="isRangeEdge(cell.iso)"
                  @click="handleDayClick(cell.iso, disableFuture && cell.isFuture)"
                  @mouseenter="anchorDate ? (hoverDate = cell.iso) : undefined"
                >
                  <span>{{ cell.day }}</span>
                </button>
              </div>

              <div class="ui-date-cal-foot">
                <span class="ui-date-cal-hint">{{ selectionHint }}</span>
                <button
                  v-if="hasValue"
                  type="button"
                  class="ui-date-foot-clear"
                  @click="clearRange"
                >
                  清空
                </button>
              </div>
            </div>
          </div>
        </PopoverContent>
      </PopoverPortal>
    </PopoverRoot>
  </div>
</template>

<style scoped>
.ui-date-range {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.ui-date-presets {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  height: var(--control-height-md);
  padding: 3px;
  border: 1px solid var(--border-control);
  border-radius: var(--radius-control);
  background: var(--color-surface);
}

.ui-date-range.is-sm .ui-date-presets {
  height: var(--control-height-sm);
  border-radius: var(--radius-control-sm);
}

.ui-date-preset-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 0 11px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: var(--color-muted);
  font-size: 13px;
  white-space: nowrap;
  cursor: pointer;
  transition: background 0.14s, border-color 0.14s, color 0.14s;
}

.ui-date-preset-btn:hover {
  background: var(--surface-hover);
  color: var(--color-text);
}

.ui-date-preset-btn.is-active {
  background: var(--gold-tint);
  border-color: rgb(240 184 75 / 40%);
  color: var(--color-gold-soft);
  font-weight: 500;
}

.ui-date-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 224px;
  height: var(--control-height-md);
  padding: 0 10px 0 12px;
  border: 1px solid var(--border-control);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.ui-date-range.is-sm .ui-date-trigger {
  min-width: 196px;
  height: var(--control-height-sm);
  padding: 0 8px 0 10px;
  border-radius: var(--radius-control-sm);
}

.ui-date-trigger:hover {
  border-color: rgb(255 255 255 / 24%);
}

.ui-date-trigger.is-open,
.ui-date-trigger:focus-visible {
  outline: none;
  border-color: rgb(240 184 75 / 55%);
}

.ui-date-trigger-icon {
  flex-shrink: 0;
  color: var(--color-muted);
}

.ui-date-trigger.has-value .ui-date-trigger-icon {
  color: var(--color-gold-soft);
}

.ui-date-trigger-text {
  flex: 1;
  min-width: 0;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ui-date-trigger-text.is-placeholder {
  color: #70727d;
}

.ui-date-clear {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  color: var(--color-muted);
  transition: background 0.14s, color 0.14s;
}

.ui-date-clear:hover {
  background: rgb(255 255 255 / 10%);
  color: var(--color-text);
}
</style>

<style>
.ui-date-popover {
  z-index: 68;
  padding: 0;
  overflow: hidden;
  border-radius: 10px;
  background: #15161c;
  border: 1px solid var(--border-control);
  box-shadow: 0 18px 48px rgb(0 0 0 / 56%);
}

body:has(.ui-dialog) .ui-date-popover {
  z-index: 76;
}

.ui-date-popover-body {
  display: flex;
  align-items: stretch;
}

.ui-date-sidebar {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 110px;
  padding: 10px 8px;
  border-right: 1px solid var(--border-subtle);
  background: rgb(255 255 255 / 1.8%);
}

.ui-date-side-btn {
  display: flex;
  align-items: center;
  height: 32px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--color-muted);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: background 0.14s, border-color 0.14s, color 0.14s;
}

.ui-date-side-btn:hover {
  background: var(--surface-hover);
  color: var(--color-text);
}

.ui-date-side-btn.is-active {
  background: var(--gold-tint);
  border-color: rgb(240 184 75 / 38%);
  color: var(--color-gold-soft);
  font-weight: 500;
}

.ui-date-side-divider {
  height: 1px;
  margin: 4px 2px;
  background: var(--border-subtle);
}

.ui-date-calendar {
  width: 280px;
  padding: 12px;
}

.ui-date-cal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.ui-date-cal-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
  font-variant-numeric: tabular-nums;
}

.ui-date-today-jump {
  padding: 2px 6px;
  border: 1px solid rgb(240 184 75 / 28%);
  border-radius: 4px;
  background: rgb(240 184 75 / 8%);
  color: var(--color-gold-soft);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
}

.ui-date-today-jump:hover {
  background: rgb(240 184 75 / 16%);
}

.ui-date-nav-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: rgb(255 255 255 / 2.5%);
  color: var(--color-muted);
  cursor: pointer;
  transition: background 0.14s, color 0.14s, border-color 0.14s;
}

.ui-date-nav-btn:hover:not(:disabled) {
  background: var(--surface-hover);
  color: var(--color-text);
  border-color: var(--border-control);
}

.ui-date-nav-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.ui-date-weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  margin-bottom: 6px;
  text-align: center;
  font-size: 11px;
  color: var(--color-muted);
}

.ui-date-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  row-gap: 3px;
}

.ui-date-day {
  position: relative;
  display: grid;
  place-items: center;
  height: 32px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}

.ui-date-day:hover:not(:disabled):not(.is-edge) {
  background: var(--surface-hover);
}

.ui-date-day.is-outside {
  color: #5d606c;
}

.ui-date-day.is-today:not(.is-edge) {
  color: var(--color-gold-soft);
  font-weight: 600;
}

.ui-date-day.is-today:not(.is-edge)::after {
  content: '';
  position: absolute;
  bottom: 3px;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--color-gold);
}

.ui-date-day.is-in-range {
  border-radius: 0;
  background: rgb(240 184 75 / 14%);
  color: var(--color-gold-soft);
}

.ui-date-day.is-edge {
  background: var(--color-gold);
  color: #121214;
  font-weight: 600;
}

.ui-date-day.is-range-start {
  border-radius: 6px 0 0 6px;
}

.ui-date-day.is-range-end {
  border-radius: 0 6px 6px 0;
}

.ui-date-day.is-disabled {
  opacity: 0.28;
  cursor: not-allowed;
}

.ui-date-cal-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 10px;
  padding-top: 9px;
  border-top: 1px solid var(--border-subtle);
  font-size: 11px;
  color: var(--color-muted);
  font-variant-numeric: tabular-nums;
}

.ui-date-cal-hint {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ui-date-foot-clear {
  flex-shrink: 0;
  border: 0;
  background: transparent;
  color: var(--color-gold-soft);
  font-size: 12px;
  cursor: pointer;
}

.ui-date-foot-clear:hover {
  text-decoration: underline;
}

@media (max-width: 480px) {
  .ui-date-popover-body {
    flex-direction: column;
  }

  .ui-date-sidebar {
    flex-direction: row;
    flex-wrap: wrap;
    width: auto;
    border-right: 0;
    border-bottom: 1px solid var(--border-subtle);
  }

  .ui-date-side-divider {
    display: none;
  }
}
</style>
