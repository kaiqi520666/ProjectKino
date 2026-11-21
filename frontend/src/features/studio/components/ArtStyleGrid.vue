<script setup lang="ts">
import { useId } from 'vue'
import { Check } from 'lucide-vue-next'
import type { ArtStyle } from './art-styles'

defineProps<{ styles: readonly ArtStyle[]; compact?: boolean }>()
const selected = defineModel<string>({ required: true })
const name = useId()
</script>

<template>
  <div class="art-style-grid" :class="{ 'art-style-grid--compact': compact }" role="group" aria-label="画风选项">
    <label v-for="style in styles" :key="style.value" class="art-style-card">
      <input v-model="selected" class="sr-only" type="radio" :name="name" :value="style.value" />
      <span class="art-style-tile">
        <img :src="`/images/art-styles/${style.value}.webp`" alt="" :loading="compact ? 'eager' : 'lazy'" decoding="async" />
        <span class="art-style-name">{{ style.label }}</span>
        <Check v-if="selected === style.value" class="art-style-check" :size="18" aria-hidden="true" />
      </span>
    </label>
    <slot />
  </div>
</template>

<style scoped>
.art-style-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(168px, 1fr)); gap: 12px; }
.art-style-grid--compact { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.art-style-card { position: relative; display: block; min-width: 0; cursor: pointer; }
.art-style-card input { top: 50%; left: 50%; }
.art-style-tile { position: relative; isolation: isolate; display: flex; align-items: flex-end; aspect-ratio: 16 / 9; overflow: hidden; padding: 6px; border: 1px solid var(--border-control); border-radius: 8px; background: var(--color-surface); }
.art-style-tile img { position: absolute; z-index: -1; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.art-style-name { max-width: 100%; padding: 2px 6px; border-radius: 4px; background: rgb(0 0 0 / 82%); color: #fff; font-size: var(--font-size-caption); line-height: 1.35; overflow-wrap: anywhere; }
.art-style-card:hover .art-style-tile { border-color: var(--color-muted); }
.art-style-card input:checked + .art-style-tile { border-color: var(--color-gold); }
.art-style-card input:focus-visible + .art-style-tile { outline: 2px solid var(--color-gold); outline-offset: 2px; }
.art-style-check { position: absolute; top: 6px; right: 6px; padding: 3px; border-radius: 50%; background: var(--color-gold); color: var(--color-ink); }
@media (max-width: 540px) {
  .art-style-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
}
</style>
