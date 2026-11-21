<script setup lang="ts">
import { useId } from 'vue'
import { SwitchRoot, SwitchThumb } from 'reka-ui'

defineProps<{ label: string; description?: string; disabled?: boolean }>()
const model = defineModel<boolean>({ default: false })
const id = useId()
</script>

<template>
  <div class="ui-switch-field">
    <label :for="id">
      <span>{{ label }}</span>
      <small v-if="description">{{ description }}</small>
    </label>
    <SwitchRoot :id="id" v-model="model" class="ui-switch" :disabled="disabled" :aria-describedby="description ? `${id}-description` : undefined">
      <SwitchThumb class="ui-switch-thumb" />
    </SwitchRoot>
    <span v-if="description" :id="`${id}-description`" class="sr-only">{{ description }}</span>
  </div>
</template>
