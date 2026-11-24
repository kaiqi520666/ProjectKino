<script setup lang="ts">
import { computed } from 'vue'
import {
  ArrowLeft,
  Bookmark,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Download,
  Film,
  Play,
  Sparkles,
  Video,
} from 'lucide-vue-next'
import {
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuPortal,
  DropdownMenuRoot,
  DropdownMenuTrigger,
} from 'reka-ui'
import UiButton from '@/components/ui/UiButton.vue'
import VideoPreview from '@/components/ui/VideoPreview.vue'
import { isCollectableMediaUrl } from '@/features/assets/user-assets-helpers'
import type { StudioEpisode } from '../studio-project'

export interface EpisodeNavItem {
  number: number
  title: string
  statusTone: 'composed' | 'video' | 'storyboard' | 'pending'
  statusText: string
}

const props = defineProps<{
  projectId: string
  projectName: string
  persisted: boolean
  episode: StudioEpisode | null
  episodeIndex: string
  episodeName: string
  title: string
  hasStoryboard: boolean
  clipCount: number
  readyCount: number
  missingVideoCount: number
  isComposedInLibrary: boolean
  togglingComposedLibrary: boolean
  episodeActionsLocked: boolean
  isSplitOrRegenRunning: boolean
  isComposeRunning: boolean
  hasActiveVideoJobs: boolean
  canCompose: boolean
  episodeNavItems: EpisodeNavItem[]
  prevEpisodeNumber: number | null
  nextEpisodeNumber: number | null
}>()

const emit = defineEmits<{
  switchEpisode: [episodeNumber: number]
  toggleComposedLibrary: []
  openBatchDialog: []
  openRegenDialog: []
  composeEpisode: []
}>()

const prevTooltip = computed(() => {
  if (!props.prevEpisodeNumber) return '已是第 1 集'
  const item = props.episodeNavItems.find((ep) => ep.number === props.prevEpisodeNumber)
  return item?.title ? `上一集：第 ${item.number} 集 · ${item.title} (Alt+←)` : `上一集：第 ${props.prevEpisodeNumber} 集 (Alt+←)`
})

const nextTooltip = computed(() => {
  if (!props.nextEpisodeNumber) return '已是最后一集'
  const item = props.episodeNavItems.find((ep) => ep.number === props.nextEpisodeNumber)
  return item?.title ? `下一集：第 ${item.number} 集 · ${item.title} (Alt+→)` : `下一集：第 ${props.nextEpisodeNumber} 集 (Alt+→)`
})
</script>

