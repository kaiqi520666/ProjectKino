import type { RouteRecordRaw } from 'vue-router'

const pendingView = () => import('@/views/WorkspacePendingView.vue')

export const workspaceRoutes: RouteRecordRaw[] = [{
  path: '/workspace',
  component: () => import('@/layouts/WorkspaceLayout.vue'),
  children: [
    {
      path: '',
      name: 'workspace',
      component: () => import('@/features/dashboard/views/WorkspaceHomeView.vue'),
      meta: { title: '创作首页', workspaceNav: 'studio' },
    },
    { path: '/projects', name: 'projects', component: pendingView, meta: { title: '全部项目', workspaceNav: 'studio' } },
    {
      path: '/projects/:projectId',
      component: () => import('@/features/studio/views/StudioProjectView.vue'),
      meta: { workspaceNav: 'studio' },
      children: [
        { path: '', redirect: to => ({ name: 'studio-script', params: to.params }) },
        { path: 'script', name: 'studio-script', component: () => import('@/features/studio/views/StudioScriptView.vue'), meta: { title: '剧本确认' } },
        { path: 'assets', name: 'studio-assets', component: () => import('@/features/studio/views/StudioAssetsView.vue'), meta: { title: '资产生成' } },
        { path: 'storyboard', name: 'studio-storyboard', component: () => import('@/features/studio/views/StudioStoryboardView.vue'), meta: { title: '分镜制作' } },
        { path: 'storyboard/:episode([1-9][0-9]*)', name: 'studio-episode', component: () => import('@/features/studio/views/StudioEpisodeView.vue'), meta: { title: '单集分镜' } },
      ],
    },
    { path: '/canvas', name: 'canvas', component: () => import('@/features/canvas/views/CanvasListView.vue'), meta: { title: '画布', workspaceNav: 'canvas' } },
    { path: '/assets', name: 'assets', component: pendingView, meta: { title: '素材', workspaceNav: 'assets' } },
    { path: '/account', name: 'account', component: pendingView, meta: { title: '我的', workspaceNav: 'account' } },
  ],
}]
