<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { AlertTriangle, Check, CheckCircle2, Clock3, Copy, RotateCcw, Sparkles, X } from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import { formatElapsedSeconds, useGenerationStore } from '@/stores/generation'

const generation = useGenerationStore()
const task = computed(() => generation.task)
const now = ref(Date.now())
const copied = ref(false)

let tickTimer: ReturnType<typeof setInterval> | null = null
let copyTimer: ReturnType<typeof setTimeout> | null = null

const elapsed = computed(() => {
  const current = task.value
  if (!current) return '00:00'
  const end = current.finishedAt ?? now.value
  return formatElapsedSeconds((end - current.startedAt) / 1000)
})

const progressWidth = computed(() => {
  const current = task.value
  if (!current) return '0%'
  if (current.progress !== undefined) return `${Math.round(current.progress)}%`
  return current.status === 'running' ? '36%' : '0%'
})

const isIndeterminate = computed(() => (
  task.value?.status === 'running' && task.value.progress === undefined
))

function stopTick() {
  if (tickTimer !== null) {
    clearInterval(tickTimer)
    tickTimer = null
  }
}

function clearCopyTimer() {
  if (copyTimer !== null) {
    clearTimeout(copyTimer)
    copyTimer = null
  }
}

function onKeydown(event: KeyboardEvent) {
  if (!task.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    if (task.value.status === 'error') generation.dismiss()
  }
}

function lockScroll(locked: boolean) {
  if (typeof document === 'undefined') return
  document.documentElement.classList.toggle('gen-scroll-locked', locked)
}

