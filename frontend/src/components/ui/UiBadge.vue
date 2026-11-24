<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'

export type UiBadgeTone = 'neutral' | 'gold' | 'success' | 'danger' | 'info' | 'purple'

withDefaults(
  defineProps<{
    tone?: UiBadgeTone
    variant?: 'soft' | 'chip'
    pill?: boolean
    truncate?: boolean
    to?: RouteLocationRaw
    title?: string
  }>(),
  {
    tone: 'neutral',
    variant: 'soft',
    pill: false,
    truncate: false,
  },
)
</script>

<template>
  <RouterLink
    v-if="to"
    :to="to"
    :title="title"
    class="ui-badge ui-badge--link"
    :class="[
      `ui-badge--${variant}`,
      `ui-badge--${tone}`,
      { 'is-pill': pill, 'is-truncate': truncate },
    ]"
  >
    <slot name="leading" />
    <span class="ui-badge__label"><slot /></span>
  </RouterLink>
  <span
    v-else
    :title="title"
    class="ui-badge"
    :class="[
      `ui-badge--${variant}`,
      `ui-badge--${tone}`,
      { 'is-pill': pill, 'is-truncate': truncate },
    ]"
  >
    <slot name="leading" />
    <span class="ui-badge__label"><slot /></span>
  </span>
</template>

<style scoped>
.ui-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: var(--badge-height);
  padding: 0 7px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-badge);
  background: rgb(255 255 255 / 4%);
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  vertical-align: middle;
}

.ui-badge.is-pill {
  border-radius: 999px;
  padding: 0 8px;
}

.ui-badge.is-truncate {
  max-width: 136px;
}

.ui-badge.is-truncate .ui-badge__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ui-badge__label {
  display: inline-flex;
  align-items: center;
  min-width: 0;
}

.ui-badge--chip {
  font-weight: 400;
  background: rgb(255 255 255 / 3.5%);
}

.ui-badge--link {
  text-decoration: none;
  transition: border-color 0.14s ease, color 0.14s ease, background-color 0.14s ease;
}

.ui-badge--link:hover {
  border-color: rgb(240 184 75 / 42%);
  color: var(--color-gold-soft);
  background: rgb(240 184 75 / 8%);
}

.ui-badge--gold {
  border-color: rgb(240 184 75 / 34%);
  background: var(--gold-tint);
  color: var(--color-gold-soft);
}

.ui-badge--success {
  border-color: rgb(128 201 161 / 32%);
  background: rgb(128 201 161 / 11%);
  color: var(--color-success);
}

.ui-badge--danger {
  border-color: rgb(239 146 146 / 34%);
  background: rgb(239 146 146 / 11%);
  color: var(--color-error);
}

.ui-badge--info {
  border-color: rgb(143 185 233 / 32%);
  background: rgb(143 185 233 / 11%);
  color: var(--color-info);
}

.ui-badge--purple {
  border-color: rgb(184 161 232 / 34%);
  background: rgb(184 161 232 / 11%);
  color: #c4b5fd;
}
</style>
