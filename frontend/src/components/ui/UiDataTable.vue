<script setup lang="ts" generic="T extends object">
import { computed, ref } from 'vue'
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, GripVertical } from 'lucide-vue-next'
import UiSelect from '@/components/ui/UiSelect.vue'
import { buildPageItems, computePagination } from './data-table-pagination'

export interface DataTableColumn {
  key: string
  label: string
  width?: string
  align?: 'left' | 'center' | 'right'
  headerClass?: string
  cellClass?: string
}

const props = withDefaults(defineProps<{
  columns: readonly DataTableColumn[]
  rows: readonly T[]
  rowKey: keyof T | ((row: T, index: number) => string | number)
  loading?: boolean
  loadingText?: string
  emptyText?: string
  paginated?: boolean
  total?: number
  pageSizeOptions?: readonly number[]
  compact?: boolean
  draggable?: boolean
  dragDisabled?: boolean
}>(), {
  loading: false,
  loadingText: '加载中...',
  emptyText: '暂无数据',
  paginated: false,
  total: 0,
  pageSizeOptions: () => [20, 30, 50, 100],
  compact: false,
  draggable: false,
  dragDisabled: false,
})

const page = defineModel<number>('page', { default: 1 })
const pageSize = defineModel<number>('pageSize', { default: 30 })

const emit = defineEmits<{
  change: [payload: { page: number; pageSize: number; offset: number }]
  reorder: [payload: { fromIndex: number; toIndex: number }]
}>()

const dragFromIndex = ref<number | null>(null)
const dragOverIndex = ref<number | null>(null)

const canDrag = computed(() => props.draggable && !props.dragDisabled && props.rows.length > 1)

const metrics = computed(() =>
  computePagination(props.total, page.value, pageSize.value, props.rows.length),
)

const pageItems = computed(() =>
  buildPageItems(metrics.value.currentPage, metrics.value.totalPages),
)

const sizeSelectOptions = computed(() =>
  props.pageSizeOptions.map((n) => ({ value: String(n), label: `${n} 条/页` })),
)

const pageSizeModel = computed({
  get: () => String(pageSize.value),
  set: (val: string) => {
    const nextSize = Number.parseInt(val, 10)
    if (!Number.isFinite(nextSize) || nextSize <= 0 || nextSize === pageSize.value) return
    pageSize.value = nextSize
    page.value = 1
    emit('change', { page: 1, pageSize: nextSize, offset: 0 })
  },
})

function resolveRowKey(row: T, index: number): string | number {
  if (typeof props.rowKey === 'function') return props.rowKey(row, index)
  const val = (row as Record<string, unknown>)[String(props.rowKey)]
  return typeof val === 'string' || typeof val === 'number' ? val : index
}

function readCell(row: T, key: string): unknown {
  return (row as Record<string, unknown>)[key]
}

function goToPage(nextPage: number) {
  const clamped = Math.min(Math.max(1, nextPage), metrics.value.totalPages)
  if (clamped === metrics.value.currentPage) return
  page.value = clamped
  emit('change', {
    page: clamped,
    pageSize: pageSize.value,
    offset: (clamped - 1) * pageSize.value,
  })
}

function onDragStart(index: number, event: DragEvent) {
  if (!canDrag.value) {
    event.preventDefault()
    return
  }
  dragFromIndex.value = index
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(index))
  }
}

function onDragOver(index: number, event: DragEvent) {
  if (dragFromIndex.value === null) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
  dragOverIndex.value = index
}

function onDrop(index: number, event: DragEvent) {
  event.preventDefault()
  const from = dragFromIndex.value
  dragFromIndex.value = null
  dragOverIndex.value = null
  if (from !== null && from !== index) {
    emit('reorder', { fromIndex: from, toIndex: index })
  }
}

function onDragEnd() {
  dragFromIndex.value = null
  dragOverIndex.value = null
}

function moveStep(index: number, delta: -1 | 1) {
  const target = index + delta
  if (!canDrag.value || target < 0 || target >= props.rows.length) return
  emit('reorder', { fromIndex: index, toIndex: target })
}
</script>

