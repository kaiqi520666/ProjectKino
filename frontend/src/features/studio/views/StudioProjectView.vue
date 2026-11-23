<script setup lang="ts">
import { computed, nextTick, ref, useTemplateRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Check, Heading, Pencil, X } from 'lucide-vue-next'
import EmptyState from '@/components/business/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { useAuthStore } from '@/stores/auth'
import { useGenerationStore } from '@/stores/generation'
import { useUiStore } from '@/stores/ui'
import { apiErrorMessage, getProjectDetail, isRetryableApiError, renameProjectApi, watchJob } from '../api'
import { useAssetExtractStore } from '../asset-extract-store'
import { artStyles } from '../components/art-styles'
import { contentLanguages, formatDurationLabel } from '../components/drama-creation'
import { isScriptJobType } from '../script-job-helpers'
import { useScriptJobStore } from '../script-job-store'
import { useStudioStore } from '../studio-store'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const studio = useStudioStore()
const scriptJobs = useScriptJobStore()
const assetExtractJobs = useAssetExtractStore()
const generation = useGenerationStore()
const ui = useUiStore()
const loadingProject = ref(false)
const loadError = ref('')
const projectId = computed(() => String(route.params.projectId))
const project = computed(() => studio.getProject(projectId.value))
const scriptJobRunning = computed(() => Boolean(project.value && scriptJobs.isRunning(project.value.id)))
const assetExtractRunning = computed(() => Boolean(project.value && assetExtractJobs.isRunning(project.value.id)))
const settings = computed(() => project.value?.creation.settings)
const draftName = ref<string>()
const nameInput = useTemplateRef<HTMLInputElement>('nameInput')
const renameTrigger = useTemplateRef<HTMLButtonElement>('renameTrigger')
const artStyle = computed(() => artStyles.find(({ value }) => value === settings.value?.visualStyle))
const language = computed(() => contentLanguages.find(({ value }) => value === settings.value?.language)?.label)
const world = computed(() => project.value?.scriptResult?.outline?.world)
const steps = [
  { name: 'studio-script', label: '剧本确认' },
  { name: 'studio-assets', label: '资产生成' },
  { name: 'studio-storyboard', label: '分镜制作' },
] as const
const active = computed(() => route.name === 'studio-episode' ? 'studio-storyboard' : route.name)
const fillHeight = computed(() => active.value === 'studio-script' || active.value === 'studio-assets')

async function ensureProjectLoaded(id: string) {
  const existing = studio.getProject(id)
  if (existing && (!existing.persisted || existing.loadedDetail)) {
    const existingScriptJob = existing.activeJobs?.find((item) => isScriptJobType(item.jobType))
    if (existingScriptJob) {
      scriptJobs.trackScriptJob(existing.id, existingScriptJob)
    }
    const existingAssetJob = existing.activeJobs?.find((item) => item.jobType === 'assets_extract')
    if (existingAssetJob) {
      assetExtractJobs.trackExtractJob(existing.id, existingAssetJob)
    }
    return
  }
  loadingProject.value = true
  loadError.value = ''
  try {
    const detail = await getProjectDetail(id)
    const hydrated = studio.hydrateProjectDetail(detail)
    const activeScriptJob = hydrated.activeJobs?.find((item) => isScriptJobType(item.jobType))
    if (activeScriptJob) {
      scriptJobs.trackScriptJob(detail.id, activeScriptJob)
    }
    const activeAssetJob = hydrated.activeJobs?.find((item) => item.jobType === 'assets_extract')
    if (activeAssetJob) {
      assetExtractJobs.trackExtractJob(detail.id, activeAssetJob)
    }
    const runningJob = hydrated.activeJobs?.find(
      (item) =>
        !isScriptJobType(item.jobType)
        && item.jobType !== 'assets_extract'
        && item.jobType !== 'asset_image'
        && item.jobType !== 'clip_video',
    )
    if (runningJob && !generation.isRunning) {
      void generation.runTask(
        {
          title: '正在恢复后台生成任务',
          subtitle: detail.name,
          description: runningJob.stepLabel || '正在同步后台任务进度',
          hint: '后台任务仍在继续执行，完成后自动刷新项目内容',
          formatError: apiErrorMessage,
          canRetryError: isRetryableApiError,
          successMessage: () => '后台任务已完成',
        },
        async (controls) => {
          controls.setJobId(runningJob.id)
          controls.setProgress(runningJob.progress)
          try {
            await watchJob(runningJob.id, (job) => {
              controls.setProgress(job.progress)
              if (job.stepLabel) controls.setDescription(job.stepLabel)
            })
            const refreshed = await getProjectDetail(id)
            studio.hydrateProjectDetail(refreshed)
            return refreshed
          } finally {
            void auth.refreshBalance()
          }
        },
      )
    }
  } catch (error) {
    loadError.value = apiErrorMessage(error)
  } finally {
    loadingProject.value = false
  }
}

