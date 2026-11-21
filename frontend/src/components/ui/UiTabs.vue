<script setup lang="ts">
import { TabsContent, TabsList, TabsRoot, TabsTrigger } from 'reka-ui'

withDefaults(defineProps<{
  label: string
  tabs: readonly { value: string; label: string; count?: number; disabled?: boolean }[]
  variant?: 'line' | 'segment'
}>(), { variant: 'line' })
const model = defineModel<string>({ required: true })
</script>

<template>
  <TabsRoot v-model="model" class="ui-tabs" :class="`ui-tabs--${variant}`">
    <TabsList class="ui-tabs-list" :aria-label="label">
      <TabsTrigger v-for="tab in tabs" :key="tab.value" :value="tab.value" :disabled="tab.disabled" class="ui-tab">
        {{ tab.label }}<span v-if="tab.count !== undefined" class="ui-tab-count">{{ tab.count }}</span>
      </TabsTrigger>
    </TabsList>
    <TabsContent v-for="tab in tabs" :key="tab.value" :value="tab.value" class="ui-tab-panel">
      <slot :name="tab.value" />
    </TabsContent>
  </TabsRoot>
</template>
