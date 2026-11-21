<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowRight, BookOpenText, ChevronRight, Clapperboard, Eye, EyeOff,
  Globe2, LockKeyhole, Mail, ShieldCheck, Sparkles, UserRound, Volume2,
} from 'lucide-vue-next'
import { UiAlert, UiButton, UiCheckbox, UiDialog, UiIconButton, UiInput, UiTabs } from '@/components'
import { apiErrorMessage } from '@/features/studio/api'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import '@/styles/auth.css'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()

const backgrounds = { desktop: '/images/auth/login-desktop.jpg', mobile: '/images/auth/login-mobile.jpg' }
const method = ref(route.query.mode === 'register' ? 'register' : 'login')
const methods = [
  { value: 'login', label: '邮箱登录' },
  { value: 'register', label: '免费注册' },
]
const email = ref('')
const nickname = ref('')
const password = ref('')
const passwordVisible = ref(false)
const agreed = ref(true)
const submitting = ref(false)
const feedback = ref('')
const feedbackTone = ref<'error' | 'warning'>('error')
const policy = ref<'user' | 'privacy' | null>(null)
const policyOpen = computed({
  get: () => policy.value !== null,
  set: (open: boolean) => { if (!open) policy.value = null },
})
const previousTitle = document.title

watch(method, () => {
  password.value = ''
  passwordVisible.value = false
  feedback.value = ''
  document.title = method.value === 'register' ? '注册 | 帧剧 FrameDrama' : '登录 | 帧剧 FrameDrama'
}, { immediate: true })
onUnmounted(() => { document.title = previousTitle })

function redirectTarget(): string {
  const next = typeof route.query.next === 'string' ? route.query.next : ''
  return next.startsWith('/') && !next.startsWith('//') ? next : '/workspace'
}

