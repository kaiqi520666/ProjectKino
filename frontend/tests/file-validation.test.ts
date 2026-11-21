import assert from 'node:assert/strict'
import { test } from 'node:test'
import { validateFile } from '../src/lib/file-validation.ts'

const limit = 20 * 1024 * 1024
const formats = ['.txt', '.md', '.pdf']

test('accepts configured extensions, case insensitively, including exact size limit', () => {
  assert.equal(validateFile({ name: 'script.PDF', size: limit }, formats, limit), null)
  assert.equal(validateFile({ name: 'story.md', size: 12 }, formats, limit), null)
})

test('rejects empty, oversized and mismatched files', () => {
  assert.match(validateFile({ name: 'script.txt', size: 0 }, formats, limit)!, /文件为空/)
  assert.match(validateFile({ name: 'script.txt', size: limit + 1 }, formats, limit)!, /20 MB/)
  assert.match(validateFile({ name: 'script.pdf.exe', size: 12 }, formats, limit)!, /格式/)
})
