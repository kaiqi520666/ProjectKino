import { acceptHMRUpdate, defineStore } from 'pinia'
import { ref } from 'vue'

export type NoticeTone = 'success' | 'error' | 'info'

export const useUiStore = defineStore('ui', () => {
  const notices = ref<{ id: string; title: string; description?: string; tone: NoticeTone }[]>([])

  function notify(title: string, tone: NoticeTone = 'success', description?: string) {
    const id = crypto.randomUUID()
    notices.value = [...notices.value.slice(-3), { id, title, tone, description }]
    return id
  }

  function dismiss(id: string) {
    notices.value = notices.value.filter((notice) => notice.id !== id)
  }

  return { notices, notify, dismiss }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useUiStore, import.meta.hot))
}