watch(projectId, (id) => {
  if (id) void ensureProjectLoaded(id)
}, { immediate: true })

watch([() => project.value?.id, () => route.name === 'studio-episode'], () => {
  draftName.value = undefined
})

watch([project, active, scriptJobRunning, assetExtractRunning], ([value, step, scriptRunning, assetsRunning]) => {
  if (!value || value.loadedDetail === false) return
  if (step !== 'studio-script' && (!value.scriptConfirmed || scriptRunning)) {
    void router.replace({ name: 'studio-script', params: { projectId: value.id } })
    return
  }
  if (step === 'studio-storyboard' && assetsRunning) {
    void router.replace({ name: 'studio-assets', params: { projectId: value.id } })
  }
}, { immediate: true })

function isStepLocked(stepName: (typeof steps)[number]['name']) {
  if (stepName !== 'studio-script' && scriptJobRunning.value) return true
  if (stepName === 'studio-storyboard' && assetExtractRunning.value) return true
  return false
}

function handleStepClick(event: MouseEvent, stepName: (typeof steps)[number]['name']) {
  if (stepName !== 'studio-script' && scriptJobRunning.value) {
    event.preventDefault()
    ui.notify('剧本正在后台生成中，请等本轮完成后再进入下一步', 'info')
    return
  }
  if (stepName === 'studio-storyboard' && assetExtractRunning.value) {
    event.preventDefault()
    ui.notify('资产正在后台识别中，请等识别完成后再进入分镜制作', 'info')
  }
}

async function startRename() {
  if (!settings.value) return

  draftName.value = settings.value.name
  await nextTick()
  nameInput.value?.focus()
  nameInput.value?.select()
}

async function closeRename() {
  draftName.value = undefined
  await nextTick()
  renameTrigger.value?.focus()
}

async function saveName() {
  if (!project.value || draftName.value === undefined) return
  const clean = draftName.value.trim()
  if (!clean) return
  if (project.value.persisted) {
    try {
      await renameProjectApi(project.value.id, clean)
    } catch (error) {
      ui.notify(apiErrorMessage(error), 'error')
      return
    }
  }
  if (studio.renameProject(project.value.id, clean)) {
    void closeRename()
  }
}

function handleNameEscape(event: KeyboardEvent) {
  if (event.isComposing) return

  event.preventDefault()
  void closeRename()
}
</script>

