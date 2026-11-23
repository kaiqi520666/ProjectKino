<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import {
  AlertTriangle,
  Check,
  CircleDashed,
  Clock,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Sparkles,
  X,
} from 'lucide-vue-next'
import UiAlert from '@/components/ui/UiAlert.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiTextarea from '@/components/ui/UiTextarea.vue'
import { useUiStore } from '@/stores/ui'
import {
  apiErrorMessage,
  confirmScriptApi,
  saveStructuredEpisodeApi,
  startAppendEpisode,
  startRegenerateStory,
  startResumeScript,
  startRewriteEpisode,
} from '../api'
import type { BackendOutlineEpisode, BackendScene } from '../api-types'
import StructuredScriptEditor from '../components/StructuredScriptEditor.vue'
import StudioEpisodeList from '../components/StudioEpisodeList.vue'
import {
  formatElapsedSeconds,
  parseWritingEpisodeNumber,
  resolveEpisodeGenerationStatus,
  scriptJobTitle,
  type EpisodeGenerationStatus,
} from '../script-job-helpers'
import { useScriptJobStore } from '../script-job-store'
import { cloneScenes, normalizeScenes, renderStructuredScript, scenesSeconds, validateStructuredScenes } from '../script-structure'
import { readEpisode } from '../studio-project'
import type { StudioEpisode, StudioProject } from '../studio-project'
import { useStudioStore } from '../studio-store'

const props = defineProps<{ project: StudioProject }>()
const studio = useStudioStore()
const scriptJobs = useScriptJobStore()
const ui = useUiStore()
const editFormId = useId()
const regenFormId = useId()
const number = ref(1)
const draft = ref<StudioEpisode>()
const structuredDraft = ref<BackendScene[]>()
const structuredSnapshot = ref('')
const episodeList = ref<HTMLElement>()
const regenMode = ref<'episode' | 'story' | 'append' | null>(null)
const regenFeedback = ref('')
const submittingJob = ref(false)
const nowTick = ref(Date.now())
let elapsedTimer: ReturnType<typeof setInterval> | null = null

const activeJob = computed(() => scriptJobs.getJob(props.project.id))
const scriptJobRunning = computed(() => activeJob.value?.status === 'running')
const scriptJobFailed = computed(() => activeJob.value?.status === 'failed')
const busy = computed(() => scriptJobRunning.value || submittingJob.value)

function stopElapsedTimer() {
  if (elapsedTimer !== null) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
}

watch(
  scriptJobRunning,
  (running) => {
    if (running) {
      clearEditDraft()
      nowTick.value = Date.now()
      if (elapsedTimer === null) {
        elapsedTimer = setInterval(() => {
          nowTick.value = Date.now()
        }, 1000)
      }
    } else {
      stopElapsedTimer()
    }
  },
  { immediate: true },
)

onBeforeUnmount(stopElapsedTimer)

const outline = computed(() => props.project.scriptResult?.outline)
const outlineEpisodesByNumber = computed(() => {
  const map = new Map<number, BackendOutlineEpisode>()
  for (const item of outline.value?.episodes ?? []) {
    if (typeof item.number === 'number') {
      map.set(item.number, item)
    }
  }
  return map
})

const total = computed(() => Math.max(
  props.project.creation.settings.episodeCount,
  outline.value?.episodes?.length ?? 0,
  props.project.scriptResult?.episodes.length ?? 0,
))
const completedEpisodeCount = computed(() => props.project.scriptResult?.episodes.length ?? 0)
const plannedEpisodeCount = computed(() => {
  const planned = outline.value?.episodes
  return Array.isArray(planned) && planned.length > 0 ? planned.length : total.value
})
const showFullScriptCounter = computed(
  () => activeJob.value?.jobType === 'script_generate' || activeJob.value?.jobType === 'script_regenerate',
)
const elapsedLabel = computed(() => {
  if (!activeJob.value) return '00:00'
  return formatElapsedSeconds((nowTick.value - activeJob.value.startedAt) / 1000)
})
const writingEpisodeNumber = computed(() => parseWritingEpisodeNumber(activeJob.value, total.value))

const episode = computed(() => readEpisode(props.project, number.value))
const backendEpisodesByNumber = computed(() => {
  const map = new Map<number, NonNullable<StudioProject['scriptResult']>['episodes'][number]>()
  for (const item of props.project.scriptResult?.episodes ?? []) {
    map.set(item.number, item)
  }
  return map
})
const backendEpisode = computed(() => backendEpisodesByNumber.value.get(number.value))
const currentOutlineEpisode = computed(() => outlineEpisodesByNumber.value.get(number.value))
const episodeWarnings = computed(() => backendEpisode.value?.warnings ?? [])
const missingEpisodeCount = computed(() => {
  if (!props.project.persisted || !outline.value) return 0
  return Math.max(0, plannedEpisodeCount.value - completedEpisodeCount.value)
})
const episodeLabel = computed(() => `第 ${number.value} 集`)
const displayEpisodeTitle = computed(() => {
  if (episode.value.title && episode.value.title !== episodeLabel.value) return episode.value.title
  const plannedTitle = currentOutlineEpisode.value?.title?.trim()
  if (plannedTitle && plannedTitle !== episodeLabel.value) return plannedTitle
  return ''
})
const isStructuredEditing = computed(() => !!draft.value && !!structuredDraft.value)
const structuredError = computed(() => {
  if (!structuredDraft.value) return null
  return validateStructuredScenes(normalizeScenes(structuredDraft.value))
})
const estimatedSeconds = computed(() => {
  if (structuredDraft.value) return scenesSeconds(normalizeScenes(structuredDraft.value))
  if (backendEpisode.value) return backendEpisode.value.seconds
  return null
})
const previewScript = computed(() => {
  if (structuredDraft.value) {
    return renderStructuredScript(normalizeScenes(structuredDraft.value), outline.value)
  }
  return draft.value?.script ?? episode.value.script
})
const dirty = computed(() => {
  if (!draft.value) return false
  if (structuredDraft.value) {
    return draft.value.title !== episode.value.title || JSON.stringify(structuredDraft.value) !== structuredSnapshot.value
  }
  return draft.value.title !== episode.value.title || draft.value.script !== episode.value.script
})
const wordCount = computed(() => [...previewScript.value].filter(char => !/\s/u.test(char)).length)

