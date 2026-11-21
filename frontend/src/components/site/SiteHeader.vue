<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowUpRight, Menu } from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiIconButton from '@/components/ui/UiIconButton.vue'
import { siteNavigation } from './site-navigation'
import type { SiteNavItem } from './site-navigation'
import '@/styles/site.css'

withDefaults(defineProps<{ items?: readonly SiteNavItem[] }>(), { items: () => siteNavigation })
defineEmits<{ account: [mode: 'login' | 'register'] }>()
const route = useRoute()
const menuOpen = ref(false)
watch(() => route.fullPath, () => { menuOpen.value = false })
</script>

<template>
  <header class="site-header">
    <div class="site-header-inner">
      <RouterLink to="/" class="site-brand" aria-label="帧剧首页">
        <img src="/brand/framedrama-logo.svg" alt="" width="36" height="36" />
        <span>帧剧<small>FRAMEDRAMA</small></span>
      </RouterLink>
      <nav class="site-desktop-nav" aria-label="主导航">
        <RouterLink v-for="item in items" :key="item.to" :to="item.to">{{ item.label }}</RouterLink>
      </nav>
      <div class="site-header-actions">
        <UiButton class="site-login" variant="ghost" @click="$emit('account', 'login')">登录</UiButton>
        <UiButton variant="primary" size="sm" @click="$emit('account', 'register')">开始创作<template #trailing><ArrowUpRight :size="15" aria-hidden="true" /></template></UiButton>
        <div class="site-mobile-menu">
          <UiDialog v-model:open="menuOpen" title="探索帧剧" description="让每一份想象，都有自己的画面。">
            <template #trigger><UiIconButton label="打开导航"><Menu :size="20" /></UiIconButton></template>
            <nav class="site-mobile-nav" aria-label="手机导航">
              <RouterLink v-for="item in items" :key="item.to" :to="item.to" @click="menuOpen = false">{{ item.label }}<ArrowUpRight :size="16" aria-hidden="true" /></RouterLink>
              <button type="button" @click="menuOpen = false; $emit('account', 'login')">登录账号<ArrowUpRight :size="16" aria-hidden="true" /></button>
            </nav>
          </UiDialog>
        </div>
      </div>
    </div>
  </header>
</template>
