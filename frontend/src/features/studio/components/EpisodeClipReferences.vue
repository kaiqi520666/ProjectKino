<script setup lang="ts">
import {
  ChevronDown,
  Clapperboard,
  LayoutGrid,
  Music,
  Pause,
  Play,
  Plus,
  X,
} from 'lucide-vue-next'
import {
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuPortal,
  DropdownMenuRoot,
  DropdownMenuTrigger,
} from 'reka-ui'
import ImagePreview from '@/components/ui/ImagePreview.vue'
import UiButton from '@/components/ui/UiButton.vue'
import type { ResolvedClipReference } from '../composables/useClipReferences'
import { assetStateLabel, type StudioAsset } from '../studio-assets'

defineProps<{
  clipId: number
  clipBackendId?: string
  persisted: boolean
  locked: boolean
  references: ResolvedClipReference[]
  isGridGenerating: boolean
  gridProgressLabel: string
  hasStoryboardGrid: boolean
  playingRefAudioId: string | null
}>()

const emit = defineEmits<{
  openGridDialog: []
  openPicker: []
  openRefVideoPreview: [url: string, title: string]
  toggleRefAudio: [id: string, url?: string]
  removeReference: [slotIndex: number]
  switchVariant: [slotIndex: number, target: StudioAsset]
}>()
</script>

<template>
  <section class="episode-references" aria-labelledby="episode-clip-title">
    <div class="episode-reference-materials">
      <div class="episode-section-head">
        <h2 id="episode-clip-title"><Clapperboard :size="17" aria-hidden="true" />片段 {{ clipId }}</h2>
        <UiButton
          v-if="persisted && clipBackendId"
          variant="outline"
          size="sm"
          :loading="isGridGenerating"
          :disabled="locked"
          @click="emit('openGridDialog')"
        >
          <template v-if="!isGridGenerating" #leading>
            <LayoutGrid :size="14" aria-hidden="true" />
          </template>
          {{
            isGridGenerating
              ? (gridProgressLabel || '生成宫格中…')
              : hasStoryboardGrid
                ? '重绘分镜宫格'
                : '生成分镜宫格'
          }}
        </UiButton>
      </div>
      <ul class="episode-reference-list" aria-label="片段参考素材">
        <li v-for="(asset, slotIndex) in references" :key="`${asset.id}-${slotIndex}`">
          <div class="episode-reference-thumb-wrap">
            <ImagePreview v-if="asset.mediaKind === 'image' && asset.imageUrl" :src="asset.imageUrl" :title="asset.displayName">
              <template #trigger>
                <button type="button" class="episode-asset-thumb" :aria-label="'预览片段参考 ' + asset.displayName">
                  <img :src="asset.imageUrl" alt="" />
                </button>
              </template>
            </ImagePreview>
            <button
              v-else-if="asset.mediaKind === 'video' && asset.mediaUrl"
              type="button"
              class="episode-asset-thumb episode-asset-thumb--video"
              :aria-label="'预览参考视频 ' + asset.displayName"
              @click="emit('openRefVideoPreview', asset.mediaUrl, asset.displayName)"
            >
              <video :src="`${asset.mediaUrl}#t=0.05`" preload="metadata" muted playsinline />
              <span class="episode-ref-play-dot"><Play :size="12" /></span>
            </button>
            <button
              v-else-if="asset.mediaKind === 'audio' && asset.mediaUrl"
              type="button"
              class="episode-asset-thumb episode-asset-thumb--audio"
              :class="{ 'is-playing': playingRefAudioId === asset.id }"
              :aria-label="(playingRefAudioId === asset.id ? '暂停 ' : '试听 ') + asset.displayName"
              @click="emit('toggleRefAudio', asset.id, asset.mediaUrl)"
            >
              <Pause v-if="playingRefAudioId === asset.id" :size="18" />
              <Music v-else :size="18" />
            </button>
            <span v-else class="episode-asset-thumb">
              <component :is="asset.icon" :size="20" :stroke-width="1.5" aria-hidden="true" />
            </span>
            <span class="episode-reference-no">{{ asset.slotLabel }}</span>
            <button
              v-if="persisted && clipBackendId && !locked"
              type="button"
              class="episode-reference-remove"
              :aria-label="`移除参考 ${asset.displayName}`"
              title="移除"
              @click="emit('removeReference', slotIndex)"
            >
              <X :size="11" aria-hidden="true" />
            </button>
          </div>
          <span class="episode-asset-name" :title="asset.displayName">{{ asset.name }}</span>
          <DropdownMenuRoot v-if="persisted && clipBackendId && asset.siblings.length >= 2">
            <DropdownMenuTrigger
              type="button"
              class="episode-variant-trigger"
              :disabled="locked"
              :title="`切换「${asset.name}」变体`"
            >
              <span>{{ asset.stateLabel }}</span>
              <ChevronDown :size="11" aria-hidden="true" />
            </DropdownMenuTrigger>
            <DropdownMenuPortal>
              <DropdownMenuContent class="episode-variant-menu" :side-offset="5" align="start">
                <DropdownMenuItem
                  v-for="sibling in asset.siblings"
                  :key="sibling.backendId || sibling.id"
                  class="episode-variant-option"
                  :class="{ 'is-current': sibling.id === asset.id }"
                  @select="emit('switchVariant', slotIndex, sibling)"
                >
                  <span class="episode-variant-option-thumb">
                    <img v-if="sibling.imageUrl" :src="sibling.imageUrl" alt="" />
                    <component :is="asset.icon" v-else :size="13" aria-hidden="true" />
                  </span>
                  <span class="episode-variant-option-label">{{ assetStateLabel(sibling) }}</span>
                  <span v-if="sibling.id === asset.id" class="episode-variant-option-tag">当前</span>
                  <span v-else-if="!sibling.imageUrl" class="episode-variant-option-missing">无图</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenuPortal>
          </DropdownMenuRoot>
        </li>
        <li>
          <UiButton
            class="episode-reference-add"
            variant="secondary"
            size="sm"
            :disabled="!persisted || !clipBackendId || locked"
            @click="emit('openPicker')"
          >
            <template #leading><Plus :size="17" aria-hidden="true" /></template>
            添加素材
          </UiButton>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.episode-references {
  display: block;
  min-width: 0;
  padding: 12px 16px;
}

