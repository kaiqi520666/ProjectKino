<script setup lang="ts">
import { computed, ref, shallowRef, useId, watch } from 'vue'
import { ArrowLeft, ArrowRight, Check, FilePenLine, FileUp, Music, Plus } from 'lucide-vue-next'
import FileDropzone from '@/components/business/FileDropzone.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import UiSwitch from '@/components/ui/UiSwitch.vue'
import UiTextarea from '@/components/ui/UiTextarea.vue'
import ArtStylePicker from './ArtStylePicker.vue'
import ImageModelPicker from './ImageModelPicker.vue'
import VideoModelPicker from './VideoModelPicker.vue'
import { useModelCatalog } from '../composables/useModelCatalog'
import {
  availableImageTiers,
  IMAGE_TIER_OPTIONS,
  resolveDefaultImageModel,
  resolveDefaultVideoModel,
  resolveImageTierForModel,
} from '../model-defaults'
import {
  contentLanguages,
  episodeDurationPresets,
  formatDurationLabel,
  initialDramaSettings,
  maxEpisodeDuration,
  maxEpisodesForDuration,
  maxInitialTotalSeconds,
  maxScriptUploadMb,
  minEpisodeDuration,
  resolveDramaSettings,
  segmentDurations,
  videoRatios,
} from './drama-creation'
import type { DramaCreation } from './drama-creation'
import { storyMaxLength, validateStory } from './story-input'

type CreationStep = 1 | 2

const props = defineProps<{ busy?: boolean }>()
const emit = defineEmits<{ submit: [input: DramaCreation] }>()
const scriptFileExtensions = ['.txt', '.md'] as const
const id = useId()
const formId = `${id}-form`
const open = ref(false)
const step = ref<CreationStep>(1)
const preserveDraftOnClose = ref(false)
const mode = ref<DramaCreation['mode']>('story')
const draft = ref(initialDramaSettings())
const story = ref('')
const file = shallowRef<File>()
const { imageModels, videoModels, ensureLoaded: ensureModelCatalog } = useModelCatalog()

const selectedImageModelId = computed({
  get: () => draft.value.imageModelId ?? '',
  set: (value: string) => {
    draft.value.imageModelId = value || undefined
  },
})

const selectedVideoModelId = computed({
  get: () => draft.value.videoModelId ?? '',
  set: (value: string) => {
    draft.value.videoModelId = value || undefined
  },
})

const selectedImageModel = computed(
  () => imageModels.value.find((m) => m.id === draft.value.imageModelId) ?? resolveDefaultImageModel(imageModels.value),
)

const imageTierChoices = computed(() => {
  const tiers = availableImageTiers(selectedImageModel.value)
  const priceMap = new Map(
    (selectedImageModel.value?.imagePrices ?? []).map((p) => [p.tier, p.creditPrice]),
  )
  return IMAGE_TIER_OPTIONS.filter((opt) => tiers.includes(opt.value)).map((opt) => ({
    ...opt,
    price: priceMap.get(opt.value),
  }))
})

function syncDefaultModelsForDraft(forceVideo = false) {
  if (imageModels.value.length) {
    const resolvedImg = resolveDefaultImageModel(imageModels.value, draft.value.imageModelId)
    if (resolvedImg) {
      draft.value.imageModelId = resolvedImg.id
      draft.value.imageTier = resolveImageTierForModel(resolvedImg, draft.value.imageTier)
    }
  }
  if (videoModels.value.length) {
    const resolvedVid = resolveDefaultVideoModel(
      videoModels.value,
      draft.value.maxSegmentDuration,
      forceVideo ? undefined : draft.value.videoModelId,
    )
    if (resolvedVid) {
      draft.value.videoModelId = resolvedVid.id
    }
  }
}

watch(
  () => draft.value.maxSegmentDuration,
  (nextCap) => {
    if (!videoModels.value.length) return
    const nextModel = resolveDefaultVideoModel(videoModels.value, nextCap)
    if (nextModel) draft.value.videoModelId = nextModel.id
  },
)

