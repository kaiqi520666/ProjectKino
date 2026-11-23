<script setup lang="ts">
import type { Component } from 'vue'
import { Boxes } from 'lucide-vue-next'
import ImagePreview from '@/components/ui/ImagePreview.vue'
import type { StudioAssetKind } from '../studio-assets'

export interface EpisodeAssetGroup {
  kind: StudioAssetKind
  label: string
  icon: Component
  assets: Array<{ id: string; name: string; imageUrl?: string }>
}

defineProps<{
  hasAssets: boolean
  groups: EpisodeAssetGroup[]
}>()
</script>

<template>
  <aside class="episode-assets" aria-labelledby="episode-assets-title">
    <h2 id="episode-assets-title"><Boxes :size="17" aria-hidden="true" />本集资产</h2>
    <p v-if="!hasAssets" class="episode-meta episode-assets-empty">暂无本集资产</p>
    <div v-else class="episode-asset-groups">
      <section v-for="group in groups" :key="group.kind" class="episode-asset-group">
        <h3><component :is="group.icon" :size="15" aria-hidden="true" />{{ group.label }}<span>{{ group.assets.length }}</span></h3>
        <ul v-if="group.assets.length" class="episode-asset-grid">
          <li v-for="asset in group.assets" :key="asset.id">
            <ImagePreview v-if="asset.imageUrl" :src="asset.imageUrl" :title="asset.name">
              <template #trigger>
                <button type="button" class="episode-asset-thumb" :aria-label="'预览资产 ' + asset.name">
                  <img :src="asset.imageUrl" alt="" />
                </button>
              </template>
            </ImagePreview>
            <span v-else class="episode-asset-thumb">
              <component :is="group.icon" :size="22" :stroke-width="1.5" aria-hidden="true" />
            </span>
            <span class="episode-asset-name">{{ asset.name }}</span>
          </li>
        </ul>
      </section>
    </div>
  </aside>
</template>

<style scoped>
.episode-assets {
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
  border-right: 1px solid var(--border-subtle);
}
.episode-assets h2,
.episode-assets h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
}
.episode-assets > h2 {
  color: var(--color-gold-soft);
}
.episode-meta {
  margin: 0;
  color: var(--color-muted);
  font-size: 12px;
}
.episode-assets-empty {
  margin-top: 12px;
}
.episode-asset-groups {
  display: grid;
  gap: 16px;
  margin-top: 16px;
}
.episode-asset-group {
  min-width: 0;
}
.episode-asset-group h3 {
  margin-bottom: 8px;
  color: var(--color-muted);
  font-weight: 500;
}
.episode-asset-group h3 span {
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 400;
}
.episode-asset-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.episode-asset-thumb {
  display: grid;
  place-items: center;
  overflow: hidden;
  aspect-ratio: 4 / 3;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: var(--surface-hover);
  color: var(--color-muted);
}
button.episode-asset-thumb {
  width: 100%;
  cursor: zoom-in;
}
.episode-asset-thumb img {
  width: 100%;
  height: 100%;
  min-height: 0;
  object-fit: cover;
}
.episode-asset-name {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  overflow-wrap: anywhere;
}
@container (max-width: 640px) {
  .episode-assets {
    border-right: 0;
    border-bottom: 1px solid var(--border-subtle);
  }
  .episode-asset-groups {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
  }
  .episode-asset-grid {
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 80px), 1fr));
  }
}
</style>
