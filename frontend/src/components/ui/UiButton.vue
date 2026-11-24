<script setup lang="ts">
import { computed } from 'vue'
import { LoaderCircle } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger'
    size?: 'xs' | 'sm' | 'md' | 'lg'
    type?: 'button' | 'submit' | 'reset'
    href?: string
    target?: string
    rel?: string
    disabled?: boolean
    loading?: boolean
  }>(),
  { variant: 'secondary', size: 'md', type: 'button' },
)

const spinnerSize = computed(() => (props.size === 'xs' ? 13 : props.size === 'sm' ? 14 : 16))
const resolvedRel = computed(() => props.rel || (props.target === '_blank' ? 'noopener noreferrer' : undefined))
</script>

<template>
  <a
    v-if="href"
    :href="href"
    :target="target"
    :rel="resolvedRel"
    class="ui-button"
    :class="[`ui-button--${variant}`, `ui-button--${size}`]"
    :aria-disabled="disabled || loading || undefined"
  >
    <LoaderCircle v-if="loading" class="ui-spin" :size="spinnerSize" aria-hidden="true" />
    <slot v-else name="leading" />
    <span v-if="$slots.default" class="ui-button__label"><slot /></span>
    <slot name="trailing" />
  </a>
  <button
    v-else
    :type="type"
    class="ui-button"
    :class="[`ui-button--${variant}`, `ui-button--${size}`]"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
  >
    <LoaderCircle v-if="loading" class="ui-spin" :size="spinnerSize" aria-hidden="true" />
    <slot v-else name="leading" />
    <span v-if="$slots.default" class="ui-button__label"><slot /></span>
    <slot name="trailing" />
  </button>
</template>
