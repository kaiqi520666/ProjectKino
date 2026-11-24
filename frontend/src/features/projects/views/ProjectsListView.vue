<script setup lang="ts">
import { computed, onMounted, ref, useTemplateRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  Clapperboard,
  FolderOpen,
  Plus,
  RotateCcw,
  Save,
  Search,
  Upload,
  X,
} from 'lucide-vue-next'
import EmptyState from '@/components/business/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiPagination from '@/components/ui/UiPagination.vue'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import AssetLibraryDialog from '@/features/assets/AssetLibraryDialog.vue'
import type { AssetLibraryItem } from '@/features/assets/asset-library-types'
import {
  apiErrorMessage,
  archiveProjectApi,
  listProjects,
  updateProjectApi,
  uploadFileToOss,
} from '@/features/studio/api'
import type { ProjectSummaryOut } from '@/features/studio/api-types'
import { artStyles } from '@/features/studio/components/art-styles'
import { useStudioStore } from '@/features/studio/studio-store'
import { useUiStore } from '@/stores/ui'
import ProjectCard from '../components/ProjectCard.vue'
import {
  resolveProjectCoverUrl,
  resolveProjectProgress,
  styleCoverUrl,
} from '../project-progress'

const router = useRouter()
const studio = useStudioStore()
const ui = useUiStore()

const loading = ref(false)
const projects = ref<ProjectSummaryOut[]>([])
const keyword = ref('')
const page = ref(1)
const pageSize = ref(12)

const editOpen = ref(false)
const editing = ref(false)
const uploadingCover = ref(false)
const coverLibraryOpen = ref(false)
const projectToEdit = ref<ProjectSummaryOut>()
const draftName = ref('')
const draftCoverUrl = ref<string | null>(null)
const draftCoverKey = ref<string | null>(null)
const coverFileInput = useTemplateRef<HTMLInputElement>('coverFileInput')

const deleteOpen = ref(false)
const deleting = ref(false)
const projectToDelete = ref<ProjectSummaryOut>()

const styleLabelMap = new Map<string, string>(artStyles.map((s) => [s.value, s.label]))

const filteredProjects = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  if (!q) return projects.value
  return projects.value.filter((item) => item.name.toLowerCase().includes(q))
})

const pagedProjects = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredProjects.value.slice(start, start + pageSize.value)
})

watch(keyword, () => {
  page.value = 1
})

const editPreviewCoverUrl = computed(() => {
  const target = projectToEdit.value
  if (!target) return ''
  return resolveProjectCoverUrl({
    coverUrl: draftCoverUrl.value,
    autoCoverUrl: target.autoCoverUrl,
    visualStyle: target.settings.visualStyle,
  }).url
})

function styleLabel(style?: string): string {
  return (style && styleLabelMap.get(style)) || style || '真人'
}

function projectCoverUrl(project: ProjectSummaryOut): string {
  return resolveProjectCoverUrl({
    coverUrl: project.coverUrl,
    autoCoverUrl: project.autoCoverUrl,
    visualStyle: project.settings.visualStyle,
  }).url
}

function projectProgress(project: ProjectSummaryOut) {
  return resolveProjectProgress({
    scriptConfirmed: project.scriptConfirmed,
    episodeCount: project.episodeCount,
    plannedEpisodeCount: project.plannedEpisodeCount ?? project.settings.episodeCount,
    assetCount: project.assetCount,
    assetImageReadyCount: project.assetImageReadyCount,
    storyboardEpisodeCount: project.storyboardEpisodeCount,
    clipCount: project.clipCount,
    clipVideoReadyCount: project.clipVideoReadyCount,
    composedEpisodeCount: project.composedEpisodeCount,
  })
}

async function fetchProjects() {
  loading.value = true
  try {
    const list = await listProjects()
    projects.value = list
    studio.syncProjectSummaries(list)
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void fetchProjects()
})

function openEdit(project: ProjectSummaryOut) {
  projectToEdit.value = project
  draftName.value = project.name
  draftCoverUrl.value = project.coverUrl ?? null
  draftCoverKey.value = project.coverKey ?? null
  editOpen.value = true
}

function handleSelectCover(item: AssetLibraryItem) {
  if (!item.mediaUrl) return
  draftCoverUrl.value = item.mediaUrl
  draftCoverKey.value = item.mediaKey ?? null
}

