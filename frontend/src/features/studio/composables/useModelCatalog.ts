import { computed, ref } from 'vue'
import { getModelCatalog } from '../api'
import type { ModelCatalogItemOut, ModelCatalogOut } from '../api-types'

const catalog = ref<ModelCatalogOut | null>(null)
const loading = ref(false)
const error = ref('')
let inflight: Promise<ModelCatalogOut | null> | null = null

export function clearModelCatalogCache() {
  catalog.value = null
  error.value = ''
  inflight = null
}

async function fetchCatalog(force = false): Promise<ModelCatalogOut | null> {
  if (!force && catalog.value) return catalog.value
  if (inflight) return inflight

  loading.value = true
  error.value = ''
  inflight = (async () => {
    try {
      const data = await getModelCatalog()
      catalog.value = data
      return data
    } catch (err) {
      error.value = err instanceof Error && err.message ? err.message : '加载模型目录失败'
      return null
    } finally {
      loading.value = false
      inflight = null
    }
  })()
  return inflight
}

export function useModelCatalog() {
  const textModels = computed<ModelCatalogItemOut[]>(() => catalog.value?.text ?? [])
  const imageModels = computed<ModelCatalogItemOut[]>(() => catalog.value?.image ?? [])
  const videoModels = computed<ModelCatalogItemOut[]>(() => catalog.value?.video ?? [])
  const loaded = computed(() => catalog.value !== null)

  return {
    catalog,
    textModels,
    imageModels,
    videoModels,
    loading,
    error,
    loaded,
    ensureLoaded: () => fetchCatalog(false),
    refresh: () => fetchCatalog(true),
    clearCatalog: clearModelCatalogCache,
  }
}