<template>
  <div class="ui-dt" :class="{ 'ui-dt--compact': compact }">
    <div class="ui-dt-surface">
      <div v-if="loading && rows.length === 0" class="ui-dt-state">{{ loadingText }}</div>
      <div v-else-if="rows.length === 0" class="ui-dt-state">{{ emptyText }}</div>
      <div v-else class="ui-dt-scroll">
        <table class="ui-dt-table" :class="{ 'is-loading': loading }">
          <thead>
            <tr>
              <th v-if="draggable" class="ui-dt-drag-col">排序</th>
              <th
                v-for="col in columns"
                :key="col.key"
                :style="{ width: col.width, textAlign: col.align || 'left' }"
                :class="col.headerClass"
              >
                {{ col.label }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, rowIndex) in rows"
              :key="resolveRowKey(row, rowIndex)"
              :draggable="canDrag"
              :class="{
                'is-draggable': canDrag,
                'is-dragging': dragFromIndex === rowIndex,
                'is-drop-before': dragOverIndex === rowIndex && dragFromIndex !== null && dragFromIndex > rowIndex,
                'is-drop-after': dragOverIndex === rowIndex && dragFromIndex !== null && dragFromIndex < rowIndex,
              }"
              @dragstart="onDragStart(rowIndex, $event)"
              @dragover="onDragOver(rowIndex, $event)"
              @drop="onDrop(rowIndex, $event)"
              @dragend="onDragEnd"
            >
              <td v-if="draggable" class="ui-dt-drag-cell">
                <div class="ui-dt-drag-controls">
                  <span class="ui-dt-grip" title="按住上下拖动排序" aria-hidden="true">
                    <GripVertical :size="14" />
                  </span>
                  <button
                    type="button"
                    class="ui-dt-step-btn"
                    :disabled="!canDrag || rowIndex === 0"
                    title="上移"
                    aria-label="上移"
                    @click.stop="moveStep(rowIndex, -1)"
                  >
                    <ChevronUp :size="13" />
                  </button>
                  <button
                    type="button"
                    class="ui-dt-step-btn"
                    :disabled="!canDrag || rowIndex === rows.length - 1"
                    title="下移"
                    aria-label="下移"
                    @click.stop="moveStep(rowIndex, 1)"
                  >
                    <ChevronDown :size="13" />
                  </button>
                </div>
              </td>
              <td
                v-for="col in columns"
                :key="col.key"
                :style="{ textAlign: col.align || 'left' }"
                :class="col.cellClass"
              >
                <slot :name="`cell-${col.key}`" :row="row" :index="rowIndex" :value="readCell(row, col.key)">
                  {{ readCell(row, col.key) ?? '-' }}
                </slot>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="paginated" class="ui-dt-footer">
      <div class="ui-dt-summary">
        第 {{ metrics.start }} - {{ metrics.end }} 条 / 共 {{ total }} 条
      </div>

      <div class="ui-dt-pager">
        <div class="ui-dt-size">
          <UiSelect v-model="pageSizeModel" :options="sizeSelectOptions" placeholder="每页条数" />
        </div>

        <div class="ui-dt-pages" role="navigation" aria-label="分页导航">
          <button
            type="button"
            class="ui-dt-page-btn"
            :disabled="loading || metrics.currentPage <= 1"
            aria-label="上一页"
            @click="goToPage(metrics.currentPage - 1)"
          >
            <ChevronLeft :size="15" />
          </button>

          <template v-for="item in pageItems" :key="item.type === 'page' ? `p-${item.page}` : `e-${item.key}`">
            <span v-if="item.type === 'ellipsis'" class="ui-dt-ellipsis">…</span>
            <button
              v-else
              type="button"
              class="ui-dt-page-btn"
              :class="{ 'is-active': item.page === metrics.currentPage }"
              :disabled="loading"
              :aria-current="item.page === metrics.currentPage ? 'page' : undefined"
              @click="goToPage(item.page)"
            >
              {{ item.page }}
            </button>
          </template>

          <button
            type="button"
            class="ui-dt-page-btn"
            :disabled="loading || metrics.currentPage >= metrics.totalPages"
            aria-label="下一页"
            @click="goToPage(metrics.currentPage + 1)"
          >
            <ChevronRight :size="15" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ui-dt {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.ui-dt-surface {
  width: 100%;
  border-radius: var(--radius-panel);
  border: 1px solid var(--border-subtle);
  background: var(--color-surface);
  overflow: hidden;
}

.ui-dt-scroll {
  width: 100%;
  overflow-x: auto;
}

.ui-dt-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  transition: opacity 0.15s;
}

