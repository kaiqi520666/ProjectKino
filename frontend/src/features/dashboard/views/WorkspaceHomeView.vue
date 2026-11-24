<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Clapperboard, LayoutDashboard, Trash2 } from 'lucide-vue-next'
import EmptyState from '@/components/business/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiPagination from '@/components/ui/UiPagination.vue'
import PromoCarousel from '../components/PromoCarousel.vue'
import ToolEntryCard from '../components/ToolEntryCard.vue'
import ProjectCard from '@/features/projects/components/ProjectCard.vue'
import {
  resolveProjectCoverUrl,
  resolveProjectProgress,
  styleCoverUrl,
} from '@/features/projects/project-progress'
import ScriptCreationPanel from '@/features/studio/components/ScriptCreationPanel.vue'
import { artStyles } from '@/features/studio/components/art-styles'
import type { DramaCreation } from '@/features/studio/components/drama-creation'
import {
  apiErrorMessage,
  archiveProjectApi,
  getProjectDetail,
  listProjects,
  startGenerateProject,
} from '@/features/studio/api'
import { useScriptJobStore } from '@/features/studio/script-job-store'
import type { StudioProject } from '@/features/studio/studio-project'
import { useStudioStore } from '@/features/studio/studio-store'
import { useUiStore } from '@/stores/ui'
import type { PromoSlide } from '../components/promo-types'

const router = useRouter()
const studio = useStudioStore()
const scriptJobs = useScriptJobStore()
const ui = useUiStore()
const creating = ref(false)
const deleteOpen = ref(false)
const deleting = ref(false)
const projectToDelete = ref<StudioProject>()

const projectPage = ref(1)
const projectPageSize = ref(8)

const styleLabelMap = new Map<string, string>(artStyles.map((s) => [s.value, s.label]))

const pagedProjects = computed(() => {
  const start = (projectPage.value - 1) * projectPageSize.value
  return studio.projects.slice(start, start + projectPageSize.value)
})

const slides: PromoSlide[] = [
  { id: 'story', title: '把灵感，写成下一幕', description: '属于你的故事，从这一刻开场。', imageUrl: '/images/workspace/banner-story.jpg', imageAlt: '编剧工作桌上的纸质剧本、钢笔和电影场记板', imagePosition: 'center' },
  { id: 'canvas', title: '让想象，自由延展', description: '每一帧画面，都有无限可能。', imageUrl: '/images/workspace/banner-canvas.jpg', imageAlt: '工作室墙面上用照片规划的影视分镜', imagePosition: 'center', actionLabel: '进入画布' },
  { id: 'assets', title: '珍藏每一份创作灵感', description: '人物、场景与故事的无限片段。', imageUrl: '/images/workspace/banner-assets.jpg', imageAlt: '桌面上整理的人物肖像、场景照片和服装参考素材', imagePosition: 'center', actionLabel: '查看素材' },
]

onMounted(async () => {
  try {
    const summaries = await listProjects()
    studio.syncProjectSummaries(summaries)
  } catch {
    // Keep existing list on transient load failure.
  }
})

function selectPromo(slide: PromoSlide) {
  if (slide.id === 'canvas') router.push('/canvas')
  else if (slide.id === 'assets') router.push('/assets')
}

function confirmProjectDeletion(project: StudioProject) {
  projectToDelete.value = project
  deleteOpen.value = true
}

async function deleteProject() {
  const target = projectToDelete.value
  if (!target || deleting.value) return
  deleting.value = true
  try {
    if (target.persisted) {
      await archiveProjectApi(target.id)
    }
    studio.removeProject(target.id)
    deleteOpen.value = false
    projectToDelete.value = undefined
    ui.notify(`已删除项目《${target.creation.settings.name}》`, 'success')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    deleting.value = false
  }
}

function projectStyleLabel(style?: string): string {
  return (style && styleLabelMap.get(style)) || style || '真人'
}

function recentProjectCoverUrl(project: StudioProject): string {
  return resolveProjectCoverUrl({
    coverUrl: project.coverUrl,
    autoCoverUrl: project.autoCoverUrl,
    visualStyle: project.creation.settings.visualStyle,
  }).url
}

function recentProjectProgress(project: StudioProject) {
  const stats = project.progressStats
  return resolveProjectProgress({
    scriptConfirmed: project.scriptConfirmed,
    episodeCount: stats?.episodeCount ?? Object.keys(project.episodes).length,
    plannedEpisodeCount: stats?.plannedEpisodeCount ?? project.creation.settings.episodeCount,
    assetCount: stats?.assetCount ?? (project.assets?.length ?? 0),
    assetImageReadyCount: stats?.assetImageReadyCount ?? (project.assets?.filter((a) => Boolean(a.imageUrl)).length ?? 0),
    storyboardEpisodeCount: stats?.storyboardEpisodeCount ?? Object.keys(project.storyboards ?? {}).length,
    clipCount: stats?.clipCount ?? 0,
    clipVideoReadyCount: stats?.clipVideoReadyCount ?? 0,
    composedEpisodeCount: stats?.composedEpisodeCount ?? 0,
  })
}

