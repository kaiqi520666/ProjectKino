import assert from 'node:assert/strict'
import test from 'node:test'
import { formatJobSpec, readLlmCreditCost } from '../src/features/admin/job-spec.ts'

test('formatJobSpec extracts model name, tier, and ratio for image jobs', () => {
  const spec = formatJobSpec(
    {
      jobType: 'asset_image',
      inputPayload: { modelId: 'gpt-image-2', tier: '2k', ratio: '16:9' },
      resultPayload: null,
      usageSummary: null,
    },
    { 'gpt-image-2': 'GPT Image 2' },
  )
  assert.deepEqual(spec, {
    title: 'GPT Image 2',
    meta: ['2K', '16:9'],
  })
})

test('formatJobSpec extracts video model, resolution, ratio, actual duration, and reference count', () => {
  const spec = formatJobSpec(
    {
      jobType: 'clip_video',
      inputPayload: {
        modelId: 'seedance-2.0',
        resolution: '720p',
        ratio: '16:9',
        durationSeconds: 10,
        referenceUrls: ['https://a.jpg', 'https://b.jpg', 'https://c.jpg', 'https://d.jpg'],
      },
      resultPayload: {
        modelId: 'seedance-2.0',
        resolution: '720p',
        duration: 11.1,
      },
      usageSummary: null,
    },
    { 'seedance-2.0': 'Seedance 2.0' },
  )
  assert.deepEqual(spec, {
    title: 'Seedance 2.0',
    meta: ['720p', '16:9', '11.1s', '4参考图'],
  })
})

test('formatJobSpec formats episode compose and LLM token specs cleanly', () => {
  const compose = formatJobSpec({
    jobType: 'episode_compose',
    inputPayload: { episodeNumber: 2, clipCount: 6 },
    resultPayload: { composedDuration: 68.5 },
    usageSummary: null,
  })
  assert.deepEqual(compose, {
    title: '第 2 集合成',
    meta: ['6 片段', '68.5s'],
  })

  const llm = formatJobSpec(
    {
      jobType: 'storyboard_generate',
      inputPayload: { episodeNumber: 1 },
      resultPayload: null,
      usageSummary: {
        modelId: 'or-ds-baidu',
        inputTokens: 12460,
        outputTokens: 6800,
        cacheReadTokens: 8100,
        cost: '0.0362',
      },
    },
    { 'or-ds-baidu': 'DeepSeek V4.1 Flash' },
  )
  assert.deepEqual(llm, {
    title: 'DeepSeek V4.1 Flash',
    meta: ['第 1 集', '入 12.5k / 出 6.8k', '缓存 8.1k'],
  })
  assert.equal(readLlmCreditCost({ cost: '0.0362' }), '0.04')
  assert.equal(readLlmCreditCost({ cost: '0.0045' }), '0.0045')
  assert.equal(readLlmCreditCost({ cost: '0' }), null)
})

test('formatJobSpec supports canvas_image, canvas_video, and canvas_text jobs', () => {
  const img = formatJobSpec(
    {
      jobType: 'canvas_image',
      inputPayload: { modelId: 'cangyuan-pro', tier: '1k', ratio: '9:16' },
      resultPayload: null,
      usageSummary: null,
    },
    { 'cangyuan-pro': '苍渊 Pro' },
  )
  assert.deepEqual(img, {
    title: '苍渊 Pro',
    meta: ['1K', '9:16'],
  })

  const vid = formatJobSpec(
    {
      jobType: 'canvas_video',
      inputPayload: {
        modelId: 'seedance-2.0',
        resolution: '1080p',
        ratio: '16:9',
        durationSeconds: 8,
        referenceUrls: ['https://a.jpg', 'https://b.jpg'],
      },
      resultPayload: { duration: 8.0 },
      usageSummary: null,
    },
    { 'seedance-2.0': 'Seedance 2.0' },
  )
  assert.deepEqual(vid, {
    title: 'Seedance 2.0',
    meta: ['1080p', '16:9', '8s', '2参考图'],
  })

  const txt = formatJobSpec(
    {
      jobType: 'canvas_text',
      inputPayload: { modelId: 'deepseek-chat' },
      resultPayload: null,
      usageSummary: { modelId: 'deepseek-chat', inputTokens: 820, outputTokens: 1500 },
    },
    { 'deepseek-chat': 'DeepSeek' },
  )
  assert.deepEqual(txt, {
    title: 'DeepSeek',
    meta: ['入 820 / 出 1.5k'],
  })
})
