import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { fetchArtStyles, type ArtStyleItem } from './api'

export const useArtStylesStore = defineStore('art-styles', () => {
  const items = ref<ArtStyleItem[]>([])
  const loaded = ref(false)
  const loading = ref(false)
  const error = ref('')
  let inflight: Promise<ArtStyleItem[]> | null = null

  const enabledStyles = computed(() => items.value.filter((item) => item.isEnabled))
  const quickStyles = computed(() => enabledStyles.value.slice(0, 3))
  const defaultStyle = computed<ArtStyleItem | null>(
    () => enabledStyles.value.find((item) => item.isDefault) ?? enabledStyles.value[0] ?? items.value[0] ?? null,
  )
  const defaultCode = computed(() => defaultStyle.value?.code ?? 'live-action')
  const byCode = computed(() => new Map(items.value.map((item) => [item.code, item])))

  async function ensureLoaded(force = false): Promise<ArtStyleItem[]> {
    if (loaded.value && !force) return items.value
    if (inflight && !force) return inflight

    loading.value = true
    error.value = ''
    const request = fetchArtStyles()
      .then((res) => {
        items.value = res.items
        loaded.value = true
        return res.items
      })
      .catch((err: unknown) => {
        error.value = err instanceof Error ? err.message : '加载画风列表失败'
        return items.value
      })
      .finally(() => {
        loading.value = false
        if (inflight === request) inflight = null
      })

    inflight = request
    return request
  }

  function refresh() {
    return ensureLoaded(true)
  }

  function clear() {
    items.value = []
    loaded.value = false
    error.value = ''
    inflight = null
  }

  function getByCode(code?: string | null): ArtStyleItem | undefined {
    if (!code) return undefined
    return byCode.value.get(code)
  }

  function getLabel(code?: string | null): string {
    if (!code) return defaultStyle.value?.label ?? '真人电影写实'
    return byCode.value.get(code)?.label || code
  }

  function getPrompt(code?: string | null): string {
    if (!code) return defaultStyle.value?.prompt ?? ''
    return byCode.value.get(code)?.prompt ?? ''
  }

  function getCoverUrl(code?: string | null): string {
    if (code) {
      const matched = byCode.value.get(code)
      if (matched?.imageUrl) return matched.imageUrl
    }
    return defaultStyle.value?.imageUrl ?? ''
  }

  return {
    items,
    loaded,
    loading,
    error,
    enabledStyles,
    quickStyles,
    defaultStyle,
    defaultCode,
    byCode,
    ensureLoaded,
    refresh,
    clear,
    getByCode,
    getLabel,
    getPrompt,
    getCoverUrl,
  }
})
