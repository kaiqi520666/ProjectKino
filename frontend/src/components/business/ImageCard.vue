<script setup lang="ts">
import UiImage from '@/components/ui/UiImage.vue'
import UiButton from '@/components/ui/UiButton.vue'
import type { ImageAspectRatio, ImageFit } from '@/components/ui/image-types'

withDefaults(defineProps<{
  src?: string
  alt: string
  title: string
  description?: string
  category?: string
  aspectRatio?: ImageAspectRatio | number
  fit?: ImageFit
  checkerboard?: boolean
  loading?: 'lazy' | 'eager'
  actionLabel?: string
  disabled?: boolean
}>(), { aspectRatio: '4:3', fit: 'cover', loading: 'lazy' })
defineEmits<{ action: [] }>()
</script>

<template>
  <article class="image-card">
    <UiImage :src="src" :alt="alt" :aspect-ratio="aspectRatio" :fit="fit" :checkerboard="checkerboard" :loading="loading" />
    <div class="image-card-body">
      <span v-if="category" class="image-card-category">{{ category }}</span>
      <h3 class="image-card-title">{{ title }}</h3>
      <p v-if="description" class="image-card-description">{{ description }}</p>
      <div v-if="$slots.actions || actionLabel" class="image-card-actions">
        <slot name="actions">
          <UiButton size="sm" :disabled="disabled" @click="$emit('action')">{{ actionLabel }}</UiButton>
        </slot>
      </div>
    </div>
  </article>
</template>