watch(
  () => task.value?.status,
  (status, prev) => {
    copied.value = false
    clearCopyTimer()

    if (status && !prev) {
      lockScroll(true)
      window.addEventListener('keydown', onKeydown, true)
    } else if (!status && prev) {
      lockScroll(false)
      window.removeEventListener('keydown', onKeydown, true)
    }

    if (status === 'running') {
      now.value = Date.now()
      stopTick()
      tickTimer = setInterval(() => {
        now.value = Date.now()
      }, 1000)
    } else {
      stopTick()
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  stopTick()
  clearCopyTimer()
  if (task.value) lockScroll(false)
  window.removeEventListener('keydown', onKeydown, true)
})

function stepState(index: number): 'done' | 'active' | 'pending' | 'overview' {
  const current = task.value
  if (!current) return 'overview'
  if (current.status === 'success') return 'done'
  if (current.activeStep < 0) return 'overview'
  if (index < current.activeStep) return 'done'
  if (index === current.activeStep) return 'active'
  return 'pending'
}

async function copyError() {
  const text = task.value?.error
  if (!text || typeof navigator === 'undefined' || !navigator.clipboard) return
  try {
    await navigator.clipboard.writeText(text)
    copied.value = true
    clearCopyTimer()
    copyTimer = setTimeout(() => {
      copied.value = false
      copyTimer = null
    }, 2000)
  } catch {
    copied.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="gen-overlay">
      <div
        v-if="task"
        class="gen-overlay"
        role="dialog"
        aria-modal="true"
        :aria-busy="task.status === 'running' ? 'true' : undefined"
        aria-labelledby="gen-overlay-title"
        aria-describedby="gen-overlay-desc"
      >
        <div class="gen-card" :class="`gen-card--${task.status}`">
          <div class="gen-card-glow" aria-hidden="true" />

          <div class="gen-head">
            <div class="gen-emblem" :class="`gen-emblem--${task.status}`" aria-hidden="true">
              <span v-if="task.status === 'running'" class="gen-ring" />
              <Sparkles v-if="task.status === 'running'" :size="22" :stroke-width="1.8" />
              <CheckCircle2 v-else-if="task.status === 'success'" :size="24" :stroke-width="1.8" />
              <AlertTriangle v-else :size="24" :stroke-width="1.8" />
            </div>

            <div class="gen-titles">
              <h2 id="gen-overlay-title">
                {{ task.status === 'error' ? '生成失败' : task.status === 'success' ? '生成完成' : task.title }}
              </h2>
              <p v-if="task.subtitle" class="gen-subtitle">{{ task.subtitle }}</p>
            </div>
          </div>

          <p id="gen-overlay-desc" class="gen-desc">
            <template v-if="task.status === 'error'">{{ task.title }}未能完成</template>
            <template v-else>{{ task.description || '正在处理中，请稍候…' }}</template>
          </p>

          <ol v-if="task.steps.length && task.status !== 'error'" class="gen-steps" aria-label="处理阶段">
            <li
              v-for="(label, index) in task.steps"
              :key="label"
              class="gen-step"
              :class="`is-${stepState(index)}`"
            >
              <span class="gen-step-dot" aria-hidden="true">
                <Check v-if="stepState(index) === 'done'" :size="12" :stroke-width="2.6" />
                <span v-else>{{ index + 1 }}</span>
              </span>
              <span class="gen-step-label">{{ label }}</span>
            </li>
          </ol>

          <template v-if="task.status === 'running'">
            <div
              class="gen-progress-track"
              :class="{ 'is-indeterminate': isIndeterminate }"
              role="progressbar"
              :aria-valuenow="task.progress !== undefined ? Math.round(task.progress) : undefined"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-label="task.title"
            >
              <span class="gen-progress-bar" :style="{ width: progressWidth }" />
            </div>
            <div class="gen-meta">
              <span class="gen-hint">{{ task.hint }}</span>
              <span class="gen-elapsed">
                <Clock3 :size="13" aria-hidden="true" />
                已用时 {{ elapsed }}
              </span>
            </div>
          </template>

          <template v-else-if="task.status === 'error'">
            <div class="gen-error-box" role="alert">
              <div class="gen-error-head">
                <span>错误详情</span>
                <button type="button" class="gen-copy-btn" @click="copyError">
                  <Check v-if="copied" :size="13" aria-hidden="true" />
                  <Copy v-else :size="13" aria-hidden="true" />
                  {{ copied ? '已复制' : '复制错误' }}
                </button>
              </div>
              <p class="gen-error-text">{{ task.error }}</p>
              <p v-if="task.errorHint" class="gen-error-hint">{{ task.errorHint }}</p>
            </div>
            <div class="gen-error-meta">
              <span class="gen-elapsed">
                <Clock3 :size="13" aria-hidden="true" />
                耗时 {{ elapsed }}
              </span>
            </div>
            <div class="gen-actions">
              <UiButton variant="secondary" @click="generation.dismiss()">
                <template #leading><X :size="15" aria-hidden="true" /></template>
                关闭返回
              </UiButton>
              <UiButton v-if="task.canRetry" variant="primary" @click="generation.retry()">
                <template #leading><RotateCcw :size="15" aria-hidden="true" /></template>
                重新生成
              </UiButton>
            </div>
          </template>

          <div v-else class="gen-success-bar" aria-hidden="true" />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style>
html.gen-scroll-locked {
  overflow: hidden;
}
</style>

<style scoped>
.gen-overlay {
  position: fixed;
  inset: 0;
  z-index: 160;
  display: grid;
  place-items: center;
  padding: 20px;
  pointer-events: auto;
  background:
    radial-gradient(circle at 50% 34%, rgb(240 184 75 / 9%), transparent 56%),
    rgb(9 10 13 / 82%);
  backdrop-filter: blur(12px);
}

.gen-card {
  position: relative;
  width: min(480px, 100%);
  overflow: hidden;
  padding: 28px 26px 24px;
  border: 1px solid rgb(255 255 255 / 11%);
  border-radius: 16px;
  background: linear-gradient(180deg, #16171d 0%, #101116 100%);
  box-shadow:
    0 28px 88px rgb(0 0 0 / 64%),
    inset 0 1px 0 rgb(255 255 255 / 8%);
}

.gen-card--error {
  border-color: rgb(239 146 146 / 26%);
}

.gen-card--success {
  border-color: rgb(128 201 161 / 28%);
}

.gen-card-glow {
  position: absolute;
  inset: 0 24px auto;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgb(240 184 75 / 65%), transparent);
  pointer-events: none;
}

.gen-card--error .gen-card-glow {
  background: linear-gradient(90deg, transparent, rgb(239 146 146 / 70%), transparent);
}

.gen-card--success .gen-card-glow {
  background: linear-gradient(90deg, transparent, rgb(128 201 161 / 75%), transparent);
}

.gen-head {
  display: flex;
  align-items: center;
  gap: 14px;
}

.gen-emblem {
  position: relative;
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  flex-shrink: 0;
  border-radius: 14px;
}

.gen-emblem--running {
  background: rgb(240 184 75 / 12%);
  color: var(--color-gold);
  box-shadow: 0 0 28px rgb(240 184 75 / 18%);
}

.gen-emblem--success {
  background: rgb(128 201 161 / 14%);
  color: var(--color-success);
}

.gen-emblem--error {
  background: rgb(239 146 146 / 14%);
  color: var(--color-error);
}

.gen-ring {
  position: absolute;
  inset: -3px;
  border: 1.5px solid transparent;
  border-top-color: rgb(240 184 75 / 85%);
  border-right-color: rgb(240 184 75 / 30%);
  border-radius: 16px;
  animation: gen-spin 1.8s linear infinite;
}

.gen-titles {
  min-width: 0;
}

.gen-titles h2 {
  margin: 0;
  color: var(--color-text);
  font-size: 18px;
  font-weight: 600;
  line-height: 1.35;
}

.gen-subtitle {
  margin: 3px 0 0;
  color: var(--color-gold-soft);
  font-size: var(--font-size-caption);
  overflow-wrap: anywhere;
}

.gen-desc {
  margin: 14px 0 0;
  color: var(--color-muted);
  font-size: var(--font-size-body);
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.gen-steps {
  display: grid;
  gap: 9px;
  margin: 16px 0 0;
  padding: 13px 14px;
  list-style: none;
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  background: rgb(255 255 255 / 2.2%);
}

.gen-step {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #c9cad3;
  font-size: 13px;
  line-height: 1.45;
}

.gen-step.is-pending {
  color: #777a86;
}

.gen-step.is-active {
  color: var(--color-gold-soft);
  font-weight: 500;
}

.gen-step.is-done {
  color: var(--color-success);
}

.gen-step-dot {
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  border: 1px solid rgb(255 255 255 / 14%);
  border-radius: 999px;
  background: rgb(255 255 255 / 4%);
  color: var(--color-muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.gen-step.is-overview .gen-step-dot {
  border-color: rgb(240 184 75 / 28%);
  background: rgb(240 184 75 / 8%);
  color: var(--color-gold-soft);
}

.gen-step.is-active .gen-step-dot {
  border-color: var(--color-gold);
  background: rgb(240 184 75 / 18%);
  color: var(--color-gold);
  box-shadow: 0 0 0 3px rgb(240 184 75 / 14%);
}

.gen-step.is-done .gen-step-dot {
  border-color: rgb(128 201 161 / 45%);
  background: rgb(128 201 161 / 16%);
  color: var(--color-success);
}

.gen-progress-track {
  position: relative;
  height: 5px;
  margin-top: 18px;
  overflow: hidden;
  border-radius: 999px;
  background: rgb(255 255 255 / 8%);
}

.gen-progress-bar {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #d7972a, var(--color-gold), var(--color-gold-soft));
  transition: width 0.25s ease;
}

.gen-progress-track.is-indeterminate .gen-progress-bar {
  position: absolute;
  inset: 0 auto 0 -40%;
  width: 42% !important;
  animation: gen-shimmer 1.75s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}

.gen-meta,
.gen-error-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 14px;
  margin-top: 12px;
  font-size: var(--font-size-caption);
  color: var(--color-muted);
}

.gen-elapsed {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #b5b7c2;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.gen-error-box {
  margin-top: 16px;
  padding: 12px 14px;
  border: 1px solid rgb(239 146 146 / 24%);
  border-radius: 10px;
  background: rgb(239 146 146 / 6%);
}

.gen-error-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 6px;
  color: var(--color-error);
  font-size: var(--font-size-caption);
  font-weight: 500;
}

.gen-copy-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px;
  border: 1px solid rgb(239 146 146 / 26%);
  border-radius: 6px;
  background: rgb(239 146 146 / 8%);
  color: #f3b5b5;
  font-size: 11px;
  transition: background 0.15s, border-color 0.15s;
}

.gen-copy-btn:hover {
  background: rgb(239 146 146 / 16%);
  border-color: rgb(239 146 146 / 44%);
}

.gen-error-text {
  max-height: 180px;
  margin: 0;
  overflow-y: auto;
  color: #f5d1d1;
  font-size: 13px;
  line-height: 1.65;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  user-select: text;
}

.gen-error-hint {
  margin: 8px 0 0;
  padding-top: 8px;
  border-top: 1px solid rgb(239 146 146 / 16%);
  color: #d9b5b5;
  font-size: var(--font-size-caption);
  line-height: 1.6;
}

.gen-actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 18px;
}

.gen-success-bar {
  height: 4px;
  margin-top: 18px;
  border-radius: 999px;
  background: linear-gradient(90deg, #54a87b, var(--color-success));
}

.gen-overlay-enter-active,
.gen-overlay-leave-active {
  transition: opacity 0.2s ease;
}

.gen-overlay-enter-active .gen-card,
.gen-overlay-leave-active .gen-card {
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.gen-overlay-enter-from,
.gen-overlay-leave-to {
  opacity: 0;
}

.gen-overlay-enter-from .gen-card,
.gen-overlay-leave-to .gen-card {
  opacity: 0;
  transform: scale(0.97) translateY(6px);
}

@keyframes gen-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes gen-shimmer {
  0% {
    transform: translateX(0);
  }
  100% {
    transform: translateX(350%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .gen-ring,
  .gen-progress-track.is-indeterminate .gen-progress-bar {
    animation: none;
  }
  .gen-progress-track.is-indeterminate .gen-progress-bar {
    left: 0;
    width: 100% !important;
    opacity: 0.55;
  }
  .gen-overlay-enter-active,
  .gen-overlay-leave-active,
  .gen-overlay-enter-active .gen-card,
  .gen-overlay-leave-active .gen-card {
    transition: none;
  }
}
</style>