<template>
  <header class="episode-toolbar">
    <div class="episode-heading">
      <RouterLink
        class="episode-back ui-button ui-button--outline ui-button--sm"
        :to="{ name: 'studio-storyboard', params: { projectId } }"
        aria-label="返回分镜列表"
        title="返回分镜列表"
      >
        <ArrowLeft :size="14" aria-hidden="true" />
      </RouterLink>
      <span class="episode-heading-divider" aria-hidden="true"></span>
      <h1 id="episode-workbench-title" :title="title">
        <span class="episode-project-name">{{ projectName }}</span>
        <ChevronRight class="episode-heading-separator" :size="13" aria-hidden="true" />
        <div v-if="episodeNavItems.length > 1 && episode" class="episode-switcher">
          <button
            type="button"
            class="episode-nav-step"
            :disabled="!prevEpisodeNumber"
            :aria-label="prevTooltip"
            :title="prevTooltip"
            @click="prevEpisodeNumber && emit('switchEpisode', prevEpisodeNumber)"
          >
            <ChevronLeft :size="14" aria-hidden="true" />
          </button>
          <DropdownMenuRoot>
            <DropdownMenuTrigger
              type="button"
              class="episode-switcher-trigger"
              :aria-label="`切换分集，当前 ${episodeIndex}`"
              title="点击快速切换分集"
            >
              <span class="episode-index">{{ episodeIndex }}</span>
              <template v-if="episodeName && episodeName !== episodeIndex">
                <span class="episode-heading-separator" aria-hidden="true">·</span>
                <span class="episode-name">{{ episodeName }}</span>
              </template>
              <ChevronDown class="episode-switcher-caret" :size="13" aria-hidden="true" />
            </DropdownMenuTrigger>
            <DropdownMenuPortal>
              <DropdownMenuContent class="episode-switcher-menu" :side-offset="6" align="start">
                <DropdownMenuItem
                  v-for="item in episodeNavItems"
                  :key="item.number"
                  class="episode-switcher-option"
                  :class="{ 'is-current': item.number === episode.number }"
                  @select="item.number !== episode.number && emit('switchEpisode', item.number)"
                >
                  <span class="episode-switcher-dot" :class="`is-${item.statusTone}`" aria-hidden="true"></span>
                  <span class="episode-switcher-no">第 {{ item.number }} 集</span>
                  <span class="episode-switcher-title">{{ item.title || '未命名分集' }}</span>
                  <span class="episode-switcher-status">{{ item.statusText }}</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenuPortal>
          </DropdownMenuRoot>
          <button
            type="button"
            class="episode-nav-step"
            :disabled="!nextEpisodeNumber"
            :aria-label="nextTooltip"
            :title="nextTooltip"
            @click="nextEpisodeNumber && emit('switchEpisode', nextEpisodeNumber)"
          >
            <ChevronRight :size="14" aria-hidden="true" />
          </button>
        </div>
        <template v-else>
          <span class="episode-index">{{ episodeIndex }}</span>
          <template v-if="episodeName && episodeName !== episodeIndex">
            <span class="episode-heading-separator" aria-hidden="true">·</span>
            <span class="episode-name">{{ episodeName }}</span>
          </template>
        </template>
      </h1>
    </div>
    <div v-if="episode" class="episode-actions">
      <span v-if="clipCount" class="episode-meta">{{ readyCount }}/{{ clipCount }} 片段已有视频</span>
      <template v-if="episode.composedVideoUrl">
        <VideoPreview :src="episode.composedVideoUrl" :title="`${episodeIndex} 完整成片`" autoplay>
          <template #trigger>
            <button type="button" class="ui-button ui-button--outline ui-button--sm">
              <Play :size="14" aria-hidden="true" />观看成片<template v-if="episode.composedDuration"> ({{ Math.round(episode.composedDuration) }}s)</template>
            </button>
          </template>
        </VideoPreview>
        <a
          class="ui-button ui-button--outline ui-button--sm"
          :href="episode.composedVideoUrl"
          :download="`${projectName}-第${episode.number}集.mp4`"
          target="_blank"
          rel="noopener"
        >
          <Download :size="14" aria-hidden="true" />下载成片
        </a>
        <UiButton
          v-if="persisted && isCollectableMediaUrl(episode.composedVideoUrl)"
          class="episode-bookmark-btn"
          :class="{ 'is-saved': isComposedInLibrary }"
          variant="outline"
          size="sm"
          :loading="togglingComposedLibrary"
          :aria-pressed="isComposedInLibrary"
          :title="isComposedInLibrary ? '已在素材库（点击取消收藏）' : '将成片加入素材库'"
          @click="emit('toggleComposedLibrary')"
        >
          <template v-if="!togglingComposedLibrary" #leading>
            <Bookmark :size="14" :fill="isComposedInLibrary ? 'currentColor' : 'none'" aria-hidden="true" />
          </template>
          {{ isComposedInLibrary ? '已入素材库' : '加入素材库' }}
        </UiButton>
      </template>
      <UiButton
        v-if="hasStoryboard && clipCount && persisted"
        :variant="missingVideoCount > 0 ? 'primary' : 'outline'"
        size="sm"
        :disabled="episodeActionsLocked"
        @click="emit('openBatchDialog')"
      >
        <template #leading><Video :size="14" aria-hidden="true" /></template>
        {{ missingVideoCount > 0 ? `批量生视频 (${missingVideoCount})` : '批量重新生成' }}
      </UiButton>
      <UiButton
        v-if="hasStoryboard"
        variant="outline"
        size="sm"
        :loading="isSplitOrRegenRunning"
        :disabled="episodeActionsLocked || hasActiveVideoJobs"
        @click="emit('openRegenDialog')"
      >
        <template v-if="!isSplitOrRegenRunning" #leading><Sparkles :size="14" aria-hidden="true" /></template>重新生成分镜
      </UiButton>
      <UiButton
        variant="primary"
        size="sm"
        :loading="isComposeRunning"
        :disabled="!canCompose"
        @click="emit('composeEpisode')"
      >
        <template v-if="!isComposeRunning" #leading><Film :size="14" aria-hidden="true" /></template>
        {{ episode.composedVideoUrl ? '重新合成本集' : '合成本集视频' }}
      </UiButton>
    </div>
  </header>
