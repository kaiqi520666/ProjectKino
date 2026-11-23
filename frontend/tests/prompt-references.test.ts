import assert from 'node:assert/strict'
import test from 'node:test'
import {
  formatPromptToken,
  hasPromptToken,
  parsePromptLine,
  remapStudioPromptOnSlotRemove,
} from '../src/components/business/prompt-references.ts'

test('parsePromptLine parses canvas and studio tokens including removed markers', () => {
  assert.deepEqual(parsePromptLine('镜头推进 {{ref:img-1}} 与 {{ref:vid_2}}', 'canvas'), [
    { type: 'text', text: '镜头推进 ' },
    { type: 'ref', tokenKey: 'img-1' },
    { type: 'text', text: ' 与 ' },
    { type: 'ref', tokenKey: 'vid_2' },
  ])

  assert.deepEqual(
    parsePromptLine('@[图片1]走进@[图片2]，参考@[视频1]运镜，配@[音频1]和@[已移除:旧道具]', 'studio'),
    [
      { type: 'ref', tokenKey: '图片1' },
      { type: 'text', text: '走进' },
      { type: 'ref', tokenKey: '图片2' },
      { type: 'text', text: '，参考' },
      { type: 'ref', tokenKey: '视频1' },
      { type: 'text', text: '运镜，配' },
      { type: 'ref', tokenKey: '音频1' },
      { type: 'text', text: '和' },
      { type: 'ref', tokenKey: '', removedLabel: '旧道具' },
    ],
  )
})

test('formatPromptToken and hasPromptToken handle both syntaxes cleanly', () => {
  assert.equal(formatPromptToken('node-1', 'canvas'), '{{ref:node-1}}')
  assert.equal(formatPromptToken('图片2', 'studio'), '@[图片2]')
  assert.equal(formatPromptToken('', 'studio', '陈国栋]'), '@[已移除:陈国栋]')
  assert.equal(hasPromptToken('包含 @[视频1]', 'studio'), true)
  assert.equal(hasPromptToken('包含 @[已移除:旧图]', 'studio'), true)
  assert.equal(hasPromptToken('纯文本', 'studio'), false)
  assert.equal(hasPromptToken('包含 {{ref:a1}}', 'canvas'), true)
})

test('remapStudioPromptOnSlotRemove shifts only same-modality higher slots and marks removed slot', () => {
  const prompt = '@[图片1] 在 @[图片2] 拿起 @[图片3]，并再次看向 @[图片1]；参考 @[视频1] 与 @[视频2]，配 @[音频1]'

  // Removing 图片1 -> 图片1 becomes 已移除:陈国栋, 图片2->图片1, 图片3->图片2; 视频 & 音频 untouched
  const r1 = remapStudioPromptOnSlotRemove(prompt, 'image', 1, '陈国栋')
  assert.equal(r1.changed, true)
  assert.equal(r1.removedCount, 2)
  assert.equal(r1.shiftedCount, 2)
  assert.equal(
    r1.prompt,
    '@[已移除:陈国栋] 在 @[图片1] 拿起 @[图片2]，并再次看向 @[已移除:陈国栋]；参考 @[视频1] 与 @[视频2]，配 @[音频1]',
  )

  // Removing 视频1 -> 视频1 becomes 已移除:运镜, 视频2->视频1; 图片 & 音频 untouched
  const r2 = remapStudioPromptOnSlotRemove(r1.prompt, 'video', 1, '运镜')
  assert.equal(r2.changed, true)
  assert.equal(r2.removedCount, 1)
  assert.equal(r2.shiftedCount, 1)
  assert.equal(
    r2.prompt,
    '@[已移除:陈国栋] 在 @[图片1] 拿起 @[图片2]，并再次看向 @[已移除:陈国栋]；参考 @[已移除:运镜] 与 @[视频1]，配 @[音频1]',
  )

  // Removing an unreferenced slot makes no change
  const r3 = remapStudioPromptOnSlotRemove(r2.prompt, 'audio', 2, '未使用音频')
  assert.equal(r3.changed, false)
  assert.equal(r3.prompt, r2.prompt)
})
