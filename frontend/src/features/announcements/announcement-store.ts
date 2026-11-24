import { acceptHMRUpdate, defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { computeUnreadIds, normalizeReadIds } from './announcement-helpers'

const STORAGE_PREFIX = 'kinoAnnouncementReads:'

export const useAnnouncementStore = defineStore('announcements', () => {
  const storageKey = ref('')
  const readIds = ref<number[]>([])
  const availableIds = ref<number[]>([])
  const loginChecked = ref(false)

  const unreadIds = computed(() => computeUnreadIds(availableIds.value, readIds.value))
  const unreadCount = computed(() => unreadIds.value.length)

  function persist() {
    if (!storageKey.value) return
    try {
      localStorage.setItem(storageKey.value, JSON.stringify(readIds.value))
    } catch {
      // Ignore storage quota/privacy restrictions; in-memory read state still works.
    }
  }

  function activate(userId: number, hostname: string) {
    const nextKey = `${STORAGE_PREFIX}${hostname}:${userId}`
    if (storageKey.value === nextKey) return
    let nextReadIds: number[] = []
    let nextLoginChecked = false
    try {
      const parsed: unknown = JSON.parse(localStorage.getItem(nextKey) ?? '[]')
      nextReadIds = normalizeReadIds(parsed)
    } catch {
      nextReadIds = []
    }
    try {
      nextLoginChecked = sessionStorage.getItem(`${nextKey}:prompted`) === '1'
    } catch {
      nextLoginChecked = false
    }
    storageKey.value = nextKey
    readIds.value = nextReadIds
    loginChecked.value = nextLoginChecked
  }

  function setAvailableIds(ids: number[]) {
    availableIds.value = ids
  }

  function isRead(id: number): boolean {
    return readIds.value.includes(id)
  }

  function markRead(id: number) {
    if (!isRead(id)) {
      readIds.value = [...readIds.value, id]
      persist()
    }
  }

  function claimLoginCheck(): boolean {
    if (loginChecked.value) return false
    loginChecked.value = true
    try {
      if (storageKey.value) {
        sessionStorage.setItem(`${storageKey.value}:prompted`, '1')
      }
    } catch {
      // Keep in-memory checked flag when sessionStorage is unavailable.
    }
    return true
  }

  function clearSession() {
    try {
      for (let i = sessionStorage.length - 1; i >= 0; i -= 1) {
        const key = sessionStorage.key(i)
        if (key?.startsWith(STORAGE_PREFIX) && key.endsWith(':prompted')) {
          sessionStorage.removeItem(key)
        }
      }
    } catch {
      // Ignore storage cleanup errors during logout.
    }
    storageKey.value = ''
    readIds.value = []
    availableIds.value = []
    loginChecked.value = false
  }

  return {
    storageKey,
    readIds,
    availableIds,
    unreadIds,
    unreadCount,
    loginChecked,
    activate,
    setAvailableIds,
    isRead,
    markRead,
    claimLoginCheck,
    clearSession,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useAnnouncementStore, import.meta.hot))
}