async function createDrama(input: DramaCreation) {
  if (creating.value) return
  creating.value = true
  try {
    const text = input.mode === 'story' ? input.story : await input.file.text()
    const style = artStyles.find(({ value }) => value === input.settings.visualStyle)
    const stylePrompt = style?.prompt
    const accepted = await startGenerateProject({
      settings: stylePrompt ? { ...input.settings, visualStyleLabel: stylePrompt } : input.settings,
      mode: input.mode,
      text,
    })
    const detail = await getProjectDetail(accepted.projectId)
    studio.hydrateProjectDetail(detail)
    scriptJobs.trackScriptJob(accepted.projectId, accepted.job)
    void listProjects().then((summaries) => studio.syncProjectSummaries(summaries)).catch(() => {})
    await router.push({ name: 'studio-script', params: { projectId: accepted.projectId } })
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="workspace-home">
    <PromoCarousel :slides="slides" @select="selectPromo" />
    <section class="dashboard-create" aria-labelledby="dashboard-create-title">
      <h1 id="dashboard-create-title">今天，拍点什么？</h1>
      <div class="dashboard-create-grid">
        <ScriptCreationPanel :busy="creating" @submit="createDrama" />
        <ToolEntryCard title="画布" description="自由连接每一帧" :icon="LayoutDashboard" image-url="/images/workspace/entry-canvas.jpg" image-alt="工作桌上排列的真人摄影分镜卡片" @select="router.push('/canvas')" />
      </div>
    </section>

    <section class="dashboard-projects" aria-labelledby="dashboard-projects-title">
      <div class="dashboard-section-heading">
        <div class="dashboard-section-title">
          <h2 id="dashboard-projects-title">最近项目</h2>
          <span v-if="studio.projects.length" class="dashboard-section-count">{{ studio.projects.length }}</span>
        </div>
        <RouterLink to="/projects">全部<ArrowRight :size="14" aria-hidden="true" /></RouterLink>
      </div>

      <template v-if="studio.projects.length">
        <ul class="dashboard-projects-grid" aria-label="最近项目列表">
          <ProjectCard
            v-for="project in pagedProjects"
            :key="project.id"
            :id="project.id"
            :name="project.creation.settings.name"
            :cover-url="recentProjectCoverUrl(project)"
            :fallback-cover-url="styleCoverUrl(project.creation.settings.visualStyle)"
            :style-label="projectStyleLabel(project.creation.settings.visualStyle)"
            :ratio="project.creation.settings.ratio || '16:9'"
            :episode-count="project.progressStats?.plannedEpisodeCount ?? project.creation.settings.episodeCount"
            :asset-count="project.progressStats?.assetCount ?? (project.assets?.length ?? 0)"
            :updated-at="project.updatedAt"
            :progress="recentProjectProgress(project)"
            @delete="confirmProjectDeletion(project)"
          />
        </ul>

        <UiPagination
          v-if="studio.projects.length > 8"
          v-model:page="projectPage"
          v-model:page-size="projectPageSize"
          :total="studio.projects.length"
          :page-size-options="[8, 12, 16]"
          item-label="个项目"
        />
      </template>

      <EmptyState v-else title="暂无项目" description="新建短剧后，项目会出现在这里">
        <template #icon><Clapperboard :size="26" :stroke-width="1.3" /></template>
      </EmptyState>
    </section>

    <UiDialog
      v-model:open="deleteOpen"
      title="删除项目"
      :description="`确定删除《${projectToDelete?.creation.settings.name ?? ''}》吗？`"
    >
      <p class="dashboard-delete-note">删除后该项目将从你的项目列表中移除，无法继续查看或编辑；已消耗的积分不予退还。</p>
      <template #footer>
        <UiButton variant="ghost" :disabled="deleting" @click="deleteOpen = false">取消</UiButton>
        <UiButton variant="danger" :loading="deleting" :disabled="deleting" @click="deleteProject">
          <template v-if="!deleting" #leading><Trash2 :size="14" aria-hidden="true" /></template>
          确认删除
        </UiButton>
      </template>
    </UiDialog>
  </div>
</template>

<style scoped>
.workspace-home { width: 100%; padding: 20px 24px 40px; }
.dashboard-create { margin-top: 27px; }
.dashboard-create h1 { margin: 0 0 22px; font-size: 26px; font-weight: 600; line-height: 1.5; }
.dashboard-create-grid { display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(0, 1fr); gap: 18px; }
.dashboard-projects { margin-top: 42px; }
.dashboard-section-heading { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--border-subtle); }
.dashboard-section-title { display: inline-flex; align-items: center; gap: 9px; }
.dashboard-section-heading h2 { margin: 0; font-size: 18px; font-weight: 500; }
.dashboard-section-count { display: inline-flex; align-items: center; height: 20px; padding: 0 7px; border-radius: 999px; border: 1px solid var(--border-subtle); background: rgb(255 255 255 / 4%); color: var(--color-muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.dashboard-section-heading a { display: inline-flex; align-items: center; gap: 7px; color: #8e8e99; font-size: 12px; }
.dashboard-section-heading a:hover { color: var(--color-gold-soft); }
.dashboard-projects-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 18px; margin: 20px 0 0; padding: 0; list-style: none; }
.dashboard-delete-note { margin: 0; color: var(--color-muted); font-size: 13px; line-height: 1.6; }
.dashboard-projects :deep(.empty-state) { min-height: 220px; }
.dashboard-projects :deep(.empty-state-icon) { border: 0; background: transparent; }
@media (max-width: 1360px) { .dashboard-projects-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 1200px) { .workspace-home { padding: 26px 28px 40px; } .dashboard-create-grid { gap: 14px; } }
@media (max-width: 960px) { .dashboard-projects-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; } }
@media (max-width: 760px) { .workspace-home { padding: 22px 20px 36px; } .dashboard-create { margin-top: 20px; } .dashboard-create h1 { font-size: 24px; margin-bottom: 18px; } .dashboard-projects { margin-top: 30px; } }
@media (max-width: 600px) { .dashboard-projects-grid { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 560px) { .dashboard-create-grid { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 360px) { .workspace-home { padding-inline: 14px; } .dashboard-create-grid { gap: 10px; } }
</style>
