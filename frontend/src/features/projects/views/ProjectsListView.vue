<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  CalendarDays,
  Clapperboard,
  Film,
  Layers,
  Pencil,
  Plus,
  Save,
  Search,
  Trash2,
  X,
} from 'lucide-vue-next'
import EmptyState from '@/components/business/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiInput from '@/components/ui/UiInput.vue'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import {
  apiErrorMessage,
  archiveProjectApi,
  listProjects,
  renameProjectApi,
} from '@/features/studio/api'
import type { ProjectSummaryOut } from '@/features/studio/api-types'
import { artStyles } from '@/features/studio/components/art-styles'
import { useStudioStore } from '@/features/studio/studio-store'
import { formatDateTime } from '@/lib/format'
import { useUiStore } from '@/stores/ui'

const router = useRouter()
const studio = useStudioStore()
const ui = useUiStore()

const loading = ref(false)
const projects = ref<ProjectSummaryOut[]>([])
const keyword = ref('')

const renameOpen = ref(false)
const renaming = ref(false)
const projectToRename = ref<ProjectSummaryOut>()
const draftName = ref('')

const deleteOpen = ref(false)
const deleting = ref(false)
const projectToDelete = ref<ProjectSummaryOut>()

const styleLabelMap = new Map<string, string>(artStyles.map((s) => [s.value, s.label]))

const filteredProjects = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  if (!q) return projects.value
  return projects.value.filter((item) => item.name.toLowerCase().includes(q))
})

function styleCoverUrl(style?: string): string {
  const matched = artStyles.find((item) => item.value === style)
  return `/images/art-styles/${matched?.value ?? 'live-action'}.webp`
}

