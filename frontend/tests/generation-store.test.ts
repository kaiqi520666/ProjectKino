import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import { formatElapsedSeconds, useGenerationStore } from '../src/stores/generation.ts'

test('formats elapsed seconds as zero-padded MM:SS', () => {
  assert.equal(formatElapsedSeconds(0), '00:00')
  assert.equal(formatElapsedSeconds(7.9), '00:07')
  assert.equal(formatElapsedSeconds(65), '01:05')
  assert.equal(formatElapsedSeconds(-5), '00:00')
})

test('runTask tracks running state, prevents re-entry, blocks dismiss while running, and closes on success', async () => {
  setActivePinia(createPinia())
  const store = useGenerationStore()

  let release!: (value: string) => void
  const pending = store.runTask(
    {
      title: '正在创建短剧剧本',
      steps: ['规划大纲', '写剧本'],
      successDelayMs: 0,
      successMessage: (value) => `完成：${value}`,
    },
    async (controls) => {
      controls.setStep(0, '规划大纲中')
      controls.setProgress(40)
      controls.setJobId('job-123')
      return await new Promise<string>((resolve) => {
        release = resolve
      })
    },
  )

  assert.equal(store.isOpen, true)
  assert.equal(store.isRunning, true)
  assert.equal(store.task?.activeStep, 0)
  assert.equal(store.task?.progress, 40)
  assert.equal(store.task?.jobId, 'job-123')
  assert.equal(store.dismiss(), false)

  // Concurrent invocation is ignored to avoid duplicate billing.
  const duplicate = await store.runTask({ title: '重复触发' }, async () => 'ignored')
  assert.equal(duplicate, undefined)
  assert.equal(store.task?.title, '正在创建短剧剧本')

  release('ok')
  const result = await pending
  assert.equal(result, 'ok')
  assert.equal(store.isOpen, false)
  assert.equal(store.task, null)
})

test('runTask keeps error overlay open on failure and supports guarded retry or dismiss', async () => {
  setActivePinia(createPinia())
  const store = useGenerationStore()

  let attempts = 0
  const first = await store.runTask(
    {
      title: '正在批量生成项目资产',
      successDelayMs: 0,
      formatError: (err) => (err instanceof Error ? err.message : String(err)),
      canRetryError: () => true,
    },
    async () => {
      attempts += 1
      if (attempts === 1) throw new Error('HTTP 502：上游模型暂时不可用')
      return 6
    },
  )

  assert.equal(first, undefined)
  assert.equal(store.task?.status, 'error')
  assert.equal(store.task?.error, 'HTTP 502：上游模型暂时不可用')
  assert.equal(store.task?.canRetry, true)

  const retried = await store.retry()
  assert.equal(retried, 6)
  assert.equal(attempts, 2)
  assert.equal(store.task, null)
})

test('non-retryable errors disable retry button and allow dismiss', async () => {
  setActivePinia(createPinia())
  const store = useGenerationStore()

  await store.runTask(
    {
      title: '正在创建短剧剧本',
      successDelayMs: 0,
      formatError: () => '故事内容不能为空。',
      canRetryError: () => false,
    },
    async () => {
      throw new Error('400')
    },
  )

  assert.equal(store.task?.status, 'error')
  assert.equal(store.task?.canRetry, false)
  assert.ok(store.task?.errorHint)
  assert.equal(await store.retry(), undefined)
  assert.equal(store.dismiss(), true)
  assert.equal(store.task, null)
})
