<script setup lang="ts">
import { useId } from 'vue'
import { Check } from 'lucide-vue-next'
import { CheckboxIndicator, CheckboxRoot } from 'reka-ui'

defineProps<{ label: string; disabled?: boolean }>()
const model = defineModel<boolean>({ default: false })
const id = useId()
</script>

<template>
  <div class="ui-check-field">
    <CheckboxRoot :id="id" v-model="model" class="ui-checkbox" :disabled="disabled">
      <CheckboxIndicator><Check :size="12" :stroke-width="3" aria-hidden="true" /></CheckboxIndicator>
    </CheckboxRoot>
    <label :for="id">{{ label }}</label>
  </div>
</template>
