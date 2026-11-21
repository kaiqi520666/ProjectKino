import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildCalendarMonthGrid,
  createDateRangePreset,
  formatLocalDate,
  matchDateRangePreset,
  normalizeDateRange,
  parseLocalDate,
  toUtcIsoBounds,
} from '../src/components/ui/date-range.ts'

test('createDateRangePreset computes inclusive today, 7d, and 30d ranges across month boundaries', () => {
  const anchor = new Date(2026, 10, 21) // 2026-11-21
  assert.deepEqual(createDateRangePreset('today', anchor), {
    start: '2026-11-21',
    end: '2026-11-21',
  })
  assert.deepEqual(createDateRangePreset('7d', anchor), {
    start: '2026-11-15',
    end: '2026-11-21',
  })
  assert.deepEqual(createDateRangePreset('30d', anchor), {
    start: '2026-10-23',
    end: '2026-11-21',
  })
})

test('parseLocalDate validates calendar dates and rejects overflow dates', () => {
  const valid = parseLocalDate('2026-02-28')
  assert.ok(valid)
  assert.equal(formatLocalDate(valid), '2026-02-28')

  assert.equal(parseLocalDate('2026-02-31'), null)
  assert.equal(parseLocalDate('not-a-date'), null)
  assert.equal(parseLocalDate(null), null)
})

test('matchDateRangePreset and normalizeDateRange handle presets and reversed selections', () => {
  const anchor = new Date(2026, 10, 21)
  assert.equal(matchDateRangePreset({ start: '2026-11-21', end: '2026-11-21' }, undefined, anchor), 'today')
  assert.equal(matchDateRangePreset({ start: '2026-11-15', end: '2026-11-21' }, undefined, anchor), '7d')
  assert.equal(matchDateRangePreset({ start: '2026-10-23', end: '2026-11-21' }, undefined, anchor), '30d')
  assert.equal(matchDateRangePreset({ start: '2026-11-10', end: '2026-11-21' }, undefined, anchor), null)
  assert.equal(matchDateRangePreset({ start: null, end: null }, undefined, anchor), null)

  assert.deepEqual(normalizeDateRange('2026-11-21', '2026-11-15'), {
    start: '2026-11-15',
    end: '2026-11-21',
  })
})

test('toUtcIsoBounds returns half-open local-midnight ISO boundaries', () => {
  const bounds = toUtcIsoBounds({ start: '2026-11-21', end: '2026-11-21' })
  assert.ok(bounds.createdFrom)
  assert.ok(bounds.createdTo)

  const fromMs = Date.parse(bounds.createdFrom)
  const toMs = Date.parse(bounds.createdTo)
  assert.equal(toMs - fromMs, 24 * 60 * 60 * 1000)

  const localStart = new Date(2026, 10, 21, 0, 0, 0, 0)
  const localNext = new Date(2026, 10, 22, 0, 0, 0, 0)
  assert.equal(bounds.createdFrom, localStart.toISOString())
  assert.equal(bounds.createdTo, localNext.toISOString())

  assert.deepEqual(toUtcIsoBounds({ start: null, end: null }), {})
})

test('buildCalendarMonthGrid builds 42 Monday-first cells with today and future flags', () => {
  const anchor = new Date(2026, 10, 21) // 2026-11-21 (Saturday)
  const grid = buildCalendarMonthGrid(2026, 10, anchor)
  assert.equal(grid.length, 42)
  // 2026-11-01 is Sunday, so Monday-first grid starts on 2026-10-26
  assert.equal(grid[0]?.iso, '2026-10-26')
  assert.equal(grid[0]?.inMonth, false)

  const nov1 = grid.find((cell) => cell.iso === '2026-11-01')
  assert.ok(nov1)
  assert.equal(nov1.inMonth, true)
  assert.equal(nov1.isFuture, false)

  const nov21 = grid.find((cell) => cell.iso === '2026-11-21')
  assert.ok(nov21)
  assert.equal(nov21.isToday, true)
  assert.equal(nov21.isFuture, false)

  const nov22 = grid.find((cell) => cell.iso === '2026-11-22')
  assert.ok(nov22)
  assert.equal(nov22.isFuture, true)
})
