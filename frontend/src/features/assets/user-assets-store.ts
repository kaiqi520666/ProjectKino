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
import {
  findMatchingUserAssets,
  planBatchLibraryCollect,
  type CollectableMediaKind,
  type MediaCollectCandidate,
} from './user-assets-helpers'

let inflightFetch: Promise<UserAssetOut[]> | null = null

export interface UploadAssetsResult {
  uploaded: UserAssetOut[]
  failed: Array<{ name: string; reason: string }>
}

export interface BatchCollectAssetsResult {
  added: number
  skippedExisting: number
  skippedEmpty: number
  failed: number
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

    findByMedia(
      kind: CollectableMediaKind,
      mediaUrl?: string | null,
      mediaKey?: string | null,
    ): UserAssetOut | undefined {
      return findMatchingUserAssets(this.items, { kind, mediaUrl, mediaKey })[0]
    },

    isSaved(
      kind: CollectableMediaKind,
      mediaUrl?: string | null,
      mediaKey?: string | null,
    ): boolean {
      return Boolean(this.findByMedia(kind, mediaUrl, mediaKey))
    },

    async toggleMediaAsset(
      input: MediaCollectCandidate & { mediaUrl: string },
    ): Promise<{ saved: boolean; asset?: UserAssetOut }> {
      if (!this.loaded) {
        await this.ensureLoaded()
      }
      const matches = findMatchingUserAssets(this.items, {
        kind: input.kind,
        mediaUrl: input.mediaUrl,
        mediaKey: input.mediaKey ?? null,
      })
      if (matches.length > 0) {
        for (const existing of matches) {
          await this.removeAsset(existing.id)
        }
        return { saved: false, asset: matches[0] }
      }
      const created = await this.createAsset({
        kind: input.kind,
        title: input.title,
        mediaUrl: input.mediaUrl,
        mediaKey: input.mediaKey ?? null,
        mediaName: input.mediaName ?? null,
        sourceType: input.sourceType ?? 'studio',
        sourceId: input.sourceId ?? null,
      })
      return { saved: true, asset: created }
    },

    async collectBatchMediaAssets(
      candidates: readonly MediaCollectCandidate[],
    ): Promise<BatchCollectAssetsResult> {
      if (!this.loaded) {
        await this.ensureLoaded()
      }
      const plan = planBatchLibraryCollect(candidates, this.items)
      let added = 0
      let failed = 0
      for (const item of plan.toAdd) {
        try {
          await this.createAsset({
            kind: item.kind,
            title: item.title,
            mediaUrl: item.mediaUrl,
            mediaKey: item.mediaKey ?? null,
            mediaName: item.mediaName ?? null,
            sourceType: item.sourceType ?? 'studio',
            sourceId: item.sourceId ?? null,
          })
          added += 1
        } catch {
          failed += 1
        }
      }
      return {
        added,
        skippedExisting: plan.skippedExisting,
        skippedEmpty: plan.skippedEmpty,
        failed,
      }
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
