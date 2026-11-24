import test from 'node:test'
import assert from 'node:assert/strict'
import type { JobOut } from '../src/features/studio/api-types.ts'
import {
  computeStoryboardLocks,
  extractStoryboardJobMeta,
  resolveStoryboardOverviewBadge,
  shouldRefreshStoryboardOnProgress,
} from '../src/features/studio/storyboard-job-helpers.ts'

function baseJob(overrides: Partial<JobOut>): JobOut {
  return {
    id: 'job-1',
    projectId: 'proj-1',
    jobType: 'storyboard_generate',
    targetId: '2',
    status: 'running',
    stepIndex: 1,
    stepTotal: 4,
    stepLabel: '第 2 集已落库 1/3 批，继续设计下一批',
    progress: 40,
    createdAt: '2026-11-24T00:00:00Z',
    ...overrides,
  }
}

test('extractStoryboardJobMeta prioritizes jobMeta and falls back to label/targetId', () => {
  const fromMeta = extractStoryboardJobMeta(
    baseJob({
      targetId: 'clip-uuid-9',
      jobMeta: {
        action: 'clip_regenerate',
        episodeNumber: 3,
        clipId: 'clip-uuid-9',
      },
    }),
  )
  assert.deepEqual(fromMeta, {
    episodeNumber: 3,
    action: 'clip_regenerate',
    clipId: 'clip-uuid-9',
    insertAfterClipId: undefined,
    completedBatches: undefined,
    totalBatches: undefined,
    segmentCount: undefined,
  })

  const composeMeta = extractStoryboardJobMeta(
    baseJob({
      jobType: 'episode_compose',
      targetId: 'ep-uuid-4',
      stepLabel: '正在合成本集视频（第 4 集）',
      jobMeta: { episodeId: 'ep-uuid-4', episodeNumber: 4, clipCount: 12 },
    }),
  )
  assert.equal(composeMeta.action, 'compose')
  assert.equal(composeMeta.episodeNumber, 4)

  const legacyEpisodeMeta = extractStoryboardJobMeta(
    baseJob({ targetId: '5', jobMeta: null, stepLabel: '正在设计第 5 集' }),
  )
  assert.equal(legacyEpisodeMeta.action, 'episode')
  assert.equal(legacyEpisodeMeta.episodeNumber, 5)
})

test('shouldRefreshStoryboardOnProgress triggers on batch increase or incremental save label', () => {
  assert.equal(shouldRefreshStoryboardOnProgress('准备中', '准备中', 0, 0), false)
  assert.equal(shouldRefreshStoryboardOnProgress('第 1/3 批设计中', '第 1/3 批设计中', 0, 1), true)
  assert.equal(
    shouldRefreshStoryboardOnProgress('第 1 集准备中', '第 1 集已落库 1/3 批，继续设计下一批', 0, 0),
    true,
  )
})

test('resolveStoryboardOverviewBadge renders running, failed, done, and pending states accurately', () => {
  const runningBoard = resolveStoryboardOverviewBadge({
    hasPersistedStoryboard: true,
    clipCount: 8,
    job: {
      jobId: 'j1',
      projectId: 'p1',
      episodeNumber: 1,
      jobType: 'storyboard_generate',
      action: 'episode',
      completedBatches: 1,
      totalBatches: 3,
      segmentCount: 10,
      status: 'running',
      stepIndex: 1,
      stepTotal: 4,
      stepLabel: '第 1 集已落库 1/3 批',
      progress: 40,
      startedAt: 1,
    },
  })
  assert.equal(runningBoard.tone, 'running')
  assert.equal(runningBoard.label, '拆分镜中')
  assert.equal(runningBoard.detail, '已完成 1/3 批 · 40%')

  const failedCompose = resolveStoryboardOverviewBadge({
    hasPersistedStoryboard: true,
    clipCount: 8,
    job: {
      jobId: 'j2',
      projectId: 'p1',
      episodeNumber: 1,
      jobType: 'episode_compose',
      action: 'compose',
      status: 'failed',
      stepIndex: 2,
      stepTotal: 4,
      stepLabel: '合成失败',
      progress: 50,
      startedAt: 1,
      errorMessage: 'FFmpeg 超时',
    },
  })
  assert.equal(failedCompose.tone, 'failed')
  assert.equal(failedCompose.label, '合成失败')
  assert.equal(failedCompose.detail, 'FFmpeg 超时')
})

test('computeStoryboardLocks isolates clip_regenerate prompt lock to the target clip only', () => {
  const locks = computeStoryboardLocks({
    episodeNumber: 2,
    job: {
      jobId: 'j3',
      projectId: 'p1',
      episodeNumber: 2,
      jobType: 'storyboard_generate',
      action: 'clip_regenerate',
      targetClipId: 'clip-2',
      status: 'running',
      stepIndex: 1,
      stepTotal: 2,
      stepLabel: '片段 2 重生成中',
      progress: 50,
      startedAt: 1,
    },
  })
  assert.equal(locks.isClipRegenRunning, true)
  assert.equal(locks.episodeActionsLocked, true)
  assert.equal(locks.structureLocked, true)
  assert.equal(locks.isClipLocked('clip-2'), true)
  assert.equal(locks.isClipLocked('clip-1'), false)

  const otherEpisodeLocks = computeStoryboardLocks({
    episodeNumber: 3,
    job: {
      jobId: 'j3',
      projectId: 'p1',
      episodeNumber: 2,
      jobType: 'storyboard_generate',
      action: 'episode',
      status: 'running',
      stepIndex: 1,
      stepTotal: 3,
      stepLabel: '第 2 集拆分镜中',
      progress: 33,
      startedAt: 1,
    },
  })
  assert.equal(otherEpisodeLocks.isAnyJobRunning, false)
  assert.equal(otherEpisodeLocks.episodeActionsLocked, false)
  assert.equal(otherEpisodeLocks.isClipLocked('clip-9'), false)
})
