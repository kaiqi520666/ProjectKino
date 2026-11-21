<script setup lang="ts">
import { CircleAlert, CircleCheck, Info, X } from 'lucide-vue-next'
import { ToastClose, ToastDescription, ToastProvider, ToastRoot, ToastTitle, ToastViewport } from 'reka-ui'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const icons = { success: CircleCheck, error: CircleAlert, info: Info }
</script>

<template>
  <ToastProvider :duration="4500" swipe-direction="right" label="通知">
    <ToastRoot v-for="notice in ui.notices" :key="notice.id" class="ui-toast" :class="`ui-toast--${notice.tone}`" @update:open="(open) => !open && ui.dismiss(notice.id)">
      <component :is="icons[notice.tone]" :size="18" class="ui-toast-icon" aria-hidden="true" />
      <div>
        <ToastTitle class="ui-toast-title">{{ notice.title }}</ToastTitle>
        <ToastDescription v-if="notice.description" class="ui-toast-description">{{ notice.description }}</ToastDescription>
      </div>
      <ToastClose class="ui-icon-button" aria-label="关闭通知"><X :size="15" /></ToastClose>
    </ToastRoot>
    <ToastViewport class="ui-toast-viewport" label="通知列表" />
  </ToastProvider>
</template>
