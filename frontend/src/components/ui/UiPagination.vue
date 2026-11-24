<script setup lang="ts">
import { computed, watch } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { buildPageItems, computePagination } from './data-table-pagination'

const props = withDefaults(defineProps<{
  total: number
  pageSizeOptions?: readonly number[]
  itemLabel?: string
}>(), {
  pageSizeOptions: () => [],
  itemLabel: '条',
})

const page = defineModel<number>('page', { default: 1 })
const pageSize = defineModel<number>('pageSize', { default: 8 })

const metrics = computed(() =>
  computePagination(props.total, page.value, pageSize.value, Math.min(pageSize.value, props.total)),
)

const pageItems = computed(() => buildPageItems(metrics.value.currentPage, metrics.value.totalPages))

watch(
  () => [props.total, pageSize.value] as const,
  () => {
    const totalPages = Math.max(1, Math.ceil(Math.max(0, props.total) / Math.max(1, pageSize.value)))
    if (page.value > totalPages) {
      page.value = totalPages
    } else if (page.value < 1) {
      page.value = 1
    }
  },
)

function goTo(target: number) {
  const clamped = Math.min(Math.max(1, target), metrics.value.totalPages)
  if (clamped !== page.value) {
    page.value = clamped
  }
}

function selectPageSize(size: number) {
  if (size === pageSize.value) return
  pageSize.value = size
  page.value = 1
}
</script>

<template>
  <nav v-if="total > 0" class="ui-pagination" aria-label="分页导航">
    <div class="ui-pagination-info">
      <span>共 <strong>{{ total }}</strong> {{ itemLabel }}</span>
      <div v-if="pageSizeOptions.length > 1" class="ui-pagination-sizes" role="group" aria-label="每页数量">
        <button
          v-for="size in pageSizeOptions"
          :key="size"
          type="button"
          class="ui-pagination-size-btn"
          :class="{ 'is-active': pageSize === size }"
          @click="selectPageSize(size)"
        >
          {{ size }}/页
        </button>
      </div>
    </div>

    <div v-if="metrics.totalPages > 1" class="ui-pagination-controls">
      <button
        type="button"
        class="ui-pagination-btn"
        :disabled="metrics.currentPage <= 1"
        aria-label="上一页"
        @click="goTo(metrics.currentPage - 1)"
      >
        <ChevronLeft :size="14" aria-hidden="true" />
      </button>

      <template v-for="item in pageItems" :key="item.type === 'page' ? `p-${item.page}` : item.key">
        <span v-if="item.type === 'ellipsis'" class="ui-pagination-ellipsis">…</span>
        <button
          v-else
          type="button"
          class="ui-pagination-btn"
          :class="{ 'is-active': item.page === metrics.currentPage }"
          :aria-current="item.page === metrics.currentPage ? 'page' : undefined"
          @click="goTo(item.page)"
        >
          {{ item.page }}
        </button>
      </template>

      <button
        type="button"
        class="ui-pagination-btn"
        :disabled="metrics.currentPage >= metrics.totalPages"
        aria-label="下一页"
        @click="goTo(metrics.currentPage + 1)"
      >
        <ChevronRight :size="14" aria-hidden="true" />
      </button>
    </div>
  </nav>
</template>

<style scoped>
.ui-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 20px;
  padding-top: 14px;
  border-top: 1px solid var(--border-subtle);
}

.ui-pagination-info {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  font-size: 12.5px;
  color: var(--color-muted);
}

.ui-pagination-info strong {
  color: var(--color-text);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.ui-pagination-sizes {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px;
  border-radius: 7px;
  border: 1px solid var(--border-subtle);
  background: rgb(255 255 255 / 2%);
}

.ui-pagination-size-btn {
  height: 24px;
  padding: 0 8px;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: var(--color-muted);
  font-size: 11.5px;
  cursor: pointer;
  transition: background-color 0.14s ease, color 0.14s ease;
}

.ui-pagination-size-btn:hover {
  color: var(--color-text);
}

.ui-pagination-size-btn.is-active {
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-weight: 500;
}

.ui-pagination-controls {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.ui-pagination-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 30px;
  height: 30px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: var(--color-surface);
  color: var(--color-muted);
  font-size: 12.5px;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  transition: border-color 0.14s ease, background-color 0.14s ease, color 0.14s ease;
}

.ui-pagination-btn:hover:not(:disabled) {
  border-color: rgb(240 184 75 / 42%);
  color: var(--color-text);
  background: var(--surface-hover);
}

.ui-pagination-btn.is-active {
  border-color: rgb(240 184 75 / 55%);
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-weight: 600;
}

.ui-pagination-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.ui-pagination-ellipsis {
  padding: 0 4px;
  color: var(--color-muted);
  font-size: 12px;
}
</style>