watch(
  () => draft.value.imageModelId,
  () => {
    if (!selectedImageModel.value) return
    draft.value.imageTier = resolveImageTierForModel(selectedImageModel.value, draft.value.imageTier)
  },
)

watch([imageModels, videoModels], () => {
  if (open.value) syncDefaultModelsForDraft()
})
const settings = computed(() => resolveDramaSettings(draft.value))
const maxEpisodes = computed(() => maxEpisodesForDuration(draft.value.secondsPerEpisode))
const episodeDurationInvalid = computed(
  () =>
    draft.value.secondsPerEpisode !== '' &&
    (!Number.isSafeInteger(draft.value.secondsPerEpisode) ||
      draft.value.secondsPerEpisode < minEpisodeDuration ||
      draft.value.secondsPerEpisode > maxEpisodeDuration),
)
const episodeCountNonPositive = computed(
  () =>
    draft.value.episodeCount !== '' &&
    (!Number.isSafeInteger(draft.value.episodeCount) || draft.value.episodeCount < 1),
)
const totalDurationExceeded = computed(
  () =>
    typeof draft.value.episodeCount === 'number' &&
    Number.isSafeInteger(draft.value.episodeCount) &&
    draft.value.episodeCount >= 1 &&
    typeof draft.value.secondsPerEpisode === 'number' &&
    Number.isSafeInteger(draft.value.secondsPerEpisode) &&
    draft.value.secondsPerEpisode >= minEpisodeDuration &&
    draft.value.episodeCount * draft.value.secondsPerEpisode > maxInitialTotalSeconds,
)
const episodeCountInvalid = computed(() => episodeCountNonPositive.value || totalDurationExceeded.value)
const episodeCountError = computed(() => {
  if (episodeCountNonPositive.value) return '集数必须是正整数'
  if (totalDurationExceeded.value) {
    return `单集 ${draft.value.secondsPerEpisode} 秒时首创最多 ${maxEpisodes.value} 集（总时长 ≤ ${maxInitialTotalSeconds / 60} 分钟），后续可在剧本页新增分集`
  }
  return ''
})
const estimatedTotalSeconds = computed(() => {
  if (typeof draft.value.episodeCount !== 'number' || typeof draft.value.secondsPerEpisode !== 'number') return null
  if (draft.value.episodeCount < 1 || draft.value.secondsPerEpisode < minEpisodeDuration) return null
  return draft.value.episodeCount * draft.value.secondsPerEpisode
})
const recommendThirtySeconds = computed(
  () =>
    typeof draft.value.secondsPerEpisode === 'number' &&
    draft.value.secondsPerEpisode > 300,
)
function estimatedClipsForSegment(segmentCap: number): number | null {
  if (typeof draft.value.secondsPerEpisode !== 'number' || draft.value.secondsPerEpisode < minEpisodeDuration) {
    return null
  }
  return Math.max(1, Math.ceil(draft.value.secondsPerEpisode / (segmentCap * 0.8)))
}
const hasValidContent = computed(() =>
  mode.value === 'story' ? validateStory(story.value) === null : !!file.value,
)
const canProceedStep1 = computed(
  () =>
    draft.value.name.trim().length > 0 &&
    hasValidContent.value &&
    videoRatios.includes(draft.value.ratio) &&
    contentLanguages.some(({ value }) => value === draft.value.language) &&
    Boolean(draft.value.visualStyle),
)
const canSubmit = computed(() => settings.value !== null && hasValidContent.value)

function goToStep(target: CreationStep) {
  if (target === 2 && !canProceedStep1.value) return
  step.value = target
}

function handleFormSubmit() {
  if (step.value === 1) {
    if (canProceedStep1.value) step.value = 2
    return
  }
  submit()
}

function submit() {
  if (props.busy || !canSubmit.value || !settings.value) return
  const payload: DramaCreation | null = mode.value === 'story'
    ? { mode: 'story', settings: settings.value, story: story.value.trim() }
    : file.value
      ? { mode: 'upload', settings: settings.value, file: file.value }
      : null
  if (!payload) return
  preserveDraftOnClose.value = true
  open.value = false
  emit('submit', payload)
}