.ui-dt-table.is-loading {
  opacity: 0.6;
}

.ui-dt-table th {
  padding: 11px 14px;
  font-weight: 500;
  font-size: 12px;
  color: var(--color-muted);
  background: rgb(255 255 255 / 2.2%);
  border-bottom: 1px solid var(--border-subtle);
  white-space: nowrap;
}

.ui-dt-table td {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-subtle);
  vertical-align: middle;
}

.ui-dt--compact .ui-dt-table th {
  padding: 9px 12px;
}

.ui-dt--compact .ui-dt-table td {
  padding: 9px 12px;
}

.ui-dt-table tbody tr:last-child td {
  border-bottom: 0;
}

.ui-dt-table tbody tr:hover {
  background: rgb(255 255 255 / 2.2%);
}

.ui-dt-table tbody tr.is-dragging {
  opacity: 0.42;
}

.ui-dt-table tbody tr.is-drop-before td {
  box-shadow: inset 0 2px 0 var(--color-gold);
}

.ui-dt-table tbody tr.is-drop-after td {
  box-shadow: inset 0 -2px 0 var(--color-gold);
}

.ui-dt-drag-col {
  width: 78px;
}

.ui-dt-drag-cell {
  width: 78px;
  padding-right: 6px !important;
}

.ui-dt-drag-controls {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.ui-dt-grip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 24px;
  color: #6b6d78;
  cursor: grab;
}

tr.is-draggable:hover .ui-dt-grip {
  color: var(--color-gold-soft);
}

.ui-dt-step-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: var(--color-muted);
  transition: background 0.12s, color 0.12s, border-color 0.12s;
}

.ui-dt-step-btn:hover:not(:disabled) {
  background: var(--surface-hover);
  border-color: var(--border-control);
  color: var(--color-gold-soft);
}

.ui-dt-step-btn:disabled {
  opacity: 0.25;
}

.ui-dt-state {
  padding: 36px 20px;
  text-align: center;
  color: var(--color-muted);
  font-size: 13px;
}

.ui-dt-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.ui-dt-summary {
  font-size: 12px;
  color: var(--color-muted);
  font-variant-numeric: tabular-nums;
}

.ui-dt-pager {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.ui-dt-size {
  width: 112px;
}

.ui-dt-size :deep(.ui-select-trigger) {
  min-height: 32px;
  padding: 0 10px;
  font-size: 12px;
  border-radius: 8px;
}

.ui-dt-pages {
  display: flex;
  align-items: center;
  gap: 4px;
}

.ui-dt-page-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 32px;
  height: 32px;
  padding: 0 8px;
  border-radius: 8px;
  border: 1px solid var(--border-control);
  background: rgb(255 255 255 / 2.5%);
  color: var(--color-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  transition: background 0.14s, border-color 0.14s, color 0.14s;
}

.ui-dt-page-btn:hover:not(:disabled) {
  background: var(--surface-hover);
  color: var(--color-text);
  border-color: rgb(255 255 255 / 22%);
}

.ui-dt-page-btn.is-active {
  background: var(--gold-tint);
  border-color: rgb(240 184 75 / 45%);
  color: var(--color-gold-soft);
  font-weight: 600;
}

.ui-dt-page-btn:disabled {
  opacity: 0.4;
}

.ui-dt-ellipsis {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  color: var(--color-muted);
  font-size: 12px;
}
</style>
