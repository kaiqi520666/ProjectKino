import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  computeFirstUnreadCursor,
  computeUnreadIds,
  normalizeReadIds,
} from '../src/features/announcements/announcement-helpers.ts'

test('normalizeReadIds filters invalid entries and deduplicates positive integers', () => {
  assert.deepEqual(normalizeReadIds([3, 1, 3, -1, 0, '2', null, 1.5, 5]), [3, 1, 5])
  assert.deepEqual(normalizeReadIds('bad'), [])
})

test('computeUnreadIds and computeFirstUnreadCursor track unread announcements cleanly', () => {
  const available = [12, 10, 7, 4]
  assert.deepEqual(computeUnreadIds(available, [10, 4]), [12, 7])
  assert.equal(computeFirstUnreadCursor(available, [10, 4]), 13)

  assert.deepEqual(computeUnreadIds(available, [12, 10, 7, 4]), [])
  assert.equal(computeFirstUnreadCursor(available, [12, 10, 7, 4]), undefined)

  // 删除旧公告后（localStorage 里残留已删 ID 99），未读计数仍精准无偏差
  assert.deepEqual(computeUnreadIds([12, 10], [99, 10]), [12])
  assert.equal(computeFirstUnreadCursor([12, 10], [99, 10]), 13)
})
