import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildModalitySlotLabels,
  formatPromptToken,
  hasPromptToken,
  migrateLegacyCanvasRefs,
  parsePromptLine,
  remapPromptOnReferenceReorder,
  remapPromptOnSlotRemove,
  removeStoryboardGridPromptBlock,
} from '../src/components/business/prompt-references.ts'

test('parsePromptLine parses unified @[...] tokens across all modalities and removed markers', () => {
  assert.deepEqual(
    parsePromptLine('@[图片1]走进@[图片2]，参考@[视频1]运镜，配@[音频1]、@[文本1]和@[已移除:旧道具]'),
    [
      { type: 'ref', tokenKey: '图片1' },
      { type: 'text', text: '走进' },
      { type: 'ref', tokenKey: '图片2' },
      { type: 'text', text: '，参考' },
      { type: 'ref', tokenKey: '视频1' },
      { type: 'text', text: '运镜，配' },
      { type: 'ref', tokenKey: '音频1' },
      { type: 'text', text: '、' },
      { type: 'ref', tokenKey: '文本1' },
      { type: 'text', text: '和' },
      { type: 'ref', tokenKey: '', removedLabel: '旧道具' },
    ],
  )
})

test('formatPromptToken and hasPromptToken handle unified tokens cleanly', () => {
  assert.equal(formatPromptToken('图片2'), '@[图片2]')
  assert.equal(formatPromptToken('文本1'), '@[文本1]')
  assert.equal(formatPromptToken('', '陈国栋]'), '@[已移除:陈国栋]')
  assert.equal(hasPromptToken('包含 @[视频1]'), true)
  assert.equal(hasPromptToken('包含 @[文本2]'), true)
  assert.equal(hasPromptToken('包含 @[已移除:旧图]'), true)
  assert.equal(hasPromptToken('纯文本'), false)
  assert.equal(hasPromptToken('遗留 {{ref:a1}} 不算新语法'), false)
})

test('buildModalitySlotLabels numbers each modality independently', () => {
  const slots = buildModalitySlotLabels([
    { id: 'n1', kind: 'image' },
    { id: 'n2', kind: 'video' },
    { id: 'n3', kind: 'image' },
    { id: 'n4', kind: 'audio' },
    { id: 'n5', kind: 'text' },
  ])
  assert.deepEqual(
    slots.map((s) => `${s.id}:${s.slotLabel}`),
    ['n1:图片1', 'n2:视频1', 'n3:图片2', 'n4:音频1', 'n5:文本1'],
  )
})

test('migrateLegacyCanvasRefs upgrades historical {{ref:nodeId}} tokens to unified @[...]', () => {
  const map = new Map([
    ['img-1', '图片1'],
    ['txt-1', '文本1'],
  ])
  assert.equal(
    migrateLegacyCanvasRefs('镜头推进 {{ref:img-1}}，结合 {{ref:txt-1}} 与 {{ref:deleted}}', map),
    '镜头推进 @[图片1]，结合 @[文本1] 与 @[已移除:节点]',
  )
  assert.equal(migrateLegacyCanvasRefs('已是新语法 @[图片1]', map), '已是新语法 @[图片1]')
})

