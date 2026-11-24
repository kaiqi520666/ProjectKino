<script setup lang="ts">
import { computed } from 'vue'
import { ChevronDown, UserRound } from 'lucide-vue-next'
import UiDropdown from '@/components/ui/UiDropdown.vue'
import type { WorkspaceUser } from './workspace-navigation'

const props = defineProps<{ user?: WorkspaceUser | null; preview?: boolean; isAdmin?: boolean }>()
const emit = defineEmits<{ account: []; admin: []; login: []; logout: []; home: [] }>()
const items = computed(() => [
  ...(props.user ? [{ value: 'account', label: '我的账户' }] : []),
  ...(props.user && props.isAdmin ? [{ value: 'admin', label: '管理后台' }] : []),
  { value: 'home', label: '返回官网' },
  props.user
    ? { value: 'logout', label: props.preview ? '结束预览，前往登录' : '退出登录', separator: true }
    : { value: 'login', label: '登录账号', separator: true },
])

function select(value: string) {
  if (value === 'account') emit('account')
  else if (value === 'admin') emit('admin')
  else if (value === 'home') emit('home')
  else if (value === 'login') emit('login')
  else if (value === 'logout') emit('logout')
}
</script>

<template>
  <UiDropdown :items="items" @select="select">
    <button type="button" class="workspace-user-trigger" :aria-label="`${user?.name || '未登录'}，账户菜单`">
      <span class="workspace-avatar">
        <img v-if="user?.avatarUrl" :src="user.avatarUrl" alt="" width="28" height="28" />
        <UserRound v-else :size="17" :stroke-width="1.7" aria-hidden="true" />
      </span>
      <span class="workspace-user-name">{{ user?.name || '未登录' }}</span>
      <ChevronDown :size="13" aria-hidden="true" />
    </button>
  </UiDropdown>
</template>

<style scoped>
.workspace-user-trigger { display: inline-flex; align-items: center; gap: 8px; min-width: 0; height: var(--control-height-sm); padding: 0 8px 0 4px; border: 0; border-radius: var(--radius-control-sm); background: transparent; color: #d2d2d6; font-size: 13px; }
.workspace-user-trigger:hover, .workspace-user-trigger[data-state="open"] { background: var(--surface-hover); }
.workspace-avatar { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; overflow: hidden; border: 1px solid var(--border-control); border-radius: 50%; background: #232328; color: #bcbcc4; }
.workspace-avatar img { width: 100%; height: 100%; object-fit: cover; }
.workspace-user-name { max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 960px) { .workspace-user-name { display: none; } }
@media (max-width: 480px) { .workspace-user-trigger { gap: 0; padding-inline: 2px; } .workspace-user-trigger > svg { display: none; } }
</style>
