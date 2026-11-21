import { createRouter, createWebHistory } from 'vue-router'
import { adminRoutes } from './admin'
import { canvasEditorRoute } from './canvas'
import { workspaceRoutes } from './workspace'

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  scrollBehavior(to, _from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.hash) {
      return { el: to.hash, top: 88, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' }
    }
    return { top: 0 }
  },
  routes: [
    { path: '/', name: 'home', component: () => import('@/views/HomeView.vue') },
    { path: '/login', name: 'login', component: () => import('@/views/AuthView.vue') },
    { path: '/register', redirect: to => ({ path: '/login', query: { ...to.query, mode: 'register' } }) },
    ...workspaceRoutes,
    ...adminRoutes,
    canvasEditorRoute,
    ...(import.meta.env.DEV ? [{
          path: '/__dev/components',
          name: 'component-preview',
          component: () => import('@/dev/ComponentPreview.vue'),
        }] : []),
  ],
})
