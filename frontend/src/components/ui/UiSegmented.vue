<script setup lang="ts">
import type { Component } from 'vue'

export interface UiSegmentedOption {
  value: string
  label: string
  icon?: Component
  count?: number
  disabled?: boolean
}

const props = withDefaults(
  defineProps<{
    options: readonly UiSegmentedOption[]
    size?: 'xs' | 'sm'
    variant?: 'box' | 'pills'
    ariaLabel?: string
  }>(),
  {
    size: 'sm',
    variant: 'box',
    ariaLabel: '切换选项',
  },
)

const model = defineModel<string>({ required: true })
const emit = defineEmits<{ change: [value: string] }>()

function select(option: UiSegmentedOption) {
  if (option.disabled || model.value === option.value) return
  model.value = option.value
  emit('change', option.value)
}
</script>

<template>
  <div
    class="ui-segmented"
    :class="[`ui-segmented--${variant}`, `ui-segmented--${size}`]"
    role="group"
    :aria-label="props.ariaLabel"
  >
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      class="ui-segmented-btn"
      :class="{ 'is-active': model === opt.value }"
      :aria-pressed="model === opt.value"
      :disabled="opt.disabled"
      @click="select(opt)"
    >
      <component :is="opt.icon" v-if="opt.icon" :size="size === 'xs' ? 12 : 13" aria-hidden="true" />
      <span>{{ opt.label }}</span>
      <span v-if="opt.count !== undefined" class="ui-segmented-count">{{ opt.count }}</span>
    </button>
  </div>
</template>

<style scoped>
.ui-segmented {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}

.ui-segmented--box {
  height: var(--control-height-sm);
  padding: 3px;
  gap: 2px;
  border: 1px solid var(--border-control);
  border-radius: var(--radius-control-sm);
  background: var(--color-canvas);
}

.ui-segmented--box.ui-segmented--xs {
  height: var(--control-height-xs);
  padding: 2px;
  border-radius: var(--radius-control-xs);
}

.ui-segmented--box .ui-segmented-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  height: 100%;
  padding: 0 11px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--color-muted);
  font-size: 13px;
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 0.14s ease, color 0.14s ease;
}

.ui-segmented--box.ui-segmented--xs .ui-segmented-btn {
  padding: 0 9px;
  gap: 4px;
  border-radius: 4px;
  font-size: 12px;
}

.ui-segmented--box .ui-segmented-btn:hover:not(:disabled) {
  color: var(--color-text);
}

.ui-segmented--box .ui-segmented-btn.is-active {
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-weight: 600;
}

.ui-segmented--pills {
  gap: 6px;
  flex-wrap: wrap;
}

.ui-segmented--pills .ui-segmented-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: var(--control-height-sm);
  padding: 0 12px;
  border: 1px solid var(--border-control);
  border-radius: var(--radius-control-sm);
  background: rgb(255 255 255 / 2.5%);
  color: var(--color-muted);
  font-size: 13px;
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 0.14s ease, border-color 0.14s ease, color 0.14s ease;
}

.ui-segmented--pills.ui-segmented--xs .ui-segmented-btn {
  height: var(--control-height-xs);
  padding: 0 9px;
  gap: 4px;
  border-radius: var(--radius-control-xs);
  font-size: 12px;
}

.ui-segmented--pills .ui-segmented-btn:hover:not(:disabled) {
  background: var(--surface-hover);
  color: var(--color-text);
}

.ui-segmented--pills .ui-segmented-btn.is-active {
  background: var(--gold-tint);
  border-color: rgb(240 184 75 / 45%);
  color: var(--color-gold-soft);
}

.ui-segmented-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.ui-segmented-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 18px;
  padding: 0 6px;
  border-radius: 999px;
  background: rgb(240 184 75 / 18%);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
</style>
