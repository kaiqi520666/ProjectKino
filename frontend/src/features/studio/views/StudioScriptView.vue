<script setup lang="ts">
import { computed, nextTick, ref, useId } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { Pencil, Plus, RefreshCw, RotateCcw, Save } from 'lucide-vue-next'
import UiAlert from '@/components/ui/UiAlert.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiTextarea from '@/components/ui/UiTextarea.vue'
import { useAuthStore } from '@/stores/auth'
import { useGenerationStore } from '@/stores/generation'
import { useUiStore } from '@/stores/ui'
import {
  apiErrorMessage,
  confirmScriptApi,
  getProjectDetail,
  isRetryableApiError,
  saveStructuredEpisodeApi,
  startAppendEpisode,
  startRegenerateStory,
  startRewriteEpisode,
  watchJob,
} from '../api'
import type { BackendScene, ProjectDetailOut } from '../api-types'
import { artStyles } from '../components/art-styles'
import StructuredScriptEditor from '../components/StructuredScriptEditor.vue'
import StudioEpisodeList from '../components/StudioEpisodeList.vue'
import { cloneScenes, normalizeScenes, renderStructuredScript, scenesSeconds, validateStructuredScenes } from '../script-structure'
import { readEpisode } from '../studio-project'
import type { StudioEpisode, StudioProject } from '../studio-project'
import { useStudioStore } from '../studio-store'

const props = defineProps<{ project: StudioProject }>()
const auth = useAuthStore()
const studio = useStudioStore()
const generation = useGenerationStore()
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

const total = computed(() => props.project.creation.settings.episodeCount)
const episode = computed(() => readEpisode(props.project, number.value))
const backendEpisode = computed(() => props.project.scriptResult?.episodes.find((item) => item.number === number.value))
const episodeLabel = computed(() => `第 ${number.value} 集`)
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
    return renderStructuredScript(normalizeScenes(structuredDraft.value), props.project.scriptResult?.outline)
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
const canRewriteEpisode = computed(() => {
  const outlineEpisodes = props.project.scriptResult?.outline?.episodes
  if (!Array.isArray(outlineEpisodes)) return false
  return outlineEpisodes.some((item) => (item as { number?: unknown })?.number === number.value)
})
const hasDownstreamAssets = computed(() => !!props.project.assets?.length)
const hasEpisodeStoryboard = computed(() => !!props.project.storyboards?.[number.value])
const hasAnyStoryboard = computed(() => !!props.project.storyboards && Object.keys(props.project.storyboards).length > 0)

const regenOpen = computed({
  get: () => regenMode.value !== null,
  set: (open: boolean) => {
    if (!open && !generation.isRunning) {
      regenMode.value = null
      regenFeedback.value = ''
    }
  },
})

