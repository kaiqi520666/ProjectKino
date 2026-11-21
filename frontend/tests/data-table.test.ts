import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildPageItems, computePagination } from '../src/components/ui/data-table-pagination.ts'

test('computePagination handles empty, partial, and clamped pages accurately', () => {
  assert.deepEqual(computePagination(0, 1, 30, 0), {
    totalPages: 1,
    currentPage: 1,
    start: 0,
    end: 0,
    offset: 0,
  })

  assert.deepEqual(computePagination(75, 2, 30, 30), {
    totalPages: 3,
    currentPage: 2,
    start: 31,
    end: 60,
    offset: 30,
  })

  assert.deepEqual(computePagination(75, 99, 30, 15), {
    totalPages: 3,
    currentPage: 3,
    start: 61,
    end: 75,
    offset: 60,
  })
})

test('buildPageItems renders full list for <=7 pages and ellipses for larger ranges', () => {
  assert.deepEqual(
    buildPageItems(2, 5).map((item) => (item.type === 'page' ? item.page : '...')),
    [1, 2, 3, 4, 5],
  )

  assert.deepEqual(
    buildPageItems(5, 12).map((item) => (item.type === 'page' ? item.page : '...')),
    [1, '...', 4, 5, 6, '...', 12],
  )

  assert.deepEqual(
    buildPageItems(1, 10).map((item) => (item.type === 'page' ? item.page : '...')),
    [1, 2, '...', 10],
  )
})