<template>
  <div class="studio-project" :class="{ 'studio-project--fill-height': project && fillHeight, 'studio-project--script': project && active === 'studio-script', 'studio-project--episode': route.name === 'studio-episode' }">
    <template v-if="project && settings">
      <header v-if="route.name !== 'studio-episode'" class="studio-project-head">
        <form v-if="draftName !== undefined" class="studio-project-rename" @submit.prevent="saveName" @keydown.esc="handleNameEscape">
          <input ref="nameInput" v-model="draftName" class="ui-input" aria-label="项目名称" required />
          <UiButton class="studio-project-rename-action" type="submit" variant="outline" size="sm" aria-label="保存项目名称" title="保存项目名称" :disabled="!draftName.trim()">
            <template #leading><Check :size="15" aria-hidden="true" /></template>
          </UiButton>
          <UiButton class="studio-project-rename-action" variant="ghost" size="sm" aria-label="取消修改项目名称" title="取消修改项目名称" @click="closeRename">
            <template #leading><X :size="15" aria-hidden="true" /></template>
          </UiButton>
        </form>
        <h1 v-else class="studio-project-name">
          <button ref="renameTrigger" type="button" class="studio-project-name-button" :aria-label="`修改项目名称：${settings.name}`" :title="settings.name" @click="startRename">
            <Heading :size="16" aria-hidden="true" />
            <span>{{ settings.name }}</span>
            <Pencil class="studio-project-name-pencil" :size="13" aria-hidden="true" />
          </button>
        </h1>
        <nav class="studio-project-nav" aria-label="项目制作步骤">
          <ol class="studio-steps">
            <li v-for="(step, index) in steps" :key="step.name">
              <RouterLink
                class="studio-step"
                :class="{ 'is-locked': isStepLocked(step.name) }"
                :to="{ name: step.name, params: { projectId: project.id } }"
                aria-current-value="step"
                :aria-current="active === step.name ? 'step' : undefined"
                :aria-disabled="isStepLocked(step.name) ? 'true' : undefined"
                @click="handleStepClick($event, step.name)"
              >
                <span class="studio-step-number" aria-hidden="true"><Check v-if="index === 0 && project.scriptConfirmed && active !== step.name && !scriptJobRunning" :size="14" /><template v-else>{{ index + 1 }}</template></span>
                {{ step.label }}
              </RouterLink>
            </li>
          </ol>
        </nav>
        <dl class="studio-project-meta">
          <div>
            <dt>比例</dt>
            <dd>{{ settings.ratio }}</dd>
          </div>
          <div>
            <dt>语言</dt>
            <dd>{{ language }}</dd>
          </div>
          <div v-if="artStyle" class="studio-project-style">
            <dt>画风</dt>
            <dd :title="artStyle.label">
              <img :src="`/images/art-styles/${artStyle.value}.webp`" alt="" />
              <span>{{ artStyle.label }}</span>
            </dd>
          </div>
          <div v-if="world" class="studio-project-world" :title="world.baseline">
            <dt>时代</dt>
            <dd>{{ world.era }}</dd>
          </div>
          <div>
            <dt>集数</dt>
            <dd>{{ settings.episodeCount }} 集</dd>
          </div>
          <div v-if="settings.secondsPerEpisode">
            <dt>单集</dt>
            <dd>约 {{ formatDurationLabel(settings.secondsPerEpisode) }}</dd>
          </div>
        </dl>
      </header>
      <RouterView v-if="active === 'studio-script' || project.scriptConfirmed" :key="project.id" :project="project" />
    </template>
    <EmptyState v-else-if="loadingProject" title="正在加载项目..." description="正在从服务器读取剧本、资产与分镜数据。" />
    <EmptyState v-else title="找不到该项目" :description="loadError || '项目可能已被删除或你暂无访问权限。'" />
  </div>
</template>