function styleLabel(style?: string): string {
  return (style && styleLabelMap.get(style)) || style || '真人'
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

function openRename(project: ProjectSummaryOut) {
  projectToRename.value = project
  draftName.value = project.name
  renameOpen.value = true
}

async function submitRename() {
  const target = projectToRename.value
  const name = draftName.value.trim()
  if (!target || !name || renaming.value) return
  renaming.value = true
  try {
    const res = await renameProjectApi(target.id, name)
    projects.value = projects.value.map((item) =>
      item.id === target.id ? { ...item, name: res.name } : item,
    )
    studio.syncProjectSummaries(projects.value)
    renameOpen.value = false
    projectToRename.value = undefined
    ui.notify('项目名称已更新', 'success')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    renaming.value = false
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

    <ul v-else class="projects-grid" aria-label="短剧项目列表">
      <li v-for="project in filteredProjects" :key="project.id" class="project-card-item">
        <RouterLink
          class="project-card"
          :to="{ name: project.scriptConfirmed ? 'studio-assets' : 'studio-script', params: { projectId: project.id } }"
        >
          <div class="project-card-cover">
            <img :src="styleCoverUrl(project.settings.visualStyle)" alt="" loading="lazy" />
            <span class="project-card-style">{{ styleLabel(project.settings.visualStyle) }}</span>
            <span class="project-card-status" :class="{ 'is-ready': project.scriptConfirmed }">
              {{ project.scriptConfirmed ? '剧本已确认' : '剧本草稿' }}
            </span>
          </div>
          <div class="project-card-body">
            <h3 :title="project.name">{{ project.name }}</h3>
            <div class="project-card-stats">
              <span><Film :size="13" aria-hidden="true" />{{ project.episodeCount }} 集</span>
              <span><Layers :size="13" aria-hidden="true" />{{ project.assetCount }} 资产</span>
              <span>{{ project.settings.ratio || '16:9' }}</span>
            </div>
            <div class="project-card-meta">
              <span><CalendarDays :size="13" aria-hidden="true" />{{ formatDateTime(project.updatedAt) }}</span>
            </div>
          </div>
        </RouterLink>

        <div class="project-card-actions">
          <button
            type="button"
            class="project-card-action"
            :aria-label="`重命名 ${project.name}`"
            title="重命名"
            @click.stop.prevent="openRename(project)"
          >
            <Pencil :size="13" aria-hidden="true" />
          </button>
          <button
            type="button"
            class="project-card-action project-card-action--danger"
            :aria-label="`删除 ${project.name}`"
            title="删除"
            @click.stop.prevent="confirmDelete(project)"
          >
            <Trash2 :size="13" aria-hidden="true" />
          </button>
        </div>
      </li>
    </ul>

    <UiDialog v-model:open="renameOpen" title="重命名项目">
      <form id="project-rename-form" class="project-form" @submit.prevent="submitRename">
        <UiInput v-model="draftName" label="项目名称" required autofocus />
      </form>
      <template #footer>
        <UiButton variant="ghost" :disabled="renaming" @click="renameOpen = false">取消</UiButton>
        <UiButton
          type="submit"
          form="project-rename-form"
          variant="primary"
          :disabled="!draftName.trim() || renaming"
          :loading="renaming"
        >
          <template #leading><Save :size="15" aria-hidden="true" /></template>
          保存
        </UiButton>
      </template>
    </UiDialog>

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
.projects-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr)); gap: 16px; margin: 20px 0 0; padding: 0; list-style: none; }
.project-card-item { position: relative; min-width: 0; }
.project-card { display: block; overflow: hidden; min-width: 0; border: 1px solid var(--border-subtle); border-radius: 8px; background: var(--color-surface); color: inherit; text-decoration: none; transition: border-color .15s; }
.project-card:hover { border-color: var(--focus-ring); }
.project-card-actions { position: absolute; top: 8px; right: 8px; z-index: 2; display: inline-flex; gap: 5px; opacity: 0; transition: opacity .15s; }
.project-card-item:hover .project-card-actions,
.project-card-item:focus-within .project-card-actions { opacity: 1; }
.project-card-action { display: grid; place-items: center; width: 28px; height: 28px; border: 1px solid rgb(255 255 255 / 14%); border-radius: 6px; background: rgb(9 10 13 / 80%); color: #e5e2dc; cursor: pointer; backdrop-filter: blur(6px); transition: color .15s, border-color .15s; }
.project-card-action:hover { color: var(--color-gold-soft); border-color: rgb(240 184 75 / 45%); }
.project-card-action--danger:hover { color: var(--color-error); border-color: rgb(239 146 146 / 45%); }
.project-card-cover { position: relative; overflow: hidden; aspect-ratio: 16 / 8; background: var(--color-elevated); }
.project-card-cover::after { position: absolute; inset: 0; background: linear-gradient(180deg, transparent 36%, rgb(5 6 8 / 65%)); content: ''; pointer-events: none; }
.project-card-cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.project-card-style { position: absolute; left: 10px; bottom: 8px; z-index: 1; padding: 2px 7px; border-radius: 5px; background: rgb(9 10 13 / 76%); color: #e5e2dc; font-size: 11px; }
.project-card-status { position: absolute; right: 10px; bottom: 8px; z-index: 1; padding: 2px 7px; border: 1px solid rgb(255 255 255 / 14%); border-radius: 5px; background: rgb(9 10 13 / 76%); color: var(--color-muted); font-size: 11px; }
.project-card-status.is-ready { border-color: rgb(240 184 75 / 32%); color: var(--color-gold-soft); }
.project-card-body { padding: 14px; }
.project-card-body h3 { margin: 0; overflow: hidden; color: var(--color-text); font-size: var(--font-size-body); font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.project-card-stats { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 8px 0 12px; color: var(--color-muted); font-size: 12px; }
.project-card-stats span { display: inline-flex; align-items: center; gap: 4px; }
.project-card-meta { display: flex; align-items: center; padding-top: 10px; border-top: 1px solid var(--border-subtle); color: var(--color-muted); font-size: 11px; }
.project-card-meta span { display: inline-flex; align-items: center; gap: 5px; }
.project-form { display: grid; gap: 12px; }
@media (max-width: 640px) {
  .projects-page { padding: 18px 16px 32px; }
  .projects-search { width: 100%; }
  .project-card-actions { opacity: 1; }
}
</style>
