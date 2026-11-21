<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import {
  Activity,
  FolderArchive,
  LayoutDashboard,
  Server,
  Settings2,
  ShieldCheck,
  Users,
} from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { workspaceAccountNavigation, workspaceNavigation } from './workspace-navigation'

const props = withDefaults(defineProps<{
  adminReviewCount?: number
  adminArchivedCount?: number
}>(), {
  adminReviewCount: 0,
  adminArchivedCount: 0,
})

const emit = defineEmits<{ navigate: [] }>()
const route = useRoute()
const auth = useAuthStore()

const adminMenuOpen = ref(false)
let closeTimer: ReturnType<typeof setTimeout> | null = null

const isAdminActive = computed(() => route.meta.workspaceNav === 'admin')
const activeAdminNav = computed(() => String(route.meta.adminNav || ''))

const adminMenuItems = computed(() => [
  { key: 'overview', to: '/admin', label: '概览', icon: LayoutDashboard, badge: 0, danger: false },
  { key: 'users', to: '/admin/users', label: '用户与积分', icon: Users, badge: 0, danger: false },
  { key: 'jobs', to: '/admin/jobs', label: '任务与核对', icon: Activity, badge: props.adminReviewCount, danger: true },
  { key: 'models', to: '/admin/models', label: '供应商与定价', icon: Server, badge: 0, danger: false },
  { key: 'settings', to: '/admin/settings', label: '系统与 OSS', icon: Settings2, badge: 0, danger: false },
  { key: 'projects', to: '/admin/projects', label: '项目与清理', icon: FolderArchive, badge: props.adminArchivedCount, danger: false },
])

function clearCloseTimer() {
  if (closeTimer) {
    clearTimeout(closeTimer)
    closeTimer = null
  }
}

function openAdminMenu() {
  clearCloseTimer()
  adminMenuOpen.value = true
}

function scheduleCloseAdminMenu() {
  clearCloseTimer()
  closeTimer = setTimeout(() => {
    adminMenuOpen.value = false
  }, 130)
}

function handleAdminItemClick() {
  clearCloseTimer()
  adminMenuOpen.value = false
  emit('navigate')
}

onUnmounted(clearCloseTimer)
</script>

<template>
  <aside class="workspace-sidebar" aria-label="工作台侧栏">
    <RouterLink to="/workspace" class="workspace-brand" aria-label="帧剧，返回创作首页" @click="$emit('navigate')">
      <img src="/brand/framedrama-logo.svg" width="42" height="42" alt="" />
      <span>帧剧</span>
    </RouterLink>
    <nav class="workspace-nav" aria-label="工作台导航">
      <RouterLink
        v-for="item in workspaceNavigation"
        :key="item.key"
        :to="item.to"
        class="workspace-nav-item"
        :class="{ 'is-active': route.meta.workspaceNav === item.key }"
        :aria-current="route.meta.workspaceNav === item.key ? 'page' : undefined"
        @click="$emit('navigate')"
      >
        <component :is="item.icon" :size="23" :stroke-width="1.6" aria-hidden="true" />
        <span>{{ item.label }}</span>
      </RouterLink>

      <div
        v-if="auth.isAdmin"
        class="workspace-admin-flyout-wrap"
        @mouseenter="openAdminMenu"
        @mouseleave="scheduleCloseAdminMenu"
        @focusin="openAdminMenu"
        @focusout="scheduleCloseAdminMenu"
      >
        <RouterLink
          to="/admin"
          class="workspace-nav-item workspace-admin-link"
          :class="{ 'is-active': isAdminActive, 'is-open': adminMenuOpen }"
          :aria-current="isAdminActive ? 'page' : undefined"
          @click="handleAdminItemClick"
        >
          <ShieldCheck :size="22" :stroke-width="1.6" aria-hidden="true" />
          <span>后台</span>
          <span v-if="adminReviewCount > 0" class="workspace-admin-badge">
            {{ adminReviewCount > 99 ? '99+' : adminReviewCount }}
          </span>
        </RouterLink>

        <div
          class="workspace-admin-flyout"
          :class="{ 'is-open': adminMenuOpen }"
          role="menu"
          aria-label="管理后台菜单"
        >
          <RouterLink
            v-for="item in adminMenuItems"
            :key="item.key"
            :to="item.to"
            class="workspace-admin-flyout-item"
            :class="{ 'is-active': activeAdminNav === item.key }"
            role="menuitem"
            @click="handleAdminItemClick"
          >
            <component :is="item.icon" :size="16" :stroke-width="1.7" aria-hidden="true" />
            <span>{{ item.label }}</span>
            <span
              v-if="item.badge > 0"
              class="workspace-admin-flyout-badge"
              :class="item.danger ? 'is-danger' : ''"
            >
              {{ item.badge }}
            </span>
          </RouterLink>
        </div>
      </div>
    </nav>

    <RouterLink
      :to="workspaceAccountNavigation.to"
      class="workspace-nav-item workspace-account-link"
      :class="{ 'is-active': route.meta.workspaceNav === workspaceAccountNavigation.key }"
      @click="$emit('navigate')"
    >
      <component :is="workspaceAccountNavigation.icon" :size="23" :stroke-width="1.6" aria-hidden="true" />
      <span>{{ workspaceAccountNavigation.label }}</span>
    </RouterLink>
  </aside>
</template>
