<script setup lang="ts">
import { DropdownMenuContent, DropdownMenuItem, DropdownMenuPortal, DropdownMenuRoot, DropdownMenuSeparator, DropdownMenuTrigger } from 'reka-ui'

defineProps<{ items: readonly { value: string; label: string; disabled?: boolean; danger?: boolean; separator?: boolean }[] }>()
defineEmits<{ select: [value: string] }>()
</script>

<template>
  <DropdownMenuRoot>
    <DropdownMenuTrigger as-child><slot /></DropdownMenuTrigger>
    <DropdownMenuPortal>
      <DropdownMenuContent class="ui-popover ui-dropdown" align="end" :side-offset="6" :collision-padding="12">
        <template v-for="item in items" :key="item.value">
          <DropdownMenuSeparator v-if="item.separator" class="ui-menu-separator" />
          <DropdownMenuItem :disabled="item.disabled" class="ui-menu-item" :class="{ 'is-danger': item.danger }" @select="$emit('select', item.value)">
            {{ item.label }}
          </DropdownMenuItem>
        </template>
      </DropdownMenuContent>
    </DropdownMenuPortal>
  </DropdownMenuRoot>
</template>
