<script setup lang="ts">
import { Bell, ChevronRight, Headphones, House, Menu, Tags } from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import UiIconButton from '@/components/ui/UiIconButton.vue'
import CreditBalance from './CreditBalance.vue'
import UserMenu from './UserMenu.vue'
import type { WorkspaceBreadcrumb, WorkspaceUser } from './workspace-navigation'

withDefaults(defineProps<{
  breadcrumbs?: readonly WorkspaceBreadcrumb[]
  balance?: number | null
  user?: WorkspaceUser | null
  isAdmin?: boolean
  preview?: boolean
}>(), { breadcrumbs: () => [] })
defineEmits<{
  menu: []
  prices: []
  support: []
  announcements: []
  recharge: []
  account: []
  admin: []
  login: []
  logout: []
  home: []
}>()
</script>

<template>
  <header class="workspace-header">
    <div class="workspace-header-leading">
      <UiIconButton class="workspace-mobile-menu-button" label="打开工作台导航" @click="$emit('menu')"><Menu :size="20" /></UiIconButton>
      <nav class="workspace-breadcrumb" aria-label="面包屑">
        <RouterLink to="/workspace" class="ui-icon-button" aria-label="工作台首页" title="工作台首页"><House :size="17" :stroke-width="1.7" aria-hidden="true" /></RouterLink>
        <template v-for="(item, index) in breadcrumbs" :key="`${index}-${item.label}`">
          <ChevronRight :size="13" class="workspace-breadcrumb-separator" aria-hidden="true" />
          <RouterLink v-if="item.to && index < breadcrumbs.length - 1" :to="item.to">{{ item.label }}</RouterLink>
          <span v-else :aria-current="index === breadcrumbs.length - 1 ? 'page' : undefined" :title="item.label">{{ item.label }}</span>
        </template>
      </nav>
    </div>
    <div class="workspace-header-actions">
      <UiButton variant="ghost" class="workspace-header-action" title="模型价格" aria-label="模型价格" @click="$emit('prices')">
        <template #leading><Tags :size="16" :stroke-width="1.7" aria-hidden="true" /></template>
        <span class="workspace-header-action-label">模型价格</span>
      </UiButton>
      <UiButton variant="ghost" class="workspace-header-action" title="客服" aria-label="客服" @click="$emit('support')">
        <template #leading><Headphones :size="16" :stroke-width="1.7" aria-hidden="true" /></template>
        <span class="workspace-header-action-label">客服</span>
      </UiButton>
      <UiIconButton class="workspace-announcements" label="公告" @click="$emit('announcements')"><Bell :size="17" :stroke-width="1.7" /></UiIconButton>
      <span class="workspace-header-divider" aria-hidden="true" />
      <CreditBalance :balance="balance" :preview="preview" @recharge="$emit('recharge')" />
      <span class="workspace-header-divider" aria-hidden="true" />
      <UserMenu :user="user" :is-admin="isAdmin" :preview="preview" @account="$emit('account')" @admin="$emit('admin')" @login="$emit('login')" @logout="$emit('logout')" @home="$emit('home')" />
    </div>
  </header>
</template>
