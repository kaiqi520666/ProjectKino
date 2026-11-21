import type { RouteRecordRaw } from 'vue-router'

export const canvasEditorRoute: RouteRecordRaw = {
  path: '/canvas/:canvasId',
  name: 'canvas-editor',
  component: () => import('@/features/canvas/views/CanvasEditorView.vue'),
  props: true,
  meta: { title: '画布编辑', requiresAuth: true },
}
