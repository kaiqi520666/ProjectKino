<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { KeyRound, LogOut, Save, UserRound } from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import { useUserAssetsStore } from '@/features/assets/user-assets-store'
import { useCanvasStore } from '@/features/canvas/canvas-store'
import { useModelCatalog } from '@/features/studio/composables/useModelCatalog'
import { useStudioStore } from '@/features/studio/studio-store'
import { extractErrorMessage } from '@/lib/format'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import AccountCreditsPanel from '../components/AccountCreditsPanel.vue'

const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const studio = useStudioStore()
const canvas = useCanvasStore()
const userAssets = useUserAssetsStore()
const { clearCatalog } = useModelCatalog()

const nickname = ref(auth.user?.nickname ?? '')
const savingProfile = ref(false)

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const savingPassword = ref(false)

const roleLabel = computed(() => {
  if (auth.user?.role === 'admin') return '管理员'
  if (auth.user?.role === 'operator') return '运营'
  return '创作者'
})

const canSaveProfile = computed(() => {
  const clean = nickname.value.trim()
  return Boolean(clean) && clean !== (auth.user?.nickname ?? '') && !savingProfile.value
})

const passwordMismatch = computed(
  () => Boolean(confirmPassword.value) && confirmPassword.value !== newPassword.value,
)

const canSavePassword = computed(
  () =>
    Boolean(currentPassword.value)
    && newPassword.value.length >= 6
    && confirmPassword.value === newPassword.value
    && !savingPassword.value,
)

watch(
  () => auth.user?.nickname,
  (val) => {
    if (val !== undefined) nickname.value = val
  },
)

async function saveProfile() {
  if (!canSaveProfile.value) return
  savingProfile.value = true
  try {
    await auth.updateProfile(nickname.value)
    ui.notify('昵称已更新', 'success')
  } catch (error) {
    ui.notify(extractErrorMessage(error, '更新昵称失败'), 'error')
  } finally {
    savingProfile.value = false
  }
}

async function savePassword() {
  if (!canSavePassword.value) return
  savingPassword.value = true
  try {
    await auth.changePassword(currentPassword.value, newPassword.value)
    currentPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    ui.notify('密码已更新，其他设备会话已失效', 'success')
  } catch (error) {
    ui.notify(extractErrorMessage(error, '修改密码失败'), 'error')
  } finally {
    savingPassword.value = false
  }
}

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

    <AccountCreditsPanel />

    <div class="account-grid">
      <article class="account-card">
        <header class="account-card-head">
          <h2><UserRound :size="15" aria-hidden="true" />基本资料</h2>
          <span class="account-role">{{ roleLabel }}</span>
        </header>
        <form class="account-form" @submit.prevent="saveProfile">
          <div class="account-readonly-row">
            <span class="ui-label">登录邮箱</span>
            <p class="account-email">{{ auth.user?.email || '-' }}</p>
          </div>
          <UiInput v-model="nickname" label="昵称" placeholder="输入昵称" required />
          <div class="account-form-actions">
            <UiButton type="submit" variant="primary" size="sm" :disabled="!canSaveProfile" :loading="savingProfile">
              <template #leading><Save :size="14" aria-hidden="true" /></template>
              保存
            </UiButton>
          </div>
        </form>
      </article>

      <article class="account-card">
        <header class="account-card-head">
          <h2><KeyRound :size="15" aria-hidden="true" />修改密码</h2>
        </header>
        <form class="account-form" @submit.prevent="savePassword">
          <UiInput
            v-model="currentPassword"
            type="password"
            label="当前密码"
            autocomplete="current-password"
            required
          />
          <UiInput
            v-model="newPassword"
            type="password"
            label="新密码（至少 6 位）"
            autocomplete="new-password"
            required
          />
          <UiInput
            v-model="confirmPassword"
            type="password"
            label="确认新密码"
            autocomplete="new-password"
            :error="passwordMismatch ? '两次输入的新密码不一致' : ''"
            required
          />
          <div class="account-form-actions">
            <UiButton type="submit" variant="primary" size="sm" :disabled="!canSavePassword" :loading="savingPassword">
              <template #leading><Save :size="14" aria-hidden="true" /></template>
              更新密码
            </UiButton>
          </div>
        </form>
      </article>
    </div>
  </section>
</template>

<style scoped>
.account-page {
  width: 100%;
  padding: 20px 24px 40px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.account-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.account-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px 20px;
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  background: var(--color-surface);
}

.account-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.account-card-head h2 {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
}

.account-role {
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid rgb(240 184 75 / 32%);
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-size: 11px;
}

.account-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.account-readonly-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.account-email {
  margin: 0;
  padding: 8px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: var(--color-canvas);
  color: var(--color-muted);
  font-size: 13px;
}

.account-form-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 4px;
}

@media (max-width: 820px) {
  .account-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 640px) {
  .account-page {
    padding: 18px 16px 32px;
  }
}
</style>