async function submit() {
  if (submitting.value) return
  if (!agreed.value) {
    feedbackTone.value = 'error'
    feedback.value = '请先阅读并同意用户服务协议和隐私政策。'
    return
  }
  const cleanEmail = email.value.trim()
  if (!cleanEmail || !cleanEmail.includes('@')) {
    feedbackTone.value = 'error'
    feedback.value = '请输入有效的邮箱地址。'
    return
  }
  if (method.value === 'register' && password.value.length < 6) {
    feedbackTone.value = 'error'
    feedback.value = '密码长度至少为 6 位。'
    return
  }

  submitting.value = true
  feedback.value = ''
  try {
    if (method.value === 'register') {
      await auth.register(cleanEmail, password.value, nickname.value.trim())
      ui.notify('注册成功，欢迎来到帧剧', 'success')
    } else {
      await auth.login(cleanEmail, password.value)
      ui.notify('登录成功', 'success')
    }
    await router.replace(redirectTarget())
  } catch (error) {
    feedbackTone.value = 'error'
    feedback.value = apiErrorMessage(error)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <picture class="auth-backdrop" aria-hidden="true">
      <source media="(max-width: 640px)" :srcset="backgrounds.mobile" />
      <img :src="backgrounds.desktop" alt="" width="1920" height="1080" fetchpriority="high" />
    </picture>
    <header class="auth-header">
      <RouterLink to="/" class="auth-brand" aria-label="帧剧，返回首页">
        <img src="/brand/framedrama-logo.svg" width="44" height="44" alt="" />
        <span>帧剧<small>FRAMEDRAMA STUDIO</small></span>
      </RouterLink>
      <div class="auth-header-actions">
        <RouterLink to="/" class="auth-home-link" aria-label="返回首页"><span>返回首页</span><ChevronRight :size="15" aria-hidden="true" /></RouterLink>
        <span class="auth-language"><Globe2 :size="15" aria-hidden="true" />简体中文</span>
      </div>
    </header>

    <main class="auth-layout">
      <section class="auth-story" aria-labelledby="auth-story-title">
        <p class="auth-eyebrow"><Sparkles :size="15" aria-hidden="true" />AI 漫剧一站式创作平台</p>
        <h1 id="auth-story-title">把灵感，变成一部<br /><span>真正完整的漫剧</span></h1>
        <p class="auth-story-description">从一句话到剧本、角色、分镜与画面，<br class="auth-wide-break" />让繁琐的制作更简单，让你专注于故事。</p>
        <div class="auth-benefits" aria-label="创作流程">
          <div><Sparkles :size="21" aria-hidden="true" /><h2>从一句话开始</h2><p>把转瞬即逝的灵感写成故事</p></div>
          <div><UserRound :size="21" aria-hidden="true" /><h2>让角色鲜活起来</h2><p>为人物与场景建立视觉表达</p></div>
          <div><Clapperboard :size="21" aria-hidden="true" /><h2>串联每一帧想象</h2><p>让故事在分镜之间自然展开</p></div>
        </div>
        <div class="auth-story-example">
          <span class="auth-example-icon"><BookOpenText :size="19" aria-hidden="true" /></span>
          <div><small>故事灵感</small><p>一封寄往过去的信，让两个人的命运再次交汇……</p></div>
          <span class="auth-example-flow"><BookOpenText :size="12" aria-hidden="true" />剧本<ChevronRight :size="12" aria-hidden="true" /><Clapperboard :size="12" aria-hidden="true" />分镜<ChevronRight :size="12" aria-hidden="true" /><Volume2 :size="12" aria-hidden="true" />配音</span>
        </div>
      </section>

      <section class="auth-panel" aria-labelledby="auth-form-title">
        <p class="auth-security-label"><LockKeyhole :size="14" aria-hidden="true" />安全创作账户</p>
        <h2 id="auth-form-title">{{ method === 'register' ? '免费创建创作账号' : '欢迎回来' }}</h2>
        <p class="auth-panel-description">{{ method === 'register' ? '填写邮箱与密码即可快速注册，开启你的第一部短剧。' : '使用邮箱和密码登录，继续你的短剧项目。' }}</p>

        <UiTabs v-model="method" :tabs="methods" label="登录方式" variant="segment">
          <template #login>
            <form class="auth-form" @submit.prevent="submit">
              <UiInput v-model="email" label="邮箱" type="email" autocomplete="email" required placeholder="请输入邮箱">
                <template #leading><Mail :size="17" /></template>
              </UiInput>
              <UiInput v-model="password" label="密码" :type="passwordVisible ? 'text' : 'password'" autocomplete="current-password" required placeholder="请输入密码">
                <template #leading><LockKeyhole :size="17" /></template>
                <template #trailing><UiIconButton :label="passwordVisible ? '隐藏密码' : '显示密码'" :active="passwordVisible" @click="passwordVisible = !passwordVisible"><EyeOff v-if="passwordVisible" :size="17" /><Eye v-else :size="17" /></UiIconButton></template>
              </UiInput>
              <UiAlert v-if="feedback" :tone="feedbackTone" :title="feedback" />
              <UiButton type="submit" size="lg" class="auth-submit" :loading="submitting" :disabled="submitting">
                登录并进入工作台<template #trailing><ArrowRight :size="18" aria-hidden="true" /></template>
              </UiButton>
            </form>
          </template>
          <template #register>
            <form class="auth-form" @submit.prevent="submit">
              <UiInput v-model="email" label="邮箱" type="email" autocomplete="email" required placeholder="请输入常用邮箱">
                <template #leading><Mail :size="17" /></template>
              </UiInput>
              <UiInput v-model="nickname" label="昵称（选填）" maxlength="40" autocomplete="nickname" placeholder="不填则默认使用邮箱前缀">
                <template #leading><UserRound :size="17" /></template>
              </UiInput>
              <UiInput v-model="password" label="设置密码" :type="passwordVisible ? 'text' : 'password'" autocomplete="new-password" minlength="6" required placeholder="至少 6 位字符">
                <template #leading><LockKeyhole :size="17" /></template>
                <template #trailing><UiIconButton :label="passwordVisible ? '隐藏密码' : '显示密码'" :active="passwordVisible" @click="passwordVisible = !passwordVisible"><EyeOff v-if="passwordVisible" :size="17" /><Eye v-else :size="17" /></UiIconButton></template>
              </UiInput>
              <UiAlert v-if="feedback" :tone="feedbackTone" :title="feedback" />
              <UiButton type="submit" size="lg" class="auth-submit" :loading="submitting" :disabled="submitting">
                立即注册并开始创作<template #trailing><ArrowRight :size="18" aria-hidden="true" /></template>
              </UiButton>
            </form>
          </template>
        </UiTabs>

        <div class="auth-agreement">
          <UiCheckbox v-model="agreed" label="已阅读并同意" />
          <span><button type="button" @click="policy = 'user'">《用户服务协议》</button>和<button type="button" @click="policy = 'privacy'">《隐私政策》</button></span>
        </div>
        <p class="auth-panel-footer"><ShieldCheck :size="14" aria-hidden="true" />让每一次灵感，都有一个开始</p>
      </section>
    </main>

    <UiDialog v-model:open="policyOpen" :title="policy === 'user' ? '用户服务协议' : '隐私政策'" description="帧剧账户服务">
      <p class="auth-policy-pending">使用帧剧服务即表示你同意合理合法使用 AI 创作能力，并妥善保管个人账户凭证。</p>
    </UiDialog>
  </div>
</template>
