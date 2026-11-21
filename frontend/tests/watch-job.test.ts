import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { JobOut } from '../src/features/studio/api-types.ts'
import { consumeSseBuffer, JobFailureError, watchJobStream } from '../src/features/studio/job-stream.ts'

function makeJob(overrides: Partial<JobOut>): JobOut {
  return {
    id: 'job-1',
    projectId: 'proj-1',
    jobType: 'generate_storyboard',
    targetId: null,
    status: 'running',
    stepIndex: 1,
    stepTotal: 2,
    stepLabel: '生成中',
    progress: 20,
    resultPayload: null,
    errorCode: null,
    errorMessage: null,
    usageSummary: null,
    createdAt: '2026-11-21T00:00:00Z',
    startedAt: null,
    finishedAt: null,
    ...overrides,
  }
}

function makeSseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk))
      }
      controller.close()
    },
  })
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

test('consumeSseBuffer splits CRLF/LF frames, ignores keepalives and malformed JSON, and keeps trailing partial frame', () => {
  const job1 = makeJob({ progress: 40 })
  const job2 = makeJob({ progress: 100, status: 'succeeded' })

  const raw = [
    ': keepalive\r\n\r\n',
    `event: progress\r\ndata: ${JSON.stringify(job1)}\r\n\r\n`,
    'data: {broken-json\n\n',
    `data: ${JSON.stringify(job2)}\n\n`,
    'data: {"id":"partial"',
  ].join('')

  const { events, rest } = consumeSseBuffer(raw)
  assert.equal(events.length, 2)
  assert.equal(events[0]!.progress, 40)
  assert.equal(events[1]!.status, 'succeeded')
  assert.equal(rest, 'data: {"id":"partial"')
})

test('watchJobStream streams chunked SSE frames and resolves on terminal succeeded job', async () => {
  const running = makeJob({ progress: 50, stepLabel: '拆分镜头中' })
  const done = makeJob({ progress: 100, status: 'succeeded', stepLabel: '完成' })
  const seen: number[] = []
  let pollCalls = 0

  const half = JSON.stringify(running)
  const result = await watchJobStream({
    fetchEvents: async () =>
      makeSseResponse([
        `data: ${half.slice(0, 20)}`,
        `${half.slice(20)}\n\ndata: ${JSON.stringify(done)}\n\n`,
      ]),
    fetchJob: async () => {
      pollCalls += 1
      return done
    },
    onProgress: (job) => seen.push(job.progress),
    pollIntervalMs: 5,
  })

  assert.equal(result.status, 'succeeded')
  assert.deepEqual(seen, [50, 100])
  assert.equal(pollCalls, 0)
})

test('watchJobStream classifies non-retryable vs retryable job failures accurately', async () => {
  const insufficient = makeJob({
    status: 'failed',
    errorCode: 'insufficient_credits',
    errorMessage: '积分不足',
  })

  await assert.rejects(
    () =>
      watchJobStream({
        fetchEvents: async () => makeSseResponse([`data: ${JSON.stringify(insufficient)}\n\n`]),
        fetchJob: async () => insufficient,
      }),
    (err: unknown) =>
      err instanceof JobFailureError
      && err.code === 'insufficient_credits'
      && err.retryable === false
      && err.message === '积分不足',
  )

  const transient = makeJob({
    status: 'failed',
    errorCode: 'upstream_timeout',
    errorMessage: '上游超时',
  })

  await assert.rejects(
    () =>
      watchJobStream({
        fetchEvents: async () => makeSseResponse([`data: ${JSON.stringify(transient)}\n\n`]),
        fetchJob: async () => transient,
      }),
    (err: unknown) =>
      err instanceof JobFailureError
      && err.code === 'upstream_timeout'
      && err.retryable === true,
  )
})

test('watchJobStream falls back to polling when SSE disconnects before reaching a terminal state', async () => {
  const progress1 = makeJob({ progress: 30 })
  const progress2 = makeJob({ progress: 70 })
  const done = makeJob({ progress: 100, status: 'succeeded' })
  const seen: number[] = []
  let pollAttempt = 0

  const result = await watchJobStream({
    fetchEvents: async () => makeSseResponse([`data: ${JSON.stringify(progress1)}\n\n`]),
    fetchJob: async () => {
      pollAttempt += 1
      return pollAttempt === 1 ? progress2 : done
    },
    onProgress: (job) => seen.push(job.progress),
    pollIntervalMs: 5,
  })

  assert.equal(result.status, 'succeeded')
  assert.equal(pollAttempt, 2)
  assert.deepEqual(seen, [30, 70, 100])
})
