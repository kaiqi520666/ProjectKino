<script setup lang="ts">
import { Ban, CircleCheck, CircleX, Clock3, LoaderCircle } from 'lucide-vue-next'
import type { TaskStatus } from './task-types'

defineProps<{ status: TaskStatus }>()
const labels = { pending: '排队中', running: '生成中', succeeded: '已完成', failed: '生成失败', canceled: '已取消' }
const icons = { pending: Clock3, running: LoaderCircle, succeeded: CircleCheck, failed: CircleX, canceled: Ban }
</script>

<template>
  <span class="task-status" :class="`task-status--${status}`">
    <component :is="icons[status]" :size="12" :class="{ 'ui-spin': status === 'running' }" aria-hidden="true" />
    {{ labels[status] }}
  </span>
</template>