const regenTitle = computed(() => {
  if (regenMode.value === 'story') return '重生成全剧剧本'
  if (regenMode.value === 'append') return `新增第 ${total.value + 1} 集`
  return `重写第 ${number.value} 集`
})
const regenDescription = computed(() => {
  if (regenMode.value === 'story') return '将重新规划全剧分集大纲与人物场景编号，并重写所有集数。'
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
  if (!canLeave() || generation.isRunning) return
  if (hasBackendScript.value) {
    openRegen('append')
    return
  }
  const added = studio.appendEpisode(props.project.id)
  if (added === undefined) return
  clearEditDraft()
  number.value = added
  await nextTick()
  const list = episodeList.value
  if (list) list.scrollTop = list.scrollHeight
}

async function save() {
  if (!draft.value) return
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
  if (!canLeave() || generation.isRunning) return
  regenFeedback.value = ''
  regenMode.value = mode
}

async function submitRegen() {
  const mode = regenMode.value
  if (!mode || !props.project.scriptResult || generation.isRunning) return

  const feedback = regenFeedback.value.trim()
  const settings = props.project.creation.settings
  const style = artStyles.find(({ value }) => value === settings.visualStyle)
  regenMode.value = null

  if (mode === 'episode') {
    const targetNumber = number.value
    const result = await generation.runTask(
      {
        title: `正在重写第 ${targetNumber} 集剧本`,
        subtitle: `${settings.name} · ${episodeLabel.value}`,
        description: feedback ? '正在结合你的修改意见重写本集剧本' : '正在沿用全剧大纲换一版更紧凑的写法重写本集',
        steps: [
          '读取全剧大纲、角色场景编号与前后集衔接信息',
          '结合修改意见重写本集结构化节拍流',
          '执行剧本质量门校验并刷新本集正文',
        ],
        hint: '后台队列正在重写本集，完成后自动刷新正文',
        formatError: apiErrorMessage,
        canRetryError: isRetryableApiError,
        successMessage: () => `第 ${targetNumber} 集已重写完成`,
      },
      async (controls) => {
        try {
          const accepted = await startRewriteEpisode(props.project.id, targetNumber, feedback)
          controls.setJobId(accepted.job.id)
          controls.setProgress(accepted.job.progress)
          await watchJob(accepted.job.id, (job) => {
            controls.setProgress(job.progress)
            if (job.stepLabel) controls.setDescription(job.stepLabel)
            controls.setStep(job.stepIndex <= 1 ? 1 : 2)
          })
          const detail = await getProjectDetail(props.project.id)
          studio.hydrateProjectDetail(detail)
          clearEditDraft()
          ui.notify(`第 ${targetNumber} 集已重写完成`, 'success')
          return detail
        } finally {
          void auth.refreshBalance()
        }
      },
    )
    if (result) regenFeedback.value = ''
    return
  }

  if (mode === 'append') {
    const nextNumber = total.value + 1
    const result = await generation.runTask(
      {
        title: `正在续写第 ${nextNumber} 集剧本`,
        subtitle: `${settings.name} · 第 ${nextNumber} 集`,
        description: feedback ? '正在结合你的剧情方向规划并续写新的一集' : `正在承接第 ${total.value} 集结尾悬念规划并续写新的一集`,
        steps: [
          '读取现有大纲、人物场景编号与上一集结尾悬念',
          '规划新分集计划并按需追加新角色/场景编号',
          '撰写结构化剧本并执行质量门校验',
        ],
        hint: '后台队列正在续写新分集，完成后自动切到新的一集',
        formatError: apiErrorMessage,
        canRetryError: isRetryableApiError,
        successMessage: () => `第 ${nextNumber} 集已续写完成`,
      },
      async (controls) => {
        try {
          const accepted = await startAppendEpisode(props.project.id, feedback)
          controls.setJobId(accepted.job.id)
          controls.setProgress(accepted.job.progress)
          await watchJob(accepted.job.id, (job) => {
            controls.setProgress(job.progress)
            if (job.stepLabel) controls.setDescription(job.stepLabel)
            controls.setStep(Math.min(2, Math.max(0, job.stepIndex - 1)))
          })
          const detail = await getProjectDetail(props.project.id)
          studio.hydrateProjectDetail(detail)
          clearEditDraft()
          const latest = detail.episodes[detail.episodes.length - 1]?.number ?? nextNumber
          number.value = latest
          await nextTick()
          const list = episodeList.value
          if (list) list.scrollTop = list.scrollHeight
          ui.notify(`第 ${latest} 集已续写完成`, 'success')
          return detail
        } finally {
          void auth.refreshBalance()
        }
      },
    )
    if (result) regenFeedback.value = ''
    return
  }

  const subtitle = [settings.name, `${settings.episodeCount} 集`, style?.label || settings.visualStyle].filter(Boolean).join(' · ')
  const result = await generation.runTask(
    {
      title: '正在重新生成全剧剧本',
      subtitle,
      description: feedback ? '正在结合你的修改意见重新规划大纲并撰写全剧剧本' : '正在重新规划分集大纲、世界观并逐集撰写剧本',
      steps: [
        '读取原始故事内容与项目设置',
        '重新规划全剧大纲、角色与世界基准',
        '逐集撰写结构化剧本并执行质量门校验',
      ],
      hint: '全剧重生成已在后台队列运行，完成后自动刷新全集',
      formatError: apiErrorMessage,
      canRetryError: isRetryableApiError,
      successMessage: (detail: ProjectDetailOut) => `《${detail.name}》全剧 ${detail.episodes.length} 集已重新生成`,
    },
    async (controls) => {
      try {
        const accepted = await startRegenerateStory(props.project.id, feedback)
        controls.setJobId(accepted.job.id)
        controls.setProgress(accepted.job.progress)
        await watchJob(accepted.job.id, (job) => {
          controls.setProgress(job.progress)
          if (job.stepLabel) controls.setDescription(job.stepLabel)
          controls.setStep(job.stepIndex <= 1 ? 1 : 2)
        })
        const detail = await getProjectDetail(props.project.id)
        studio.hydrateProjectDetail(detail)
        clearEditDraft()
        number.value = 1
        ui.notify(`《${detail.name}》全剧已重新生成`, 'success')
        return detail
      } finally {
        void auth.refreshBalance()
      }
    },
  )
  if (result) regenFeedback.value = ''
}

onBeforeRouteLeave((to) => {
  if (!canLeave()) return false
  if (to.params.projectId === props.project.id) {
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
    <div class="script-editor">
      <aside class="script-episodes">
        <div class="script-episodes-heading">
          <h2>分集</h2>
          <span>{{ total }} 集</span>
        </div>
        <div ref="episodeList" class="script-episodes-list">
          <StudioEpisodeList :total="total" :active="number">
            <template #default="{ number: index }">
              <button type="button" class="script-episode" :aria-current="index === number ? 'true' : undefined" @click="selectEpisode(index)">
                <span class="script-episode-index">{{ index }}</span>
                <span>{{ readEpisode(project, index).title }}</span>
              </button>
            </template>
          </StudioEpisodeList>
        </div>
        <div class="script-episodes-footer">
          <UiButton class="script-add-episode" variant="outline" size="sm" :disabled="total === Number.MAX_SAFE_INTEGER || generation.isRunning" @click="addEpisode">
            <template #leading><Plus :size="15" aria-hidden="true" /></template>新增一集
          </UiButton>
          <UiButton v-if="hasBackendScript" class="script-regen-all" variant="secondary" size="sm" :disabled="generation.isRunning" @click="openRegen('story')">
            <template #leading><RotateCcw :size="14" aria-hidden="true" /></template>重生成全剧
          </UiButton>
        </div>
      </aside>

      <section class="script-document" aria-labelledby="script-episode-title">
        <header class="script-document-head">
          <div class="script-document-heading">
            <div class="script-document-title" :class="{ 'is-editing': draft }">
              <h2 id="script-episode-title">
                <span class="script-document-index">{{ episodeLabel }}</span>
                <span v-if="!draft && episode.title !== episodeLabel">{{ episode.title }}</span>
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
              :disabled="generation.isRunning"
              @click="openRegen('episode')"
            >
              <template #leading><RefreshCw :size="14" aria-hidden="true" /></template>重写本集
            </UiButton>
            <UiButton v-if="!draft" size="sm" :disabled="generation.isRunning" @click="startEdit">
              <template #leading><Pencil :size="15" aria-hidden="true" /></template>编辑
            </UiButton>
          </div>
        </header>

        <form v-if="draft" :id="editFormId" class="script-edit-form" @submit.prevent="save">
          <StructuredScriptEditor
            v-if="isStructuredEditing && structuredDraft"
            v-model="structuredDraft"
            :outline="project.scriptResult?.outline"
          />
          <div v-else class="script-body-field">
            <UiTextarea v-model="draft.script" label="剧本正文" :rows="4" />
          </div>
          <div class="script-edit-actions">
            <span v-if="structuredError" class="script-edit-error" role="alert">{{ structuredError }}</span>
            <UiButton variant="ghost" @click="clearEditDraft">取消编辑</UiButton>
            <UiButton type="submit" variant="primary" :disabled="!dirty || !draft.title.trim() || !!structuredError">
              <template #leading><Save :size="16" aria-hidden="true" /></template>保存本集
            </UiButton>
          </div>
        </form>
        <div v-else class="script-reading">
          <p v-if="episode.script" class="script-prose">{{ episode.script }}</p>
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
        <UiButton variant="ghost" :disabled="generation.isRunning" @click="regenOpen = false">取消</UiButton>
        <UiButton type="submit" :form="regenFormId" variant="primary" :disabled="generation.isRunning">
          <template #leading>
            <RotateCcw v-if="regenMode === 'story'" :size="15" aria-hidden="true" />
            <Plus v-else-if="regenMode === 'append'" :size="15" aria-hidden="true" />
            <RefreshCw v-else :size="15" aria-hidden="true" />
          </template>
          {{ regenMode === 'story' ? '开始重生成全剧' : regenMode === 'append' ? `开始续写第 ${total + 1} 集` : `开始重写第 ${number} 集` }}
        </UiButton>
      </template>
    </UiDialog>
  </section>
</template>

<style scoped>
.studio-script { display: flex; flex: 1; flex-direction: column; min-height: 0; padding-top: 16px; }
.script-editor { display: grid; flex: 1; min-height: 0; overflow: hidden; grid-template-columns: minmax(160px, 220px) minmax(0, 1fr); align-items: stretch; border: 1px solid var(--border-subtle); border-radius: 8px; background: var(--color-surface); }
.script-episodes { display: grid; grid-template-rows: auto minmax(0, 1fr) auto; min-width: 0; min-height: 0; border-right: 1px solid var(--border-subtle); padding: 16px 12px; background: rgb(255 255 255 / 1.5%); }
.script-episodes-list { min-height: 0; overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin; scrollbar-color: rgb(255 255 255 / 16%) transparent; }
.script-episodes-footer { display: grid; gap: 8px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-subtle); }
.script-add-episode, .script-regen-all { width: 100%; min-height: 36px; }
.script-regen-all { color: #c5c7d0; }
.script-regen-all:hover:not(:disabled) { border-color: rgb(240 184 75 / 35%); color: var(--color-gold-soft); }
.script-episodes-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin: 0 4px 14px; }
.script-episodes-heading h2 { margin: 0; color: var(--color-text); font-size: 14px; font-weight: 600; overflow-wrap: anywhere; }
.script-episodes-heading > span { color: var(--color-muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.script-episode { position: relative; display: grid; grid-template-columns: 26px minmax(0, 1fr); align-items: center; gap: 8px; width: 100%; min-height: 42px; padding: 8px 10px; border: 1px solid transparent; border-radius: 7px; color: var(--color-muted); text-align: left; overflow-wrap: anywhere; transition: background .15s, border-color .15s, color .15s; }
.script-episode:hover { border-color: rgb(255 255 255 / 8%); background: var(--surface-hover); color: var(--color-text); }
.script-episode[aria-current="true"] { border-color: rgb(240 184 75 / 18%); background: linear-gradient(90deg, rgb(240 184 75 / 13%), rgb(240 184 75 / 6%)); color: var(--color-gold-soft); }
.script-episode[aria-current="true"]::before { position: absolute; top: 8px; bottom: 8px; left: -1px; width: 2px; border-radius: 2px; background: var(--color-gold); content: ''; }
.script-episode-index { color: inherit; text-align: center; font-variant-numeric: tabular-nums; font-size: 12px; }
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
.script-reading { flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin; scrollbar-color: rgb(255 255 255 / 16%) transparent; }
.script-reading p { margin: 0; overflow-wrap: anywhere; white-space: pre-wrap; }
.script-prose { line-height: 1.9; }
.script-edit-form { display: grid; flex: 1; min-height: 0; grid-template-rows: minmax(0, 1fr) auto; gap: 14px; }
.script-body-field { display: grid; min-height: 0; }
.script-body-field :deep(.ui-field) { grid-template-rows: auto minmax(0, 1fr); min-height: 0; }
.script-body-field :deep(.ui-textarea) { height: 100%; overflow-y: auto; resize: none; }
.script-edit-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 8px 12px; }
.script-edit-error { margin-right: auto; color: var(--color-error); font-size: 12px; }
.script-regen-form { display: grid; gap: 16px; }
.script-regen-form :deep(.ui-alert) { padding: 10px 12px; }
.script-regen-form :deep(.ui-alert strong) { font-size: 13px; font-weight: 400; line-height: 1.55; }
@media (max-width: 640px) {
  .script-editor { flex: 1 0 auto; overflow: visible; grid-template-columns: minmax(0, 1fr); }
  .script-episodes { max-height: 230px; border-right: 0; border-bottom: 1px solid var(--border-subtle); }
  .script-reading { overflow-y: visible; }
  .script-document-head { gap: 8px; padding-inline: 12px; }
}
</style>
