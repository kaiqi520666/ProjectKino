<script setup lang="ts">
import { computed, useId } from 'vue'

defineOptions({ inheritAttrs: false })
const props = withDefaults(
  defineProps<{ label?: string; hint?: string; error?: string; id?: string; required?: boolean }>(),
  {},
)
const model = defineModel<string>({ default: '' })
const generatedId = useId()
const fieldId = computed(() => props.id || generatedId)
const messageId = computed(() => (props.error || props.hint ? `${fieldId.value}-message` : undefined))
</script>

<template>
  <div class="ui-field">
    <label v-if="label" :for="fieldId" class="ui-label">
      {{ label }}<span v-if="required" class="ui-required" aria-hidden="true">*</span>
    </label>
    <div class="ui-input-wrap" :class="{ 'has-error': error, 'has-leading': $slots.leading, 'has-trailing': $slots.trailing }">
      <span v-if="$slots.leading" class="ui-input-icon" aria-hidden="true"><slot name="leading" /></span>
      <input
        :id="fieldId"
        v-model="model"
        class="ui-input"
        :required="required"
        :aria-invalid="error ? true : undefined"
        :aria-describedby="messageId"
        v-bind="$attrs"
      />
      <span v-if="$slots.trailing" class="ui-input-trailing"><slot name="trailing" /></span>
    </div>
    <p v-if="error || hint" :id="messageId" class="ui-field-message" :class="{ 'is-error': error }" :role="error ? 'alert' : undefined">
      {{ error || hint }}
    </p>
  </div>
</template>
