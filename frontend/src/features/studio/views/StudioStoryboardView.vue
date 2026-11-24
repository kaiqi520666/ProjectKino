<script setup lang="ts">
import { computed } from 'vue'
import { AlertTriangle, CheckCircle2, ChevronRight, Clapperboard, Clock3, Film, Loader2 } from 'lucide-vue-next'
import StudioEpisodeList from '../components/StudioEpisodeList.vue'
import { resolveStoryboardOverviewBadge } from '../storyboard-job-helpers'
import { useStoryboardJobStore } from '../storyboard-job-store'
import { episodeLabel, readEpisode } from '../studio-project'
import type { StudioProject } from '../studio-project'

const props = defineProps<{ project: StudioProject }>()
const storyboardJobs = useStoryboardJobStore()
const total = computed(() => props.project.creation.settings.episodeCount)

function cardPreview(number: number) {
  const ep = readEpisode(props.project, number)
  const summary = ep.summary.replace(/\s+/gu, ' ').trim()
  if (summary) return summary
  const outlineSummary = props.project.scriptResult?.outline?.episodes
    ?.find((item) => item.number === number)
    ?.summary
    ?.replace(/\s+/gu, ' ')
    .trim()
  if (outlineSummary) return outlineSummary
  return ep.script.replace(/\s+/gu, ' ').trim() || '暂无本集简介'
}

function cardStatus(number: number) {
  const ep = readEpisode(props.project, number)
  const board = props.project.storyboards?.[number]
  const job = storyboardJobs.getEpisodeJob(props.project.id, number)
  if (job?.status === 'running' || job?.status === 'failed') {
    return resolveStoryboardOverviewBadge({
      hasPersistedStoryboard: Boolean(board?.clips.length),
      clipCount: board?.clips.length ?? 0,
      job,
    })
  }
  if (!board?.clips.length) {
    return resolveStoryboardOverviewBadge({
      hasPersistedStoryboard: false,
      clipCount: 0,
    })
  }
  const clipCount = board.clips.length
  const readyCount = board.clips.filter((clip) => clip.videoUrl).length
  const totalSeconds = Math.round(board.clips.reduce((sum, clip) => sum + clip.durationSeconds, 0))
  const detail = ep.composedDuration
    ? `成片 ${Math.round(ep.composedDuration)} 秒`
    : totalSeconds > 0
      ? `约 ${totalSeconds} 秒`
      : ''
  if (ep.composedVideoUrl) {
    return { tone: 'done' as const, complete: true, label: `已合成本集 · ${clipCount} 段`, detail }
  }
  if (readyCount === clipCount) {
    return { tone: 'done' as const, complete: true, label: `片段齐备 · ${clipCount} 段`, detail }
  }
  if (readyCount > 0) {
    return { tone: 'done' as const, complete: false, label: `视频 ${readyCount}/${clipCount} 段`, detail }
  }
  return { tone: 'ready' as const, complete: false, label: `已拆分镜 · ${clipCount} 段`, detail }
}
</script>

<template>
  <section class="studio-storyboard" aria-label="分镜制作">
    <StudioEpisodeList :total="total" label="分镜分集列表" layout="grid">
      <template #default="{ number }">
        <RouterLink
          class="storyboard-card"
          :class="{
            'is-running': cardStatus(number).tone === 'running',
            'is-failed': cardStatus(number).tone === 'failed',
          }"
          :to="{ name: 'studio-episode', params: { projectId: project.id, episode: number } }"
          :aria-labelledby="`storyboard-card-title-${number}`"
        >
          <div class="storyboard-card-heading">
            <span class="storyboard-card-icon" aria-hidden="true"><Film :size="17" :stroke-width="1.7" /></span>
            <h2 :id="`storyboard-card-title-${number}`">{{ episodeLabel(readEpisode(project, number)) }}</h2>
            <ChevronRight class="storyboard-card-arrow" :size="16" aria-hidden="true" />
          </div>
          <p class="storyboard-card-preview">{{ cardPreview(number) }}</p>
          <div class="storyboard-card-meta">
            <span class="storyboard-status" :class="`is-${cardStatus(number).tone}`">
              <Loader2 v-if="cardStatus(number).tone === 'running'" class="is-spin" :size="13" aria-hidden="true" />
              <AlertTriangle v-else-if="cardStatus(number).tone === 'failed'" :size="13" aria-hidden="true" />
              <CheckCircle2 v-else-if="cardStatus(number).complete" :size="13" aria-hidden="true" />
              <Clapperboard v-else-if="cardStatus(number).tone !== 'pending'" :size="13" aria-hidden="true" />
              <Clock3 v-else :size="13" aria-hidden="true" />
              {{ cardStatus(number).label }}
            </span>
            <span v-if="cardStatus(number).detail" class="storyboard-card-duration">{{ cardStatus(number).detail }}</span>
          </div>
        </RouterLink>
      </template>
    </StudioEpisodeList>
  </section>
</template>

<style scoped>
.studio-storyboard { padding-top: 20px; }
.storyboard-card { display: flex; flex-direction: column; height: 100%; min-height: 126px; padding: 14px 16px; border: 1px solid var(--border-subtle); border-radius: var(--radius-panel); background: var(--color-surface); overflow-wrap: anywhere; transition: border-color .15s, background-color .15s; }
.storyboard-card:hover { border-color: rgb(240 184 75 / 45%); background: var(--surface-hover); }
.storyboard-card.is-running { border-color: rgb(240 184 75 / 35%); }
.storyboard-card.is-failed { border-color: rgb(239 68 68 / 32%); }
.storyboard-card:focus-visible { outline: 2px solid var(--color-gold); outline-offset: 2px; }
.storyboard-card-heading { display: grid; grid-template-columns: 30px minmax(0, 1fr) 16px; align-items: center; gap: 10px; margin-bottom: 6px; }
.storyboard-card h2 { margin: 0; font-size: 15px; font-weight: 600; line-height: 1.4; }
.storyboard-card-icon { display: grid; place-items: center; width: 30px; height: 30px; border-radius: 6px; background: var(--gold-tint); color: var(--color-gold-soft); }
.storyboard-card-arrow { color: var(--color-muted); transition: color .15s; }
.storyboard-card:is(:hover, :focus-visible) .storyboard-card-arrow { color: var(--color-gold-soft); }
.storyboard-card-preview { display: -webkit-box; overflow: hidden; margin: 0 0 12px; color: var(--color-muted); font-size: 14px; line-height: 1.65; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.storyboard-card-meta { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: auto; padding-top: 10px; border-top: 1px solid var(--border-subtle); font-size: 12px; }
.storyboard-status { display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px; border-radius: 999px; font-weight: 500; line-height: 1.5; flex-shrink: 0; }
.storyboard-status.is-pending { background: rgb(255 255 255 / 4%); color: var(--color-muted); }
.storyboard-status.is-ready { background: var(--gold-tint); color: var(--color-gold-soft); }
.storyboard-status.is-running { background: var(--gold-tint); color: var(--color-gold-soft); border: 1px solid rgb(240 184 75 / 30%); }
.storyboard-status.is-failed { background: rgb(239 68 68 / 14%); color: #f87171; border: 1px solid rgb(239 68 68 / 32%); }
.storyboard-status.is-done { background: rgb(74 222 128 / 12%); color: var(--color-success); }
.storyboard-card-duration { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--color-muted); }
.is-spin { animation: storyboard-spin 1s linear infinite; }
@keyframes storyboard-spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
</style>
