<script setup lang="ts">
import { computed, useId } from 'vue'
import TaskStatusBadge from './TaskStatus.vue'
import type { TaskStatus } from './task-types'

const props = defineProps<{ title: string; status: TaskStatus; progress?: number; description?: string }>()
const id = useId()
const progress = computed(() => props.progress === undefined || !Number.isFinite(props.progress)
  ? undefined
  : Math.min(100, Math.max(0, props.progress)))
</script>

<template>
  <div class="task-progress">
    <div class="task-progress-heading">
      <strong :id="id">{{ title }}</strong>
      <TaskStatusBadge :status="status" />
    </div>
    <div
      class="task-progress-track"
      :class="{ 'is-indeterminate': progress === undefined && status === 'running' }"
      role="progressbar"
      :aria-labelledby="id"
      :aria-valuenow="progress"
      :aria-valuemin="0"
      :aria-valuemax="100"
    >
      <span :style="{ width: progress === undefined ? (status === 'running' ? '30%' : '0%') : `${progress}%` }" />
    </div>
    <div class="task-progress-bottom">
      <span>{{ description }}</span>
      <span v-if="progress !== undefined">{{ Math.round(progress) }}%</span>
    </div>
    <div v-if="$slots.actions" class="task-progress-actions"><slot name="actions" /></div>
  </div>
</template>
