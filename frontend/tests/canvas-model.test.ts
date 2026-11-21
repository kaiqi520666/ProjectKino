import assert from 'node:assert/strict'
import test from 'node:test'
import {
  canConnectCanvasKinds,
  computeCanvasMediaBox,
  createCanvasNode,
  hydrateCanvasGraph,
  isPersistedMediaUrl,
  MAX_CANVAS_NODE_HISTORY,
  parseCanvasRatio,
  serializeCanvasGraph,
} from '../src/features/canvas/canvas-model.ts'

test('isPersistedMediaUrl allows https/http/relative URLs and blocks blob/data URLs', () => {
  assert.equal(isPersistedMediaUrl('https://image.nodepass.net/framedrama/1/a.png'), true)
  assert.equal(isPersistedMediaUrl('http://127.0.0.1:8000/a.png'), true)
  assert.equal(isPersistedMediaUrl('/images/workspace/banner-story.jpg'), true)
  assert.equal(isPersistedMediaUrl('blob:http://127.0.0.1:5173/abc'), false)
  assert.equal(isPersistedMediaUrl('data:image/png;base64,AAAA'), false)
  assert.equal(isPersistedMediaUrl(''), false)
})

test('serializeCanvasGraph strips Vue Flow runtime props, blob URLs, dangling edges, and caps history', () => {
  const history = Array.from({ length: 25 }, (_, i) => ({
    url: `https://example.com/${i}.png`,
    name: `${i}.png`,
  }))
  const n1 = {
    ...createCanvasNode('n1', 'image-generation', 12.345, 98.765, {
      title: '主视觉',
      prompt: '雨夜 {{ref:n2}}',
      media: { url: 'blob:http://localhost/tmp', name: 'tmp.png' },
      history,
      settings: { modelId: 'gpt-image-2', tier: '2k', ratio: '16:9' },
    }),
    selected: true,
    dragging: true,
  }
  const n2 = createCanvasNode('n2', 'text', 0, 0, { text: '凌晨档案室' })

  const serialized = serializeCanvasGraph(
    [n1, n2],
    [
      { id: 'e1', source: 'n2', target: 'n1' },
      { id: 'e-dup', source: 'n2', target: 'n1' },
      { id: 'e-dangling', source: 'missing', target: 'n1' },
    ],
  )

  assert.equal(serialized.nodes.length, 2)
  assert.equal('selected' in serialized.nodes[0]!, false)
  assert.equal('dragging' in serialized.nodes[0]!, false)
  assert.deepEqual(serialized.nodes[0]!.position, { x: 12.35, y: 98.77 })
  assert.equal(serialized.nodes[0]!.data.media, undefined)
  assert.equal(serialized.nodes[0]!.data.history?.length, MAX_CANVAS_NODE_HISTORY)
  assert.equal(serialized.nodes[0]!.data.history?.[0]?.name, '5.png')
  assert.equal(serialized.edges.length, 1)
  assert.equal(serialized.edges[0]?.id, 'e1')

  const hydrated = hydrateCanvasGraph(serialized)
  assert.equal(hydrated.nodes.length, 2)
  assert.equal(hydrated.nodes[1]?.data.text, '凌晨档案室')
  assert.equal(hydrated.edges.length, 1)
})

test('canConnectCanvasKinds enforces valid media/generation connection rules', () => {
  assert.equal(canConnectCanvasKinds('text', 'image-generation'), true)
  assert.equal(canConnectCanvasKinds('image', 'image-generation'), true)
  assert.equal(canConnectCanvasKinds('video', 'image-generation'), false)
  assert.equal(canConnectCanvasKinds('video', 'video-generation'), true)
  assert.equal(canConnectCanvasKinds('image', 'video-generation'), true)
})

test('parseCanvasRatio and computeCanvasMediaBox preserve aspect ratio across landscape, square, and portrait', () => {
  assert.equal(parseCanvasRatio('16:9'), 16 / 9)
  assert.equal(parseCanvasRatio('9:16'), 9 / 16)
  assert.equal(parseCanvasRatio('auto'), null)

  const landscape = computeCanvasMediaBox(16 / 9)
  assert.ok(landscape.width > landscape.height)
  assert.ok(Math.abs(landscape.width / landscape.height - 16 / 9) < 0.03)

  const portrait = computeCanvasMediaBox(9 / 16)
  assert.ok(portrait.height > portrait.width)
  assert.ok(Math.abs(portrait.width / portrait.height - 9 / 16) < 0.03)

  const square = computeCanvasMediaBox(1)
  assert.equal(square.width, square.height)

  const ultrawide = computeCanvasMediaBox(21 / 9)
  assert.ok(ultrawide.width > landscape.width)
  assert.ok(Math.abs(ultrawide.width / ultrawide.height - 21 / 9) < 0.04)
})
