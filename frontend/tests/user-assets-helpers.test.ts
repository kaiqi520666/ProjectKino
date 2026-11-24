import assert from 'node:assert/strict'
import test from 'node:test'
import {
  findMatchingUserAssets,
  formatBatchCollectSummary,
  isCollectableMediaUrl,
  planBatchLibraryCollect,
} from '../src/features/assets/user-assets-helpers.ts'

test('isCollectableMediaUrl accepts persisted HTTP and relative URLs and rejects blob/data URLs', () => {
  assert.equal(isCollectableMediaUrl('https://oss.example.com/a.png'), true)
  assert.equal(isCollectableMediaUrl('/api/v1/media/1.mp4'), true)
  assert.equal(isCollectableMediaUrl('blob:http://localhost:5173/abc'), false)
  assert.equal(isCollectableMediaUrl('data:image/png;base64,abc'), false)
  assert.equal(isCollectableMediaUrl(''), false)
  assert.equal(isCollectableMediaUrl(undefined), false)
})

test('findMatchingUserAssets matches by kind and mediaKey or mediaUrl', () => {
  const items = [
    { id: '1', kind: 'image', mediaUrl: 'https://oss.example.com/a.png', mediaKey: 'assets/a.png' },
    { id: '2', kind: 'video', mediaUrl: 'https://oss.example.com/v.mp4', mediaKey: 'videos/v.mp4' },
  ]
  assert.deepEqual(
    findMatchingUserAssets(items, { kind: 'image', mediaUrl: 'https://oss.example.com/a.png' }).map((i) => i.id),
    ['1'],
  )
  assert.deepEqual(
    findMatchingUserAssets(items, { kind: 'video', mediaUrl: 'https://cdn.example.com/other.mp4', mediaKey: 'videos/v.mp4' }).map((i) => i.id),
    ['2'],
  )
  assert.deepEqual(
    findMatchingUserAssets(items, { kind: 'video', mediaUrl: 'https://oss.example.com/a.png' }),
    [],
  )
})

test('planBatchLibraryCollect skips empty, already saved, and in-batch duplicate URLs', () => {
  const existing = [
    { id: 'e1', kind: 'image', mediaUrl: 'https://oss.example.com/1.png', mediaKey: 'k1' },
  ]
  const plan = planBatchLibraryCollect(
    [
      { kind: 'image', title: '已有图', mediaUrl: 'https://oss.example.com/1.png', mediaKey: 'k1' },
      { kind: 'image', title: '空图', mediaUrl: '' },
      { kind: 'image', title: '本地blob', mediaUrl: 'blob:http://localhost/x' },
      { kind: 'image', title: '新图A', mediaUrl: 'https://oss.example.com/2.png', mediaKey: 'k2' },
      { kind: 'image', title: '新图A重复', mediaUrl: 'https://oss.example.com/2.png' },
      { kind: 'video', title: '新视频', mediaUrl: 'https://oss.example.com/3.mp4' },
    ],
    existing,
  )
  assert.equal(plan.toAdd.length, 2)
  assert.equal(plan.toAdd[0]?.title, '新图A')
  assert.equal(plan.toAdd[1]?.title, '新视频')
  assert.equal(plan.skippedExisting, 2)
  assert.equal(plan.skippedEmpty, 2)
})

test('formatBatchCollectSummary produces clear user feedback for all outcomes', () => {
  assert.deepEqual(
    formatBatchCollectSummary({ added: 3, skippedExisting: 1, skippedEmpty: 0, failed: 0 }),
    { message: '已加入 3 项到素材库，1 项已存在', tone: 'success' },
  )
  assert.deepEqual(
    formatBatchCollectSummary({ added: 0, skippedExisting: 2, skippedEmpty: 0, failed: 0 }),
    { message: '所选项均已在素材库中', tone: 'info' },
  )
  assert.deepEqual(
    formatBatchCollectSummary({ added: 0, skippedExisting: 0, skippedEmpty: 0, failed: 2 }),
    { message: '加入素材库失败（2 项）', tone: 'error' },
  )
})
