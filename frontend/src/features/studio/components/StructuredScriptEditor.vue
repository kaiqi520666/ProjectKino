<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { ArrowDown, ArrowUp, Clapperboard, MessageSquareText, Plus, SunMedium, Trash2 } from 'lucide-vue-next'
import UiSelect from '@/components/ui/UiSelect.vue'
import type { BackendBeat, BackendOutline, BackendScene } from '../api-types'
import { chineseNumber, readOutlineCharacters, readOutlineScenes, scenesSeconds } from '../script-structure'

const props = defineProps<{
  modelValue: BackendScene[]
  outline?: BackendOutline
}>()

const emit = defineEmits<{
  'update:modelValue': [scenes: BackendScene[]]
}>()

const container = ref<HTMLElement>()

const sceneCards = computed(() => new Map(readOutlineScenes(props.outline).map((card) => [card.id, card])))
const characters = computed(() => readOutlineCharacters(props.outline))

function sceneHeading(scene: BackendScene) {
  const card = sceneCards.value.get(scene.sceneId)
  if (!card) return scene.sceneId
  return `${card.kind} · ${card.name} · ${card.time}`
}

function sceneDuration(scene: BackendScene) {
  return scenesSeconds([scene])
}

function isActionBeat(beat: BackendBeat): boolean {
  return beat.action !== undefined && beat.action !== null
}

function speakerOptions(scene: BackendScene) {
  const known = characters.value
  const list = known.map((card) => ({ value: card.id, label: card.name }))
  for (const id of scene.characters) {
    if (id !== 'VO' && !list.some((item) => item.value === id)) {
      list.push({ value: id, label: id })
    }
  }
  list.push({ value: 'VO', label: '画外音' })
  return list
}

function defaultSpeaker(scene: BackendScene): string {
  const first = scene.characters.find((id) => id !== 'VO')
  if (first) return first
  return characters.value[0]?.id ?? 'VO'
}

function updateScene(sceneIndex: number, updater: (scene: BackendScene) => BackendScene) {
  const next = props.modelValue.map((scene, index) => (index === sceneIndex ? updater(scene) : scene))
  emit('update:modelValue', next)
}

function updateLighting(sceneIndex: number, value: string) {
  updateScene(sceneIndex, (scene) => ({ ...scene, lighting: value }))
}

function updateBeat(sceneIndex: number, beatIndex: number, patch: Partial<BackendBeat>) {
  updateScene(sceneIndex, (scene) => ({
    ...scene,
    flow: scene.flow.map((beat, idx) => (idx === beatIndex ? { ...beat, ...patch } : beat)),
  }))
}

function moveBeat(sceneIndex: number, beatIndex: number, delta: -1 | 1) {
  const target = beatIndex + delta
  updateScene(sceneIndex, (scene) => {
    if (target < 0 || target >= scene.flow.length) return scene
    const flow = [...scene.flow]
    const [item] = flow.splice(beatIndex, 1)
    if (!item) return scene
    flow.splice(target, 0, item)
    return { ...scene, flow }
  })
}

function removeBeat(sceneIndex: number, beatIndex: number) {
  updateScene(sceneIndex, (scene) => ({
    ...scene,
    flow: scene.flow.filter((_, idx) => idx !== beatIndex),
  }))
}

async function addBeat(sceneIndex: number, kind: 'action' | 'line') {
  const scene = props.modelValue[sceneIndex]
  if (!scene) return
  const beat: BackendBeat = kind === 'action'
    ? { action: '' }
    : { speaker: defaultSpeaker(scene), delivery: '', line: '' }
  const targetIndex = scene.flow.length
  updateScene(sceneIndex, (current) => ({ ...current, flow: [...current.flow, beat] }))
  await nextTick()
  const el = container.value?.querySelector<HTMLTextAreaElement | HTMLInputElement>(
    `[data-beat-input="${sceneIndex}-${targetIndex}"]`,
  )
  el?.focus()
}
</script>

