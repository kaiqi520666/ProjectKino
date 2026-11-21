<script setup lang="ts">
import { TooltipContent, TooltipPortal, TooltipRoot, TooltipTrigger } from 'reka-ui'

defineOptions({ inheritAttrs: false })
withDefaults(defineProps<{ label: string; disabled?: boolean; active?: boolean }>(), { active: undefined })
defineEmits<{ click: [event: MouseEvent] }>()
</script>

<template>
  <TooltipRoot>
    <TooltipTrigger as-child>
      <button
        v-bind="$attrs"
        type="button"
        class="ui-icon-button"
        :class="{ 'is-active': active }"
        :aria-label="label"
        :aria-pressed="active"
        :disabled="disabled"
        @click="$emit('click', $event)"
      >
        <slot />
      </button>
    </TooltipTrigger>
    <TooltipPortal>
      <TooltipContent class="ui-tooltip" :side-offset="8">{{ label }}</TooltipContent>
    </TooltipPortal>
  </TooltipRoot>
</template>
