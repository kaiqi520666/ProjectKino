<script setup lang="ts">
defineProps<{
  eyebrow?: string
  title: string
  titleId?: string
  badge?: string | number
}>()
</script>

<template>
  <header class="ws-page-header">
    <div class="ws-page-header-main">
      <span v-if="$slots.icon" class="ws-page-header-icon" aria-hidden="true">
        <slot name="icon" />
      </span>
      <div class="ws-page-header-copy">
        <div class="ws-page-header-title-row">
          <h1 :id="titleId" class="ws-page-header-title">{{ title }}</h1>
          <span v-if="badge !== undefined && badge !== ''" class="ws-page-header-badge">
            {{ badge }}
          </span>
        </div>
      </div>
    </div>
    <div v-if="$slots.actions" class="ws-page-header-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.ws-page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-subtle);
}

.ws-page-header-main {
  display: flex;
  align-items: center;
  gap: 13px;
  min-width: 0;
}

.ws-page-header-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border-radius: 9px;
  border: 1px solid rgb(240 184 75 / 24%);
  background: linear-gradient(145deg, rgb(240 184 75 / 14%), rgb(240 184 75 / 4%));
  color: var(--color-gold-soft);
}

.ws-page-header-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.ws-page-header-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.ws-page-header-title {
  margin: 0;
  font-size: 21px;
  font-weight: 600;
  line-height: 1.25;
  color: #f4f4f6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-page-header-badge {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 99px;
  border: 1px solid var(--border-control);
  background: rgb(255 255 255 / 4%);
  color: var(--color-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.ws-page-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

@media (max-width: 640px) {
  .ws-page-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 12px;
    padding-bottom: 14px;
  }

  .ws-page-header-actions {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