<template>
  <div ref="container" class="structured-editor">
    <article v-for="(scene, sceneIndex) in modelValue" :key="`${scene.sceneId}-${sceneIndex}`" class="scene-block">
      <header class="scene-head">
        <div class="scene-title">
          <span class="scene-index">第{{ chineseNumber(sceneIndex + 1) }}场</span>
          <span class="scene-location">{{ sceneHeading(scene) }}</span>
          <span class="scene-meta">{{ scene.flow.length }} 拍 · 约 {{ sceneDuration(scene) }} 秒</span>
        </div>
        <label class="scene-lighting">
          <SunMedium :size="13" aria-hidden="true" />
          <span class="scene-lighting-label">光线</span>
          <input
            type="text"
            class="scene-lighting-input"
            :value="scene.lighting"
            placeholder="补充光线氛围，如：冷白台灯微光"
            @input="updateLighting(sceneIndex, ($event.target as HTMLInputElement).value)"
          />
        </label>
      </header>

      <ol class="beat-list">
        <li v-for="(beat, beatIndex) in scene.flow" :key="beatIndex" class="beat-row" :class="{ 'is-action': isActionBeat(beat) }">
          <template v-if="isActionBeat(beat)">
            <span class="beat-tag beat-tag--action">
              <Clapperboard :size="12" aria-hidden="true" />动作
            </span>
            <textarea
              rows="1"
              class="beat-input beat-input--action"
              :data-beat-input="`${sceneIndex}-${beatIndex}`"
              :value="beat.action ?? ''"
              placeholder="描写画面里可拍到的动作或细节..."
              @input="updateBeat(sceneIndex, beatIndex, { action: ($event.target as HTMLTextAreaElement).value })"
            />
          </template>
          <template v-else>
            <UiSelect
              class="beat-speaker-select"
              placeholder="说话人"
              :options="speakerOptions(scene)"
              :model-value="beat.speaker ?? 'VO'"
              @update:model-value="updateBeat(sceneIndex, beatIndex, { speaker: $event || 'VO' })"
            />
            <textarea
              rows="1"
              class="beat-delivery"
              aria-label="语气"
              :value="beat.delivery ?? ''"
              placeholder="语气（可选）"
              maxlength="30"
              @input="updateBeat(sceneIndex, beatIndex, { delivery: ($event.target as HTMLTextAreaElement).value })"
            />
            <textarea
              rows="1"
              class="beat-input"
              :data-beat-input="`${sceneIndex}-${beatIndex}`"
              :value="beat.line ?? ''"
              placeholder="输入角色台词..."
              @input="updateBeat(sceneIndex, beatIndex, { line: ($event.target as HTMLTextAreaElement).value })"
            />
          </template>

          <div class="beat-actions">
            <button
              type="button"
              class="beat-icon-btn"
              title="上移"
              aria-label="上移一拍"
              :disabled="beatIndex === 0"
              @click="moveBeat(sceneIndex, beatIndex, -1)"
            >
              <ArrowUp :size="13" aria-hidden="true" />
            </button>
            <button
              type="button"
              class="beat-icon-btn"
              title="下移"
              aria-label="下移一拍"
              :disabled="beatIndex === scene.flow.length - 1"
              @click="moveBeat(sceneIndex, beatIndex, 1)"
            >
              <ArrowDown :size="13" aria-hidden="true" />
            </button>
            <button
              type="button"
              class="beat-icon-btn beat-icon-btn--danger"
              title="删除此拍"
              aria-label="删除此拍"
              @click="removeBeat(sceneIndex, beatIndex)"
            >
              <Trash2 :size="13" aria-hidden="true" />
            </button>
          </div>
        </li>
      </ol>

      <footer class="scene-footer">
        <button type="button" class="scene-add-btn" @click="addBeat(sceneIndex, 'action')">
          <Plus :size="13" aria-hidden="true" />
          <Clapperboard :size="13" aria-hidden="true" />
          添加动作
        </button>
        <button type="button" class="scene-add-btn" @click="addBeat(sceneIndex, 'line')">
          <Plus :size="13" aria-hidden="true" />
          <MessageSquareText :size="13" aria-hidden="true" />
          添加台词
        </button>
      </footer>
    </article>
  </div>
</template>

<style scoped>
.structured-editor {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-right: 6px;
  scrollbar-width: thin;
  scrollbar-color: rgb(255 255 255 / 16%) transparent;
}

.scene-block {
  flex: 0 0 auto;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: rgb(255 255 255 / 1.8%);
}

.scene-head {
  display: grid;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-subtle);
  background: rgb(255 255 255 / 2%);
}

.scene-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
}

.scene-index {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-size: 12px;
  font-weight: 600;
}

.scene-location {
  color: var(--color-text);
  font-size: 13px;
  font-weight: 500;
}

