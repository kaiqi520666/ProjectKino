import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildAcceptAttribute,
  detectFileMediaKind,
  isHttpMediaUrl,
  stripFileExtension,
} from '../src/features/assets/asset-library-types.ts'

test('detectFileMediaKind classifies image, video, and audio by MIME or extension fallback', () => {
  assert.equal(detectFileMediaKind({ name: 'hero.png', type: 'image/png' } as File), 'image')
  assert.equal(detectFileMediaKind({ name: 'clip.mp4', type: 'video/mp4' } as File), 'video')
  assert.equal(detectFileMediaKind({ name: 'bgm.flac', type: '' } as File), 'audio')
  assert.equal(detectFileMediaKind({ name: 'shot.mov', type: '' } as File), 'video')
  assert.equal(detectFileMediaKind({ name: 'notes.txt', type: 'text/plain' } as File), null)
})

test('buildAcceptAttribute, stripFileExtension, and isHttpMediaUrl handle edge cases cleanly', () => {
  assert.equal(buildAcceptAttribute(['image', 'video', 'audio', 'text']), 'image/*,video/*,audio/*')
  assert.equal(buildAcceptAttribute(['image']), 'image/*')
  assert.equal(stripFileExtension('雨夜镜头.final.mp4'), '雨夜镜头.final')
  assert.equal(stripFileExtension('.hidden'), '.hidden')
  assert.equal(isHttpMediaUrl('https://cdn.example.com/a.png'), true)
  assert.equal(isHttpMediaUrl('blob:http://localhost:5173/1'), false)
})