watch(open, (isOpen) => {
  if (isOpen) {
    syncDefaultModelsForDraft()
    void ensureModelCatalog().then(() => {
      if (open.value) syncDefaultModelsForDraft()
    })
    return
  }
  if (preserveDraftOnClose.value) {
    preserveDraftOnClose.value = false
    return
  }
  step.value = 1
  mode.value = 'story'
  draft.value = initialDramaSettings()
  story.value = ''
  file.value = undefined
})
</script>

<template>
  <section class="script-creation-panel" aria-labelledby="studio-entry-title">
    <div class="script-entry-heading">
      <span class="script-entry-symbol"><FilePenLine :size="21" :stroke-width="1.5" aria-hidden="true" /></span>
      <h2 id="studio-entry-title">短剧制作</h2>
    </div>

    <UiDialog v-model:open="open" title="新建短剧" size="wide">
      <template #trigger>
        <UiButton variant="primary" class="script-entry-button">
          <template #leading><Plus :size="17" aria-hidden="true" /></template>
          新建短剧
        </UiButton>
      </template>

      <nav class="drama-stepper" aria-label="创建步骤">
        <button
          type="button"
          class="drama-step-tab"
          :class="{ 'is-active': step === 1, 'is-done': step === 2 }"
          :aria-current="step === 1 ? 'step' : undefined"
          @click="goToStep(1)"
        >
          <span class="drama-step-badge" aria-hidden="true">
            <Check v-if="step === 2" :size="12" :stroke-width="2.6" />
            <template v-else>1</template>
          </span>
          <span class="drama-step-title">故事与画风</span>
        </button>
        <span class="drama-step-divider" aria-hidden="true" />
        <button
          type="button"
          class="drama-step-tab"
          :class="{ 'is-active': step === 2 }"
          :disabled="!canProceedStep1"
          :aria-current="step === 2 ? 'step' : undefined"
          @click="goToStep(2)"
        >
          <span class="drama-step-badge" aria-hidden="true">2</span>
          <span class="drama-step-title">篇幅与模型</span>
        </button>
      </nav>

      <form :id="formId" class="drama-form" novalidate @submit.prevent="handleFormSubmit">
        <div v-show="step === 1" class="drama-step-panel">
          <div class="drama-step1-top">
            <UiInput v-model="draft.name" label="项目名称" placeholder="输入短剧名称" required />
            <UiSelect v-model="draft.language" label="内容语言" :options="contentLanguages" required />
          </div>

          <fieldset class="drama-section">
            <div class="drama-segments drama-modes">
              <label>
                <input v-model="mode" type="radio" :name="`${id}-mode`" value="story" />
                <span><FilePenLine :size="15" aria-hidden="true" />写故事</span>
              </label>
              <label>
                <input v-model="mode" type="radio" :name="`${id}-mode`" value="upload" />
                <span><FileUp :size="15" aria-hidden="true" />上传剧本</span>
              </label>
            </div>
            <UiTextarea
              v-show="mode === 'story'"
              v-model="story"
              label="故事梗概"
              placeholder="例如：城市停电后，失忆的法医发现自己的旧档案不见了……"
              :maxlength="storyMaxLength"
              :rows="4"
              :required="mode === 'story'"
            />
            <FileDropzone
              v-show="mode === 'upload'"
              label="选择文件"
              :extensions="scriptFileExtensions"
              :max-size-mb="maxScriptUploadMb"
              @select="file = $event"
              @clear="file = undefined"
            />
          </fieldset>

          <ArtStylePicker v-model="draft.visualStyle" />

          <fieldset class="drama-choice">
            <legend class="ui-label">视频比例<span class="ui-required" aria-hidden="true">*</span></legend>
            <div class="drama-segments drama-ratios">
              <label v-for="ratio in videoRatios" :key="ratio">
                <input v-model="draft.ratio" type="radio" :name="`${id}-ratio`" :value="ratio" required />
                <span>{{ ratio }}</span>
              </label>
            </div>
          </fieldset>
        </div>

        <div v-show="step === 2" class="drama-step-panel">
          <fieldset class="drama-step-card">
            <legend class="drama-card-title">剧集篇幅</legend>
            <div class="drama-card-body">
              <div class="ui-field">
                <label class="ui-label" :for="`${id}-ep-seconds`">
                  单集目标时长（{{ minEpisodeDuration }}–{{ maxEpisodeDuration }} 秒）<span class="ui-required" aria-hidden="true">*</span>
                </label>
                <div class="drama-ep-duration-row">
                  <div class="drama-segments drama-ep-presets" role="group" aria-label="快捷时长">
                    <button
                      v-for="sec in episodeDurationPresets"
                      :key="sec"
                      type="button"
                      class="drama-ep-preset"
                      :class="{ 'is-active': draft.secondsPerEpisode === sec }"
                      @click="draft.secondsPerEpisode = sec"
                    >
                      {{ formatDurationLabel(sec) }}
                    </button>
                  </div>
                  <label class="drama-ep-custom" :class="{ 'is-invalid': episodeDurationInvalid }">
                    <input
                      :id="`${id}-ep-seconds`"
                      v-model.number="draft.secondsPerEpisode"
                      type="number"
                      :min="minEpisodeDuration"
                      :max="maxEpisodeDuration"
                      step="1"
                      required
                      :aria-invalid="episodeDurationInvalid || undefined"
                      :aria-describedby="episodeDurationInvalid ? `${id}-ep-seconds-error` : undefined"
                    />
                    <span>秒</span>
                  </label>
                </div>
                <p v-if="episodeDurationInvalid" :id="`${id}-ep-seconds-error`" class="ui-field-message is-error">
                  单集目标时长须为 {{ minEpisodeDuration }}–{{ maxEpisodeDuration }} 秒之间的整数
                </p>
              </div>

              <div class="drama-ep-count-row">
                <div class="ui-field">
                  <label class="ui-label" :for="`${id}-episodes`">
                    集数（1–{{ maxEpisodes }}）<span class="ui-required" aria-hidden="true">*</span>
                  </label>
                  <input
                    :id="`${id}-episodes`"
                    v-model.number="draft.episodeCount"
                    type="number"
                    class="ui-input"
                    :class="{ 'is-invalid': episodeCountInvalid }"
                    min="1"
                    :max="maxEpisodes"
                    step="1"
                    required
                    :aria-invalid="episodeCountInvalid || undefined"
                    :aria-describedby="episodeCountInvalid ? `${id}-episodes-error` : undefined"
                  />
                  <p v-if="episodeCountInvalid" :id="`${id}-episodes-error`" class="ui-field-message is-error">{{ episodeCountError }}</p>
                </div>

                <div class="ui-field">
                  <span class="ui-label">背景音乐</span>
                  <div class="drama-switch-row" :class="{ 'is-active': draft.backgroundMusic }">
                    <span class="drama-switch-icon" aria-hidden="true"><Music :size="15" :stroke-width="1.8" /></span>
                    <UiSwitch v-model="draft.backgroundMusic" class="drama-switch-control" label="生成背景音乐" />
                  </div>
                </div>
              </div>
            </div>
          </fieldset>

          <fieldset class="drama-step-card">
            <legend class="drama-card-title">默认模型</legend>
            <div class="drama-card-body">
              <fieldset class="drama-choice">
                <legend class="ui-label">单片段最长时长<span class="ui-required" aria-hidden="true">*</span></legend>
                <div class="drama-segments drama-durations">
                  <label v-for="duration in segmentDurations" :key="duration">
                    <input v-model="draft.maxSegmentDuration" type="radio" :name="`${id}-duration`" :value="duration" required />
                    <span>
                      <strong class="drama-duration-main">{{ duration }} 秒</strong>
                      <small v-if="estimatedClipsForSegment(duration) !== null" class="drama-duration-sub">
                        约 {{ estimatedClipsForSegment(duration) }} 段/集
                      </small>
                      <em v-if="duration === 30 && recommendThirtySeconds" class="drama-duration-badge">推荐</em>
                    </span>
                  </label>
                </div>
              </fieldset>

              <div class="ui-field">
                <span class="ui-label">默认视频模型（按 {{ draft.maxSegmentDuration }} 秒档自动匹配）</span>
                <div class="drama-model-picker-wrap">
                  <VideoModelPicker
                    v-model="selectedVideoModelId"
                    :models="videoModels"
                    :project-ratio="draft.ratio"
                    :min-max-duration="draft.maxSegmentDuration === 30 ? 30 : undefined"
                    placeholder="加载视频模型…"
                  />
                </div>
              </div>

              <div class="drama-image-defaults">
                <div class="ui-field">
                  <span class="ui-label">默认图片模型</span>
                  <div class="drama-model-picker-wrap">
                    <ImageModelPicker
                      v-model="selectedImageModelId"
                      :models="imageModels"
                      :tier="draft.imageTier"
                      placeholder="加载图片模型…"
                    />
                  </div>
                </div>
                <fieldset class="drama-choice">
                  <legend class="ui-label">默认图片清晰度</legend>
                  <div
                    class="drama-segments drama-image-tiers"
                    :style="{ gridTemplateColumns: `repeat(${Math.max(1, imageTierChoices.length)}, minmax(0, 1fr))` }"
                  >
                    <label v-for="opt in imageTierChoices" :key="opt.value">
                      <input v-model="draft.imageTier" type="radio" :name="`${id}-image-tier`" :value="opt.value" />
                      <span>{{ opt.label }}</span>
                    </label>
                  </div>
                </fieldset>
              </div>
            </div>
          </fieldset>
        </div>
      </form>

      <template #footer>
        <div class="drama-dialog-footer">
          <span
            v-if="step === 2 && estimatedTotalSeconds !== null"
            class="drama-footer-summary"
            :class="{ 'is-exceeded': totalDurationExceeded }"
          >
            首创总时长 <strong>{{ formatDurationLabel(estimatedTotalSeconds) }}</strong> / {{ maxInitialTotalSeconds / 60 }} 分钟
          </span>
          <div class="drama-footer-actions">
            <template v-if="step === 1">
              <UiButton variant="ghost" :disabled="busy" @click="open = false">取消</UiButton>
              <UiButton variant="primary" type="button" :disabled="!canProceedStep1 || busy" @click="goToStep(2)">
                下一步
                <template #trailing><ArrowRight :size="16" aria-hidden="true" /></template>
              </UiButton>
            </template>
            <template v-else>
              <UiButton variant="ghost" :disabled="busy" @click="goToStep(1)">
                <template #leading><ArrowLeft :size="15" aria-hidden="true" /></template>
                上一步
              </UiButton>
              <UiButton variant="primary" type="submit" :form="formId" :disabled="!canSubmit || busy" :loading="busy">
                {{ busy ? '正在生成剧本…' : '创建剧本' }}
                <template v-if="!busy" #trailing><ArrowRight :size="16" aria-hidden="true" /></template>
              </UiButton>
            </template>
          </div>
        </div>
      </template>
    </UiDialog>
  </section>
