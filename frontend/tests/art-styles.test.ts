import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  computeFitDimensions,
  replaceFileExtWithWebp,
} from '../src/features/art-styles/webp-compress.ts'

test('computeFitDimensions scales oversized images proportionally and preserves small ones', () => {
  assert.deepEqual(computeFitDimensions(1920, 1080, 960, 540), { width: 960, height: 540 })
  assert.deepEqual(computeFitDimensions(2000, 1000, 960, 540), { width: 960, height: 480 })
  assert.deepEqual(computeFitDimensions(1000, 1000, 960, 540), { width: 540, height: 540 })
  assert.deepEqual(computeFitDimensions(640, 360, 960, 540), { width: 640, height: 360 })
})

test('replaceFileExtWithWebp normalizes uploaded filenames to .webp', () => {
  assert.equal(replaceFileExtWithWebp('ink-painting.png'), 'ink-painting.webp')
  assert.equal(replaceFileExtWithWebp('photo.final.JPEG'), 'photo.final.webp')
  assert.equal(replaceFileExtWithWebp('noext'), 'noext.webp')
  assert.equal(replaceFileExtWithWebp('   '), 'art-style.webp')
})
