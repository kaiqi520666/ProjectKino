import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createMemoryHistory, createRouter } from 'vue-router'
import { shouldTriggerUnauthorized } from '../src/lib/http.ts'
import { adminRoutes } from '../src/router/admin.ts'
import { canvasEditorRoute } from '../src/router/canvas.ts'
import { workspaceRoutes } from '../src/router/workspace.ts'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [...workspaceRoutes, ...adminRoutes, canvasEditorRoute],
})

test('workspace pages share a layout without requiring a workspace URL prefix', () => {
  for (const [path, name, navigation] of [
    ['/workspace', 'workspace', 'studio'],
    ['/projects', 'projects', 'studio'],
    ['/canvas', 'canvas', 'canvas'],
    ['/assets', 'assets', 'assets'],
    ['/account', 'account', 'account'],
  ]) {
    const route = router.resolve(path!)
    assert.equal(route.name, name)
    assert.equal(route.matched.length, 2)
    assert.equal(route.matched[0]!.path, '/workspace')
    assert.equal(route.meta.workspaceNav, navigation)
  }
})

test('named navigation resolves to the agreed short URLs', () => {
  assert.equal(router.resolve({ name: 'canvas' }).path, '/canvas')
  assert.equal(router.resolve({ name: 'assets' }).path, '/assets')
  assert.equal(router.resolve({ name: 'account' }).path, '/account')
})

test('the canvas editor resolves outside the workspace layout', () => {
  const route = router.resolve({ name: 'canvas-editor', params: { canvasId: '1' } })
  assert.equal(route.path, '/canvas/1')
  assert.equal(route.matched.length, 1)
})

test('studio steps and episode detail are scoped under one project', () => {
  for (const [name, suffix] of [
    ['studio-script', 'script'],
    ['studio-assets', 'assets'],
    ['studio-storyboard', 'storyboard'],
    ['studio-episode', 'storyboard/3'],
  ] as const) {
    const params = name === 'studio-episode' ? { projectId: 'draft-1', episode: 3 } : { projectId: 'draft-1' }
    const route = router.resolve({ name, params })
    assert.equal(route.path, `/projects/draft-1/${suffix}`)
    assert.equal(route.meta.workspaceNav, 'studio')
  }
})

test('protected workspace, canvas, and admin routes carry auth and role meta', () => {
  for (const path of ['/workspace', '/projects', '/projects/p1/script', '/canvas', '/canvas/c1', '/assets', '/account']) {
    const resolved = router.resolve(path)
    assert.equal(
      resolved.matched.some((record) => record.meta.requiresAuth === true),
      true,
      `${path} should require auth`,
    )
  }

  for (const path of ['/admin', '/admin/users', '/admin/models', '/admin/jobs', '/admin/projects', '/admin/settings']) {
    const resolved = router.resolve(path)
    assert.equal(
      resolved.matched.some((record) => record.meta.requiresAuth === true),
      true,
      `${path} should require auth`,
    )
    assert.equal(
      resolved.matched.some((record) => record.meta.requiresAdmin === true),
      true,
      `${path} should require admin`,
    )
  }
})

test('401 unauthorized trigger skips auth endpoints and explicit opt-outs', () => {
  assert.equal(shouldTriggerUnauthorized('/auth/login'), false)
  assert.equal(shouldTriggerUnauthorized('/auth/register'), false)
  assert.equal(shouldTriggerUnauthorized('/auth/logout'), false)
  assert.equal(shouldTriggerUnauthorized('/api/v1/auth/logout?force=1'), false)
  assert.equal(shouldTriggerUnauthorized('/users/me', true), false)
  assert.equal(shouldTriggerUnauthorized('/projects'), true)
  assert.equal(shouldTriggerUnauthorized('/credits/balance'), true)
})