</template>

<style scoped>
.script-creation-panel { display: flex; flex-direction: column; justify-content: center; align-items: flex-start; gap: 22px; min-width: 0; min-height: 184px; padding: 24px 28px; border: 1px solid rgb(240 184 75 / 17%); border-radius: 8px; background: #171619; }
.script-entry-heading { display: flex; align-items: center; gap: 12px; }
.script-entry-heading h2 { margin: 0; font-size: 18px; font-weight: 500; line-height: 1.4; }
.script-entry-symbol { display: grid; place-items: center; width: 40px; height: 40px; flex-shrink: 0; border: 1px solid rgb(240 184 75 / 16%); border-radius: 8px; background: var(--gold-tint); color: var(--color-gold-soft); }
.script-entry-button { min-width: 128px; }
.drama-stepper { display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); align-items: center; gap: 10px; margin-bottom: 20px; padding: 4px; border: 1px solid var(--border-subtle); border-radius: 10px; background: rgb(255 255 255 / 2%); }
.drama-step-tab { display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 36px; padding: 6px 12px; border: 1px solid transparent; border-radius: 7px; background: transparent; color: var(--color-muted); font-size: 13px; font-weight: 500; cursor: pointer; transition: border-color .15s, background-color .15s, color .15s; }
.drama-step-tab:hover:not(:disabled) { color: var(--color-text); background: var(--surface-hover); }
.drama-step-tab.is-active { border-color: rgb(240 184 75 / 28%); background: var(--gold-tint); color: var(--color-gold-soft); }
.drama-step-tab.is-done { color: var(--color-text); }
.drama-step-tab:disabled { opacity: .45; cursor: not-allowed; }
.drama-step-badge { display: inline-grid; place-items: center; width: 20px; height: 20px; flex-shrink: 0; border-radius: 999px; border: 1px solid rgb(255 255 255 / 16%); background: rgb(255 255 255 / 4%); font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums; }
.drama-step-tab.is-active .drama-step-badge { border-color: rgb(240 184 75 / 45%); background: rgb(240 184 75 / 18%); color: var(--color-gold-soft); }
.drama-step-tab.is-done .drama-step-badge { border-color: rgb(240 184 75 / 40%); background: rgb(240 184 75 / 14%); color: var(--color-gold-soft); }
.drama-step-divider { width: 24px; height: 1px; background: var(--border-subtle); }
.drama-form { display: block; }
.drama-step-panel { display: grid; gap: 18px; }
.drama-step1-top { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); align-items: start; gap: 12px; }
.drama-step-card { min-width: 0; margin: 0; padding: 16px; border: 1px solid var(--border-subtle); border-radius: 10px; background: rgb(255 255 255 / 2%); }
.drama-card-title { float: left; width: 100%; margin: 0 0 14px; padding: 0; color: var(--color-text); font-size: 13px; font-weight: 600; letter-spacing: .02em; }
.drama-card-body { clear: left; display: grid; gap: 14px; }
.drama-ep-count-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.35fr); align-items: start; gap: 12px; }
.drama-section, .drama-choice { min-width: 0; margin: 0; padding: 0; border: 0; }
.drama-modes { margin-bottom: 12px; }
.drama-choice > legend { margin-bottom: 8px; padding: 0; }
.drama-segments { display: grid; gap: 4px; padding: 4px; border: 1px solid var(--border-control); border-radius: 8px; background: var(--color-surface); }
.drama-modes, .drama-durations { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.drama-ratios { grid-template-columns: repeat(5, minmax(0, 1fr)); }
.drama-segments label { position: relative; min-width: 0; cursor: pointer; }
.drama-segments input { position: absolute; width: 1px; height: 1px; opacity: 0; }
.drama-segments span { display: flex; align-items: center; justify-content: center; gap: 7px; min-height: 34px; padding: 2px; border: 1px solid transparent; border-radius: 5px; color: var(--color-muted); line-height: 1.25; }
.drama-segments label:hover span { color: var(--color-text); background: var(--surface-hover); }
.drama-segments input:checked + span { border-color: rgb(240 184 75 / 28%); background: var(--gold-tint); color: var(--color-gold-soft); }
.drama-segments input:focus-visible + span { outline: 2px solid var(--color-gold); outline-offset: -2px; }
.drama-switch-row { display: flex; align-items: center; gap: 10px; min-height: 40px; padding: 0 12px; border: 1px solid var(--border-control); border-radius: var(--radius-control); background: rgb(255 255 255 / 3%); transition: border-color .15s, background-color .15s; }
.drama-switch-row:hover { border-color: rgb(255 255 255 / 22%); }
.drama-switch-row.is-active { border-color: rgb(240 184 75 / 32%); background: rgb(240 184 75 / 6%); }
.drama-switch-icon { display: grid; place-items: center; width: 24px; height: 24px; flex-shrink: 0; border-radius: 6px; background: rgb(255 255 255 / 5%); color: var(--color-muted); transition: background-color .15s, color .15s; }
.drama-switch-row.is-active .drama-switch-icon { background: var(--gold-tint); color: var(--color-gold-soft); }
.drama-switch-control { flex: 1; min-width: 0; min-height: 0; }
.drama-switch-control :deep(label) { flex: 1; color: #c9cad3; font-size: 13px; font-weight: 500; }
.drama-switch-row.is-active .drama-switch-control :deep(label) { color: var(--color-text); }
.drama-form input.is-invalid { border-color: var(--color-error); }
.drama-ep-duration-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: stretch; gap: 8px; }
.drama-ep-presets { grid-template-columns: repeat(5, minmax(0, 1fr)); }
.drama-ep-preset { min-height: 34px; padding: 2px 6px; border: 1px solid transparent; border-radius: 5px; background: transparent; color: var(--color-muted); font-size: 13px; line-height: 1.25; cursor: pointer; transition: border-color .15s, background-color .15s, color .15s; }
.drama-ep-preset:hover { color: var(--color-text); background: var(--surface-hover); }
.drama-ep-preset.is-active { border-color: rgb(240 184 75 / 28%); background: var(--gold-tint); color: var(--color-gold-soft); font-weight: 500; }
.drama-ep-custom { display: inline-flex; align-items: center; gap: 4px; padding: 0 10px; border: 1px solid var(--border-control); border-radius: 8px; background: var(--color-surface); color: var(--color-muted); font-size: 13px; transition: border-color .15s; }
.drama-ep-custom:focus-within { border-color: rgb(240 184 75 / 55%); }
.drama-ep-custom.is-invalid { border-color: var(--color-error); }
.drama-ep-custom input { width: 46px; padding: 0; border: 0; background: transparent; color: var(--color-text); font-size: 13px; font-variant-numeric: tabular-nums; text-align: center; outline: none; -moz-appearance: textfield; }
.drama-ep-custom input::-webkit-outer-spin-button,
.drama-ep-custom input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.drama-duration-main { font-weight: 500; }
.drama-duration-sub { color: var(--color-muted); font-size: 12px; opacity: .82; }
.drama-segments input:checked + span .drama-duration-sub { color: var(--color-gold-soft); opacity: .78; }
.drama-duration-badge { padding: 1px 6px; border: 1px solid rgb(240 184 75 / 38%); border-radius: 999px; background: rgb(240 184 75 / 14%); color: var(--color-gold-soft); font-size: 11px; font-style: normal; font-weight: 500; line-height: 1.35; }
.drama-image-defaults { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); align-items: end; gap: 12px; }
.drama-model-picker-wrap { display: flex; }
.drama-model-picker-wrap :deep(.vmp-trigger),
.drama-model-picker-wrap :deep(.imp-trigger) { width: 100%; justify-content: space-between; min-height: 40px; }
.drama-image-tiers span { min-height: 30px; font-size: 13px; }
.drama-dialog-footer { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px 14px; width: 100%; }
.drama-footer-summary { color: var(--color-muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.drama-footer-summary strong { color: var(--color-text); font-weight: 500; }
.drama-footer-summary.is-exceeded,
.drama-footer-summary.is-exceeded strong { color: var(--color-error); }
.drama-footer-actions { display: inline-flex; align-items: center; gap: 8px; margin-left: auto; }
.drama-form :deep(.file-dropzone) { min-height: 158px; padding-block: 12px; gap: 5px; }
.drama-form :deep(.ui-counter) { color: var(--color-muted); }
@media (max-width: 520px) {
  .drama-step1-top,
  .drama-ep-count-row,
  .drama-image-defaults { grid-template-columns: minmax(0, 1fr); }
  .drama-step-divider { width: 12px; }
  .drama-step-panel { gap: 14px; }
}
</style>
