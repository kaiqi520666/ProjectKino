<script setup lang="ts">
import { ArrowUp } from 'lucide-vue-next'
import { siteNavigation } from './site-navigation'
import type { SiteNavItem } from './site-navigation'
import '@/styles/site.css'

withDefaults(defineProps<{
  items?: readonly SiteNavItem[]
  legalLinks?: readonly { label: string; href: string }[]
  contact?: { label: string; href: string }
  record?: { label: string; href: string }
}>(), { items: () => siteNavigation, legalLinks: () => [] })
const year = new Date().getFullYear()
</script>

<template>
  <footer class="site-footer">
    <div class="site-container">
      <div class="site-footer-main">
        <div>
          <RouterLink to="/" class="site-brand" aria-label="帧剧首页"><img src="/brand/framedrama-logo.svg" alt="" width="36" height="36" /><span>帧剧<small>FRAMEDRAMA</small></span></RouterLink>
          <p>让每一份想象，都有自己的画面。</p>
        </div>
        <nav aria-label="页脚导航"><RouterLink v-for="item in items" :key="item.to" :to="item.to">{{ item.label }}</RouterLink><a v-if="contact" :href="contact.href">{{ contact.label }}</a></nav>
        <RouterLink class="site-back-top" to="/#top">返回顶部<ArrowUp :size="15" aria-hidden="true" /></RouterLink>
      </div>
      <div class="site-footer-bottom">
        <span>© {{ year }} 帧剧 FrameDrama</span>
        <div v-if="legalLinks.length || record">
          <a v-for="link in legalLinks" :key="link.href" :href="link.href">{{ link.label }}</a>
          <a v-if="record" :href="record.href" target="_blank" rel="noopener noreferrer">{{ record.label }}</a>
        </div>
        <span>为故事而创作</span>
      </div>
    </div>
  </footer>
</template>
