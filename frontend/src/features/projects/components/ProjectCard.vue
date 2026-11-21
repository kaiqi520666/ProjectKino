<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowUpRight, MoreHorizontal, Trash2 } from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiDropdown from '@/components/ui/UiDropdown.vue'
import UiImage from '@/components/ui/UiImage.vue'
import type { ProjectSummary } from '../project-types'

const props = defineProps<{ project: ProjectSummary; disabled?: boolean }>()
const emit = defineEmits<{ open: [id: string]; rename: [id: string]; remove: [id: string] }>()
const confirmOpen = ref(false)
const updatedLabel = computed(() => {
  if (!props.project.updatedAt) return ''
  const date = new Date(props.project.updatedAt)
  return Number.isFinite(date.getTime())
    ? date.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
    : ''
})
const items = [
  { value: 'open', label: '打开项目' },
  { value: 'rename', label: '重命名' },
  { value: 'remove', label: '删除项目', danger: true, separator: true },
]

function select(value: string) {
  if (props.disabled) return
  if (value === 'remove') confirmOpen.value = true
  else if (value === 'open') emit('open', props.project.id)
  else if (value === 'rename') emit('rename', props.project.id)
}

function remove() {
  if (props.disabled) return
  confirmOpen.value = false
  emit('remove', props.project.id)
}
</script>

<template>
  <article class="project-card" :class="{ 'is-disabled': disabled }">
    <button type="button" class="project-card-cover" :aria-label="`打开项目：${project.name}`" :disabled="disabled" @click="$emit('open', project.id)">
      <UiImage :src="project.coverUrl" :alt="project.name" :aspect-ratio="1.6" :retryable="false" />
      <span class="project-card-open" aria-hidden="true"><ArrowUpRight :size="20" /></span>
    </button>
    <div class="project-card-body">
      <div class="project-card-meta">
        <button type="button" class="project-card-title" :title="project.name" :disabled="disabled" @click="$emit('open', project.id)">{{ project.name }}</button>
        <time v-if="updatedLabel" :datetime="project.updatedAt">{{ updatedLabel }}</time>
      </div>
      <UiDropdown :items="items" @select="select">
        <button type="button" class="ui-icon-button project-card-menu" :aria-label="`${project.name}，更多操作`" title="更多操作" :disabled="disabled"><MoreHorizontal :size="18" aria-hidden="true" /></button>
      </UiDropdown>
    </div>
    <UiDialog v-model:open="confirmOpen" title="删除项目" :description="`确定删除「${project.name}」吗？`">
      <p class="project-delete-description">请确认已备份需要保留的内容。</p>
      <template #footer><UiButton variant="ghost" @click="confirmOpen = false">取消</UiButton><UiButton variant="danger" :disabled="disabled" @click="remove"><template #leading><Trash2 :size="15" aria-hidden="true" /></template>确认删除</UiButton></template>
    </UiDialog>
  </article>
</template>

<style scoped>
.project-card { min-width: 0; overflow: hidden; border: 1px solid var(--border-subtle); border-radius: 8px; background: #141418; transition: border-color .15s; }
.project-card:hover, .project-card:focus-within { border-color: rgb(240 184 75 / 26%); }
.project-card-cover { position: relative; display: block; width: 100%; padding: 0; border: 0; background: transparent; }
.project-card-cover :deep(.ui-image) { border: 0; border-radius: 0; }
.project-card-open { position: absolute; right: 12px; bottom: 12px; display: flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: 1px solid rgb(255 255 255 / 20%); border-radius: 6px; background: rgb(0 0 0 / 55%); color: white; opacity: 0; transition: opacity .15s; }
.project-card:hover .project-card-open, .project-card:focus-within .project-card-open { opacity: 1; }
.project-card-body { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 76px; padding: 14px 14px 14px 16px; }
.project-card-meta { min-width: 0; }
.project-card-title { display: block; max-width: 100%; overflow: hidden; padding: 0; border: 0; background: transparent; color: #dddddf; font-size: 14px; text-overflow: ellipsis; white-space: nowrap; text-align: left; }
.project-card-title:hover { color: var(--color-gold-soft); }
.project-card-meta time { display: block; margin-top: 4px; color: #83838e; font-size: 12px; }
.project-card-menu { opacity: .6; }
.project-card:hover .project-card-menu, .project-card:focus-within .project-card-menu { opacity: 1; }
.project-card.is-disabled { opacity: .5; }
.project-delete-description { margin: 0; color: var(--color-muted); font-size: 14px; overflow-wrap: anywhere; }
@media (hover: none) { .project-card-menu { opacity: 1; } }
</style>
