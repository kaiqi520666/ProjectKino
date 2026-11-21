import type { RouteRecordRaw } from 'vue-router'

export const adminRoutes: RouteRecordRaw[] = [
  {
    path: '/admin',
    component: () => import('@/layouts/WorkspaceLayout.vue'),
    meta: { requiresAdmin: true, workspaceNav: 'admin' },
    children: [
      {
        path: '',
        name: 'admin-overview',
        meta: { title: '概览', adminNav: 'overview', workspaceNav: 'admin', requiresAdmin: true },
        component: () => import('@/features/admin/views/AdminOverviewView.vue'),
      },
      {
        path: 'users',
        name: 'admin-users',
        meta: { title: '用户与积分', adminNav: 'users', workspaceNav: 'admin', requiresAdmin: true },
        component: () => import('@/features/admin/views/AdminUsersView.vue'),
      },
      {
        path: 'jobs',
        name: 'admin-jobs',
        meta: { title: '任务与核对', adminNav: 'jobs', workspaceNav: 'admin', requiresAdmin: true },
        component: () => import('@/features/admin/views/AdminJobsView.vue'),
      },
      {
        path: 'models',
        name: 'admin-models',
        meta: { title: '供应商与定价', adminNav: 'models', workspaceNav: 'admin', requiresAdmin: true },
        component: () => import('@/features/admin/views/AdminModelsView.vue'),
      },
      {
        path: 'settings',
        name: 'admin-settings',
        meta: { title: '系统与 OSS', adminNav: 'settings', workspaceNav: 'admin', requiresAdmin: true },
        component: () => import('@/features/admin/views/AdminSettingsView.vue'),
      },
      {
        path: 'projects',
        name: 'admin-projects',
        meta: { title: '项目与清理', adminNav: 'projects', workspaceNav: 'admin', requiresAdmin: true },
        component: () => import('@/features/admin/views/AdminProjectsView.vue'),
      },
    ],
  },
]
