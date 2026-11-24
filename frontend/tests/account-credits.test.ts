import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  buildBillsCsv,
  buildLedgersCsv,
  computeBreakdownSegments,
  formatCreditReason,
  formatLedgerChangeDisplay,
  formatRateSpec,
} from '../src/features/account/credits-helpers.ts'
import { formatCompactCount, formatTokenUsage } from '../src/lib/format.ts'

test('formatTokenUsage reads camelCase backend tokenUsage and hides modelId by default', () => {
  assert.equal(formatCompactCount(850), '850')
  assert.equal(formatCompactCount(12400), '12.4k')
  assert.equal(formatCompactCount(1_250_000), '1.25M')

  const camel = formatTokenUsage({
    modelId: 'or-ds-baidu',
    inputTokens: 12400,
    cacheReadTokens: 8100,
    outputTokens: 2300,
  })
  assert.equal(camel, '输入 12.4k · 缓存命中 8.1k · 输出 2.3k')

  const withModel = formatTokenUsage(
    {
      modelId: 'or-ds-baidu',
      inputTokens: 12400,
      cacheReadTokens: 8100,
      outputTokens: 2300,
    },
    { includeModel: true },
  )
  assert.equal(withModel, 'or-ds-baidu · 输入 12.4k · 缓存命中 8.1k · 输出 2.3k')

  const snake = formatTokenUsage({
    model: 'deepseek-reasoner',
    input_tokens: 500,
    output_tokens: 120,
    cache_hit_tokens: 0,
  })
  assert.equal(snake, '输入 500 · 输出 120')
})

test('formatCreditReason translates legacy English codes into clean Chinese while preserving 27s and 2K', () => {
  assert.equal(formatCreditReason('LLM 任务消耗 (script_generate:outline)'), '全剧大纲规划')
  assert.equal(formatCreditReason('LLM 任务消耗 (script_generate:ep5)'), '第 5 集剧本生成')
  assert.equal(formatCreditReason('LLM 任务消耗 (script_regenerate:ep2)'), '第 2 集剧本重写')
  assert.equal(formatCreditReason('LLM 任务消耗 (storyboard_generate/episode)'), '单集分镜规划')
  assert.equal(formatCreditReason('LLM 任务消耗 (storyboard_generate/clip_regenerate)'), '片段分镜重绘')
  assert.equal(formatCreditReason('LLM 任务消耗 (assets_extract)'), '项目资产识别')
  assert.equal(
    formatCreditReason('片段生视频预冻结 (片段1 · cc-sd2.5-flash-t-480/27s)'),
    '片段 1 视频生成（27s）',
  )
  assert.equal(
    formatCreditReason('片段分镜宫格预冻结 (片段1 · gpt-image-2.6-flare/2k)'),
    '片段 1 分镜宫格图（2K）',
  )
  assert.equal(
    formatCreditReason('资产生图预冻结 (主角 · gpt-image-2.6-flare/2k)'),
    '资产「主角」生图（2K）',
  )
  assert.equal(
    formatCreditReason('片段视频完成结算 (cc-sd2.5-flash-t-480/27s)'),
    '片段视频完成结算（27s）',
  )
  assert.equal(
    formatCreditReason('画布生图失败退还冻结积分 (provider_timeout)'),
    '画布生图失败，已退还冻结积分',
  )
  assert.equal(formatCreditReason('片段 1 分镜宫格规划'), '片段 1 分镜宫格规划')
})

test('computeBreakdownSegments calculates category percentages cleanly', () => {
  const empty = computeBreakdownSegments(null)
  assert.deepEqual(
    empty.map((s) => s.percent),
    [0, 0, 0],
  )

  const segments = computeBreakdownSegments({
    videoSpent: '60',
    imageSpent: '30',
    textSpent: '10',
  })
  assert.deepEqual(
    segments.map((s) => ({ key: s.key, percent: s.percent })),
    [
      { key: 'video', percent: 60 },
      { key: 'image', percent: 30 },
      { key: 'text', percent: 10 },
    ],
  )
})

test('formatRateSpec formats media rate snapshots and falls back to token usage', () => {
  assert.equal(
    formatRateSpec({ tier: '2k', basePrice: '4.5', unit: 'call' }, null),
    '2K · 4.5 积分/次',
  )
  assert.equal(
    formatRateSpec({ ruleKey: '720p', durationSeconds: 15, basePrice: '1.2', unit: 'second' }, null),
    '720p · 15s · 1.2 积分/秒',
  )
  assert.equal(
    formatRateSpec(null, { modelId: 'or-ds-baidu', inputTokens: 1000, outputTokens: 200 }),
    '输入 1k · 输出 200',
  )
})

test('formatLedgerChangeDisplay clarifies settle, freeze, and release entries', () => {
  const settled = formatLedgerChangeDisplay({
    operation: 'settle',
    balanceChange: '0.0000',
    frozenChange: '-12.0000',
  })
  assert.equal(settled.primary, '冻结 -12')
  assert.equal(settled.secondary, '可用不变 · 已结算')
  assert.equal(settled.tone, 'neutral')

  const frozen = formatLedgerChangeDisplay({
    operation: 'freeze',
    balanceChange: '-12.0000',
    frozenChange: '12.0000',
  })
  assert.equal(frozen.primary, '-12')
  assert.equal(frozen.secondary, '冻结 +12')
  assert.equal(frozen.tone, 'frozen')

  const released = formatLedgerChangeDisplay({
    operation: 'release',
    balanceChange: '12.0000',
    frozenChange: '-12.0000',
  })
  assert.equal(released.primary, '+12')
  assert.equal(released.secondary, '解冻 -12')
  assert.equal(released.tone, 'pos')
})

test('buildBillsCsv and buildLedgersCsv emit UTF-8 BOM and escape commas', () => {
  const billsCsv = buildBillsCsv([
    {
      id: 'b1',
      category: 'video',
      status: 'charged',
      amount: '-12.0000',
      originalAmount: '12.0000',
      balanceAfter: '88.0000',
      title: '生成分镜视频',
      reason: '片段1, 夜景',
      operation: 'freeze',
      projectId: 'p1',
      projectName: '夜行档案',
      modelId: 'vid-1',
      modelName: 'Seedance 2.0',
      rateSnapshot: { ruleKey: '720p', durationSeconds: 10, basePrice: '1.2', unit: 'second' },
      createdAt: '2026-11-24T10:00:00Z',
      timeline: [],
    },
  ])
  assert.equal(billsCsv.startsWith('\uFEFF时间,分类,状态'), true)
  assert.equal(billsCsv.includes('"片段1, 夜景"'), true)
  assert.equal(billsCsv.includes('短剧：夜行档案'), true)

  const ledgersCsv = buildLedgersCsv([
    {
      id: 'l1',
      operation: 'settle',
      balanceChange: '0.0000',
      frozenChange: '-12.0000',
      balanceBefore: '88.0000',
      balanceAfter: '88.0000',
      frozenBefore: '12.0000',
      frozenAfter: '0.0000',
      reason: '视频生成成功结算',
      createdAt: '2026-11-24T10:01:00Z',
    },
  ])
  assert.equal(ledgersCsv.startsWith('\uFEFF时间,操作类型,可用变动'), true)
  assert.equal(ledgersCsv.includes('消费结算'), true)
})
