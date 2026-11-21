<script setup lang="ts">
import { CircleAlert, CircleCheck, Info, TriangleAlert } from 'lucide-vue-next'

withDefaults(defineProps<{ title: string; tone?: 'info' | 'success' | 'warning' | 'error' }>(), { tone: 'info' })
const icons = { info: Info, success: CircleCheck, warning: TriangleAlert, error: CircleAlert }
</script>

<template>
  <div class="ui-alert" :class="`ui-alert--${tone}`" :role="tone === 'error' ? 'alert' : 'status'">
    <component :is="icons[tone]" :size="17" aria-hidden="true" />
    <div><strong>{{ title }}</strong><p v-if="$slots.default"><slot /></p></div>
    <slot name="action" />
  </div>
</template>
