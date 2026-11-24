<script setup lang="ts">
import { AlertCircle, Bookmark, Clock, History, Sparkles, Video, X } from 'lucide-vue-next'
import RichPromptInput from '@/components/business/RichPromptInput.vue'
import type { PromptReferenceOption } from '@/components/business/prompt-references'
import UiButton from '@/components/ui/UiButton.vue'
import { isCollectableMediaUrl } from '@/features/assets/user-assets-helpers'
import type { ModelCatalogItemOut } from '../api-types'
import type { StoryboardClip } from '../studio-storyboard'
import VideoModelPicker from './VideoModelPicker.vue'
import VideoParamsPopover from './VideoParamsPopover.vue'

export interface ClipJobAlertInfo {
  status: 'failed' | 'review'
  message: string
  jobId?: string
}

export interface EstimatedVideoQuote {
  amount: string
  unitHint: string
  hint: string
}

defineProps<{
  episodeNumber: number
  clip: StoryboardClip
  persisted: boolean
  defaultRatio: string
  promptReferences: PromptReferenceOption[]
  referenceCount: number
  currentClipLocked: boolean
  episodeActionsLocked: boolean
  clipAlert: ClipJobAlertInfo | null
  durationMismatch: { exceeded: boolean; maxDuration: number }
  recommendedLongVideoModel: ModelCatalogItemOut | null
  videoModels: ModelCatalogItemOut[]
  currentVideoModel: ModelCatalogItemOut | null
  isClipInLibrary: boolean
  isClipLibraryBusy: boolean
  isClipGenerating: boolean
  isSubmittingClip: boolean
  estimatedVideoQuote: EstimatedVideoQuote | null
}>()

const selectedVideoModelId = defineModel<string>('videoModelId', { required: true })
const selectedResolution = defineModel<'480p' | '720p' | '1080p'>('resolution', { required: true })
const selectedRatio = defineModel<string>('ratio', { required: true })
const selectedDuration = defineModel<number>('duration', { required: true })

const emit = defineEmits<{
  updatePrompt: [value: string]
  dismissClipAlert: [jobId?: string]
  switchToLongVideoModel: []
  commitDuration: [seconds: number]
  toggleClipLibrary: []
  openHistory: []
  generateVideo: []
}>()
</script>

<template>
  <section class="episode-prompt" aria-label="片段提示词编辑">
    <div
      v-if="clipAlert"
      class="episode-clip-job-banner"
      :class="clipAlert.status === 'review' ? 'is-review' : 'is-failed'"
      :title="clipAlert.message"
    >
      <Clock v-if="clipAlert.status === 'review'" :size="14" aria-hidden="true" />
      <AlertCircle v-else :size="14" aria-hidden="true" />
      <span class="episode-clip-job-banner-text">
        <strong>{{ clipAlert.status === 'review' ? '最近重绘待后台核对（积分冻结中）' : '最近生视频失败' }}：</strong>
        {{ clipAlert.message }}
      </span>
      <button
        v-if="clipAlert.jobId"
        type="button"
        class="episode-clip-job-close"
        aria-label="忽略本次提示"
        title="忽略本次提示"
        @click="emit('dismissClipAlert', clipAlert.jobId)"
      >
        <X :size="13" aria-hidden="true" />
      </button>
    </div>

    <div class="episode-prompt-field">
      <span class="ui-label">视频提示词</span>
      <RichPromptInput
        :key="`${episodeNumber}-${clip.backendId || clip.id}`"
        :model-value="clip.prompt"
        :references="promptReferences"
        :disabled="currentClipLocked"
        expanded
        :min-height="180"
        placeholder="输入视频提示词，输入 @ 引用上方图片、视频或音频素材"
        mention-title="引用素材"
        @update:model-value="emit('updatePrompt', $event)"
      />
    </div>

    <div
      v-if="durationMismatch.exceeded"
      class="episode-clip-job-banner is-failed"
      role="alert"
    >
      <AlertCircle :size="14" aria-hidden="true" />
      <span class="episode-clip-job-banner-text">
        当前片段 {{ clip.durationSeconds }} 秒超出所选模型上限 {{ durationMismatch.maxDuration }} 秒，请切换支持 30 秒的模型或调短片段时长。
      </span>
      <UiButton
        v-if="recommendedLongVideoModel"
        variant="outline"
        size="sm"
        @click="emit('switchToLongVideoModel')"
      >
        切换 {{ recommendedLongVideoModel.displayName }}
      </UiButton>
    </div>

    <div class="episode-prompt-actions">
      <div class="episode-video-controls">
        <VideoModelPicker
          v-model="selectedVideoModelId"
          :models="videoModels"
          :clip-duration="selectedDuration"
          :project-ratio="selectedRatio"
          :reference-count="referenceCount"
          :prompt-length="clip.prompt.trim().length"
          :disabled="currentClipLocked"
        />
        <VideoParamsPopover
          v-model:resolution="selectedResolution"
          v-model:ratio="selectedRatio"
          v-model:duration="selectedDuration"
          :model="currentVideoModel"
          :default-ratio="defaultRatio"
          mode="single"
          :disabled="currentClipLocked"
          @duration-commit="emit('commitDuration', $event)"
        />
      </div>

      <div class="episode-video-controls">
        <UiButton
          v-if="persisted && clip.videoUrl && isCollectableMediaUrl(clip.videoUrl)"
          class="episode-bookmark-btn"
          :class="{ 'is-saved': isClipInLibrary }"
          variant="outline"
          size="sm"
          :loading="isClipLibraryBusy"
          :disabled="currentClipLocked"
          :aria-pressed="isClipInLibrary"
          :title="isClipInLibrary ? '已在素材库（点击取消收藏）' : '将当前片段视频加入素材库'"
          @click="emit('toggleClipLibrary')"
        >
          <template v-if="!isClipLibraryBusy" #leading>
            <Bookmark :size="14" :fill="isClipInLibrary ? 'currentColor' : 'none'" aria-hidden="true" />
          </template>
          {{ isClipInLibrary ? '已入素材库' : '加入素材库' }}
        </UiButton>
        <UiButton
          v-if="persisted && clip.backendId && (clip.videoHistory?.length ?? 0) >= 2"
          variant="outline"
          size="sm"
          :disabled="currentClipLocked"
          @click="emit('openHistory')"
        >
          <template #leading><History :size="14" aria-hidden="true" /></template>
          历史 · {{ clip.videoHistory?.length }}
        </UiButton>
        <div
          class="episode-cta-split"
          :class="{ 'is-solo': !estimatedVideoQuote || isClipGenerating }"
        >
          <span
            v-if="estimatedVideoQuote && !isClipGenerating"
            class="episode-cta-cost"
            :title="estimatedVideoQuote.hint"
          >
            <Sparkles :size="13" class="episode-cta-cost-icon" aria-hidden="true" />
            <strong class="episode-cta-cost-num">{{ estimatedVideoQuote.amount }}</strong>
            <span class="episode-cta-cost-unit">积分</span>
          </span>
          <UiButton
            class="episode-generate-btn"
            variant="primary"
            size="sm"
            :loading="isSubmittingClip || isClipGenerating"
            :disabled="!clip.prompt.trim() || !currentVideoModel || durationMismatch.exceeded || episodeActionsLocked || currentClipLocked || isSubmittingClip"
            @click="emit('generateVideo')"
          >
            <template v-if="!isSubmittingClip && !isClipGenerating" #leading><Video :size="15" aria-hidden="true" /></template>
            {{ isClipGenerating ? '生成中…' : clip.videoUrl ? '重新生成视频' : '生成视频' }}
          </UiButton>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.episode-prompt {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: 12px 16px;
  overflow: hidden;
  border-top: 1px solid var(--border-subtle);
}