</template>

<style scoped>
.episode-toolbar,
.episode-heading,
.episode-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.episode-toolbar {
  flex-shrink: 0;
  justify-content: space-between;
  flex-wrap: wrap;
  padding: 8px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-panel);
  background: var(--color-surface);
}

.episode-heading {
  flex: 1 1 260px;
  min-width: 0;
  gap: 8px;
}

.episode-heading-divider {
  flex: 0 0 1px;
  height: 18px;
  background: var(--border-subtle);
}

.episode-heading h1 {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 6px;
  min-width: 0;
  margin: 0;
  font-size: var(--font-size-body);
  font-weight: 500;
  line-height: 1.4;
  white-space: nowrap;
}

.episode-project-name,
.episode-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.episode-project-name {
  max-width: 32%;
  color: var(--color-muted);
}

.episode-heading-separator,
.episode-index {
  flex-shrink: 0;
}

.episode-heading-separator {
  color: var(--color-muted);
}

.episode-name {
  color: var(--color-gold-soft);
}

.episode-switcher {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
  max-width: 100%;
  padding: 2px;
  border: 1px solid var(--border-control);
  border-radius: 7px;
  background: rgb(255 255 255 / 2.5%);
}

.episode-nav-step {
  flex: none;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--color-muted);
  cursor: pointer;
  transition: background-color 140ms ease, color 140ms ease;
}

.episode-nav-step:not(:disabled):hover {
  background: var(--surface-hover);
  color: var(--color-gold-soft);
}

.episode-nav-step:disabled {
  opacity: 0.34;
  cursor: not-allowed;
}

.episode-switcher-trigger {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  max-width: 240px;
  height: 24px;
  padding: 0 7px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--color-text);
  font: inherit;
  cursor: pointer;
  transition: background-color 140ms ease;
}

.episode-switcher-trigger:hover,
.episode-switcher-trigger[data-state='open'] {
  background: var(--surface-hover);
}

.episode-switcher-caret {
  flex: none;
  color: var(--color-muted);
}

.episode-actions {
  flex-wrap: wrap;
}

.episode-meta {
  margin: 0;
  color: var(--color-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.episode-toolbar .ui-button {
  gap: 6px;
  min-height: var(--control-height-sm);
  padding-inline: 10px;
}

.episode-back.ui-button {
  flex: 0 0 var(--control-height-sm);
  width: var(--control-height-sm);
  padding: 0;
}

.episode-bookmark-btn.ui-button.is-saved {
  border-color: rgb(240 184 75 / 42%);
  background: var(--gold-tint);
  color: var(--color-gold-soft);
}

:global(.episode-switcher-menu) {
  z-index: 120;
  min-width: 240px;
  max-width: 340px;
  max-height: 320px;
  overflow-y: auto;
  padding: 4px;
  border: 1px solid var(--border-control);
  border-radius: 8px;
  background: var(--color-elevated);
  box-shadow: 0 10px 28px rgb(0 0 0 / 46%);
}

:global(.episode-switcher-option) {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 5px;
  color: var(--color-text);
  font-size: 12px;
  cursor: pointer;
  outline: none;
}

:global(.episode-switcher-option[data-highlighted]) {
  background: var(--gold-tint);
  color: var(--color-gold-soft);
}

:global(.episode-switcher-option.is-current) {
  background: rgb(240 184 75 / 12%);
  color: var(--color-gold-soft);
  font-weight: 600;
}

:global(.episode-switcher-dot) {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-muted);
}

:global(.episode-switcher-dot.is-storyboard) {
  background: var(--color-gold);
}

:global(.episode-switcher-dot.is-video) {
  background: #60a5fa;
}

:global(.episode-switcher-dot.is-composed) {
  background: var(--color-success);
}

:global(.episode-switcher-no) {
  flex: none;
  font-variant-numeric: tabular-nums;
}

:global(.episode-switcher-title) {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-muted);
}

:global(.episode-switcher-option.is-current .episode-switcher-title) {
  color: inherit;
}

:global(.episode-switcher-status) {
  flex: none;
  font-size: 11px;
  color: var(--color-muted);
}
</style>
