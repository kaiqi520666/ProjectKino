<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import { Music, Save } from 'lucide-vue-next'
import UiAlert from '@/components/ui/UiAlert.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiSwitch from '@/components/ui/UiSwitch.vue'
import type { ImageAspectRatio } from '@/components/ui/image-types'
import { useUiStore } from '@/stores/ui'
import { apiErrorMessage, updateProjectApi } from '../api'
import type { ProjectMetaUpdatePayload } from '../api-types'
import { useModelCatalog } from '../composables/useModelCatalog'
import {
  availableImageTiers,
  IMAGE_TIER_OPTIONS,
  modelMaxDuration,
  resolveDefaultImageModel,
  resolveDefaultVideoModel,
  resolveImageTierForModel,
  type ImageTier,
} from '../model-defaults'
import type { StudioProject } from '../studio-project'
import { useArtStylesStore } from '@/features/art-styles/art-styles-store'
import { useStudioStore } from '../studio-store'
import ArtStylePicker from './ArtStylePicker.vue'
import {
  defaultSegmentDuration,
  segmentDurations,
  videoRatios,
  type SegmentDuration,
} from './drama-creation'
import ImageModelPicker from './ImageModelPicker.vue'
import VideoModelPicker from './VideoModelPicker.vue'

const props = defineProps<{
  project: StudioProject
}>()

const open = defineModel<boolean>('open', { required: true })

const studio = useStudioStore()
const artStylesStore = useArtStylesStore()
const ui = useUiStore()
const { imageModels, videoModels, ensureLoaded: ensureModelCatalog } = useModelCatalog()

const id = useId()
const formId = `${id}-form`
const saving = ref(false)

const visualStyle = ref('')
const ratio = ref<ImageAspectRatio>('16:9')
const maxSegmentDuration = ref<SegmentDuration>(defaultSegmentDuration)
const backgroundMusic = ref(true)
const selectedImageModelId = ref('')
const selectedImageTier = ref<ImageTier>('1k')
const selectedVideoModelId = ref('')

const currentImageModel = computed(
  () => imageModels.value.find((m) => m.id === selectedImageModelId.value) ?? null,
)

const imageTierChoices = computed(() => {
  const allowed = availableImageTiers(currentImageModel.value)
  return IMAGE_TIER_OPTIONS.filter((opt) => allowed.includes(opt.value))
})

function syncDraftFromProject() {
  const settings = props.project.creation.settings
  visualStyle.value = settings.visualStyle
  ratio.value = settings.ratio
  maxSegmentDuration.value = settings.maxSegmentDuration ?? defaultSegmentDuration
  backgroundMusic.value = settings.backgroundMusic ?? true

  const imgModel = resolveDefaultImageModel(imageModels.value, settings.imageModelId)
  selectedImageModelId.value = settings.imageModelId || imgModel?.id || ''
  selectedImageTier.value = resolveImageTierForModel(imgModel, settings.imageTier)

  const vidModel = resolveDefaultVideoModel(
    videoModels.value,
    maxSegmentDuration.value,
    settings.videoModelId,
  )
  selectedVideoModelId.value = settings.videoModelId || vidModel?.id || ''
}

watch(
  open,
  async (isOpen) => {
    if (!isOpen) return
    syncDraftFromProject()
    await ensureModelCatalog()
    if (open.value) syncDraftFromProject()
  },
)

watch(maxSegmentDuration, (cap) => {
  if (!open.value || !videoModels.value.length) return
  const current = videoModels.value.find((m) => m.id === selectedVideoModelId.value)
  if (cap >= 30 && (!current || modelMaxDuration(current) < 30)) {
    const resolved = resolveDefaultVideoModel(videoModels.value, 30)
    if (resolved) selectedVideoModelId.value = resolved.id
  } else if (!current) {
    const resolved = resolveDefaultVideoModel(videoModels.value, cap)
    if (resolved) selectedVideoModelId.value = resolved.id
  }
})

watch(selectedImageModelId, () => {
  if (!open.value) return
  selectedImageTier.value = resolveImageTierForModel(currentImageModel.value, selectedImageTier.value)
})

