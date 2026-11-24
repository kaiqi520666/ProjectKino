<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Film, Layers, Pencil, Trash2 } from 'lucide-vue-next'
import type { ProjectProgressState } from '../project-progress'

const props = withDefaults(defineProps<{
  id: string
  name: string
  coverUrl: string
  fallbackCoverUrl: string
  styleLabel: string
  ratio?: string
  episodeCount: number
  assetCount?: number
  updatedAt?: string
  progress: ProjectProgressState
  showEdit?: boolean
}>(), {
  ratio: '16:9',
  assetCount: 0,
  updatedAt: '',
  showEdit: false,
})

const emit = defineEmits<{
  edit: []
  delete: []
}>()

const coverFailed = ref(false)

watch(
  () => props.coverUrl,
  () => {
    coverFailed.value = false
  },
)

const activeCoverUrl = computed(() => (coverFailed.value ? props.fallbackCoverUrl : props.coverUrl))

const compactTime = computed(() => {
  if (!props.updatedAt) return ''
  const date = new Date(props.updatedAt)
  if (Number.isNaN(date.getTime())) return ''
  const now = new Date()
  const sameYear = date.getFullYear() === now.getFullYear()
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  const dd = String(date.getDate()).padStart(2, '0')
  const hh = String(date.getHours()).padStart(2, '0')
  const mi = String(date.getMinutes()).padStart(2, '0')
  return sameYear ? `${mm}-${dd} ${hh}:${mi}` : `${date.getFullYear()}-${mm}-${dd}`
})
</script>

<template>
  <li class="kino-card-item">
    <RouterLink
      class="kino-card"
      :to="{ name: progress.targetRoute, params: { projectId: id } }"
    >
      <div class="kino-card-cover">
        <img
          :src="activeCoverUrl"
          alt=""
          loading="lazy"
          @error="coverFailed = true"
        />
        <div class="kino-card-top-badges">
          <span class="kino-glass-chip">{{ styleLabel }}</span>
          <span v-if="ratio" class="kino-glass-chip is-mono">{{ ratio }}</span>
        </div>

        <div class="kino-card-bottom-bar">
          <span class="kino-stage-badge" :class="`is-${progress.tone}`">
            <span class="kino-stage-dot" aria-hidden="true"></span>
            {{ progress.label }}
          </span>
        </div>

        <span class="kino-progress-track" aria-hidden="true">
          <span
            class="kino-progress-fill"
            :class="`is-${progress.tone}`"
            :style="{ width: `${progress.percent}%` }"
          ></span>
        </span>
      </div>

      <div class="kino-card-body">
        <h3 class="kino-card-title" :title="name">{{ name }}</h3>
        <div class="kino-card-meta">
          <div class="kino-card-stats">
            <span><Film :size="12" aria-hidden="true" />{{ episodeCount }} 集</span>
            <span v-if="assetCount > 0"><Layers :size="12" aria-hidden="true" />{{ assetCount }} 资产</span>
          </div>
          <span v-if="compactTime" class="kino-card-time">{{ compactTime }}</span>
        </div>
      </div>
    </RouterLink>

    <div class="kino-card-actions">
      <button
        v-if="showEdit"
        type="button"
        class="kino-card-action"
        :aria-label="`编辑项目 ${name}`"
        title="编辑名称与封面"
        @click.stop.prevent="emit('edit')"
      >
        <Pencil :size="13" aria-hidden="true" />
      </button>
      <button
        type="button"
        class="kino-card-action is-danger"
        :aria-label="`删除项目 ${name}`"
        title="删除"
        @click.stop.prevent="emit('delete')"
      >
        <Trash2 :size="13" aria-hidden="true" />
      </button>
    </div>
  </li>
</template>

<style scoped>
.kino-card-item {
  position: relative;
  min-width: 0;
}

.kino-card {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 12px;
  background: linear-gradient(180deg, rgb(255 255 255 / 2.5%) 0%, var(--color-surface) 100%);
  color: inherit;
  text-decoration: none;
  box-shadow: 0 4px 16px rgb(0 0 0 / 24%);
  transition: transform 0.22s cubic-bezier(0.22, 1, 0.36, 1), border-color 0.22s ease, box-shadow 0.22s ease;
}

