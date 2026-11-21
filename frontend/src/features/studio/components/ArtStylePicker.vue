<script setup lang="ts">
import { computed, ref } from 'vue'
import { Check, Palette } from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import ArtStyleGrid from './ArtStyleGrid.vue'
import { artStyles, quickArtStyles } from './art-styles'

const selected = defineModel<string>({ required: true })
const open = ref(false)
const pending = ref(selected.value)
const quickStyles = computed(() => {
  if (quickArtStyles.some((style) => style.value === selected.value)) return quickArtStyles
  const current = artStyles.find((style) => style.value === selected.value)
  return current ? [current, ...quickArtStyles.slice(0, 2)] : quickArtStyles
})
function updateOpen(value: boolean) {
  if (value) pending.value = selected.value
  open.value = value
}

function confirm() {
  selected.value = pending.value
  open.value = false
}
</script>

<template>
  <fieldset class="art-style-picker">
    <legend class="ui-label">画风<span class="ui-required" aria-hidden="true">*</span></legend>
    <ArtStyleGrid v-model="selected" :styles="quickStyles" compact>
      <UiDialog :open="open" title="选择画风" size="gallery" @update:open="updateOpen">
        <template #trigger>
          <button type="button" class="more-art-styles">
            <Palette :size="19" aria-hidden="true" />
            <span>更多画风</span>
          </button>
        </template>

        <ArtStyleGrid v-model="pending" :styles="artStyles" />

        <template #footer>
          <UiButton variant="ghost" @click="open = false">取消</UiButton>
          <UiButton variant="primary" @click="confirm"><template #leading><Check :size="16" aria-hidden="true" /></template>确定</UiButton>
        </template>
      </UiDialog>
    </ArtStyleGrid>
  </fieldset>
</template>

<style scoped>
.art-style-picker { min-width: 0; margin: 0; padding: 0; }
.art-style-picker > legend { margin-bottom: 8px; padding: 0; }
.more-art-styles { display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 5px; width: 100%; aspect-ratio: 16 / 9; padding: 6px; border: 1px dashed var(--border-control); border-radius: 8px; background: var(--color-surface); color: var(--color-muted); font-size: var(--font-size-caption); }
.more-art-styles:hover, .more-art-styles[data-state="open"] { border-color: var(--color-gold); color: var(--color-gold-soft); }
</style>
