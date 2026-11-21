<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, FolderOpen, Images, UserRound } from 'lucide-vue-next'
import EmptyState from '@/components/business/EmptyState.vue'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'

const route = useRoute()

const headerMeta = computed(() => {
  if (route.meta.workspaceNav === 'account') {
    return { eyebrow: '个人中心', icon: UserRound }
  }
  return { eyebrow: '创作工具', icon: Images }
})
</script>

<template>
  <section class="workspace-pending-view">
    <WorkspacePageHeader :eyebrow="headerMeta.eyebrow" :title="String(route.meta.title || '')">
      <template #icon><component :is="headerMeta.icon" :size="19" :stroke-width="1.7" /></template>
    </WorkspacePageHeader>
    <div class="workspace-pending-body">
      <EmptyState :title="`${route.meta.title}暂未开放`" description="该页面尚未实现。">
        <template #icon><FolderOpen :size="26" :stroke-width="1.4" /></template>
        <RouterLink to="/workspace" class="ui-button ui-button--secondary"><ArrowLeft :size="16" aria-hidden="true" />返回创作首页</RouterLink>
      </EmptyState>
    </div>
  </section>
</template>

<style scoped>
.workspace-pending-view { width: 100%; padding: 20px 24px 40px; }
.workspace-pending-body { margin-top: 24px; }
@media (max-width: 760px) { .workspace-pending-view { padding: 18px 16px 32px; } }
</style>