const hasBackendScript = computed(() => !!props.project.scriptResult)
const showEpisodeStatusIcons = computed(
  () => Boolean(props.project.persisted || hasBackendScript.value || scriptJobRunning.value),
)
const canRegenerateStory = computed(
  () => Boolean(props.project.persisted && (props.project.scriptResult || props.project.sourceText?.trim())),
)
const canRewriteEpisode = computed(() => {
  const outlineEpisodes = outline.value?.episodes
  if (!Array.isArray(outlineEpisodes)) return false
  return outlineEpisodes.some((item) => item.number === number.value)
})
const hasDownstreamAssets = computed(() => !!props.project.assets?.length)
const hasEpisodeStoryboard = computed(() => !!props.project.storyboards?.[number.value])
const hasAnyStoryboard = computed(() => !!props.project.storyboards && Object.keys(props.project.storyboards).length > 0)

const outlineCharacters = computed(() => {
  const ids = currentOutlineEpisode.value?.characterIds ?? []
  const byId = new Map((outline.value?.characters ?? []).map((item) => [item.id, item]))
  return ids.map((id) => ({
    id,
    name: byId.get(id)?.name || id,
    role: byId.get(id)?.role || '',
  }))
})
const outlineScenes = computed(() => {
  const ids = currentOutlineEpisode.value?.sceneIds ?? []
  const byId = new Map((outline.value?.scenes ?? []).map((item) => [item.id, item]))
  return ids.map((id) => {
    const item = byId.get(id)
    return {
      id,
      name: item?.name || id,
      meta: item ? `${item.kind} · ${item.time}` : '',
    }
  })
})
const outlineProps = computed(() => {
  const ids = currentOutlineEpisode.value?.propIds ?? []
  const byId = new Map((outline.value?.props ?? []).map((item) => [item.id, item]))
  return ids.map((id) => ({
    id,
    name: byId.get(id)?.name || id,
    role: byId.get(id)?.role || '',
  }))
})

const isCurrentEpisodeRewriting = computed(
  () => scriptJobRunning.value
    && activeJob.value?.jobType === 'episode_rewrite'
    && writingEpisodeNumber.value === number.value,
)

const regenOpen = computed({
  get: () => regenMode.value !== null,
  set: (open: boolean) => {
    if (!open && !submittingJob.value) {
      regenMode.value = null
      regenFeedback.value = ''
    }
  },
})

const regenTitle = computed(() => {
  if (regenMode.value === 'story') return hasBackendScript.value ? '重生成全剧剧本' : '生成全剧剧本'
  if (regenMode.value === 'append') return `新增第 ${total.value + 1} 集`
  return `重写第 ${number.value} 集`
})
const regenDescription = computed(() => {
  if (regenMode.value === 'story') {
    return hasBackendScript.value
      ? '将重新规划全剧分集大纲与人物场景编号，并重写所有集数；生成过程在页内实时推进，不阻挡浏览。'
      : '将根据项目原稿重新规划分集大纲并逐集撰写正文，完成后自动同步到页面。'
  }
  if (regenMode.value === 'append') return `沿用当前全剧大纲与人物场景编号，承接第 ${total.value} 集结尾续写新的一集。`
  return '沿用当前全剧大纲与人物场景编号，仅重写当前这一集剧本。'
})
const regenWarning = computed(() => {
  if (regenMode.value === 'story') {
    if (hasDownstreamAssets.value || hasAnyStoryboard.value) {
      return '重生成全剧会重新分配角色、场景与道具编号，将清空本项目已生成的资产与分镜。'
    }
    return ''
  }
  if (regenMode.value === 'append') {
    if (hasDownstreamAssets.value) {
      return '若新的一集引入了新角色、场景或道具，续写完成后建议到资产页重新识别补充。'
    }
    return ''
  }
  if (regenMode.value === 'episode') {
    if (hasEpisodeStoryboard.value) {
      return `重写第 ${number.value} 集后，本集已生成的分镜将被清空，其余集数不受影响。`
    }
    if (hasDownstreamAssets.value) {
      return '角色与场景编号保持不变；重写完成后如出场人物有变动，建议到资产页核对。'
    }
  }
  return ''
})

function sidebarEpisodeTitle(index: number): string {
  const saved = props.project.episodes[index]
  if (saved?.title?.trim()) return saved.title
  const planned = outlineEpisodesByNumber.value.get(index)?.title?.trim()
  if (planned) return planned
  return readEpisode(props.project, index).title
}

