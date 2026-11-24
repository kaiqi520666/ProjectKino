<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { DialogClose, DialogContent, DialogOverlay, DialogPortal, DialogRoot, DialogTitle, DialogTrigger } from 'reka-ui'

defineProps<{ title: string }>()
const open = defineModel<boolean>('open', { default: false })
defineEmits<{ keydown: [event: KeyboardEvent] }>()
let opener: HTMLElement | null = null

function rememberFocus(event: Event) {
  const target = document.activeElement
  opener = target instanceof HTMLElement && target !== document.body ? target : null
  if (event.target instanceof HTMLElement) {
    event.preventDefault()
    event.target.focus({ preventScroll: true })
  }
}

function restoreFocus(event: Event) {
  if (opener?.isConnected) {
    event.preventDefault()
    opener.focus({ preventScroll: true })
  }
  opener = null
}

function handleEscape(event: KeyboardEvent) {
  if (document.fullscreenElement?.closest('.media-preview-dialog')) event.preventDefault()
}

function handleBackdropClick(event: MouseEvent) {
  if (document.fullscreenElement?.closest('.media-preview-dialog')) return
  const target = event.target
  if (!(target instanceof HTMLElement)) return
  if (
    target.classList.contains('media-preview-dialog')
    || target.classList.contains('media-preview-header')
    || target.classList.contains('media-preview-content')
    || target.classList.contains('media-preview-footer')
  ) {
    open.value = false
  }
}
</script>

<template>
  <DialogRoot v-model:open="open">
    <DialogTrigger v-if="$slots.trigger" as-child><slot name="trigger" /></DialogTrigger>
    <DialogPortal>
      <DialogOverlay class="media-preview-overlay" />
      <DialogContent
        class="media-preview-dialog"
        tabindex="-1"
        :aria-describedby="undefined"
        @open-auto-focus="rememberFocus"
        @close-auto-focus="restoreFocus"
        @escape-key-down="handleEscape"
        @click="handleBackdropClick"
        @keydown="$emit('keydown', $event)"
      >
        <header class="media-preview-header">
          <DialogTitle class="media-preview-title" :title="title">{{ title }}</DialogTitle>
          <div class="media-preview-header-actions">
            <slot name="header-actions" />
            <DialogClose class="ui-icon-button media-preview-close" aria-label="关闭预览" title="关闭预览">
              <X :size="21" aria-hidden="true" />
            </DialogClose>
          </div>
        </header>
        <div class="media-preview-content"><slot /></div>
        <footer v-if="$slots.toolbar" class="media-preview-footer"><slot name="toolbar" /></footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.media-preview-overlay { position: fixed; inset: 0; z-index: 140; background: rgb(5 6 8 / 97%); }
.media-preview-dialog {
  position: fixed;
  inset: 0;
  z-index: 141;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  padding: max(12px, env(safe-area-inset-top)) max(20px, env(safe-area-inset-right))
    max(16px, env(safe-area-inset-bottom)) max(20px, env(safe-area-inset-left));
  color: var(--color-text);
  outline: none;
}
.media-preview-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-bottom: 8px; }
.media-preview-header-actions { display: inline-flex; flex-shrink: 0; align-items: center; gap: 8px; }
.media-preview-title {
  overflow: hidden;
  margin: 0;
  color: var(--color-muted);
  font-size: var(--font-size-body);
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.media-preview-close { width: 40px; height: 40px; color: var(--color-text); background: var(--color-elevated); border-color: var(--border-control); }
.media-preview-content { position: relative; min-width: 0; min-height: 0; }
.media-preview-footer { display: flex; justify-content: center; padding-top: 12px; }
@media (max-width: 560px) {
  .media-preview-dialog { padding-inline: max(10px, env(safe-area-inset-left)) max(10px, env(safe-area-inset-right)); }
}
</style>
