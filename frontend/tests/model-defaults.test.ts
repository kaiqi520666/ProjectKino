import test from 'node:test'
import assert from 'node:assert/strict'
import type { ModelCatalogItemOut } from '../src/features/studio/api-types.ts'
import {
  isClipDurationExceededByModel,
  resolveDefaultImageModel,
  resolveDefaultVideoModel,
  resolveImageTierForModel,
} from '../src/features/studio/model-defaults.ts'

function videoModel(
  id: string,
  opts: { isDefault?: boolean; isDefaultLong?: boolean; maxDuration?: number } = {},
): ModelCatalogItemOut {
  return {
    id,
    mediaType: 'video',
    displayName: id,
    isDefault: Boolean(opts.isDefault),
    isDefaultLong: Boolean(opts.isDefaultLong),
    capabilities: { minDuration: 4, maxDuration: opts.maxDuration ?? 15 },
    defaults: { resolution: '720p' },
    imagePrices: [],
    videoPrices: [],
  }
}

function imageModel(
  id: string,
  opts: { isDefault?: boolean; tiers?: Array<'web' | '1k' | '2k' | '4k'>; defaultTier?: string } = {},
): ModelCatalogItemOut {
  return {
    id,
    mediaType: 'image',
    displayName: id,
    isDefault: Boolean(opts.isDefault),
    capabilities: {},
    defaults: opts.defaultTier ? { tier: opts.defaultTier } : {},
    imagePrices: (opts.tiers ?? ['web', '1k', '2k', '4k']).map((tier) => ({ tier, creditPrice: '1' })),
    videoPrices: [],
  }
}

test('resolveDefaultVideoModel selects 15s default vs 30s default and enforces 30s capability on preference', () => {
  const models = [
    videoModel('v15-default', { isDefault: true, maxDuration: 15 }),
    videoModel('v30-alt', { maxDuration: 30 }),
    videoModel('v30-default', { isDefaultLong: true, maxDuration: 30 }),
  ]

  assert.equal(resolveDefaultVideoModel(models, 15)?.id, 'v15-default')
  assert.equal(resolveDefaultVideoModel(models, 30)?.id, 'v30-default')
  assert.equal(resolveDefaultVideoModel(models, 30, 'v30-alt')?.id, 'v30-alt')
  // Rejects a preferred 15s model when segmentCap is 30s and falls back to 30s default
  assert.equal(resolveDefaultVideoModel(models, 30, 'v15-default')?.id, 'v30-default')
  // Falls back cleanly when preferred model was removed
  assert.equal(resolveDefaultVideoModel(models, 30, 'deleted-model')?.id, 'v30-default')
})

test('resolveDefaultImageModel and resolveImageTierForModel respect project preference and model tier availability', () => {
  const models = [
    imageModel('img-default', { isDefault: true, tiers: ['1k', '2k'], defaultTier: '1k' }),
    imageModel('img-pro', { tiers: ['2k', '4k'], defaultTier: '2k' }),
  ]

  assert.equal(resolveDefaultImageModel(models)?.id, 'img-default')
  assert.equal(resolveDefaultImageModel(models, 'img-pro')?.id, 'img-pro')
  assert.equal(resolveImageTierForModel(models[0], '2k'), '2k')
  assert.equal(resolveImageTierForModel(models[0], '4k'), '1k')
  assert.equal(resolveImageTierForModel(models[1], 'web'), '2k')
  assert.equal(resolveImageTierForModel(models[1], '4k'), '4k')
})

test('isClipDurationExceededByModel flags clips longer than model maxDuration', () => {
  const m15 = videoModel('v15', { maxDuration: 15 })
  const m30 = videoModel('v30', { maxDuration: 30 })

  assert.deepEqual(isClipDurationExceededByModel(27, m15), {
    exceeded: true,
    minDuration: 4,
    maxDuration: 15,
  })
  assert.deepEqual(isClipDurationExceededByModel(15, m15), {
    exceeded: false,
    minDuration: 4,
    maxDuration: 15,
  })
  assert.deepEqual(isClipDurationExceededByModel(27, m30), {
    exceeded: false,
    minDuration: 4,
    maxDuration: 30,
  })
})
