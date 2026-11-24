<script setup lang="ts">
import { AlertCircle, CheckCircle2, Clock, Loader2, RefreshCw, X } from 'lucide-vue-next'
import UiAlert from '@/components/ui/UiAlert.vue'
import UiButton from '@/components/ui/UiButton.vue'
import type { EpisodeStoryboardJobSnapshot } from '../storyboard-job-helpers'

export interface BatchBannerSummary {
  visible: boolean
  finished: boolean
  total: number
  succeeded: number
  failed: number
  running: number
  percent: number
  failedIds: string[]
}

defineProps<{
  episodeJob?: EpisodeStoryboardJobSnapshot
  episodeJobTitle: string
  elapsedLabel: string
  canCompose: boolean
  episodeActionsLocked: boolean
  batchSummary: BatchBannerSummary | null
  batchSubmitting: boolean
}>()

const emit = defineEmits<{
  retryCompose: []
  retrySplit: []
  dismissEpisodeJob: []
  retryFailedBatch: []
  dismissBatchBanner: []
}>()
</script>

<template>
  <div v-if="episodeJob?.status === 'running'" class="episode-job-banner" role="status" aria-live="polite">
    <div class="episode-job-banner-head">
      <div class="episode-job-banner-main">
        <Loader2 class="is-spin" :size="15" aria-hidden="true" />
        <strong>{{ episodeJobTitle }}</strong>
        <span
          v-if="episodeJob.action === 'episode' && episodeJob.totalBatches"
          class="episode-job-pill"
        >
          已落库 {{ episodeJob.completedBatches ?? 0 }}/{{ episodeJob.totalBatches }} 批<template v-if="episodeJob.segmentCount"> · 共 {{ episodeJob.segmentCount }} 段</template>
        </span>
        <span v-if="episodeJob.stepLabel" class="episode-job-banner-step">{{ episodeJob.stepLabel }}</span>
      </div>
      <div class="episode-job-banner-meta">
        <span v-if="elapsedLabel" class="episode-job-banner-elapsed">
          <Clock :size="12" aria-hidden="true" />
          {{ elapsedLabel }}
        </span>
      </div>
    </div>
    <div class="episode-batch-track" role="progressbar" :aria-valuenow="episodeJob.progress" aria-valuemin="0" aria-valuemax="100">
      <div class="episode-batch-fill" :style="{ width: `${Math.max(6, episodeJob.progress)}%` }"></div>
    </div>
  </div>

  <UiAlert
    v-else-if="episodeJob?.status === 'failed'"
    tone="error"
    :title="episodeJob.jobType === 'episode_compose' ? '本集视频合成失败' : '分镜任务执行失败'"
  >
    {{ episodeJob.errorMessage || episodeJob.stepLabel || '后台任务执行失败，请重试' }}
    <template #action>
      <div class="episode-job-alert-actions">
        <UiButton
          v-if="episodeJob.action === 'compose'"
          variant="outline"
          size="sm"
          :disabled="!canCompose"
          @click="emit('retryCompose')"
        >
          重试合成
        </UiButton>
        <UiButton
          v-else-if="episodeJob.action === 'episode'"
          variant="outline"
          size="sm"
          :disabled="episodeActionsLocked"
          @click="emit('retrySplit')"
        >
          重新拆分镜
        </UiButton>
        <UiButton
          variant="ghost"
          size="sm"
          @click="emit('dismissEpisodeJob')"
        >
          忽略
        </UiButton>
      </div>
    </template>
  </UiAlert>

  <div v-if="batchSummary?.visible" class="episode-batch-banner" :class="{ 'is-done': batchSummary.finished }">
    <div class="episode-batch-banner-head">
      <span class="episode-batch-banner-title">
        <Loader2 v-if="!batchSummary.finished" class="is-spin" :size="15" aria-hidden="true" />
        <CheckCircle2 v-else-if="batchSummary.failed === 0" :size="15" aria-hidden="true" />
        <AlertCircle v-else :size="15" aria-hidden="true" />
        <template v-if="!batchSummary.finished">
          后台批量生视频中：已完成 {{ batchSummary.succeeded }} / {{ batchSummary.total }}
          <template v-if="batchSummary.running"> · 进行中 {{ batchSummary.running }}</template>
          <template v-if="batchSummary.failed"> · 失败 {{ batchSummary.failed }}</template>
        </template>
        <template v-else>
          批量生视频已完成：成功 {{ batchSummary.succeeded }} 段<template v-if="batchSummary.failed"> · 失败 {{ batchSummary.failed }} 段（已自动退还积分）</template>
        </template>
      </span>
      <div class="episode-batch-banner-actions">
        <UiButton
          v-if="batchSummary.finished && batchSummary.failedIds.length"
          variant="outline"
          size="sm"
          :loading="batchSubmitting"
          @click="emit('retryFailedBatch')"
        >
          <template #leading><RefreshCw :size="13" aria-hidden="true" /></template>
          重试失败片段 ({{ batchSummary.failedIds.length }})
        </UiButton>
        <button
          v-if="batchSummary.finished"
          type="button"
          class="episode-batch-close"
          aria-label="关闭批量视频进度提示"
          @click="emit('dismissBatchBanner')"
        >
          <X :size="14" aria-hidden="true" />
        </button>
      </div>
    </div>
    <div class="episode-batch-track" role="progressbar" :aria-valuenow="batchSummary.percent" aria-valuemin="0" aria-valuemax="100">
      <div class="episode-batch-fill" :style="{ width: `${Math.max(6, batchSummary.percent)}%` }"></div>
    </div>
  </div>
</template>

<style scoped>
.episode-batch-banner,
.episode-job-banner {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid rgb(240 184 75 / 32%);
  border-radius: var(--radius-panel);
  background: var(--color-surface);
}

.episode-batch-banner.is-done {
  border-color: var(--border-subtle);
}

.episode-batch-banner-head,
.episode-job-banner-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.episode-batch-banner-title {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  color: var(--color-gold-soft);
}

.episode-batch-banner.is-done .episode-batch-banner-title {
  color: var(--color-text);
}

.episode-batch-banner-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.episode-batch-close {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  color: var(--color-muted);
  cursor: pointer;
}

.episode-batch-close:hover {
  background: var(--surface-hover);
  color: var(--color-text);
}

.episode-batch-track {
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: rgb(255 255 255 / 8%);
}

.episode-batch-fill {
  height: 100%;
  border-radius: inherit;
  background: var(--color-gold);
  transition: width 0.35s ease;
}

.episode-job-banner-main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-size: 13px;
  color: var(--color-gold-soft);
}

.episode-job-pill {
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--gold-tint);
  border: 1px solid rgb(240 184 75 / 30%);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.episode-job-banner-step {
  color: var(--color-text);
  font-size: 12px;
}

.episode-job-banner-meta {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--color-muted);
}

.episode-job-banner-elapsed {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-variant-numeric: tabular-nums;
  color: var(--color-gold-soft);
}

.episode-job-alert-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.is-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
