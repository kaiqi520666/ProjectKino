<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  ArrowRight,
  Coins,
  KeyRound,
  Lock,
  Mail,
  Save,
  ShieldCheck,
  UserRound,
} from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import UiInput from '@/components/ui/UiInput.vue'
import { extractErrorMessage, formatCredits } from '@/lib/format'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

const auth = useAuthStore()
const ui = useUiStore()

const nickname = ref(auth.user?.nickname ?? '')
const savingProfile = ref(false)

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const savingPassword = ref(false)

const displayName = computed(() => auth.user?.nickname?.trim() || auth.user?.email || '创作者')

const avatarInitial = computed(() => {
  const source = displayName.value.trim()
  return source ? source[0]!.toUpperCase() : 'U'
})

const roleLabel = computed(() => {
  if (auth.user?.role === 'admin') return '管理员'
  if (auth.user?.role === 'operator') return '运营'
  return '创作者'
})

const multiplierNumber = computed(() => {
  const val = Number(auth.user?.usageMultiplier ?? 1)
  return Number.isFinite(val) ? val : 1
})

const multiplierLabel = computed(() => {
  if (multiplierNumber.value < 1) {
    return `专属 ${(multiplierNumber.value * 10).toFixed(1).replace(/\.0$/, '')} 折`
  }
  return `${multiplierNumber.value.toFixed(2)}× 标准费率`
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
  (next) => {
    nickname.value = next ?? ''
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
</script>

<template>
  <div class="security-layout">
    <!-- 左侧：个人名片与账户摘要 -->
    <aside class="security-profile-card" aria-label="个人账户名片">
      <div class="security-profile-hero">
        <span class="security-avatar" aria-hidden="true">{{ avatarInitial }}</span>
        <div class="security-profile-copy">
          <div class="security-profile-name-row">
            <h2>{{ displayName }}</h2>
            <span class="security-role-badge">{{ roleLabel }}</span>
          </div>
          <p class="security-profile-email">
            <Mail :size="13" aria-hidden="true" />
            <span>{{ auth.user?.email || '-' }}</span>
          </p>
        </div>
      </div>

      <dl class="security-profile-stats">
        <div class="security-stat-row">
          <dt>账号编号</dt>
          <dd class="security-mono">#{{ auth.user?.id ?? '-' }}</dd>
        </div>
        <div class="security-stat-row">
          <dt>可用积分</dt>
          <dd class="security-mono is-gold">{{ formatCredits(auth.user?.balance) }}</dd>
        </div>
        <div class="security-stat-row">
          <dt>冻结积分</dt>
          <dd class="security-mono">{{ formatCredits(auth.user?.frozen) }}</dd>
        </div>
        <div class="security-stat-row">
          <dt>计费费率</dt>
          <dd :class="{ 'is-gold': multiplierNumber < 1 }">{{ multiplierLabel }}</dd>
        </div>
      </dl>

      <div class="security-profile-foot">
        <RouterLink :to="{ name: 'account-credits' }" class="security-credits-link">
          <span class="security-credits-link-label">
            <Coins :size="14" aria-hidden="true" />
            查看消费账单与明细
          </span>
          <ArrowRight :size="14" aria-hidden="true" />
        </RouterLink>
      </div>
    </aside>

    <!-- 右侧：基本资料 + 登录密码 -->
    <div class="security-main-stack">
      <section class="security-card" aria-label="基本资料设置">
        <header class="security-card-head">
          <h3><UserRound :size="15" aria-hidden="true" />基本资料</h3>
        </header>

        <form class="security-card-body" @submit.prevent="saveProfile">
          <div class="security-fields-grid is-cols-2">
            <div class="security-readonly-field">
              <span class="ui-label">登录邮箱</span>
              <div class="security-readonly-box">
                <span class="security-readonly-value">{{ auth.user?.email || '-' }}</span>
                <span class="security-readonly-lock">
                  <Lock :size="12" aria-hidden="true" />已绑定
                </span>
              </div>
            </div>

            <UiInput v-model="nickname" label="昵称" placeholder="输入显示昵称" required />
          </div>

          <div class="security-card-actions">
            <UiButton
              type="submit"
              variant="primary"
              size="sm"
              :disabled="!canSaveProfile"
              :loading="savingProfile"
            >
              <template #leading><Save :size="14" aria-hidden="true" /></template>
              保存修改
            </UiButton>
          </div>
        </form>
      </section>

      <section class="security-card" aria-label="登录密码设置">
        <header class="security-card-head">
          <h3><KeyRound :size="15" aria-hidden="true" />登录密码</h3>
        </header>

        <form class="security-card-body" @submit.prevent="savePassword">
          <div class="security-fields-grid is-cols-3">
            <UiInput
              v-model="currentPassword"
              type="password"
              label="当前密码"
              placeholder="请输入当前密码"
              autocomplete="current-password"
              required
            />
            <UiInput
              v-model="newPassword"
              type="password"
              label="新密码（至少 6 位）"
              placeholder="请输入新密码"
              autocomplete="new-password"
              required
            />
            <UiInput
              v-model="confirmPassword"
              type="password"
              label="确认新密码"
              placeholder="请再次输入新密码"
              autocomplete="new-password"
              :error="passwordMismatch ? '两次输入的新密码不一致' : ''"
              required
            />
          </div>

          <div class="security-card-actions">
            <UiButton
              type="submit"
              variant="primary"
              size="sm"
              :disabled="!canSavePassword"
              :loading="savingPassword"
            >
              <template #leading><ShieldCheck :size="14" aria-hidden="true" /></template>
              更新密码
            </UiButton>
          </div>
        </form>
      </section>
    </div>
  </div>
</template>

<style scoped>
.security-layout {
  width: 100%;
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.security-profile-card {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 20px;
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  background:
    radial-gradient(circle at 0% 0%, rgb(240 184 75 / 11%), transparent 56%),
    var(--color-surface);
}

.security-profile-hero {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.security-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 50px;
  height: 50px;
  flex-shrink: 0;
  border-radius: 999px;
  border: 1px solid rgb(240 184 75 / 40%);
  background: linear-gradient(145deg, rgb(240 184 75 / 22%), rgb(240 184 75 / 5%));
  color: var(--color-gold-soft);
  font-size: 20px;
  font-weight: 700;
}

.security-profile-copy {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}

.security-profile-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.security-profile-name-row h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.security-role-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid rgb(240 184 75 / 34%);
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-size: 11px;
  font-weight: 500;
  flex-shrink: 0;
}

.security-profile-email {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: 12.5px;
  color: var(--color-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.security-profile-stats {
  margin: 0;
  padding: 14px 0;
  border-top: 1px solid var(--border-subtle);
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  gap: 11px;
}

.security-stat-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}

.security-stat-row dt {
  color: var(--color-muted);
}

.security-stat-row dd {
  margin: 0;
  color: var(--color-text);
  font-weight: 500;
}

.security-stat-row dd.is-gold {
  color: var(--color-gold-soft);
}

.security-mono {
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
  font-variant-numeric: tabular-nums;
}

.security-profile-foot {
  display: flex;
  flex-direction: column;
}

.security-credits-link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
  background: rgb(255 255 255 / 2.5%);
  color: var(--color-text);
  font-size: 13px;
  font-weight: 500;
  text-decoration: none;
  transition: border-color 0.16s ease, background-color 0.16s ease, color 0.16s ease;
}

.security-credits-link:hover {
  border-color: rgb(240 184 75 / 38%);
  background: rgb(240 184 75 / 7%);
  color: var(--color-gold-soft);
}

.security-credits-link-label {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.security-main-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.security-card {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  background: var(--color-surface);
  overflow: hidden;
}

.security-card-head {
  padding: 15px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.security-card-head h3 {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  font-size: 14.5px;
  font-weight: 600;
  color: var(--color-text);
}

.security-card-body {
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.security-fields-grid {
  display: grid;
  gap: 16px;
  align-items: start;
}

.security-fields-grid.is-cols-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.security-fields-grid.is-cols-3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.security-readonly-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}

.security-readonly-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 36px;
  padding: 7px 11px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: var(--color-canvas);
  color: var(--color-muted);
  font-size: 13px;
}

.security-readonly-value {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.security-readonly-lock {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--color-muted);
  opacity: 0.8;
  flex-shrink: 0;
}

.security-card-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-subtle);
}

@media (max-width: 1160px) {
  .security-layout {
    grid-template-columns: 280px minmax(0, 1fr);
  }

  .security-fields-grid.is-cols-3 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 960px) {
  .security-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 640px) {
  .security-fields-grid.is-cols-2,
  .security-fields-grid.is-cols-3 {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
