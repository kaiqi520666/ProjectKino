import { defineStore } from 'pinia'
import {
  createUserAssetApi,
  deleteUserAssetApi,
  listUserAssetsApi,
  type UserAssetOut,
} from '@/features/canvas/api'
import { apiErrorMessage, uploadFileToOss } from '@/features/studio/api'
import {
  detectFileMediaKind,
  stripFileExtension,
  type UploadableMediaKind,
} from './asset-library-types'

let inflightFetch: Promise<UserAssetOut[]> | null = null

export interface UploadAssetsResult {
  uploaded: UserAssetOut[]
  failed: Array<{ name: string; reason: string }>
}

export const useUserAssetsStore = defineStore('userAssets', {
  state: () => ({
    items: [] as UserAssetOut[],
    loaded: false,
    loading: false,
    uploadingCount: 0,
  }),
  actions: {
    async ensureLoaded(force = false): Promise<UserAssetOut[]> {
      if (this.loaded && !force) return this.items
      if (inflightFetch && !force) return inflightFetch

      this.loading = true
      const task = listUserAssetsApi()
        .then((list) => {
          this.items = list
          this.loaded = true
          return list
        })
        .finally(() => {
          this.loading = false
          if (inflightFetch === task) inflightFetch = null
        })
      inflightFetch = task
      return task
    },

    upsertLocal(asset: UserAssetOut) {
      const idx = this.items.findIndex((item) => item.id === asset.id)
      if (idx >= 0) {
        this.items.splice(idx, 1, asset)
      } else {
        this.items.unshift(asset)
      }
    },

    async createAsset(body: Parameters<typeof createUserAssetApi>[0]): Promise<UserAssetOut> {
      const created = await createUserAssetApi(body)
      this.upsertLocal(created)
      this.loaded = true
      return created
    },

    async uploadFiles(
      files: readonly File[],
      allowedKinds: readonly UploadableMediaKind[] = ['image', 'video', 'audio'],
    ): Promise<UploadAssetsResult> {
      const uploaded: UserAssetOut[] = []
      const failed: Array<{ name: string; reason: string }> = []
      const allowedSet = new Set<UploadableMediaKind>(allowedKinds)

      this.uploadingCount += files.length
      try {
        for (const file of files) {
          const kind = detectFileMediaKind(file)
          if (!kind || !allowedSet.has(kind)) {
            failed.push({ name: file.name, reason: '不支持的文件格式' })
            continue
          }
          try {
            const oss = await uploadFileToOss(file, kind)
            const created = await createUserAssetApi({
              kind,
              title: stripFileExtension(file.name),
              mediaKey: oss.key,
              mediaUrl: oss.url,
              mediaName: file.name,
              sourceType: 'upload',
            })
            this.upsertLocal(created)
            this.loaded = true
            uploaded.push(created)
          } catch (error) {
            failed.push({ name: file.name, reason: apiErrorMessage(error) })
          }
        }
      } finally {
        this.uploadingCount = Math.max(0, this.uploadingCount - files.length)
      }

      return { uploaded, failed }
    },

    async removeAsset(id: string) {
      await deleteUserAssetApi(id)
      this.items = this.items.filter((item) => item.id !== id)
    },

    clear() {
      this.items = []
      this.loaded = false
      this.loading = false
      this.uploadingCount = 0
      inflightFetch = null
    },
  },
})