function episodeStatus(index: number): EpisodeGenerationStatus {
  const ep = backendEpisodesByNumber.value.get(index)
  const localScript = props.project.episodes[index]?.script?.trim() ?? ''
  return resolveEpisodeGenerationStatus({
    episodeNumber: index,
    writingEpisodeNumber: writingEpisodeNumber.value,
    hasWrittenScript: Boolean(ep?.script?.trim() || localScript),
    warningCount: ep?.warnings?.length ?? 0,
  })
}

function episodeStatusLabel(status: EpisodeGenerationStatus): string {
  switch (status) {
    case 'writing':
      return '正在撰写中'
    case 'warning':
      return '已完成，有质量门提醒'
    case 'completed':
      return '已完成'
    case 'pending':
    default:
      return '等待撰写'
  }
}

function canLeave() {
  if (!dirty.value) return true
  ui.notify('请先保存或取消当前编辑', 'info')
  return false
}

function clearEditDraft() {
  draft.value = undefined
  structuredDraft.value = undefined
  structuredSnapshot.value = ''
}

function startEdit() {
  if (busy.value) return
  if (props.project.persisted && !episode.value.script.trim()) return
  draft.value = { ...episode.value }
  if (backendEpisode.value?.scenes.length) {
    const cloned = cloneScenes(backendEpisode.value.scenes)
    structuredDraft.value = cloned
    structuredSnapshot.value = JSON.stringify(cloned)
  } else {
    structuredDraft.value = undefined
    structuredSnapshot.value = ''
  }
}

function selectEpisode(value: number) {
  if (value === number.value || !canLeave()) return
  clearEditDraft()
  number.value = value
}

async function addEpisode() {
  if (!canLeave() || busy.value) return
  if (hasBackendScript.value) {
    openRegen('append')
    return
  }
  if (props.project.persisted) return
  const added = studio.appendEpisode(props.project.id)
  if (added === undefined) return
  clearEditDraft()
  number.value = added
  await nextTick()
  const list = episodeList.value
  if (list) list.scrollTop = list.scrollHeight
}

async function save() {
  if (!draft.value || busy.value) return
  if (structuredDraft.value) {
    if (structuredError.value) {
      ui.notify(structuredError.value, 'info')
      return
    }
    const cleanTitle = draft.value.title.trim()
    const cleanScenes = normalizeScenes(structuredDraft.value)
    if (props.project.persisted) {
      try {
        await saveStructuredEpisodeApi(props.project.id, draft.value.number, cleanTitle, cleanScenes)
      } catch (error) {
        ui.notify(apiErrorMessage(error), 'error')
        return
      }
    }
    if (studio.saveStructuredEpisode(props.project.id, draft.value.number, cleanTitle, cleanScenes)) {
      clearEditDraft()
      ui.notify('本集剧本已保存并同步结构化数据', 'success')
    }
    return
  }
  if (studio.saveEpisode(props.project.id, draft.value)) clearEditDraft()
}

function openRegen(mode: 'episode' | 'story' | 'append') {
  if (!canLeave() || busy.value) return
  regenFeedback.value = ''
  regenMode.value = mode
}

async function submitRegen() {
  const mode = regenMode.value
  if (!mode || busy.value) return
  if (mode === 'story' ? !canRegenerateStory.value : !props.project.scriptResult) return

  const feedback = regenFeedback.value.trim()
  regenMode.value = null
  submittingJob.value = true

  try {
    if (mode === 'episode') {
      const targetNumber = number.value
      const accepted = await startRewriteEpisode(props.project.id, targetNumber, feedback)
      clearEditDraft()
      regenFeedback.value = ''
      scriptJobs.trackScriptJob(props.project.id, accepted.job, { targetEpisodeNumber: targetNumber })
      ui.notify(`已提交第 ${targetNumber} 集重写任务，正在后台生成`, 'info')
      return
    }

    if (mode === 'append') {
      const nextNumber = total.value + 1
      const accepted = await startAppendEpisode(props.project.id, feedback)
      clearEditDraft()
      regenFeedback.value = ''
      scriptJobs.trackScriptJob(props.project.id, accepted.job, {
        onCompleted: async (detail) => {
          const latest = detail.episodes[detail.episodes.length - 1]?.number ?? nextNumber
          number.value = latest
          await nextTick()
          const list = episodeList.value
          if (list) list.scrollTop = list.scrollHeight
        },
      })
      ui.notify(`已提交第 ${nextNumber} 集续写任务，完成后将自动切换`, 'info')
      return
    }

    const accepted = await startRegenerateStory(props.project.id, feedback)
    clearEditDraft()
    regenFeedback.value = ''
    number.value = 1
    scriptJobs.trackScriptJob(props.project.id, accepted.job)
    ui.notify('已开始生成全剧剧本，每写完一集将实时呈现', 'info')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    submittingJob.value = false
  }
}

async function resumeMissingEpisodes() {
  if (busy.value || missingEpisodeCount.value <= 0) return
  const missing = missingEpisodeCount.value
  submittingJob.value = true
  try {
    const accepted = await startResumeScript(props.project.id)
    clearEditDraft()
    scriptJobs.trackScriptJob(props.project.id, accepted.job)
    ui.notify(`已开始续写剩余 ${missing} 集剧本，每写完一集将实时呈现`, 'info')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    submittingJob.value = false
  }
}

onBeforeRouteLeave((to) => {
  if (!canLeave()) return false
  if (to.params.projectId === props.project.id) {
    if (scriptJobRunning.value) {
      ui.notify('剧本正在后台生成中，请等本轮完成后再进入下一步', 'info')
      return false
    }
    studio.confirmScript(props.project.id)
    if (props.project.persisted) {
      void confirmScriptApi(props.project.id).catch(() => {})
    }
  }
})
onBeforeRouteUpdate(canLeave)
</script>