async function handleUploadCover(event: Event) {
  const input = event.currentTarget as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!file.type.startsWith('image/')) {
    ui.notify('请选择图片文件', 'error')
    return
  }
  uploadingCover.value = true
  try {
    const uploaded = await uploadFileToOss(file, 'image')
    draftCoverUrl.value = uploaded.url
    draftCoverKey.value = uploaded.key
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    uploadingCover.value = false
  }
}

function clearCover() {
  draftCoverUrl.value = null
  draftCoverKey.value = null
}

async function submitEdit() {
  const target = projectToEdit.value
  const name = draftName.value.trim()
  if (!target || !name || editing.value || uploadingCover.value) return
  editing.value = true
  try {
    const res = await updateProjectApi(target.id, {
      name,
      coverUrl: draftCoverUrl.value,
      coverKey: draftCoverKey.value,
    })
    projects.value = projects.value.map((item) =>
      item.id === target.id
        ? {
            ...item,
            name: res.name,
            settings: res.settings,
            coverUrl: res.coverUrl ?? null,
            coverKey: res.coverKey ?? null,
            updatedAt: res.updatedAt,
          }
        : item,
    )
    studio.applyProjectMeta(target.id, res)
    studio.syncProjectSummaries(projects.value)
    editOpen.value = false
    projectToEdit.value = undefined
    ui.notify('项目信息已更新', 'success')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    editing.value = false
  }
}

function confirmDelete(project: ProjectSummaryOut) {
  projectToDelete.value = project
  deleteOpen.value = true
}

