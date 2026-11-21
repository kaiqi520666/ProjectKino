<script setup lang="ts">
import { computed, useId } from 'vue'

defineOptions({ inheritAttrs: false })
const props = withDefaults(
  defineProps<{ label?: string; hint?: string; error?: string; maxlength?: number; rows?: number; id?: string; required?: boolean }>(),
  { rows: 4 },
)
const model = defineModel<string>({ default: '' })
const generatedId = useId()
const fieldId = computed(() => props.id || generatedId)
</script>

<template>
  <div class="ui-field">
    <label v-if="label" :for="fieldId" class="ui-label">
      {{ label }}<span v-if="required" class="ui-required" aria-hidden="true">*</span>
    </label>
    <textarea
      :id="fieldId"
      v-model="model"
      class="ui-textarea"
      :class="{ 'has-error': error }"
      :rows="rows"
      :maxlength="maxlength"
      :required="required"
      :aria-invalid="error ? true : undefined"
      :aria-describedby="error || hint ? `${fieldId}-message` : undefined"
      v-bind="$attrs"
    />
    <div v-if="error || hint || maxlength" class="ui-field-bottom">
      <p :id="`${fieldId}-message`" class="ui-field-message" :class="{ 'is-error': error }" :role="error ? 'alert' : undefined">{{ error || hint }}</p>
      <span v-if="maxlength" class="ui-counter">{{ model.length }} / {{ maxlength }}</span>
    </div>
  </div>
</template>
