import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import { setUnauthorizedHandler } from './lib/http'
import { useAuthStore } from './stores/auth'
import { useUiStore } from './stores/ui'
import { clearModelCatalogCache } from './features/studio/composables/useModelCatalog'
import { useCanvasStore } from './features/canvas/canvas-store'
import { useStudioStore } from './features/studio/studio-store'
import './styles/index.css'

const pinia = createPinia()
const app = createApp(App).use(pinia).use(router)

let handlingUnauthorized = false

setUnauthorizedHandler(() => {
  const auth = useAuthStore(pinia)
  const studio = useStudioStore(pinia)
  const canvas = useCanvasStore(pinia)
  const current = router.currentRoute.value
  const onProtectedRoute = current.matched.some((record) => record.meta.requiresAuth)
  auth.clearSession()
  studio.clearProjects()
  canvas.clearAll()
  clearModelCatalogCache()
  if (!onProtectedRoute || handlingUnauthorized) return

  handlingUnauthorized = true
  useUiStore(pinia).notify('登录已过期，请重新登录', 'error')
  void router.replace({ name: 'login', query: { next: current.fullPath } }).finally(() => {
    handlingUnauthorized = false
  })
})

app.mount('#app')