.episode-prompt :deep(.ui-field) {
  display: flex;
  flex: 1;
  flex-direction: column;
}

.episode-prompt :deep(textarea) {
  flex: 1;
  width: 100%;
  min-height: 142px;
}

.episode-prompt-field {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  gap: 6px;
}

.episode-prompt-actions {
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
}

.episode-video-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.episode-cta-split {
  display: inline-flex;
  align-items: stretch;
  height: 36px;
  border-radius: 9px;
  overflow: hidden;
  border: 1px solid rgb(240 184 75 / 55%);
  box-shadow: 0 2px 10px rgb(240 184 75 / 12%);
}

.episode-cta-split.is-solo {
  border-color: transparent;
  box-shadow: none;
}

.episode-cta-cost {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  padding: 0 12px;
  background: #13151c;
  color: var(--color-gold-soft);
  user-select: none;
}

.episode-cta-cost-icon {
  align-self: center;
  color: var(--color-gold);
  flex-shrink: 0;
}

.episode-cta-cost-num {
  align-self: center;
  font-size: 16px;
  font-weight: 700;
  color: #f8cc66;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  line-height: 1;
}

.episode-cta-cost-unit {
  align-self: center;
  font-size: 11px;
  font-weight: 500;
  color: rgb(248 204 102 / 82%);
  line-height: 1;
}

.episode-generate-btn.ui-button {
  min-height: 34px;
  height: 100%;
  padding: 0 15px;
  border: 0;
  border-radius: 0;
}

.episode-cta-split.is-solo .episode-generate-btn.ui-button {
  border-radius: 9px;
}

.episode-clip-job-banner {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  padding: 7px 10px;
  margin-bottom: 8px;
  border-radius: 7px;
  font-size: 12px;
  line-height: 1.45;
}

.episode-clip-job-banner svg {
  flex: none;
  margin-top: 2px;
}

.episode-clip-job-banner.is-failed {
  border: 1px solid color-mix(in srgb, var(--color-error) 35%, transparent);
  background: color-mix(in srgb, var(--color-error) 10%, transparent);
  color: var(--color-error);
}

.episode-clip-job-banner.is-review {
  border: 1px solid color-mix(in srgb, var(--color-gold) 40%, transparent);
  background: color-mix(in srgb, var(--color-gold) 10%, transparent);
  color: var(--color-gold-soft);
}

.episode-clip-job-banner-text {
  flex: 1 1 auto;
  min-width: 0;
  overflow-wrap: anywhere;
}

.episode-clip-job-close {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  color: inherit;
  opacity: 0.72;
  cursor: pointer;
}

.episode-clip-job-close:hover {
  opacity: 1;
  background: rgb(255 255 255 / 8%);
}

.episode-bookmark-btn.ui-button.is-saved {
  border-color: rgb(240 184 75 / 42%);
  background: var(--gold-tint);
  color: var(--color-gold-soft);
}

@container (max-width: 640px) {
  .episode-prompt-field {
    min-height: 240px;
  }
}
</style>
