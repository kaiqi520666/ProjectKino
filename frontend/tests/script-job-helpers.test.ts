import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  formatElapsedSeconds,
  isScriptJobType,
  parseTargetEpisodeNumber,
  parseWritingEpisodeNumber,
  resolveEpisodeGenerationStatus,
  scriptJobSuccessMessage,
  scriptJobTitle,
  shouldRefreshDetailOnProgress,
} from '../src/features/studio/script-job-helpers.ts'

test('isScriptJobType distinguishes script jobs from downstream media/storyboard jobs', () => {
  assert.equal(isScriptJobType('script_generate'), true)
  assert.equal(isScriptJobType('script_regenerate'), true)
  assert.equal(isScriptJobType('episode_rewrite'), true)
  assert.equal(isScriptJobType('episode_append'), true)

  assert.equal(isScriptJobType('assets_extract'), false)
  assert.equal(isScriptJobType('storyboard_generate'), false)
  assert.equal(isScriptJobType('asset_image'), false)
  assert.equal(isScriptJobType('clip_video'), false)
  assert.equal(isScriptJobType('episode_compose'), false)
})

test('parseTargetEpisodeNumber extracts target episode from targetId or stepLabel', () => {
  assert.equal(
    parseTargetEpisodeNumber({ jobType: 'episode_rewrite', targetId: '3', stepLabel: '正在重写' }),
    3,
  )
  assert.equal(
    parseTargetEpisodeNumber({ jobType: 'episode_rewrite', targetId: null, stepLabel: '正在重写第 5 集剧本' }),
    5,
  )
  assert.equal(
    parseTargetEpisodeNumber({ jobType: 'script_generate', targetId: '3', stepLabel: '正在规划全剧 6 集大纲' }),
    undefined,
  )
})

test('parseWritingEpisodeNumber tracks active writing episode without false positives during planning', () => {
  assert.equal(
    parseWritingEpisodeNumber(
      { jobType: 'script_generate', status: 'running', stepLabel: '正在规划全剧 6 集大纲与世界观' },
      6,
    ),
    null,
  )
  assert.equal(
    parseWritingEpisodeNumber(
      { jobType: 'script_generate', status: 'running', stepLabel: '全剧 6 集大纲已保存，开始逐集撰写正文' },
      6,
    ),
    null,
  )
  assert.equal(
    parseWritingEpisodeNumber(
      { jobType: 'script_generate', status: 'running', stepLabel: '正在撰写第 3/6 集《照片里的裂痕》' },
      6,
    ),
    3,
  )
  assert.equal(
    parseWritingEpisodeNumber(
      { jobType: 'script_generate', status: 'running', stepLabel: '第 3/6 集《照片里的裂痕》已保存' },
      6,
    ),
    null,
  )
  assert.equal(
    parseWritingEpisodeNumber(
      { jobType: 'episode_rewrite', status: 'running', stepLabel: '正在重写本集', targetEpisodeNumber: 2 },
      6,
    ),
    2,
  )
  assert.equal(
    parseWritingEpisodeNumber(
      { jobType: 'episode_append', status: 'running', stepLabel: '正在续写新增分集' },
      6,
    ),
    7,
  )
  assert.equal(
    parseWritingEpisodeNumber(
      { jobType: 'script_generate', status: 'failed', stepLabel: '正在撰写第 3/6 集' },
      6,
    ),
    null,
  )
})

test('shouldRefreshDetailOnProgress refreshes immediately on save milestones and avoids duplicate fetches', () => {
  assert.equal(
    shouldRefreshDetailOnProgress(
      '正在规划全剧 6 集大纲与世界观',
      '全剧 6 集大纲已保存，开始逐集撰写正文',
    ),
    true,
  )
  assert.equal(
    shouldRefreshDetailOnProgress(
      '正在撰写第 1/6 集《标题》',
      '第 1/6 集《标题》已保存',
    ),
    true,
  )
  // Saved event already triggered refresh; immediately entering EP 2 should not duplicate it.
  assert.equal(
    shouldRefreshDetailOnProgress(
      '第 1/6 集《标题》已保存',
      '正在撰写第 2/6 集《下一集》',
    ),
    false,
  )
  // If an SSE saved event was missed, entering EP 2 still triggers a sync.
  assert.equal(
    shouldRefreshDetailOnProgress(
      '正在撰写第 1/6 集《标题》',
      '正在撰写第 2/6 集《下一集》',
    ),
    true,
  )
  assert.equal(
    shouldRefreshDetailOnProgress(
      '正在撰写第 2/6 集《下一集》',
      '正在撰写第 2/6 集《下一集》',
    ),
    false,
  )
})

test('resolveEpisodeGenerationStatus prioritizes active writing over completed and distinguishes warnings', () => {
  assert.equal(
    resolveEpisodeGenerationStatus({
      episodeNumber: 2,
      writingEpisodeNumber: 2,
      hasWrittenScript: true,
      warningCount: 1,
    }),
    'writing',
  )
  assert.equal(
    resolveEpisodeGenerationStatus({
      episodeNumber: 1,
      writingEpisodeNumber: 2,
      hasWrittenScript: true,
      warningCount: 0,
    }),
    'completed',
  )
  assert.equal(
    resolveEpisodeGenerationStatus({
      episodeNumber: 1,
      writingEpisodeNumber: 2,
      hasWrittenScript: true,
      warningCount: 2,
    }),
    'warning',
  )
  assert.equal(
    resolveEpisodeGenerationStatus({
      episodeNumber: 4,
      writingEpisodeNumber: 2,
      hasWrittenScript: false,
      warningCount: 0,
    }),
    'pending',
  )
})

test('formatElapsedSeconds and labels format cleanly', () => {
  assert.equal(formatElapsedSeconds(-5), '00:00')
  assert.equal(formatElapsedSeconds(0), '00:00')
  assert.equal(formatElapsedSeconds(65), '01:05')
  assert.equal(formatElapsedSeconds(754), '12:34')

  assert.equal(scriptJobTitle('episode_rewrite', 4), '正在重写第 4 集')
  assert.equal(scriptJobTitle('episode_append'), '正在续写新增分集')
  assert.equal(scriptJobSuccessMessage('script_generate', '全家福', 6), '《全家福》已生成 6 集剧本')
  assert.equal(scriptJobSuccessMessage('episode_rewrite', '全家福', 6, 4), '第 4 集已重写完成')
})
