<script setup lang="ts">
import { Sparkles } from 'lucide-vue-next'
import UiImage from '@/components/ui/UiImage.vue'

withDefaults(defineProps<{
  title: string
  description?: string
  imageSrc?: string
  imageAlt?: string
  layout?: 'horizontal' | 'vertical'
}>(), { imageAlt: '', layout: 'horizontal' })
</script>

<template>
  <article class="feature-item" :class="`feature-item--${layout}`">
    <div class="feature-item-visual" :class="{ 'has-image': imageSrc }">
      <UiImage v-if="imageSrc" :src="imageSrc" :alt="imageAlt" aspect-ratio="1:1" fit="contain" :retryable="false" />
      <span v-else class="feature-item-icon" aria-hidden="true"><slot name="icon"><Sparkles :size="24" :stroke-width="1.5" /></slot></span>
    </div>
    <div class="feature-item-content">
      <h3>{{ title }}</h3>
      <p v-if="description">{{ description }}</p>
      <slot />
    </div>
  </article>
</template>
