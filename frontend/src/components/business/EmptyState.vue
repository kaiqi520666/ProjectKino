<script setup lang="ts">
import { Film } from 'lucide-vue-next'

defineProps<{ title: string; description?: string }>()
</script>

<template>
  <div class="empty-state">
    <div class="empty-state-icon" aria-hidden="true"><slot name="icon"><Film :size="25" :stroke-width="1.4" /></slot></div>
    <h3>{{ title }}</h3>
    <p v-if="description">{{ description }}</p>
    <div v-if="$slots.default" class="empty-state-actions"><slot /></div>
  </div>
</template>