.episode-reference-materials {
  min-width: 0;
}

.episode-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.episode-section-head h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
}

.episode-section-head h2 svg {
  color: var(--color-gold-soft);
}

.episode-reference-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
}

.episode-reference-list li {
  flex: 0 1 84px;
  min-width: 0;
  max-width: 100%;
}

.episode-reference-thumb-wrap {
  position: relative;
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

.episode-asset-thumb--video {
  position: relative;
  cursor: pointer;
}

.episode-asset-thumb--video video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.episode-ref-play-dot {
  position: absolute;
  inset: 0;
  margin: auto;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: rgb(10 11 14 / 72%);
  color: var(--color-gold-soft);
}

.episode-asset-thumb--audio {
  cursor: pointer;
  background: radial-gradient(circle at 50% 45%, rgb(212 175 55 / 16%), rgb(18 19 24 / 96%) 74%);
  color: var(--color-gold-soft);
}

.episode-asset-thumb--audio.is-playing {
  border-color: var(--color-gold);
  background: var(--gold-tint);
}

.episode-reference-no {
  position: absolute;
  top: 4px;
  left: 4px;
  padding: 0 5px;
  border: 1px solid rgb(240 184 75 / 26%);
  border-radius: 4px;
  background: rgb(9 10 13 / 78%);
  color: var(--color-gold-soft);
  font-size: 10px;
  font-weight: 500;
  line-height: 17px;
  pointer-events: none;
}

.episode-reference-remove {
  position: absolute;
  top: 4px;
  right: 4px;
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border: 1px solid rgb(255 255 255 / 16%);
  border-radius: 50%;
  background: rgb(9 10 13 / 82%);
  color: var(--color-text);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, border-color 0.15s, color 0.15s;
}

.episode-reference-thumb-wrap:is(:hover, :focus-within) .episode-reference-remove {
  opacity: 1;
}

.episode-reference-remove:is(:hover, :focus-visible) {
  border-color: var(--color-error);
  color: var(--color-error);
}

.episode-asset-name {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  overflow: hidden;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.episode-reference-add.ui-button {
  flex-direction: column;
  gap: 3px;
  width: 100%;
  min-height: 0;
  aspect-ratio: 4 / 3;
  padding: 4px;
  border-style: dashed;
  border-radius: 6px;
  background: transparent;
  color: var(--color-muted);
  opacity: 1;
}

.episode-reference-add.ui-button:not(:disabled):is(:hover, :focus-visible) {
  border-color: var(--color-gold);
  color: var(--color-gold-soft);
}

.episode-variant-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  max-width: 100%;
  margin-top: 2px;
  padding: 1px 6px;
  border: 1px solid color-mix(in srgb, var(--color-gold) 45%, transparent);
  border-radius: 999px;
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-size: 11px;
  line-height: 1.35;
  cursor: pointer;
}

.episode-variant-trigger span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.episode-variant-trigger:hover {
  border-color: var(--color-gold);
}

:global(.episode-variant-menu) {
  z-index: 120;
  min-width: 168px;
  max-width: 240px;
  padding: 4px;
  border: 1px solid var(--border-control);
  border-radius: 8px;
  background: var(--color-elevated);
  box-shadow: 0 8px 24px rgb(0 0 0 / 40%);
}

:global(.episode-variant-option) {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 7px;
  border-radius: 5px;
  color: var(--color-text);
  font-size: 12px;
  cursor: pointer;
  outline: none;
}

:global(.episode-variant-option[data-highlighted]) {
  background: var(--gold-tint);
  color: var(--color-gold-soft);
}

:global(.episode-variant-option.is-current) {
  color: var(--color-gold-soft);
  font-weight: 500;
}

:global(.episode-variant-option-thumb) {
  flex: none;
  display: grid;
  place-items: center;
  width: 28px;
  height: 20px;
  overflow: hidden;
  border-radius: 3px;
  background: var(--color-canvas);
  color: var(--color-muted);
}

:global(.episode-variant-option-thumb img) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

:global(.episode-variant-option-label) {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:global(.episode-variant-option-tag) {
  flex: none;
  font-size: 10px;
  color: var(--color-gold-soft);
}

:global(.episode-variant-option-missing) {
  flex: none;
  font-size: 10px;
  color: var(--color-muted);
}
</style>
