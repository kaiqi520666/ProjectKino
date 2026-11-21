<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowDown, ArrowRight, ArrowUpRight, BookOpenText, ChevronLeft, ChevronRight,
  Clapperboard, Image, Layers3, Sparkles,
} from 'lucide-vue-next'
import { FeatureItem, ImageCard, ProcessSteps, UiButton, UiDialog, UiIconButton, UiImage, UiTabs } from '@/components'
import type { ImageAspectRatio, ProcessStep } from '@/components'
import SiteHeader from '@/components/site/SiteHeader.vue'
import SiteFooter from '@/components/site/SiteFooter.vue'
import '@/styles/home.css'

interface Work {
  id: string
  title: string
  genre: 'fantasy' | 'modern'
  category: string
  description: string
  image: string
  alt: string
  ratio: ImageAspectRatio
}

const works: readonly Work[] = [
  { id: 'bamboo', title: '竹影行', genre: 'fantasy', category: '东方武侠', description: '竹林深处，一段江湖故事正要开始。', image: '/images/home/cover-wuxia.jpg', alt: '身着红色披风的女侠站在青绿色竹林中', ratio: '3:4' },
  { id: 'city', title: '下一站，晴天', genre: 'modern', category: '都市奇遇', description: '一个转身，遇见城市的另一种可能。', image: '/images/home/cover-city.jpg', alt: '白色夹克的短发女孩站在有轨电车经过的街头', ratio: '3:4' },
  { id: 'cloud', title: '云上来信', genre: 'fantasy', category: '旅行冒险', description: '越过森林与山谷，去往故事的远方。', image: '/images/home/scene-fantasy.jpg', alt: '背着行囊的旅行者站在石桥上，望向山崖上的城堡', ratio: '4:3' },
  { id: 'space', title: '星际回声', genre: 'modern', category: '未来科幻', description: '在遥远星河，寻找属于自己的回声。', image: '/images/home/scene-scifi.jpg', alt: '女宇航员透过空间站的观景窗望向蓝绿色行星', ratio: '4:3' },
]
const genre = ref('all')
const genreTabs = [
  { value: 'all', label: '全部画面', count: 4 },
  { value: 'fantasy', label: '东方与幻想', count: 2 },
  { value: 'modern', label: '都市与科幻', count: 2 },
]
const visibleWorks = computed(() => works.filter(work => genre.value === 'all' || work.genre === genre.value))
const previewOpen = ref(false)
const selectedWorkId = ref(works[0]!.id)
const selectedWork = computed(() => works.find(work => work.id === selectedWorkId.value) ?? works[0]!)
const selectedPosition = computed(() => visibleWorks.value.findIndex(work => work.id === selectedWorkId.value))
const router = useRouter()
const steps: ProcessStep[] = [
  { id: 'story', title: '写下你的故事', description: '从一句灵感、一段梗概开始，梳理人物、场景和故事脉络。' },
  { id: 'visuals', title: '让想象有迹可循', description: '确定角色形象与场景风格，把故事拆解为有节奏的分镜。' },
  { id: 'review', title: '打磨每一个画面', description: '回看、调整、整理素材，让每一帧都更接近心中的故事。' },
]

function openAccount(mode: 'login' | 'register' = 'register') {
  void router.push({ path: '/login', query: { next: '/', source: mode === 'login' ? 'header_login' : 'start_creating' } })
}

function openWork(work: Work) {
  selectedWorkId.value = work.id
  previewOpen.value = true
}

function moveWork(direction: number) {
  const list = visibleWorks.value
  const index = (selectedPosition.value + direction + list.length) % list.length
  selectedWorkId.value = list[index]!.id
}
</script>