<style scoped>
.studio-project { container-type: inline-size; width: 100%; padding: 24px 12px 44px; }
.studio-project--fill-height { display: flex; flex-direction: column; min-height: inherit; padding-bottom: 12px; }
.studio-project--script { height: calc(100dvh - 64px); overflow: hidden; }
.studio-project--script > .studio-project-head { flex-shrink: 0; }
.studio-project--episode { display: grid; height: calc(100dvh - 64px); min-height: 0; overflow: hidden; padding-block: 12px; }
.studio-project-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-areas: "name" "meta" "steps";
  align-items: center;
  gap: 10px 12px;
  padding: 8px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-panel);
  background: var(--color-surface);
}
.studio-project-name, .studio-project-rename { grid-area: name; min-width: 0; margin: 0; }
.studio-project-name { font-size: var(--font-size-body); line-height: 1.4; }
.studio-project-name-button { display: flex; align-items: center; gap: 8px; max-width: 100%; min-height: 34px; padding: 0; text-align: left; cursor: pointer; }
.studio-project-name-button svg { flex-shrink: 0; color: var(--color-gold-soft); }
.studio-project-name-button .studio-project-name-pencil { color: var(--color-muted); }
.studio-project-name-button:is(:hover, :focus-visible) .studio-project-name-pencil { color: var(--color-gold-soft); }
.studio-project-name span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.studio-project-rename { display: flex; align-items: center; gap: 4px; }
.studio-project-rename input { min-width: 0; height: 34px; padding-inline: 8px; }
.studio-project-rename-action { flex: 0 0 32px; padding-inline: 0; }
.studio-project-nav { grid-area: steps; width: min(100%, 416px); justify-self: center; }
.studio-project-meta { grid-area: meta; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; min-width: 0; max-width: 100%; overflow: hidden; margin: 0; font-size: 12px; }
.studio-project-meta > div { display: flex; align-items: center; gap: 4px; min-width: 0; }
.studio-project-meta dt { flex-shrink: 0; color: var(--color-muted); }
.studio-project-meta dd { min-width: 0; margin: 0; color: var(--color-text); overflow-wrap: anywhere; }
.studio-project-style dd { display: flex; align-items: center; gap: 4px; }
.studio-project-world dd { max-width: 148px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.studio-project-style img { flex-shrink: 0; width: 24px; height: 16px; border-radius: 3px; object-fit: cover; }
.studio-steps { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin: 0; padding: 0; list-style: none; }
.studio-step { display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 44px; height: 100%; padding: 6px 8px; border: 1px solid var(--border-control); border-radius: var(--radius-control); background: var(--color-surface); color: var(--color-text); font-size: 13px; font-weight: 600; line-height: 1.35; text-align: center; word-break: keep-all; }
.studio-step:hover { border-color: var(--color-gold); color: var(--color-gold-soft); }
.studio-step.is-locked { opacity: .48; cursor: not-allowed; }
.studio-step.is-locked:hover { border-color: var(--border-control); color: var(--color-text); }
.studio-step:focus-visible { outline: 2px solid var(--color-gold); outline-offset: 2px; }
.studio-step[aria-current="step"] { border-color: var(--color-gold); background: var(--gold-tint); color: var(--color-gold-soft); }
.studio-step-number { display: grid; flex: 0 0 22px; place-items: center; width: 22px; height: 22px; border: 1px solid var(--border-control); border-radius: 50%; color: var(--color-muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.studio-step[aria-current="step"] .studio-step-number { border-color: var(--color-gold); background: var(--color-gold); color: var(--color-ink); }
@container (min-width: 560px) {
  .studio-project-head { grid-template-columns: minmax(0, 1fr) minmax(0, 380px); grid-template-areas: "name meta" "steps steps"; }
  .studio-project-meta { justify-content: flex-end; }
}
@container (min-width: 1040px) {
  .studio-project-head { grid-template-columns: minmax(150px, 0.72fr) 336px minmax(0, 1.28fr); grid-template-areas: "name steps meta"; }
  .studio-project-meta { justify-content: flex-end; flex-wrap: wrap; }
  .studio-project-meta > div:not(.studio-project-style):not(.studio-project-world) { flex-shrink: 0; }
  .studio-project-style span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
}
@container (min-width: 1440px) {
  .studio-project-meta { flex-wrap: nowrap; white-space: nowrap; }
  .studio-project-world dd { max-width: 180px; }
}
@media (max-width: 760px) {
  .studio-project--script,
  .studio-project--episode { height: calc(100dvh - 58px); }
}
@media (max-width: 640px) {
  .studio-project--script,
  .studio-project--episode { height: auto; overflow: visible; }
}
@media (max-width: 420px) {
  .studio-steps { gap: 6px; }
  .studio-step { gap: 5px; padding-inline: 4px; }
  .studio-step-number { flex-basis: 18px; width: 18px; height: 18px; }
}
@container (max-width: 320px) {
  .studio-step { flex-direction: column; }
}
</style>
