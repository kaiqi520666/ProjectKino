<script setup lang="ts">
withDefaults(defineProps<{
  shape?: 'rect' | 'text' | 'circle'
  width?: string
  height?: string
  animated?: boolean
}>(), { shape: 'rect', animated: true })
</script>

<template>
  <span
    class="ui-skeleton"
    :class="[`ui-skeleton--${shape}`, { 'is-animated': animated }]"
    :style="{ width: width ?? (shape === 'circle' ? '40px' : '100%'), height: height ?? (shape === 'circle' ? '40px' : '16px') }"
    aria-hidden="true"
  />
</template>