const hasChanges = computed(() => {
  const s = props.project.creation.settings
  return (
    visualStyle.value !== s.visualStyle
    || ratio.value !== s.ratio
    || maxSegmentDuration.value !== (s.maxSegmentDuration ?? defaultSegmentDuration)
    || backgroundMusic.value !== (s.backgroundMusic ?? true)
    || (selectedImageModelId.value || null) !== (s.imageModelId ?? null)
    || selectedImageTier.value !== (s.imageTier ?? '1k')
    || (selectedVideoModelId.value || null) !== (s.videoModelId ?? null)
  )
})

async function submit() {
  if (saving.value) return
  if (!props.project.persisted) {
    props.project.creation.settings = {
      ...props.project.creation.settings,
      visualStyle: visualStyle.value,
      ratio: ratio.value,
      maxSegmentDuration: maxSegmentDuration.value,
      backgroundMusic: backgroundMusic.value,
      imageModelId: selectedImageModelId.value || undefined,
      imageTier: selectedImageTier.value,
      videoModelId: selectedVideoModelId.value || undefined,
    }
    open.value = false
    ui.notify('项目默认配置已更新', 'success')
    return
  }

  const stylePrompt = artStylesStore.getPrompt(visualStyle.value)
  const payload: ProjectMetaUpdatePayload = {
    visualStyle: visualStyle.value,
    visualStyleLabel: stylePrompt || null,
    ratio: ratio.value,
    maxSegmentDuration: maxSegmentDuration.value,
    backgroundMusic: backgroundMusic.value,
    imageModelId: selectedImageModelId.value || null,
    imageTier: selectedImageTier.value,
    videoModelId: selectedVideoModelId.value || null,
  }

  saving.value = true
  try {
    const updated = await updateProjectApi(props.project.id, payload)
    studio.applyProjectMeta(props.project.id, updated)
    open.value = false
    ui.notify('项目默认配置已更新', 'success')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <UiDialog
    v-model:open="open"
    title="项目默认配置"
    description="调整本项目的画面风格、默认比例与生图/生视频模型。"
    size="wide"
  >
    <form :id="formId" class="proj-settings-form" @submit.prevent="submit">
      <UiAlert
        tone="info"
        title="修改仅对后续新建或重绘的资产、分镜与视频生效，不会改动已生成的成片与素材。"
      />

      <ArtStylePicker v-model="visualStyle" />

      <div class="proj-settings-row">
        <fieldset class="proj-settings-choice">
          <legend class="ui-label">画面比例</legend>
          <div class="proj-settings-segments proj-settings-ratios">
            <label v-for="item in videoRatios" :key="item">
              <input v-model="ratio" type="radio" :name="`${id}-ratio`" :value="item" />
              <span>{{ item }}</span>
            </label>
          </div>
        </fieldset>

        <div class="ui-field">
          <span class="ui-label">背景音乐</span>
          <div class="proj-settings-switch" :class="{ 'is-active': backgroundMusic }">
            <span class="proj-settings-switch-icon" aria-hidden="true">
              <Music :size="15" :stroke-width="1.8" />
            </span>
            <UiSwitch v-model="backgroundMusic" label="生成背景音乐" />
          </div>
        </div>
      </div>

      <fieldset class="proj-settings-card">
        <legend class="proj-settings-card-title">默认模型与单段上限</legend>
        <div class="proj-settings-card-body">
          <fieldset class="proj-settings-choice">
            <legend class="ui-label">单片段最长时长</legend>
            <div class="proj-settings-segments proj-settings-durations">
              <label v-for="duration in segmentDurations" :key="duration">
                <input
                  v-model="maxSegmentDuration"
                  type="radio"
                  :name="`${id}-duration`"
                  :value="duration"
                />
                <span>
                  <strong>{{ duration }} 秒</strong>
                  <small>{{ duration === 30 ? '长片段 · 更少剪辑切点' : '常规节奏 · 灵活分镜' }}</small>
                </span>
              </label>
            </div>
          </fieldset>

          <div class="ui-field">
            <span class="ui-label">默认视频模型（按 {{ maxSegmentDuration }} 秒档自动适配）</span>
            <VideoModelPicker
              v-model="selectedVideoModelId"
              :models="videoModels"
              :project-ratio="ratio"
              :min-max-duration="maxSegmentDuration === 30 ? 30 : undefined"
              placeholder="加载视频模型…"
            />
          </div>

          <div class="proj-settings-image-grid">
            <div class="ui-field">
              <span class="ui-label">默认图片模型</span>
              <ImageModelPicker
                v-model="selectedImageModelId"
                :models="imageModels"
                :tier="selectedImageTier"
                placeholder="加载图片模型…"
              />
            </div>

            <fieldset class="proj-settings-choice">
              <legend class="ui-label">默认图片清晰度</legend>
              <div
                class="proj-settings-segments"
                :style="{ gridTemplateColumns: `repeat(${Math.max(1, imageTierChoices.length)}, minmax(0, 1fr))` }"
              >
                <label v-for="opt in imageTierChoices" :key="opt.value">
                  <input
                    v-model="selectedImageTier"
                    type="radio"
                    :name="`${id}-tier`"
                    :value="opt.value"
                  />
                  <span>{{ opt.label }}</span>
                </label>
              </div>
            </fieldset>
          </div>
        </div>
      </fieldset>
    </form>

    <template #footer>
      <UiButton variant="ghost" :disabled="saving" @click="open = false">取消</UiButton>
      <UiButton
        type="submit"
        :form="formId"
        variant="primary"
        :loading="saving"
        :disabled="saving || !hasChanges"
      >
        <template v-if="!saving" #leading><Save :size="14" aria-hidden="true" /></template>
        保存配置
      </UiButton>
    </template>
  </UiDialog>
</template>

<style scoped>
.proj-settings-form {
  display: grid;
  gap: 16px;
}

.proj-settings-row {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(0, 1fr);
  gap: 14px;
  align-items: end;
}

.proj-settings-choice {
  margin: 0;
  padding: 0;
  border: 0;
  min-width: 0;
}

.proj-settings-choice > legend {
  margin-bottom: 6px;
}

.proj-settings-segments {
  display: grid;
  gap: 6px;
}

.proj-settings-ratios {
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.proj-settings-durations {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.proj-settings-segments label {
  position: relative;
  display: block;
  min-width: 0;
  cursor: pointer;
}

.proj-settings-segments input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.proj-settings-segments span {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  min-height: var(--control-height-md);
  padding: 6px 8px;
  border: 1px solid var(--border-control);
  border-radius: var(--radius-control);
  background: var(--color-canvas);
  color: var(--color-muted);
  font-size: 12px;
  text-align: center;
  transition: border-color 140ms ease, background-color 140ms ease, color 140ms ease;
}

.proj-settings-segments span strong {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
}

.proj-settings-segments span small {
  font-size: 11px;
  color: var(--color-muted);
}

.proj-settings-segments input:checked + span {
  border-color: var(--color-gold);
  background: var(--gold-tint);
  color: var(--color-gold-soft);
}

.proj-settings-segments input:checked + span strong {
  color: var(--color-gold-soft);
}

.proj-settings-segments input:focus-visible + span {
  outline: 2px solid var(--color-gold);
  outline-offset: 2px;
}

.proj-settings-switch {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: var(--control-height-md);
  padding: 0 12px;
  border: 1px solid var(--border-control);
  border-radius: var(--radius-control);
  background: var(--color-canvas);
}

.proj-settings-switch.is-active {
  border-color: rgb(240 184 75 / 35%);
}

.proj-settings-switch-icon {
  display: grid;
  place-items: center;
  color: var(--color-muted);
}

.proj-settings-switch.is-active .proj-settings-switch-icon {
  color: var(--color-gold-soft);
}

.proj-settings-card {
  margin: 0;
  padding: 12px 14px 14px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: rgb(255 255 255 / 2%);
}

.proj-settings-card-title {
  padding: 0 6px;
  color: var(--color-muted);
  font-size: 12px;
  font-weight: 500;
}

.proj-settings-card-body {
  display: grid;
  gap: 12px;
}

.proj-settings-image-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
  gap: 12px;
  align-items: end;
}

@media (max-width: 640px) {
  .proj-settings-row,
  .proj-settings-image-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
