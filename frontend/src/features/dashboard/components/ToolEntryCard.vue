<script setup lang="ts">
import type { Component } from 'vue'
import { ArrowUpRight } from 'lucide-vue-next'

defineProps<{
  title: string
  description?: string
  icon: Component
  imageUrl?: string
  imageAlt?: string
  disabled?: boolean
}>()
defineEmits<{ select: [] }>()
</script>

<template>
  <button type="button" class="tool-entry-card" :disabled="disabled" @click="$emit('select')">
    <component :is="icon" :size="22" :stroke-width="1.5" class="tool-entry-icon" aria-hidden="true" />
    <strong>{{ title }}</strong>
    <span v-if="description" class="tool-entry-description">{{ description }}</span>
    <ArrowUpRight :size="17" class="tool-entry-arrow" aria-hidden="true" />
    <img v-if="imageUrl" :src="imageUrl" :alt="imageAlt || ''" loading="lazy" decoding="async" />
  </button>
</template>

<style scoped>
.tool-entry-card { position: relative; display: flex; flex-direction: column; align-items: flex-start; min-width: 0; min-height: 184px; overflow: hidden; padding: 22px; border: 1px solid var(--border-subtle); border-radius: 8px; background: #151519; color: #eeeeef; text-align: left; transition: border-color .15s, background .15s; isolation: isolate; }
.tool-entry-card:hover:not(:disabled) { background: #1a1a1f; border-color: rgb(240 184 75 / 28%); }
.tool-entry-icon { margin-bottom: 12px; color: var(--color-gold-soft); }
.tool-entry-card strong { position: relative; z-index: 1; font-size: 17px; font-weight: 500; }
.tool-entry-description { position: relative; z-index: 1; max-width: 60%; margin-top: 5px; color: #92929c; font-size: 12px; }
.tool-entry-arrow { position: absolute; top: 22px; right: 20px; color: #8c8b93; }
.tool-entry-card img { position: absolute; z-index: -1; right: -18px; bottom: -28px; width: 54%; height: 104px; object-fit: cover; border-radius: 4px; transform: rotate(-10deg); opacity: .8; transition: transform .2s; }
.tool-entry-card:hover img { transform: translateY(-4px) rotate(-7deg); }
.tool-entry-card:disabled { opacity: .45; }
@media (max-width: 560px) { .tool-entry-card { min-height: 155px; padding: 18px; } .tool-entry-arrow { top: 18px; right: 14px; } .tool-entry-description { max-width: 100%; } .tool-entry-card img { width: 55%; height: 74px; opacity: .55; } }
</style>
