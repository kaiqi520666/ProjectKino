<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { LogOut, ShieldCheck, UserRound, Wallet } from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import { useUserAssetsStore } from '@/features/assets/user-assets-store'
import { useCanvasStore } from '@/features/canvas/canvas-store'
import { useModelCatalog } from '@/features/studio/composables/useModelCatalog'
import { useStudioStore } from '@/features/studio/studio-store'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const studio = useStudioStore()
const canvas = useCanvasStore()
const userAssets = useUserAssetsStore()
const { clearCatalog } = useModelCatalog()

const accountTabs = [
  {
    key: 'credits',
    label: '积分与账单',
    to: { name: 'account-credits' },
    icon: Wallet,
  },
  {
    key: 'security',
    label: '账号与安全',
    to: { name: 'account-security' },
    icon: ShieldCheck,
  },
] as const

const activeTab = computed(() => String(route.meta.accountTab || 'credits'))

async function handleLogout() {
  await auth.logout()
  studio.clearProjects()
  canvas.clearAll()
  userAssets.clear()
  clearCatalog()
  await router.replace('/login')
}
</script>

<template>
  <section class="account-page" aria-labelledby="account-page-title">
    <WorkspacePageHeader title="我的" title-id="account-page-title">
      <template #icon><UserRound :size="19" :stroke-width="1.7" /></template>
      <template #actions>
        <UiButton variant="outline" size="sm" @click="handleLogout">
          <template #leading><LogOut :size="14" aria-hidden="true" /></template>
          退出登录
        </UiButton>
      </template>
    </WorkspacePageHeader>

    <nav class="account-tabs" aria-label="个人中心导航">
      <RouterLink
        v-for="tab in accountTabs"
        :key="tab.key"
        :to="tab.to"
        class="account-tab"
        :class="{ 'is-active': activeTab === tab.key }"
        :aria-current="activeTab === tab.key ? 'page' : undefined"
      >
        <component :is="tab.icon" :size="15" aria-hidden="true" />
        <span>{{ tab.label }}</span>
      </RouterLink>
    </nav>

    <div class="account-content">
      <RouterView />
    </div>
  </section>
</template>

<style scoped>
.account-page {
  width: 100%;
  padding: 20px 24px 40px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.account-tabs {
  display: flex;
  align-items: center;
  gap: 6px;
  border-bottom: 1px solid var(--border-subtle);
  margin-top: -4px;
}

.account-tab {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 9px 14px 11px;
  color: var(--color-muted);
  font-size: 13.5px;
  font-weight: 500;
  text-decoration: none;
  border-radius: 7px 7px 0 0;
  transition: color 0.16s ease, background-color 0.16s ease;
}

.account-tab:hover {
  color: var(--color-text);
  background: rgb(255 255 255 / 3%);
}

.account-tab.is-active {
  color: var(--color-gold-soft);
  font-weight: 600;
}

.account-tab.is-active::after {
  content: '';
  position: absolute;
  left: 10px;
  right: 10px;
  bottom: -1px;
  height: 2px;
  border-radius: 2px;
  background: var(--color-gold);
}

.account-content {
  width: 100%;
  min-width: 0;
}

@media (max-width: 640px) {
  .account-page {
    padding: 18px 16px 32px;
  }

  .account-tab {
    padding: 8px 12px 10px;
    font-size: 13px;
  }
}
</style>
