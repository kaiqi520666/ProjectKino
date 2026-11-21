<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import UiIconButton from '@/components/ui/UiIconButton.vue'
import { episodePage, episodePageSize } from '../studio-project'

const props = defineProps<{ total: number; active?: number; disabled?: boolean; label?: string; layout?: 'grid' }>()
const page = ref(1)
const lastPage = computed(() => Math.max(1, Math.ceil(props.total / episodePageSize)))
const numbers = computed(() => episodePage(props.total, page.value))
watch(() => props.active, (number) => {
  if (number) page.value = Math.ceil(number / episodePageSize)
}, { immediate: true })
</script>

<template>
  <div class="studio-episode-list">
    <ul :aria-label="label || '分集列表'" :class="{ 'episode-grid': layout === 'grid' }">
      <li v-for="number in numbers" :key="number"><slot :number="number" /></li>
    </ul>
    <div v-if="lastPage > 1" class="episode-pagination" aria-label="分集分页" role="group">
      <UiIconButton label="上一页" :disabled="disabled || page <= 1" @click="page--"><ChevronLeft :size="16" /></UiIconButton>
      <span>{{ numbers[0] }}–{{ numbers[numbers.length - 1] }}</span>
      <UiIconButton label="下一页" :disabled="disabled || page >= lastPage" @click="page++"><ChevronRight :size="16" /></UiIconButton>
    </div>
  </div>
</template>

<style scoped>
.studio-episode-list ul { margin: 0; padding: 0; list-style: none; }
.studio-episode-list ul:not(.episode-grid) li + li { border-top: 1px solid var(--border-subtle); }
.episode-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; }
@media (min-width: 761px) {
  .episode-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
.episode-pagination { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding-top: 8px; color: var(--color-muted); font-size: 12px; overflow-wrap: anywhere; }
</style>
