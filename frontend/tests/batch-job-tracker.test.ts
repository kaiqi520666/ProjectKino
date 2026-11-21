import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  applyTerminalJobStatus,
  computeBatchSummary,
  mergeTrackedJobs,
} from '../src/features/studio/composables/useBatchJobTracker.ts'

test('mergeTrackedJobs starts fresh or merges unfinished batches and resets retried targets', () => {
  const checked = new Set<string>(['job-1'])
  const first = mergeTrackedJobs(
    null,
    [
      { id: 'job-1', targetId: 'asset-a' },
      { id: 'job-2', targetId: 'asset-b' },
    ],
    { modelId: 'gpt-image-2', tier: '1k' },
    false,
    checked,
  )
  assert.deepEqual(first.jobToTarget, { 'job-1': 'asset-a', 'job-2': 'asset-b' })
  assert.equal(checked.has('job-1'), false)

  applyTerminalJobStatus(first, 'job-1', 'succeeded', null, '生成失败')
  applyTerminalJobStatus(first, 'job-2', 'failed', '上游超时', '生成失败')
  assert.deepEqual(first.succeededIds, ['asset-a'])
  assert.deepEqual(first.failedById, { 'asset-b': '上游超时' })

  // 合并新提交的重试任务时，清除旧失败记录并保留已成功项
  checked.add('job-3')
  const merged = mergeTrackedJobs(
    first,
    [{ id: 'job-3', targetId: 'asset-b' }],
    { modelId: 'gpt-image-2.6-flare', tier: '2k' },
    true,
    checked,
  )
  assert.equal(merged.meta.modelId, 'gpt-image-2.6-flare')
  assert.deepEqual(merged.succeededIds, ['asset-a'])
  assert.deepEqual(merged.failedById, {})
  assert.equal(merged.jobToTarget['job-3'], 'asset-b')
  assert.equal(checked.has('job-3'), false)
})

test('applyTerminalJobStatus ignores non-terminal statuses and falls back to default error message', () => {
  const checked = new Set<string>()
  const state = mergeTrackedJobs(
    null,
    [{ id: 'job-1', targetId: 'clip-1' }],
    { episodeNumber: 1 },
    false,
    checked,
  )

  assert.equal(applyTerminalJobStatus(state, 'job-1', 'running', null, '视频生成失败'), false)
  assert.deepEqual(state.succeededIds, [])
  assert.deepEqual(state.failedById, {})

  assert.equal(applyTerminalJobStatus(state, 'job-1', 'review', '', '视频生成失败'), true)
  assert.deepEqual(state.failedById, { 'clip-1': '视频生成失败' })
})

test('computeBatchSummary converges progress, handles scope mismatch, and recovers from activeCount', () => {
  const checked = new Set<string>()
  const state = mergeTrackedJobs(
    null,
    [
      { id: 'job-1', targetId: 'clip-1' },
      { id: 'job-2', targetId: 'clip-2' },
    ],
    { episodeNumber: 2 },
    false,
    checked,
  )

  applyTerminalJobStatus(state, 'job-1', 'succeeded', null, '失败')
  const runningSummary = computeBatchSummary(state, 1, true)
  assert.equal(runningSummary?.total, 2)
  assert.equal(runningSummary?.succeeded, 1)
  assert.equal(runningSummary?.running, 1)
  assert.equal(runningSummary?.percent, 50)
  assert.equal(runningSummary?.finished, false)

  applyTerminalJobStatus(state, 'job-2', 'failed', '余额不足', '失败')
  const doneSummary = computeBatchSummary(state, 0, true)
  assert.equal(doneSummary?.percent, 100)
  assert.equal(doneSummary?.failed, 1)
  assert.deepEqual(doneSummary?.failedIds, ['clip-2'])
  assert.equal(doneSummary?.finished, true)

  // 切换到其他分集（inScope = false）时，不显示旧集横幅；若新集有运行中任务则回退展示
  assert.equal(computeBatchSummary(state, 0, false), null)
  const recovered = computeBatchSummary(state, 3, false)
  assert.equal(recovered?.total, 3)
  assert.equal(recovered?.finished, false)
})