.scene-meta {
  margin-left: auto;
  color: var(--color-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.scene-lighting {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--color-muted);
  font-size: 12px;
}

.scene-lighting-label {
  flex-shrink: 0;
}

.scene-lighting-input {
  flex: 1;
  min-width: 0;
  height: 28px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: var(--color-text);
  font-size: 12px;
  transition: border-color .15s, background-color .15s;
}

.scene-lighting-input:hover {
  border-color: var(--border-subtle);
  background: rgb(255 255 255 / 2%);
}

.scene-lighting-input:focus {
  outline: none;
  border-color: rgb(240 184 75 / 50%);
  background: var(--color-elevated);
}

.beat-list {
  display: grid;
  gap: 4px;
  margin: 0;
  padding: 10px 12px;
  list-style: none;
}

.beat-row {
  display: grid;
  grid-template-columns: 108px 176px minmax(0, 1fr) auto;
  align-items: start;
  gap: 8px;
  padding: 5px 6px;
  border-radius: 6px;
  transition: background-color .15s;
}

.beat-row:hover,
.beat-row:focus-within {
  background: rgb(255 255 255 / 3%);
}

.beat-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  width: 100%;
  height: 34px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: rgb(255 255 255 / 3%);
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 500;
}

.beat-speaker-select {
  min-width: 0;
}

.beat-speaker-select :deep(.ui-select-trigger) {
  min-height: 34px;
  height: 34px;
  padding: 0 8px 0 10px;
  border-color: rgb(240 184 75 / 22%);
  border-radius: 6px;
  background: rgb(240 184 75 / 8%);
  color: var(--color-gold-soft);
  font-size: 12px;
  font-weight: 500;
}

.beat-speaker-select :deep(.ui-select-trigger:hover) {
  border-color: rgb(240 184 75 / 45%);
  background: rgb(240 184 75 / 12%);
}

.beat-speaker-select :deep(.ui-select-trigger:focus-visible) {
  border-color: rgb(240 184 75 / 60%);
}

.beat-delivery,
.beat-input {
  width: 100%;
  min-width: 0;
  min-height: 34px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: rgb(255 255 255 / 2.5%);
  color: var(--color-text);
  line-height: 1.5;
  resize: none;
  overflow: hidden;
  field-sizing: content;
  transition: border-color .15s, background-color .15s;
}

.beat-delivery {
  padding: 7px 9px;
  color: var(--color-muted);
  font-size: 12px;
}

.beat-input {
  padding: 7px 10px;
  font-size: 13px;
}

.beat-input--action {
  grid-column: 2 / 4;
}

.beat-delivery:hover,
.beat-input:hover {
  border-color: var(--border-subtle);
  background: rgb(255 255 255 / 4%);
}

.beat-delivery:focus,
.beat-input:focus {
  outline: none;
  border-color: rgb(240 184 75 / 55%);
  background: var(--color-elevated);
  color: var(--color-text);
}

.beat-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  height: 34px;
  opacity: 0.45;
  transition: opacity .15s;
}

.beat-row:hover .beat-actions,
.beat-row:focus-within .beat-actions {
  opacity: 1;
}

.beat-icon-btn {
  display: inline-grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--color-muted);
  cursor: pointer;
  transition: background-color .15s, color .15s;
}

.beat-icon-btn:hover:not(:disabled) {
  background: rgb(255 255 255 / 7%);
  color: var(--color-text);
}

.beat-icon-btn--danger:hover:not(:disabled) {
  background: rgb(239 68 68 / 12%);
  color: var(--color-error);
}

.beat-icon-btn:disabled {
  opacity: 0.25;
  cursor: not-allowed;
}

.scene-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 14px 12px;
  border-top: 1px dashed rgb(255 255 255 / 7%);
}

.scene-add-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: transparent;
  color: var(--color-muted);
  font-size: 12px;
  cursor: pointer;
  transition: border-color .15s, color .15s, background-color .15s;
}

.scene-add-btn:hover {
  border-color: rgb(240 184 75 / 40%);
  background: rgb(240 184 75 / 8%);
  color: var(--color-gold-soft);
}

@media (max-width: 720px) {
  .beat-row {
    grid-template-columns: 100px minmax(0, 1fr) auto;
  }
  .beat-input {
    grid-column: 1 / -1;
  }
  .beat-input--action {
    grid-column: 1 / -1;
  }
}
</style>
