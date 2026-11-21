<script setup lang="ts">
import { ArrowRight } from 'lucide-vue-next'
import UiImage from '@/components/ui/UiImage.vue'
import type { ProcessStep } from './process-types'

withDefaults(defineProps<{
  steps: readonly ProcessStep[]
  label?: string
  orientation?: 'horizontal' | 'vertical'
}>(), { label: '创作流程', orientation: 'horizontal' })
</script>

<template>
  <ol
    v-if="steps.length"
    class="process-steps"
    :class="`process-steps--${orientation}`"
    :style="{ '--step-count': steps.length }"
    :aria-label="label"
  >
    <li v-for="(step, index) in steps" :key="step.id" class="process-step">
      <div class="process-step-number" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</div>
      <h3>{{ step.title }}</h3>
      <p v-if="step.description">{{ step.description }}</p>
      <UiImage v-if="step.imageSrc" :src="step.imageSrc" :alt="step.imageAlt ?? step.title" :aspect-ratio="step.aspectRatio ?? '16:9'" />
      <ArrowRight v-if="index < steps.length - 1" class="process-step-connector" :size="18" aria-hidden="true" />
    </li>
  </ol>
</template>