<template>
  <section class="studio-script" aria-label="剧本确认">
    <div v-if="scriptJobRunning && activeJob" class="script-live-bar" role="status" aria-live="polite">
      <div class="script-live-bar-main">
        <div class="script-live-bar-left">
          <Loader2 class="script-live-spinner" :size="15" aria-hidden="true" />
          <strong class="script-live-title">{{ scriptJobTitle(activeJob.jobType, activeJob.targetEpisodeNumber) }}</strong>
          <span class="script-live-sep" aria-hidden="true">·</span>
          <span class="script-live-step">{{ activeJob.stepLabel }}</span>
        </div>
        <div class="script-live-bar-right">
          <span v-if="showFullScriptCounter" class="script-live-pill">
            已完成 {{ completedEpisodeCount }}/{{ plannedEpisodeCount }} 集
          </span>
          <span class="script-live-pct">{{ activeJob.progress }}%</span>
          <span class="script-live-timer">
            <Clock :size="13" aria-hidden="true" />
            {{ elapsedLabel }}
          </span>
        </div>
      </div>
      <div class="script-live-track" aria-hidden="true">
        <div class="script-live-fill" :style="{ width: `${Math.max(4, Math.min(100, activeJob.progress))}%` }" />
      </div>
    </div>

    <div v-else-if="scriptJobFailed && activeJob" class="script-live-error" role="alert">
      <div class="script-live-error-body">
        <AlertTriangle class="script-live-error-icon" :size="16" aria-hidden="true" />
        <div class="script-live-error-text">
          <strong>剧本生成任务中断</strong>
          <span>{{ activeJob.errorMessage || '后台生成未能完成，请重试。' }}</span>
        </div>
      </div>
      <div class="script-live-error-actions">
        <UiButton
          v-if="missingEpisodeCount > 0"
          variant="primary"
          size="sm"
          :disabled="busy"
          @click="resumeMissingEpisodes"
        >
          <template #leading><RefreshCw :size="14" aria-hidden="true" /></template>继续生成剩余 {{ missingEpisodeCount }} 集
        </UiButton>
        <UiButton
          v-else-if="activeJob.jobType === 'episode_rewrite' && canRewriteEpisode"
          variant="outline"
          size="sm"
          :disabled="busy"
          @click="openRegen('episode')"
        >
          <template #leading><RefreshCw :size="14" aria-hidden="true" /></template>重新重写本集
        </UiButton>
        <UiButton
          v-else-if="canRegenerateStory"
          variant="outline"
          size="sm"
          :disabled="busy"
          @click="openRegen('story')"
        >
          <template #leading><RotateCcw :size="14" aria-hidden="true" /></template>{{ hasBackendScript ? '重生成全剧' : '生成全剧剧本' }}
        </UiButton>
        <button
          type="button"
          class="script-live-dismiss"
          aria-label="关闭失败提示"
          @click="scriptJobs.dismiss(project.id)"
        >
          <X :size="15" aria-hidden="true" />
        </button>
      </div>
    </div>

    <div class="script-editor">
      <aside class="script-episodes">
        <div class="script-episodes-heading">
          <h2>分集</h2>
          <span v-if="scriptJobRunning && showFullScriptCounter">{{ completedEpisodeCount }}/{{ total }} 集</span>
          <span v-else>{{ total }} 集</span>
        </div>
        <div ref="episodeList" class="script-episodes-list">
          <StudioEpisodeList :total="total" :active="number">
            <template #default="{ number: index }">
              <button
                type="button"
                class="script-episode"
                :class="{
                  'is-writing': showEpisodeStatusIcons && episodeStatus(index) === 'writing',
                  'is-pending': showEpisodeStatusIcons && episodeStatus(index) === 'pending',
                }"
                :aria-current="index === number ? 'true' : undefined"
                @click="selectEpisode(index)"
              >
                <span class="script-episode-index">{{ index }}</span>
                <span class="script-episode-name">{{ sidebarEpisodeTitle(index) }}</span>
                <span
                  v-if="showEpisodeStatusIcons"
                  class="script-episode-status"
                  :title="episodeStatusLabel(episodeStatus(index))"
                  :aria-label="episodeStatusLabel(episodeStatus(index))"
                >
                  <Loader2
                    v-if="episodeStatus(index) === 'writing'"
                    class="script-ep-icon is-writing"
                    :size="13"
                    aria-hidden="true"
                  />
                  <AlertTriangle
                    v-else-if="episodeStatus(index) === 'warning'"
                    class="script-ep-icon is-warning"
                    :size="13"
                    aria-hidden="true"
                  />
                  <Check
                    v-else-if="episodeStatus(index) === 'completed'"
                    class="script-ep-icon is-done"
                    :size="13"
                    aria-hidden="true"
                  />
                  <CircleDashed
                    v-else
                    class="script-ep-icon is-pending"
                    :size="12"
                    aria-hidden="true"
                  />
                </span>
              </button>
            </template>
          </StudioEpisodeList>
        </div>
        <div class="script-episodes-footer">
          <UiButton
            v-if="missingEpisodeCount > 0 && !scriptJobRunning"
            class="script-resume-episodes"
            variant="primary"
            size="sm"
            :disabled="busy"
            @click="resumeMissingEpisodes"
          >
            <template #leading><RefreshCw :size="14" aria-hidden="true" /></template>继续生成剩余 {{ missingEpisodeCount }} 集
          </UiButton>
          <UiButton
            class="script-add-episode"
            variant="outline"
            size="sm"
            :disabled="total === Number.MAX_SAFE_INTEGER || busy || (project.persisted && !hasBackendScript)"
            @click="addEpisode"
          >
            <template #leading><Plus :size="15" aria-hidden="true" /></template>新增一集
          </UiButton>
          <UiButton
            v-if="canRegenerateStory"
            class="script-regen-all"
            variant="secondary"
            size="sm"
            :disabled="busy"
            @click="openRegen('story')"
          >
            <template #leading><RotateCcw :size="14" aria-hidden="true" /></template>{{ hasBackendScript ? '重生成全剧' : '生成全剧剧本' }}
          </UiButton>
        </div>
      </aside>

      <section class="script-document" aria-labelledby="script-episode-title">
        <header class="script-document-head">
          <div class="script-document-heading">
            <div class="script-document-title" :class="{ 'is-editing': draft }">
              <h2 id="script-episode-title">
                <span class="script-document-index">{{ episodeLabel }}</span>
                <span v-if="!draft && displayEpisodeTitle">{{ displayEpisodeTitle }}</span>
              </h2>
              <div v-if="draft" class="script-title-field">
                <UiInput v-model="draft.title" :form="editFormId" aria-label="本集标题" required />
              </div>
            </div>
            <span v-if="episode.example" class="script-example">示例草稿</span>
            <span v-if="dirty" class="script-example">未保存</span>
          </div>
          <div class="script-document-actions">
            <span v-if="estimatedSeconds !== null" class="script-duration">约 {{ estimatedSeconds }} 秒</span>
            <span class="script-word-count">{{ wordCount }}字/20000字</span>
            <UiButton
              v-if="!draft && canRewriteEpisode"
              variant="outline"
              size="sm"
              :disabled="busy"
              @click="openRegen('episode')"
            >
              <template #leading><RefreshCw :size="14" aria-hidden="true" /></template>重写本集
            </UiButton>
            <UiButton
              v-if="!draft"
              size="sm"
              :disabled="busy || (project.persisted && !episode.script.trim())"
              @click="startEdit"
            >
              <template #leading><Pencil :size="15" aria-hidden="true" /></template>编辑
            </UiButton>
          </div>
        </header>

        <div
          v-if="!draft && (
            (!scriptJobRunning && missingEpisodeCount > 0)
            || episodeWarnings.length > 0
            || (!scriptJobRunning && !hasBackendScript && canRegenerateStory)
            || isCurrentEpisodeRewriting
          )"
          class="script-banners"
        >
          <UiAlert
            v-if="isCurrentEpisodeRewriting"
            tone="info"
            title="正在按最新要求重写本集剧本"
            description="下方为上一版本内容，重写完成并落库后会自动替换为新版正文。"
          />
          <UiAlert
            v-if="!scriptJobRunning && !hasBackendScript && canRegenerateStory"
            tone="info"
            title="该项目尚未生成剧本正文"
            description="上次创建任务可能在大纲阶段中断；点击左侧「生成全剧剧本」即可直接重新生成。"
          />
          <UiAlert
            v-if="!scriptJobRunning && missingEpisodeCount > 0"
            tone="warning"
            :title="`全剧大纲已保存，还有 ${missingEpisodeCount} 集待继续生成`"
            description="已完成的分集均已安全落库；点击左侧「继续生成剩余分集」可从断点接着补写，不会覆盖已有集数。"
          />
          <UiAlert
            v-if="episodeWarnings.length > 0"
            tone="warning"
            title="本集质量门提醒"
            :description="episodeWarnings.join('；')"
          />
        </div>

        <form v-if="draft" :id="editFormId" class="script-edit-form" @submit.prevent="save">
          <StructuredScriptEditor
            v-if="isStructuredEditing && structuredDraft"
            v-model="structuredDraft"
            :outline="outline"
          />
          <div v-else class="script-body-field">
            <UiTextarea v-model="draft.script" label="剧本正文" :rows="4" />
          </div>
          <div class="script-edit-actions">
            <span v-if="structuredError" class="script-edit-error" role="alert">{{ structuredError }}</span>
            <UiButton variant="ghost" @click="clearEditDraft">取消编辑</UiButton>
            <UiButton type="submit" variant="primary" :disabled="!dirty || !draft.title.trim() || !!structuredError || busy">
              <template #leading><Save :size="16" aria-hidden="true" /></template>保存本集
            </UiButton>
          </div>
        </form>
        <div v-else class="script-reading">
          <p v-if="episode.script" class="script-prose">{{ episode.script }}</p>

          <article v-else-if="currentOutlineEpisode" class="script-outline-preview">
            <div class="script-outline-status">
              <span
                class="script-outline-badge"
                :class="{ 'is-writing': writingEpisodeNumber === number }"
              >
                <Loader2 v-if="writingEpisodeNumber === number" class="script-live-spinner" :size="13" aria-hidden="true" />
                <Clock v-else-if="scriptJobRunning" :size="13" aria-hidden="true" />
                <Sparkles v-else :size="13" aria-hidden="true" />
                <template v-if="writingEpisodeNumber === number">
                  正在撰写第 {{ number }} 集正文，完成后自动展示
                </template>
                <template v-else-if="scriptJobRunning">
                  排队撰写中 · 先预览本集分集大纲
                </template>
                <template v-else>
                  本集正文尚未生成 · 分集大纲预览
                </template>
              </span>
              <UiButton
                v-if="!scriptJobRunning && missingEpisodeCount > 0"
                variant="outline"
                size="sm"
                :disabled="busy"
                @click="resumeMissingEpisodes"
              >
                <template #leading><RefreshCw :size="13" aria-hidden="true" /></template>继续生成剩余 {{ missingEpisodeCount }} 集
              </UiButton>
            </div>

            <div v-if="currentOutlineEpisode.summary" class="script-outline-section">
              <h3>本集梗概</h3>
              <p>{{ currentOutlineEpisode.summary }}</p>
            </div>

            <div
              v-if="currentOutlineEpisode.hook || currentOutlineEpisode.suspense || currentOutlineEpisode.ending"
              class="script-outline-grid"
            >
              <div v-if="currentOutlineEpisode.hook" class="script-outline-card">
                <h3>开场钩子</h3>
                <p>{{ currentOutlineEpisode.hook }}</p>
              </div>
              <div v-if="currentOutlineEpisode.suspense" class="script-outline-card">
                <h3>中段悬念</h3>
                <p>{{ currentOutlineEpisode.suspense }}</p>
              </div>
              <div v-if="currentOutlineEpisode.ending" class="script-outline-card">
                <h3>结尾钩子</h3>
                <p>{{ currentOutlineEpisode.ending }}</p>
              </div>
            </div>

            <div
              v-if="outlineCharacters.length || outlineScenes.length || outlineProps.length"
              class="script-outline-tags"
            >
              <div v-if="outlineCharacters.length" class="script-outline-tag-group">
                <h4>出场角色</h4>
                <ul>
                  <li v-for="item in outlineCharacters" :key="item.id" :title="item.role || item.id">
                    <span>{{ item.name }}</span>
                    <small>{{ item.id }}</small>
                  </li>
                </ul>
              </div>
              <div v-if="outlineScenes.length" class="script-outline-tag-group">
                <h4>涉及场景</h4>
                <ul>
                  <li v-for="item in outlineScenes" :key="item.id" :title="item.meta || item.id">
                    <span>{{ item.name }}</span>
                    <small v-if="item.meta">{{ item.meta }}</small>
                  </li>
                </ul>
              </div>
              <div v-if="outlineProps.length" class="script-outline-tag-group">
                <h4>关键道具</h4>
                <ul>
                  <li v-for="item in outlineProps" :key="item.id" :title="item.role || item.id">
                    <span>{{ item.name }}</span>
                    <small>{{ item.id }}</small>
                  </li>
                </ul>
              </div>
            </div>
          </article>

          <div v-else-if="scriptJobRunning && activeJob" class="script-planning-skeleton">
            <div class="script-planning-head">
              <Loader2 class="script-live-spinner" :size="18" aria-hidden="true" />
              <div>
                <h3>{{ activeJob.stepLabel || '正在规划全剧分集大纲与世界观' }}</h3>
                <p>大纲保存后会立即解锁各集剧情卡片，随后每写完一集都会实时呈现；期间你可以自由切集浏览或离开当前页面。</p>
              </div>
            </div>
            <div class="script-skeleton-lines" aria-hidden="true">
              <span class="script-skeleton-line is-wide" />
              <span class="script-skeleton-line is-medium" />
              <span class="script-skeleton-line is-short" />
            </div>
          </div>

          <p v-else class="script-muted">暂无剧本正文</p>
        </div>
      </section>
    </div>

    <UiDialog v-model:open="regenOpen" :title="regenTitle" :description="regenDescription">
      <form :id="regenFormId" class="script-regen-form" @submit.prevent="submitRegen">
        <UiAlert v-if="regenWarning" tone="warning" :title="regenWarning" />
        <UiTextarea
          v-model="regenFeedback"
          :label="regenMode === 'append' ? '本集剧情方向（可选）' : '修改意见（可选）'"
          :rows="4"
          :maxlength="500"
          :placeholder="regenMode === 'story'
            ? '可留空直接重来；或说明整体方向，例如：悬疑节奏更快、反转更出人意料、减少拖沓过场'
            : regenMode === 'append'
              ? '可留空由 AI 自动承接上一集悬念续写；或写一句方向，例如：揭开房东真实身份，引入老物业管理员'
              : '可留空直接换一版重写；或说明本集修改点，例如：冲突提前到前3拍、对白更口语、结尾悬念更强'"
        />
      </form>
      <template #footer>
        <UiButton variant="ghost" :disabled="submittingJob" @click="regenOpen = false">取消</UiButton>
        <UiButton type="submit" :form="regenFormId" variant="primary" :loading="submittingJob" :disabled="busy">
          <template v-if="!submittingJob" #leading>
            <RotateCcw v-if="regenMode === 'story'" :size="15" aria-hidden="true" />
            <Plus v-else-if="regenMode === 'append'" :size="15" aria-hidden="true" />
            <RefreshCw v-else :size="15" aria-hidden="true" />
          </template>
          {{ regenMode === 'story' ? (hasBackendScript ? '开始重生成全剧' : '开始生成全剧') : regenMode === 'append' ? `开始续写第 ${total + 1} 集` : `开始重写第 ${number} 集` }}
        </UiButton>
      </template>
    </UiDialog>
  </section>
