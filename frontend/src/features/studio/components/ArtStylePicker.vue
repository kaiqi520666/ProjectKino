<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Check, Palette } from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import { useArtStylesStore } from '@/features/art-styles/art-styles-store'
import ArtStyleGrid from './ArtStyleGrid.vue'
import { toArtStyleOption } from './art-styles'

const selected = defineModel<string>({ required: true })
const artStylesStore = useArtStylesStore()
const open = ref(false)
const pending = ref(selected.value)

const allOptions = computed(() => artStylesStore.enabledStyles.map(toArtStyleOption))
const quickOptions = computed(() => {
  const baseQuick = artStylesStore.quickStyles.map(toArtStyleOption)
  if (!selected.value || baseQuick.some((style) => style.value === selected.value)) {
    return baseQuick
  }
  const current = artStylesStore.getByCode(selected.value)
  if (current) {
    return [toArtStyleOption(current), ...baseQuick.slice(0, 2)]
  }
  return baseQuick
})

watch(
  () => [artStylesStore.loaded, artStylesStore.defaultCode] as const,
  ([loaded, defaultCode]) => {
    if (!loaded) return
    if (!selected.value || !artStylesStore.getByCode(selected.value)) {
      selected.value = defaultCode
    }
  },
  { immediate: true },
)

onMounted(() => {
  void artStylesStore.ensureLoaded()
})

function updateOpen(value: boolean) {
  if (value) {
    void artStylesStore.ensureLoaded()
    pending.value = selected.value || artStylesStore.defaultCode
  }
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
    <ArtStyleGrid v-model="selected" :styles="quickOptions" compact>
      <UiDialog :open="open" title="选择画风" size="gallery" @update:open="updateOpen">
        <template #trigger>
          <button type="button" class="more-art-styles">
            <Palette :size="19" aria-hidden="true" />
            <span>更多画风</span>
          </button>
        </template>

        <ArtStyleGrid v-model="pending" :styles="allOptions" />

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