test('remapPromptOnSlotRemove shifts only same-modality higher slots and marks removed slot', () => {
  const prompt = '@[图片1] 在 @[图片2] 拿起 @[图片3]，并再次看向 @[图片1]；参考 @[视频1] 与 @[视频2]，配 @[音频1] 与 @[文本1] @[文本2]'

  // Removing 图片1 -> 图片1 becomes 已移除:陈国栋, 图片2->图片1, 图片3->图片2; 视频/音频/文本 untouched
  const r1 = remapPromptOnSlotRemove(prompt, 'image', 1, '陈国栋')
  assert.equal(r1.changed, true)
  assert.equal(r1.removedCount, 2)
  assert.equal(r1.shiftedCount, 2)
  assert.equal(
    r1.prompt,
    '@[已移除:陈国栋] 在 @[图片1] 拿起 @[图片2]，并再次看向 @[已移除:陈国栋]；参考 @[视频1] 与 @[视频2]，配 @[音频1] 与 @[文本1] @[文本2]',
  )

  // Removing 视频1 -> 视频1 becomes 已移除:运镜, 视频2->视频1
  const r2 = remapPromptOnSlotRemove(r1.prompt, 'video', 1, '运镜')
  assert.equal(r2.changed, true)
  assert.equal(r2.removedCount, 1)
  assert.equal(r2.shiftedCount, 1)
  assert.equal(
    r2.prompt,
    '@[已移除:陈国栋] 在 @[图片1] 拿起 @[图片2]，并再次看向 @[已移除:陈国栋]；参考 @[已移除:运镜] 与 @[视频1]，配 @[音频1] 与 @[文本1] @[文本2]',
  )

  // Removing 文本1 -> 文本1 becomes 已移除:氛围, 文本2->文本1
  const r3 = remapPromptOnSlotRemove(r2.prompt, 'text', 1, '氛围')
  assert.equal(r3.changed, true)
  assert.equal(
    r3.prompt,
    '@[已移除:陈国栋] 在 @[图片1] 拿起 @[图片2]，并再次看向 @[已移除:陈国栋]；参考 @[已移除:运镜] 与 @[视频1]，配 @[音频1] 与 @[已移除:氛围] @[文本1]',
  )

  // Removing an unreferenced slot makes no change
  const r4 = remapPromptOnSlotRemove(r3.prompt, 'audio', 2, '未使用音频')
  assert.equal(r4.changed, false)
  assert.equal(r4.prompt, r3.prompt)
})

test('remapPromptOnReferenceReorder atomically swaps same-modality slots without double replacement', () => {
  const prev = [
    { id: 'img-a', kind: 'image' as const },
    { id: 'vid-a', kind: 'video' as const },
    { id: 'img-b', kind: 'image' as const },
    { id: 'txt-a', kind: 'text' as const },
  ]
  const next = [
    { id: 'img-b', kind: 'image' as const },
    { id: 'vid-a', kind: 'video' as const },
    { id: 'img-a', kind: 'image' as const },
    { id: 'txt-a', kind: 'text' as const },
  ]

  const res = remapPromptOnReferenceReorder(
    '@[图片1] 看向 @[图片2]，参考 @[视频1] 与 @[文本1]',
    prev,
    next,
  )
  assert.equal(res.changed, true)
  assert.equal(res.prompt, '@[图片2] 看向 @[图片1]，参考 @[视频1] 与 @[文本1]')

  // Reordering across different modalities without changing relative within-modality order is a no-op
  const crossModalOnly = [
    { id: 'vid-a', kind: 'video' as const },
    { id: 'img-a', kind: 'image' as const },
    { id: 'txt-a', kind: 'text' as const },
    { id: 'img-b', kind: 'image' as const },
  ]
  const noop = remapPromptOnReferenceReorder('@[图片1] 与 @[视频1]', prev, crossModalOnly)
  assert.equal(noop.changed, false)
  assert.equal(noop.prompt, '@[图片1] 与 @[视频1]')
})

test('removeStoryboardGridPromptBlock strips grid header and drive block without touching cuts', () => {
  const promptWithGrid = [
    '@[图片1] = 林晚',
    '@[图片2] = 美术教室',
    '@[图片3] = 分镜宫格（3×3）',
    '',
    '【分镜宫格驱动】',
    '@[图片3] 为 3×3 无字分镜宫格图，按从左到右、从上到下（格1→格9）依次对应本段各镜头构图：',
    '镜头1=格1–格2；镜头2=格3–格4；镜头3=格5。',
    '全程仅输出单画幅全屏连续镜头，严禁出现宫格分屏、黑边或画中画。',
    '',
    '【人物关系与构图逻辑】',
    '美术教室，大窗在左。林晚：站在讲台左侧。',
    '',
    '【镜头1｜0-5s】',
    '画面：女教师站在讲台前翻动教案。',
  ].join('\n')

  const stripped = removeStoryboardGridPromptBlock(promptWithGrid)
  assert.equal(stripped.changed, true)
  assert.equal(stripped.prompt.includes('【分镜宫格驱动】'), false)
  assert.equal(stripped.prompt.includes('分镜宫格'), false)
  assert.equal(stripped.prompt.includes('【镜头1｜0-5s】'), true)

  const remapped = remapPromptOnSlotRemove(stripped.prompt, 'image', 3, '分镜宫格（3×3）')
  assert.equal(remapped.removedCount, 0)
  assert.equal(remapped.prompt.includes('@[已移除:'), false)
})