</template>

<style scoped>
.studio-script { display: flex; flex: 1; flex-direction: column; gap: 12px; min-height: 0; padding-top: 12px; }
.script-live-bar {
  position: relative;
  flex-shrink: 0;
  overflow: hidden;
  border: 1px solid rgb(240 184 75 / 26%);
  border-radius: 8px;
  background: linear-gradient(90deg, rgb(240 184 75 / 9%), rgb(255 255 255 / 2.5%) 55%, rgb(255 255 255 / 2%));
}
.script-live-bar-main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
  padding: 10px 14px;
}
.script-live-bar-left { display: flex; align-items: center; gap: 8px; min-width: 0; flex: 1 1 260px; }
.script-live-title { flex-shrink: 0; color: var(--color-gold-soft); font-size: 13px; font-weight: 600; }
.script-live-sep { flex-shrink: 0; color: var(--color-muted); }
.script-live-step { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--color-text); font-size: 13px; }
.script-live-bar-right { display: flex; flex-shrink: 0; align-items: center; gap: 10px; font-size: 12px; font-variant-numeric: tabular-nums; }
.script-live-pill { padding: 2px 8px; border: 1px solid rgb(240 184 75 / 28%); border-radius: 999px; background: rgb(240 184 75 / 12%); color: var(--color-gold-soft); font-weight: 500; }
.script-live-pct { color: var(--color-text); font-weight: 600; }
.script-live-timer { display: inline-flex; align-items: center; gap: 4px; color: var(--color-muted); }
.script-live-track { height: 2px; background: rgb(255 255 255 / 7%); }
.script-live-fill { height: 100%; background: linear-gradient(90deg, var(--color-gold), #ffe09a); transition: width .35s ease; }
.script-live-spinner { flex-shrink: 0; color: var(--color-gold-soft); animation: script-spin 1.1s linear infinite; }
.script-live-error {
  display: flex;
  flex-shrink: 0;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px 14px;
  padding: 10px 14px;
  border: 1px solid rgb(239 68 68 / 34%);
  border-radius: 8px;
  background: rgb(239 68 68 / 9%);
}
.script-live-error-body { display: flex; align-items: flex-start; gap: 10px; min-width: 0; flex: 1 1 260px; }
.script-live-error-icon { flex-shrink: 0; margin-top: 2px; color: #f87171; }
.script-live-error-text { display: grid; gap: 2px; min-width: 0; }
.script-live-error-text strong { color: #fecaca; font-size: 13px; font-weight: 600; }
.script-live-error-text span { color: var(--color-text); font-size: 12px; line-height: 1.5; overflow-wrap: anywhere; }
.script-live-error-actions { display: flex; flex-shrink: 0; align-items: center; gap: 8px; }
.script-live-dismiss { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 6px; color: var(--color-muted); transition: background .15s, color .15s; }
.script-live-dismiss:hover { background: rgb(255 255 255 / 8%); color: var(--color-text); }

.script-editor { display: grid; flex: 1; min-height: 0; overflow: hidden; grid-template-columns: minmax(180px, 236px) minmax(0, 1fr); align-items: stretch; border: 1px solid var(--border-subtle); border-radius: 8px; background: var(--color-surface); }
.script-episodes { display: grid; grid-template-rows: auto minmax(0, 1fr) auto; min-width: 0; min-height: 0; border-right: 1px solid var(--border-subtle); padding: 16px 12px; background: rgb(255 255 255 / 1.5%); }
.script-episodes-list { min-height: 0; overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin; scrollbar-color: rgb(255 255 255 / 16%) transparent; }
.script-episodes-footer { display: grid; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-subtle); }
.script-add-episode, .script-regen-all { width: 100%; min-height: 36px; }
.script-regen-all { color: #c5c7d0; }
.script-regen-all:hover:not(:disabled) { border-color: rgb(240 184 75 / 35%); color: var(--color-gold-soft); }
.script-episodes-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin: 0 4px 14px; }
.script-episodes-heading h2 { margin: 0; color: var(--color-text); font-size: 14px; font-weight: 600; overflow-wrap: anywhere; }
.script-episodes-heading > span { color: var(--color-muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.script-episode { position: relative; display: grid; grid-template-columns: 22px minmax(0, 1fr) auto; align-items: center; gap: 8px; width: 100%; min-height: 42px; padding: 8px 10px; border: 1px solid transparent; border-radius: 7px; color: var(--color-muted); text-align: left; transition: background .15s, border-color .15s, color .15s; }
.script-episode:hover { border-color: rgb(255 255 255 / 8%); background: var(--surface-hover); color: var(--color-text); }
.script-episode.is-writing { border-color: rgb(240 184 75 / 22%); background: rgb(240 184 75 / 6%); color: var(--color-text); }
.script-episode.is-pending:not([aria-current="true"]) { opacity: .72; }
.script-episode[aria-current="true"] { border-color: rgb(240 184 75 / 22%); background: linear-gradient(90deg, rgb(240 184 75 / 14%), rgb(240 184 75 / 6%)); color: var(--color-gold-soft); opacity: 1; }
.script-episode[aria-current="true"]::before { position: absolute; top: 8px; bottom: 8px; left: -1px; width: 2px; border-radius: 2px; background: var(--color-gold); content: ''; }
.script-episode-index { color: inherit; text-align: center; font-variant-numeric: tabular-nums; font-size: 12px; }
.script-episode-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.script-episode-status { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
.script-ep-icon.is-writing { color: var(--color-gold-soft); animation: script-spin 1.1s linear infinite; }
.script-ep-icon.is-warning { color: #f59e0b; }
.script-ep-icon.is-done { color: #34d399; opacity: .82; }
.script-ep-icon.is-pending { color: var(--color-muted); opacity: .55; }

.script-document { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
.script-document-head { display: flex; flex-shrink: 0; flex-wrap: wrap; align-items: center; gap: 8px 16px; padding: 12px 16px; border-bottom: 1px solid var(--border-subtle); }
.script-document-heading { display: flex; flex: 1 1 110px; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; min-width: 0; }
.script-document-title { display: flex; align-items: center; gap: 8px; min-width: 0; max-width: 100%; }
.script-document-title.is-editing { flex: 1 1 190px; }
.script-document-heading h2 { display: flex; align-items: baseline; gap: 8px; min-width: 0; margin: 0; font-size: var(--font-size-body); font-weight: 500; line-height: 1.4; overflow-wrap: anywhere; }
.script-document-index { flex-shrink: 0; color: var(--color-gold-soft); font-size: 13px; white-space: nowrap; }
.script-title-field { flex: 1; min-width: 0; max-width: 320px; }
.script-title-field :deep(.ui-input) { height: 34px; padding-inline: 8px; }
.script-document-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; min-height: 32px; margin-left: auto; }
.script-word-count { color: var(--color-muted); font-size: 12px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.script-duration { padding: 2px 8px; border-radius: 999px; background: var(--gold-tint); color: var(--color-gold-soft); font-size: 12px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.script-muted { color: var(--color-muted); }
.script-example { color: var(--color-gold-soft); font-size: 12px; }
.script-reading, .script-edit-form { padding: 16px; }
.script-banners { display: grid; flex-shrink: 0; gap: 8px; padding: 12px 16px 0; }
.script-resume-episodes { width: 100%; }
.script-reading { flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin; scrollbar-color: rgb(255 255 255 / 16%) transparent; }
.script-reading p { margin: 0; overflow-wrap: anywhere; white-space: pre-wrap; }
.script-prose { line-height: 1.9; }

.script-outline-preview { display: grid; gap: 16px; max-width: 820px; }
.script-outline-status { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; }
.script-outline-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 11px;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: rgb(255 255 255 / 3%);
  color: var(--color-muted);
  font-size: 12px;
}
.script-outline-badge.is-writing {
  border-color: rgb(240 184 75 / 32%);
  background: rgb(240 184 75 / 10%);
  color: var(--color-gold-soft);
}
.script-outline-section {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: rgb(255 255 255 / 2%);
}
.script-outline-section h3, .script-outline-card h3 { margin: 0; color: var(--color-gold-soft); font-size: 12px; font-weight: 600; letter-spacing: .02em; }
.script-outline-section p, .script-outline-card p { color: var(--color-text); font-size: 14px; line-height: 1.75; }
.script-outline-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; }
.script-outline-card {
  display: grid;
  align-content: start;
  gap: 6px;
  padding: 12px 14px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: rgb(255 255 255 / 1.8%);
}
.script-outline-tags { display: grid; gap: 12px; padding-top: 4px; }
.script-outline-tag-group { display: grid; gap: 6px; }
.script-outline-tag-group h4 { margin: 0; color: var(--color-muted); font-size: 12px; font-weight: 500; }
.script-outline-tag-group ul { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; padding: 0; list-style: none; }
.script-outline-tag-group li {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: rgb(255 255 255 / 2.5%);
  color: var(--color-text);
  font-size: 12px;
}
.script-outline-tag-group li small { color: var(--color-muted); font-size: 11px; }

.script-planning-skeleton {
  display: grid;
  gap: 18px;
  max-width: 680px;
  padding: 20px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: rgb(255 255 255 / 1.8%);
}
.script-planning-head { display: flex; align-items: flex-start; gap: 12px; }
.script-planning-head h3 { margin: 0 0 6px; color: var(--color-text); font-size: 14px; font-weight: 600; }
.script-planning-head p { color: var(--color-muted); font-size: 13px; line-height: 1.65; }
.script-skeleton-lines { display: grid; gap: 10px; }
.script-skeleton-line {
  display: block;
  height: 11px;
  border-radius: 6px;
  background: linear-gradient(90deg, rgb(255 255 255 / 4%), rgb(255 255 255 / 10%), rgb(255 255 255 / 4%));
  background-size: 200% 100%;
  animation: script-shimmer 1.6s ease-in-out infinite;
}
.script-skeleton-line.is-wide { width: 92%; }
.script-skeleton-line.is-medium { width: 74%; }
.script-skeleton-line.is-short { width: 48%; }

.script-edit-form { display: grid; flex: 1; min-height: 0; grid-template-rows: minmax(0, 1fr) auto; gap: 14px; }
.script-body-field { display: grid; min-height: 0; }
.script-body-field :deep(.ui-field) { grid-template-rows: auto minmax(0, 1fr); min-height: 0; }
.script-body-field :deep(.ui-textarea) { height: 100%; overflow-y: auto; resize: none; }
.script-edit-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 8px 12px; }
.script-edit-error { margin-right: auto; color: var(--color-error); font-size: 12px; }
.script-regen-form { display: grid; gap: 16px; }
.script-regen-form :deep(.ui-alert) { padding: 10px 12px; }
.script-regen-form :deep(.ui-alert strong) { font-size: 13px; font-weight: 400; line-height: 1.55; }

@keyframes script-spin {
  to { transform: rotate(360deg); }
}
@keyframes script-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

@media (max-width: 640px) {
  .script-editor { flex: 1 0 auto; overflow: visible; grid-template-columns: minmax(0, 1fr); }
  .script-episodes { max-height: 230px; border-right: 0; border-bottom: 1px solid var(--border-subtle); }
  .script-reading { overflow-y: visible; }
  .script-document-head { gap: 8px; padding-inline: 12px; }
}
</style>
