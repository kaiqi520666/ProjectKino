export interface PaginationMetrics {
  totalPages: number
  currentPage: number
  start: number
  end: number
  offset: number
}

export type PageButtonItem =
  | { type: 'page'; page: number }
  | { type: 'ellipsis'; key: string }

export function computePagination(total: number, page: number, pageSize: number, rowCount: number): PaginationMetrics {
  const safeTotal = Math.max(0, Math.floor(total))
  const safeSize = Math.max(1, Math.floor(pageSize))
  const totalPages = Math.max(1, Math.ceil(safeTotal / safeSize))
  const currentPage = Math.min(Math.max(1, Math.floor(page)), totalPages)
  const offset = (currentPage - 1) * safeSize
  const start = safeTotal === 0 || rowCount === 0 ? 0 : offset + 1
  const end = safeTotal === 0 || rowCount === 0 ? 0 : Math.min(offset + rowCount, safeTotal)
  return { totalPages, currentPage, start, end, offset }
}

export function buildPageItems(currentPage: number, totalPages: number): PageButtonItem[] {
  const safeTotal = Math.max(1, Math.floor(totalPages))
  const safeCurrent = Math.min(Math.max(1, Math.floor(currentPage)), safeTotal)

  if (safeTotal <= 7) {
    return Array.from({ length: safeTotal }, (_, idx) => ({ type: 'page', page: idx + 1 }))
  }

  const items: PageButtonItem[] = [{ type: 'page', page: 1 }]
  const left = Math.max(2, safeCurrent - 1)
  const right = Math.min(safeTotal - 1, safeCurrent + 1)

  if (left > 2) {
    items.push({ type: 'ellipsis', key: 'left' })
  }
  for (let p = left; p <= right; p += 1) {
    items.push({ type: 'page', page: p })
  }
  if (right < safeTotal - 1) {
    items.push({ type: 'ellipsis', key: 'right' })
  }
  items.push({ type: 'page', page: safeTotal })
  return items
}
