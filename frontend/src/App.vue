<script setup lang="ts">
import { TooltipProvider } from 'reka-ui'
import GlobalGenerationOverlay from '@/components/business/GlobalGenerationOverlay.vue'
import UiToastViewport from '@/components/ui/UiToastViewport.vue'
</script>

<template>
  <TooltipProvider :delay-duration="300">
    <RouterView />
    <GlobalGenerationOverlay />
    <UiToastViewport />
  </TooltipProvider>
</template>