async function submitDelete() {
  const target = projectToDelete.value
  if (!target || deleting.value) return
  deleting.value = true
  try {
    await archiveProjectApi(target.id)
    projects.value = projects.value.filter((item) => item.id !== target.id)
    studio.removeProject(target.id)
    deleteOpen.value = false
    projectToDelete.value = undefined
    ui.notify(`已删除项目《${target.name}》`, 'success')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <section class="projects-page" aria-labelledby="projects-page-title">
    <WorkspacePageHeader title="全部项目" title-id="projects-page-title" :badge="projects.length">
      <template #icon><Clapperboard :size="19" :stroke-width="1.7" /></template>
      <template #actions>
        <label class="projects-search">
          <Search :size="14" aria-hidden="true" />
          <input v-model="keyword" type="text" placeholder="搜索项目" aria-label="搜索项目" />
          <button
            v-if="keyword"
            type="button"
            class="projects-search-clear"
            aria-label="清空搜索"
            @click="keyword = ''"
          >
            <X :size="12" />
          </button>
        </label>
        <UiButton variant="primary" size="sm" @click="router.push('/workspace')">
          <template #leading><Plus :size="15" aria-hidden="true" /></template>
          新建短剧
        </UiButton>
      </template>
    </WorkspacePageHeader>

    <p v-if="loading && !projects.length" class="projects-status">正在加载项目…</p>

    <EmptyState
      v-else-if="!projects.length"
      title="暂无项目"
      description="前往创作首页生成你的第一部短剧"
    >
      <template #icon><Clapperboard :size="26" :stroke-width="1.4" /></template>
      <UiButton variant="primary" size="sm" @click="router.push('/workspace')">
        <template #leading><Plus :size="15" aria-hidden="true" /></template>
        新建短剧
      </UiButton>
    </EmptyState>

    <p v-else-if="!filteredProjects.length" class="projects-status">未找到匹配项目</p>

    <template v-else>
      <ul class="projects-grid" aria-label="短剧项目列表">
        <ProjectCard
          v-for="project in pagedProjects"
          :key="project.id"
          :id="project.id"
          :name="project.name"
          :cover-url="projectCoverUrl(project)"
          :fallback-cover-url="styleCoverUrl(project.settings.visualStyle)"
          :style-label="styleLabel(project.settings.visualStyle)"
          :ratio="project.settings.ratio || '16:9'"
          :episode-count="project.plannedEpisodeCount ?? project.settings.episodeCount ?? project.episodeCount"
          :asset-count="project.assetCount"
          :updated-at="project.updatedAt"
          :progress="projectProgress(project)"
          show-edit
          @edit="openEdit(project)"
          @delete="confirmDelete(project)"
        />
      </ul>

      <UiPagination
        v-model:page="page"
        v-model:page-size="pageSize"
        :total="filteredProjects.length"
        :page-size-options="[12, 24, 48]"
        item-label="个项目"
      />
    </template>

    <UiDialog v-model:open="editOpen" title="编辑项目" description="修改项目名称或自定义项目封面">
      <form id="project-edit-form" class="project-form" @submit.prevent="submitEdit">
        <UiInput v-model="draftName" label="项目名称" required autofocus />
        <div class="project-cover-field">
          <div class="project-cover-label-row">
            <span class="ui-label">项目封面</span>
            <span class="project-cover-hint">
              {{ draftCoverUrl ? '自定义封面' : projectToEdit?.autoCoverUrl ? '自动使用项目资产图' : '默认画风封面' }}
            </span>
          </div>
          <div class="project-cover-preview">
            <img v-if="editPreviewCoverUrl" :src="editPreviewCoverUrl" alt="" />
          </div>
          <input
            ref="coverFileInput"
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            hidden
            @change="handleUploadCover"
          />
          <div class="project-cover-actions">
            <UiButton
              variant="outline"
              size="sm"
              :loading="uploadingCover"
              :disabled="uploadingCover || editing"
              @click="coverFileInput?.click()"
            >
              <template v-if="!uploadingCover" #leading><Upload :size="13" aria-hidden="true" /></template>
              上传封面
            </UiButton>
            <UiButton
              variant="outline"
              size="sm"
              :disabled="uploadingCover || editing"
              @click="coverLibraryOpen = true"
            >
              <template #leading><FolderOpen :size="13" aria-hidden="true" /></template>
              从素材库选择
            </UiButton>
            <UiButton
              v-if="draftCoverUrl"
              variant="ghost"
              size="sm"
              :disabled="uploadingCover || editing"
              @click="clearCover"
            >
              <template #leading><RotateCcw :size="13" aria-hidden="true" /></template>
              恢复自动封面
            </UiButton>
          </div>
        </div>
      </form>
      <template #footer>
        <UiButton variant="ghost" :disabled="editing" @click="editOpen = false">取消</UiButton>
        <UiButton
          type="submit"
          form="project-edit-form"
          variant="primary"
          :disabled="!draftName.trim() || editing || uploadingCover"
          :loading="editing"
        >
          <template #leading><Save :size="15" aria-hidden="true" /></template>
          保存
        </UiButton>
      </template>
    </UiDialog>

    <AssetLibraryDialog
      v-model:open="coverLibraryOpen"
      title="选择封面图片"
      mode="single"
      :allowed-kinds="['image']"
      require-http-url
      @select="handleSelectCover"
    />

    <UiDialog
      v-model:open="deleteOpen"
      title="删除项目"
      :description="projectToDelete ? `确定删除《${projectToDelete.name}》吗？` : ''"
    >
      <template #footer>
        <UiButton variant="ghost" :disabled="deleting" @click="deleteOpen = false">取消</UiButton>
        <UiButton variant="danger" :disabled="deleting" :loading="deleting" @click="submitDelete">
          确认删除
        </UiButton>
      </template>
    </UiDialog>
  </section>
</template>

<style scoped>
.projects-page { width: 100%; padding: 20px 24px 40px; }
.projects-search {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  width: 200px;
  height: 32px;
  padding: 0 10px;
  border-radius: 7px;
  border: 1px solid var(--border-control);
  background: rgb(255 255 255 / 3%);
  color: var(--color-muted);
}
.projects-search:focus-within { border-color: rgb(240 184 75 / 50%); color: var(--color-text); }
.projects-search input { width: 100%; min-width: 0; border: 0; background: transparent; color: var(--color-text); font-size: 12px; outline: none; }
.projects-search input::placeholder { color: var(--color-muted); }
.projects-search-clear { display: grid; place-items: center; width: 18px; height: 18px; border: 0; background: transparent; color: var(--color-muted); cursor: pointer; }
.projects-search-clear:hover { color: var(--color-text); }
.projects-status { padding: 48px 0; text-align: center; color: var(--color-muted); font-size: var(--font-size-body); }
.projects-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 18px; margin: 20px 0 0; padding: 0; list-style: none; }
.project-form { display: grid; gap: 14px; }
.project-cover-field { display: grid; gap: 8px; }
.project-cover-label-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.project-cover-hint { color: var(--color-muted); font-size: 12px; }
.project-cover-preview { overflow: hidden; aspect-ratio: 16 / 9; border: 1px solid var(--border-subtle); border-radius: 8px; background: var(--color-elevated); }
.project-cover-preview img { width: 100%; height: 100%; object-fit: cover; display: block; }
.project-cover-actions { display: flex; flex-wrap: wrap; gap: 8px; }
@media (max-width: 1360px) { .projects-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 960px) { .projects-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; } }
@media (max-width: 640px) {
  .projects-page { padding: 18px 16px 32px; }
  .projects-search { width: 100%; }
  .projects-grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
