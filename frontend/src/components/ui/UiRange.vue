<script setup lang="ts">
import { useId } from 'vue'

withDefaults(defineProps<{ label: string; min?: number; max?: number; step?: number; unit?: string; disabled?: boolean }>(), {
  min: 0, max: 100, step: 1, unit: '',
})
const model = defineModel<number>({ default: 0 })
const id = useId()
</script>

<template>
  <div class="ui-field">
    <div class="ui-range-heading">
      <label :for="id" class="ui-label">{{ label }}</label>
      <output :for="id">{{ model }}{{ unit }}</output>
    </div>
    <input :id="id" v-model.number="model" type="range" class="ui-range" :min="min" :max="max" :step="step" :disabled="disabled" />
  </div>
</template>