.kino-card:hover {
  transform: translateY(-3px);
  border-color: rgb(240 184 75 / 44%);
  box-shadow: 0 12px 28px rgb(0 0 0 / 42%), 0 0 0 1px rgb(240 184 75 / 12%);
}

.kino-card-cover {
  position: relative;
  overflow: hidden;
  aspect-ratio: 16 / 9;
  background: var(--color-elevated);
}

.kino-card-cover::after {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(180deg, rgb(6 7 10 / 42%) 0%, transparent 34%, rgb(6 7 10 / 82%) 100%);
  content: '';
  pointer-events: none;
}

.kino-card-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 0.42s cubic-bezier(0.22, 1, 0.36, 1);
}

.kino-card:hover .kino-card-cover img {
  transform: scale(1.045);
}

.kino-card-top-badges {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.kino-glass-chip {
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid rgb(255 255 255 / 14%);
  background: rgb(9 10 14 / 62%);
  backdrop-filter: blur(8px);
  color: #e7e4de;
  font-size: 11px;
  line-height: 1.4;
}

.kino-glass-chip.is-mono {
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
  color: rgb(231 228 222 / 82%);
}

.kino-card-bottom-bar {
  position: absolute;
  left: 10px;
  right: 10px;
  bottom: 10px;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.kino-stage-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid rgb(255 255 255 / 14%);
  background: rgb(9 10 14 / 76%);
  backdrop-filter: blur(8px);
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
}

.kino-stage-dot {
  width: 5px;
  height: 5px;
  border-radius: 999px;
  background: currentColor;
}

.kino-stage-badge.is-ready {
  border-color: rgb(240 184 75 / 38%);
  color: var(--color-gold-soft);
}

.kino-stage-badge.is-progress {
  border-color: rgb(96 165 250 / 42%);
  color: #93c5fd;
}

.kino-stage-badge.is-done {
  border-color: rgb(74 222 128 / 42%);
  color: #4ade80;
}

.kino-progress-track {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 3;
  height: 2.5px;
  background: rgb(255 255 255 / 10%);
}

.kino-progress-fill {
  display: block;
  height: 100%;
  background: var(--color-muted);
  transition: width 0.3s ease;
}

.kino-progress-fill.is-ready {
  background: linear-gradient(90deg, #d89b2b, var(--color-gold-soft));
}

.kino-progress-fill.is-progress {
  background: linear-gradient(90deg, #3b82f6, #93c5fd);
}

.kino-progress-fill.is-done {
  background: linear-gradient(90deg, #22c55e, #4ade80);
}

.kino-card-body {
  display: flex;
  flex-direction: column;
  gap: 9px;
  padding: 13px 14px 14px;
}

.kino-card-title {
  margin: 0;
  color: var(--color-text);
  font-size: 14.5px;
  font-weight: 600;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: color 0.16s ease;
}

.kino-card:hover .kino-card-title {
  color: var(--color-gold-soft);
}

.kino-card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
  color: var(--color-muted);
}

.kino-card-stats {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.kino-card-stats span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.kino-card-time {
  font-size: 11.5px;
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
  font-variant-numeric: tabular-nums;
  opacity: 0.8;
  white-space: nowrap;
}

.kino-card-actions {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 4;
  display: inline-flex;
  gap: 6px;
  opacity: 0;
  transform: translateY(-2px);
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.kino-card-item:hover .kino-card-actions,
.kino-card-item:focus-within .kino-card-actions {
  opacity: 1;
  transform: translateY(0);
}

.kino-card-action {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 1px solid rgb(255 255 255 / 16%);
  border-radius: 7px;
  background: rgb(9 10 14 / 76%);
  color: #e7e4de;
  cursor: pointer;
  backdrop-filter: blur(8px);
  transition: color 0.15s ease, border-color 0.15s ease, background-color 0.15s ease;
}

.kino-card-action:hover {
  color: var(--color-gold-soft);
  border-color: rgb(240 184 75 / 50%);
  background: rgb(9 10 14 / 92%);
}

.kino-card-action.is-danger:hover {
  color: var(--color-error);
  border-color: rgb(248 113 113 / 50%);
}

@media (max-width: 640px) {
  .kino-card-actions {
    opacity: 1;
    transform: none;
  }
}
</style>
