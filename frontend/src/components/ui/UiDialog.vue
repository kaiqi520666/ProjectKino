<script setup lang="ts">
import { X } from 'lucide-vue-next'
import {
  DialogClose, DialogContent, DialogDescription, DialogOverlay, DialogPortal,
  DialogRoot, DialogTitle, DialogTrigger,
} from 'reka-ui'

defineProps<{ title: string; description?: string; size?: 'wide' | 'gallery' | 'landscape' | 'editor' }>()
const open = defineModel<boolean>('open', { default: false })
</script>

<template>
  <DialogRoot v-model:open="open">
    <DialogTrigger v-if="$slots.trigger" as-child><slot name="trigger" /></DialogTrigger>
    <DialogPortal>
      <DialogOverlay class="ui-dialog-overlay" :class="{ 'ui-dialog-overlay--gallery': size === 'gallery' }" />
      <DialogContent class="ui-dialog" :class="size && `ui-dialog--${size}`" v-bind="description ? {} : { 'aria-describedby': undefined }">
        <header class="ui-dialog-header">
          <DialogTitle class="ui-dialog-title">{{ title }}</DialogTitle>
          <DialogDescription v-if="description" class="ui-dialog-description">{{ description }}</DialogDescription>
          <DialogClose class="ui-icon-button ui-dialog-close" aria-label="关闭弹窗"><X :size="17" /></DialogClose>
        </header>
        <div class="ui-dialog-body"><slot /></div>
        <footer v-if="$slots.footer" class="ui-dialog-footer"><slot name="footer" /></footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