<template>
  <div id="top" class="home-page">
    <a class="home-skip-link" href="#home-content">跳到主要内容</a>
    <SiteHeader @account="openAccount" />
    <main id="home-content">
      <section class="home-hero" aria-labelledby="home-title">
        <picture class="home-hero-picture">
          <source media="(max-width: 640px)" srcset="/images/home/hero-mobile.jpg" />
          <img src="/images/home/hero-desktop.jpg" alt="红衣女侠眺望群山之间的水上古城" width="1920" height="1080" fetchpriority="high" />
        </picture>
        <div class="home-container home-hero-content">
          <p class="home-eyebrow"><Sparkles :size="16" aria-hidden="true" />AI 漫剧创作</p>
          <h1 id="home-title">帧剧<span>FRAMEDRAMA</span></h1>
          <p class="home-hero-tagline">把想象，拍成故事。</p>
          <p class="home-hero-description">从一段灵感，到一个鲜活的世界。<br />让人物、场景与分镜，承载你的每一次表达。</p>
          <div class="home-hero-actions">
            <UiButton variant="primary" size="lg" @click="openAccount()">开始创作<template #trailing><ArrowUpRight :size="18" aria-hidden="true" /></template></UiButton>
            <RouterLink to="/#works" class="ui-button ui-button--secondary ui-button--lg">探索作品<ArrowDown :size="16" aria-hidden="true" /></RouterLink>
          </div>
          <div class="home-hero-disciplines"><span><BookOpenText :size="15" aria-hidden="true" />故事构思</span><span><Image :size="15" aria-hidden="true" />视觉创作</span><span><Clapperboard :size="15" aria-hidden="true" />分镜表达</span></div>
        </div>
        <div class="home-hero-caption"><span>原创视觉 · 山河之间</span></div>
      </section>

      <section id="works" class="home-section home-works" aria-labelledby="works-title">
        <div class="home-container">
          <div class="home-section-heading">
            <div><p class="home-eyebrow">灵感放映室</p><h2 id="works-title">故事的世界，<span>不止一种模样。</span></h2></div>
            <p>东方、都市、幻想与未来<br />在不同的画面里，找到你的下一次灵感。</p>
          </div>
          <UiTabs v-model="genre" label="作品题材" :tabs="genreTabs">
            <template v-for="tab in genreTabs" :key="tab.value" #[tab.value]>
              <div class="home-gallery">
                <ImageCard
                  v-for="work in works.filter(item => tab.value === 'all' || item.genre === tab.value)"
                  :key="work.id"
                  :src="work.image"
                  :alt="work.alt"
                  :title="work.title"
                  :category="work.category"
                  :description="work.description"
                  :aspect-ratio="work.ratio"
                  action-label="查看画面"
                  @action="openWork(work)"
                />
              </div>
            </template>
          </UiTabs>
          <p class="home-gallery-note"><Sparkles :size="13" aria-hidden="true" />AI 生成视觉样片</p>
        </div>
      </section>

      <section id="features" class="home-section home-features" aria-labelledby="features-title">
        <div class="home-container">
          <div class="home-section-heading"><div><p class="home-eyebrow">专注于创作本身</p><h2 id="features-title">让灵感，<span>一步步成为画面。</span></h2></div><p>围绕故事组织创作<br />让每一次调整，都有迹可循。</p></div>
          <div class="home-feature-grid">
            <FeatureItem title="故事与分镜" description="把梗概拆解为场景和镜头，用清晰的结构承载叙事节奏。" layout="vertical"><template #icon><BookOpenText :size="27" :stroke-width="1.5" /></template></FeatureItem>
            <FeatureItem title="角色与场景" description="围绕角色形象与场景风格整理素材，让不同画面彼此呼应。" layout="vertical"><template #icon><Image :size="27" :stroke-width="1.5" /></template></FeatureItem>
            <FeatureItem title="作品与版本" description="在回看与调整中积累创作素材，为每个故事保留自己的脉络。" layout="vertical"><template #icon><Layers3 :size="27" :stroke-width="1.5" /></template></FeatureItem>
          </div>
        </div>
      </section>

      <section id="workflow" class="home-section home-workflow" aria-labelledby="workflow-title">
        <div class="home-container">
          <div class="home-section-heading"><div><p class="home-eyebrow">从第一帧开始</p><h2 id="workflow-title">三个步骤，<span>走进你的故事。</span></h2></div><RouterLink to="/#works" class="home-text-link">寻找灵感<ArrowRight :size="17" aria-hidden="true" /></RouterLink></div>
          <ProcessSteps :steps="steps" label="漫剧创作流程" />
        </div>
      </section>

      <section class="home-start" aria-labelledby="start-title">
        <div class="home-container home-start-inner"><div><p class="home-eyebrow"><Sparkles :size="15" aria-hidden="true" />故事，始终属于你</p><h2 id="start-title">下一次开场，<br class="home-mobile-break" />从你的想象开始。</h2></div><UiButton variant="primary" size="lg" @click="openAccount()">开启我的故事<template #trailing><ArrowUpRight :size="18" aria-hidden="true" /></template></UiButton></div>
      </section>
    </main>
    <SiteFooter />

    <UiDialog v-model:open="previewOpen" :title="selectedWork.title" :description="`${selectedWork.category} · AI 生成视觉样片`">
      <div @keydown.left.prevent="moveWork(-1)" @keydown.right.prevent="moveWork(1)">
        <UiImage :src="selectedWork.image" :alt="selectedWork.alt" :aspect-ratio="selectedWork.ratio" fit="contain" loading="eager" />
      </div>
      <template #footer><div class="home-work-preview-footer"><span>{{ selectedPosition + 1 }} / {{ visibleWorks.length }}</span><div><UiIconButton label="上一张画面" @click="moveWork(-1)"><ChevronLeft :size="19" /></UiIconButton><UiIconButton label="下一张画面" @click="moveWork(1)"><ChevronRight :size="19" /></UiIconButton></div></div></template>
    </UiDialog>
  </div>
</template>
