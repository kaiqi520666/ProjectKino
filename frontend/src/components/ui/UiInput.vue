<script setup lang="ts">
import { computed, useAttrs, useId, useSlots } from 'vue'
import { X } from 'lucide-vue-next'

defineOptions({ inheritAttrs: false })
const props = withDefaults(
  defineProps<{
    label?: string
    hint?: string
    error?: string
    id?: string
    size?: 'sm' | 'md'
    clearable?: boolean
    required?: boolean
  }>(),
  { size: 'md', clearable: false },
)
const emit = defineEmits<{ clear: [] }>()
const model = defineModel<string>({ default: '' })
const attrs = useAttrs()
const slots = useSlots()
const generatedId = useId()
const fieldId = computed(() => props.id || generatedId)
const messageId = computed(() => (props.error || props.hint ? `${fieldId.value}-message` : undefined))
const showClear = computed(() => props.clearable && Boolean(model.value) && !attrs.disabled)
const hasTrailing = computed(() => Boolean(slots.trailing) || showClear.value)

function handleClear() {
  model.value = ''
  emit('clear')
}
</script>

<template>
  <div class="ui-field">
    <label v-if="label" :for="fieldId" class="ui-label">
      {{ label }}<span v-if="required" class="ui-required" aria-hidden="true">*</span>
    </label>
    <div
      class="ui-input-wrap"
      :class="{
        'ui-input-wrap--sm': size === 'sm',
        'has-error': error,
        'has-leading': Boolean($slots.leading),
        'has-trailing': hasTrailing,
      }"
    >
      <span v-if="$slots.leading" class="ui-input-icon" aria-hidden="true"><slot name="leading" /></span>
      <input
        :id="fieldId"
        v-model="model"
        class="ui-input"
        :class="size === 'sm' ? 'ui-input--sm' : undefined"
        :required="required"
        :aria-invalid="error ? true : undefined"
        :aria-describedby="messageId"
        v-bind="$attrs"
      />
      <span v-if="hasTrailing" class="ui-input-trailing">
        <button
          v-if="showClear"
          type="button"
          class="ui-input-clear"
          aria-label="清空"
          @click="handleClear"
        >
          <X :size="12" aria-hidden="true" />
        </button>
        <slot name="trailing" />
      </span>
    </div>
    <p v-if="error || hint" :id="messageId" class="ui-field-message" :class="{ 'is-error': error }" :role="error ? 'alert' : undefined">
      {{ error || hint }}
    </p>
  </div>
</template>
