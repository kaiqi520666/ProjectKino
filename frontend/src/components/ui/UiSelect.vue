<script setup lang="ts">
import { useId } from 'vue'
import { Check, ChevronDown } from 'lucide-vue-next'
import {
  SelectContent, SelectItem, SelectItemIndicator, SelectItemText, SelectPortal,
  SelectRoot, SelectTrigger, SelectValue, SelectViewport,
} from 'reka-ui'

withDefaults(
  defineProps<{
    label?: string
    placeholder?: string
    options: readonly { value: string; label: string; disabled?: boolean }[]
    size?: 'sm' | 'md'
    disabled?: boolean
    required?: boolean
  }>(),
  { size: 'md' },
)
const model = defineModel<string>()
const id = useId()
</script>

<template>
  <div class="ui-field">
    <label v-if="label" :for="id" class="ui-label">{{ label }}<span v-if="required" class="ui-required" aria-hidden="true">*</span></label>
    <SelectRoot v-model="model" :disabled="disabled" :required="required">
      <SelectTrigger
        :id="id"
        class="ui-select-trigger"
        :class="size === 'sm' ? 'ui-select-trigger--sm' : undefined"
        :aria-label="label || placeholder"
      >
        <SelectValue :placeholder="placeholder || '请选择'" />
        <ChevronDown :size="size === 'sm' ? 14 : 15" aria-hidden="true" />
      </SelectTrigger>
      <SelectPortal>
        <SelectContent class="ui-popover ui-select-content" position="popper" :side-offset="6" :collision-padding="12">
          <SelectViewport class="ui-popover-list">
            <SelectItem v-for="option in options" :key="option.value" :value="option.value" :disabled="option.disabled" class="ui-select-item">
              <SelectItemText>{{ option.label }}</SelectItemText>
              <SelectItemIndicator><Check :size="14" /></SelectItemIndicator>
            </SelectItem>
          </SelectViewport>
        </SelectContent>
      </SelectPortal>
    </SelectRoot>
  </div>
</template>
