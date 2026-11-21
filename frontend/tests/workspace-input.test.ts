import assert from 'node:assert/strict'
import { readdirSync } from 'node:fs'
import { test } from 'node:test'
import { wrapSlideIndex } from '../src/features/dashboard/components/carousel-index.ts'
import { storyMaxLength, validateStory } from '../src/features/studio/components/story-input.ts'
import { initialDramaSettings, resolveDramaSettings } from '../src/features/studio/components/drama-creation.ts'
import { artStyles, defaultArtStyle, quickArtStyles } from '../src/features/studio/components/art-styles.ts'

test('carousel wraps next and previous indices without exceeding the slide count', () => {
  assert.equal(wrapSlideIndex(3, 3), 0)
  assert.equal(wrapSlideIndex(-1, 3), 2)
  assert.equal(wrapSlideIndex(-7, 3), 2)
  assert.equal(wrapSlideIndex(0, 1), 0)
  assert.equal(wrapSlideIndex(1, 1), 0)
})

test('carousel handles an empty or invalid list and invalid indices', () => {
  for (const count of [0, -1, 1.5, NaN, Infinity]) assert.equal(wrapSlideIndex(2, count), 0)
  for (const index of [NaN, Infinity, -Infinity]) assert.equal(wrapSlideIndex(index, 3), 0)
})

test('story validation rejects whitespace and over-limit input without inventing a minimum length', () => {
  assert.match(validateStory(' \n\t')!, /请输入|请先输入/)
  assert.equal(validateStory('一'), null)
  assert.equal(validateStory('字'.repeat(storyMaxLength)), null)
  assert.match(validateStory('字'.repeat(storyMaxLength + 1))!, /不能超过/)
})

test('short drama requires valid project settings', () => {
  const draft = { ...initialDramaSettings(), name: ' Night Files ' }
  assert.deepEqual(resolveDramaSettings(draft), { ...draft, name: 'Night Files' })
  assert.equal(resolveDramaSettings({ ...draft, name: '   ' }), null)
  assert.equal(resolveDramaSettings({ ...draft, language: '' }), null)
  assert.equal(resolveDramaSettings({ ...draft, visualStyle: '' }), null)
})

test('short drama defaults to a 15-second segment cap and supports 30 seconds', () => {
  const draft = { ...initialDramaSettings(), name: 'Night Files' }
  assert.equal(resolveDramaSettings(draft)?.maxSegmentDuration, 15)
  assert.equal(resolveDramaSettings({ ...draft, maxSegmentDuration: 30 })?.maxSegmentDuration, 30)
  assert.equal(resolveDramaSettings({ ...draft, maxSegmentDuration: 20 as typeof draft.maxSegmentDuration }), null)
})

test('short drama keeps the user-defined episode count and rejects invalid counts', () => {
  const draft = { ...initialDramaSettings(), name: 'Night Files' }
  assert.equal(resolveDramaSettings({ ...draft, episodeCount: 7 })?.episodeCount, 7)
  for (const episodeCount of ['', 0, -2, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1] as const) {
    assert.equal(resolveDramaSettings({ ...draft, episodeCount }), null)
  }
})

test('the style catalog has a local preview for each pure visual style and defaults to live-action', () => {
  const assets = new Set(readdirSync(new URL('../public/images/art-styles/', import.meta.url)))
  const expected = artStyles.map(({ value }) => `${value}.webp`)
  assert.equal(new Set(expected).size, expected.length)
  for (const file of expected) {
    assert.ok(assets.has(file), `missing preview asset: ${file}`)
  }
  assert.ok(artStyles.every(({ prompt }) => prompt.trim().length > 0))
  assert.deepEqual(quickArtStyles.map(({ label }) => label), ['真人电影写实', '半写实 3D', '日漫'])
  assert.equal(defaultArtStyle, 'live-action')
  assert.equal(initialDramaSettings().visualStyle, defaultArtStyle)
})
