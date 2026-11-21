<script setup lang="ts">
import { computed, ref } from 'vue'
import { Clapperboard, FolderHeart } from 'lucide-vue-next'
import {
  FeatureItem, ImageCard, ProcessSteps, UiDialog, UiImage, UiSelect, UiSkeleton, UiSwitch,
  imageAspectRatios,
} from '@/components'
import type { ImageAspectRatio, ImageFit, ProcessStep } from '@/components'
import brandCutout from './assets/brand-cutout.svg'

const brandImage = '/brand/framedrama-logo.svg'
const ratio = ref<ImageAspectRatio>('16:9')
const fit = ref<ImageFit>('contain')
const sourceMode = ref('normal')
const orientation = ref<'horizontal' | 'vertical'>('horizontal')
const showStepImages = ref(false)
const dialogOpen = ref(false)
const selectedImage = ref({ src: brandImage, title: '品牌视觉', transparent: false })
const retries = ref(0)
const ratios = Object.keys(imageAspectRatios) as ImageAspectRatio[]
const ratioOptions = ratios.map(value => ({ value, label: value }))
const source = computed(() => ({
  normal: brandImage,
  transparent: brandCutout,
  empty: '',
  error: 'data:image/png;base64,AA==',
}[sourceMode.value] ?? ''))
const steps = computed<ProcessStep[]>(() => [
  { id: 'story', title: '整理故事', description: '确定人物、场景与故事梗概。' },
  { id: 'visuals', title: '准备视觉', description: '挑选角色、场景和封面素材。' },
  { id: 'review', title: '确认作品', description: '检查画面与内容，保存当前版本。' },
].map(step => ({
  ...step,
  imageSrc: showStepImages.value ? brandImage : undefined,
  imageAlt: '帧剧品牌素材',
})))

function previewImage(src: string, title: string, transparent = false) {
  selectedImage.value = { src, title, transparent }
  dialogOpen.value = true
}

function reset() {
  ratio.value = '16:9'
  fit.value = 'contain'
  sourceMode.value = 'normal'
  orientation.value = 'horizontal'
  showStepImages.value = false
  dialogOpen.value = false
  retries.value = 0
}

defineExpose({ reset })
</script>

<template>
  <section id="images" class="preview-section">
    <div class="preview-section-heading"><h2>图片与占位</h2><code>UiImage · UiSkeleton</code></div>
    <div class="preview-grid">
      <div>
        <div class="preview-image-controls preview-image-controls--three">
          <UiSelect v-model="ratio" label="图片比例" :options="ratioOptions" />
          <UiSelect v-model="fit" label="适配方式" :options="[{value:'contain',label:'完整显示'},{value:'cover',label:'填满裁切'}]" />
          <UiSelect v-model="sourceMode" label="图片来源" :options="[{value:'normal',label:'品牌标识'},{value:'transparent',label:'透明标识'},{value:'empty',label:'空图片'},{value:'error',label:'加载失败'}]" />
        </div>
        <figure class="preview-figure">
          <UiImage :src="source" alt="帧剧品牌标识" :aspect-ratio="ratio" :fit="fit" :checkerboard="sourceMode === 'transparent'" loading="eager" @retry="retries++" />
          <figcaption><span>帧剧品牌标识</span><span>{{ ratio }}</span></figcaption>
        </figure>
        <p v-if="retries" class="preview-retry-count">已重试 {{ retries }} 次</p>
      </div>
      <div class="preview-skeleton-example" role="status" aria-label="内容加载中" aria-busy="true">
        <UiSkeleton height="auto" />
        <div class="preview-skeleton-header">
          <UiSkeleton shape="circle" />
          <div class="preview-skeleton-copy"><UiSkeleton shape="text" width="42%" height="14px" /><UiSkeleton shape="text" width="70%" height="12px" /></div>
        </div>
        <UiSkeleton shape="text" width="95%" height="12px" />
        <UiSkeleton shape="text" width="76%" height="12px" />
      </div>
    </div>
    <div class="preview-ratio-list" aria-label="五种图片比例">
      <figure v-for="preset in ratios" :key="preset" class="preview-figure">
        <UiImage :src="brandCutout" alt="透明帧剧标识" :aspect-ratio="preset" fit="contain" checkerboard />
        <figcaption>{{ preset }}</figcaption>
      </figure>
    </div>
  </section>

  <section id="showcase" class="preview-section">
    <div class="preview-section-heading"><h2>内容展示</h2><code>ImageCard · FeatureItem</code></div>
    <div class="preview-image-cards">
      <ImageCard :src="brandImage" alt="黑底金色帧剧标识" title="品牌视觉" description="黑金色的帧剧品牌标识。" category="品牌素材" fit="contain" action-label="查看图片" @action="previewImage(brandImage, '品牌视觉')" />
      <ImageCard :src="brandCutout" alt="透明背景帧剧标识" title="透明标识" description="保留透明区域，适配不同背景。" category="透明素材" fit="contain" checkerboard action-label="查看图片" @action="previewImage(brandCutout, '透明标识', true)" />
      <ImageCard :src="brandImage" alt="方形帧剧标识" title="方形素材" description="卡片也可只展示图片与说明。" aspect-ratio="1:1" fit="contain" />
    </div>
    <div class="preview-feature-items">
      <FeatureItem title="故事创作" description="集中整理故事梗概、人物与场景。"><template #icon><Clapperboard :size="24" :stroke-width="1.5" /></template></FeatureItem>
      <FeatureItem title="品牌素材" description="图像与文案组合展示，保持统一视觉。" :image-src="brandCutout" image-alt="帧剧品牌标识" />
      <FeatureItem title="资产管理" description="整理并复用角色、场景与封面素材。" layout="vertical"><template #icon><FolderHeart :size="24" :stroke-width="1.5" /></template></FeatureItem>
    </div>
  </section>

  <section id="process" class="preview-section">
    <div class="preview-section-heading"><h2>流程步骤</h2><code>ProcessSteps</code></div>
    <div class="preview-process-controls">
      <UiSelect v-model="orientation" label="排列方式" :options="[{value:'horizontal',label:'横向排列'},{value:'vertical',label:'纵向排列'}]" />
      <UiSwitch v-model="showStepImages" label="展示步骤配图" />
    </div>
    <ProcessSteps :steps="steps" :orientation="orientation" />
  </section>

  <UiDialog v-model:open="dialogOpen" :title="selectedImage.title" description="帧剧品牌素材">
    <UiImage :src="selectedImage.src" :alt="selectedImage.title" aspect-ratio="1:1" fit="contain" :checkerboard="selectedImage.transparent" loading="eager" />
  </UiDialog>
</template>
