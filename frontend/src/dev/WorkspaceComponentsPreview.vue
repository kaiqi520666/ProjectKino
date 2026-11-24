<script setup lang="ts">
import { ref } from 'vue'
import ProjectCard from '@/features/projects/components/ProjectCard.vue'
import type { ProjectSummary } from '@/features/projects/project-types'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiInput from '@/components/ui/UiInput.vue'

const initialProjects: ProjectSummary[] = [
  { id: 'sample-city', name: '旧城来信 · 示例', coverUrl: '/images/auth/login-desktop.jpg', updatedAt: '2026-11-17T08:30:00+08:00' },
  { id: 'sample-wuxia', name: '竹影寻踪 · 示例', coverUrl: '/images/home/cover-wuxia.jpg' },
  { id: 'sample-empty', name: '还没有封面的项目 · 示例' },
]
const projects = ref(initialProjects.map(project => ({ ...project })))
const renameId = ref<string | null>(null)
const name = ref('')
const renameOpen = ref(false)
const nameError = ref('')

function startRename(id: string) {
  const project = projects.value.find(item => item.id === id)
  if (!project) return
  renameId.value = id
  name.value = project.name
  nameError.value = ''
  renameOpen.value = true
}

function rename() {
  if (!name.value.trim()) {
    nameError.value = '请输入项目名称'
    return
  }
  const project = projects.value.find(item => item.id === renameId.value)
  if (project) project.name = name.value.trim()
  renameOpen.value = false
}

function reset() {
  projects.value = initialProjects.map(project => ({ ...project }))
  renameOpen.value = false
}
defineExpose({ reset })
</script>

<template>
  <section id="workspace-components" class="preview-section">
    <div class="preview-section-heading"><h2>工作台项目卡片</h2><code>ProjectCard / 本地示例，不连接项目服务</code></div>
    <ul class="workspace-preview-projects">
      <ProjectCard
        v-for="project in projects"
        :key="project.id"
        :id="project.id"
        :name="project.name"
        :cover-url="project.coverUrl || '/images/art-styles/live-action.webp'"
        fallback-cover-url="/images/art-styles/live-action.webp"
        style-label="真人"
        ratio="16:9"
        :episode-count="6"
        :asset-count="12"
        :updated-at="project.updatedAt"
        :progress="{ label: '剧本已确认', tone: 'ready', targetRoute: 'studio-assets', percent: 35 }"
        show-edit
        @edit="startRename(project.id)"
        @delete="projects = projects.filter(item => item.id !== project.id)"
      />
    </ul>
    <UiDialog v-model:open="renameOpen" title="重命名示例" description="仅修改本次开发预览中的项目名称。">
      <form id="rename-project-example" @submit.prevent="rename"><UiInput v-model="name" label="项目名称" :error="nameError" required /></form>
      <template #footer><UiButton variant="ghost" @click="renameOpen = false">取消</UiButton><UiButton variant="primary" form="rename-project-example" type="submit">保存</UiButton></template>
    </UiDialog>
  </section>
</template>

<style scoped>
.workspace-preview-projects { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; margin: 0; padding: 0; list-style: none; }
@media (max-width: 960px) { .workspace-preview-projects { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 560px) { .workspace-preview-projects { grid-template-columns: minmax(0, 1fr); } }
</style>
