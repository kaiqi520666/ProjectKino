<script setup lang="ts">
import { computed, ref, useId, useTemplateRef, watch } from 'vue'
import { ArrowLeft, Download, FolderOpen, History, ImageIcon, RefreshCw, Save, Sparkles, Trash2, Upload } from 'lucide-vue-next'
import ImagePreview from '@/components/ui/ImagePreview.vue'
import UiAlert from '@/components/ui/UiAlert.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import UiTextarea from '@/components/ui/UiTextarea.vue'
import { apiErrorMessage, uploadFileToOss } from '../api'
import type { ModelCatalogItemOut } from '../api-types'
import { assetKindOptions, exampleAssetLibrary } from '../studio-assets'
import type { StudioAsset, StudioAssetDraft, StudioAssetKind } from '../studio-assets'
import ImageModelPicker from './ImageModelPicker.vue'
import ImageParamsPopover from './ImageParamsPopover.vue'

const props = withDefaults(
  defineProps<{
    imageModels?: ModelCatalogItemOut[]
    persisted?: boolean
    generatingImage?: boolean
  }>(),
  {
    imageModels: () => [],
    persisted: false,
    generatingImage: false,
  },
)

const emit = defineEmits<{
  create: [kind: StudioAssetKind, draft: StudioAssetDraft]
  save: [id: string, draft: StudioAssetDraft]
  generateImage: [
    asset: StudioAsset,
    options: { modelId: string; tier: 'web' | '1k' | '2k' | '4k'; ratio: string; draft: StudioAssetDraft },
  ]
  openHistory: [asset: StudioAsset]
}>()

const formId = useId()
const open = ref(false)
const asset = ref<StudioAsset>()
const kind = ref<StudioAssetKind>('character')
const draft = ref<StudioAssetDraft>()
const picking = ref(false)
const loadingImage = ref(false)
const imageError = ref('')
const imageNotice = ref('')
const selectedModelId = ref('gpt-image-2')
const selectedTier = ref<'web' | '1k' | '2k' | '4k'>('1k')
const selectedRatio = ref('16:9')
const fileInput = useTemplateRef<HTMLInputElement>('fileInput')
const library = computed(() => exampleAssetLibrary[kind.value])

const modelCatalogList = computed<ModelCatalogItemOut[]>(() => props.imageModels)

const currentModel = computed(
  () => modelCatalogList.value.find((m) => m.id === selectedModelId.value) ?? modelCatalogList.value[0] ?? null,
)

const defaultRatio = computed(() => (kind.value === 'prop' ? '1:1' : '16:9'))

const estimatedAmount = computed(() => {
  const price = currentModel.value?.imagePrices.find((p) => p.tier === selectedTier.value)
  if (!price) return ''
  const num = Number(price.creditPrice)
  return Number.isFinite(num) ? String(Number(num.toFixed(2))) : ''
})

const canGenerateAiImage = computed(
  () =>
    props.persisted
    && !!asset.value?.backendId
    && !!currentModel.value
    && !!draft.value?.prompt.trim()
    && !loadingImage.value
    && !props.generatingImage,
)

const downloadName = computed(() => {
  const imageUrl = draft.value?.imageUrl ?? ''
  const extension = imageUrl.match(/^data:image\/(\w+);/u)?.[1] ?? imageUrl.match(/\.(\w+)$/u)?.[1]
  const name = draft.value?.name.trim() || asset.value?.name || '资产图片'
  return extension ? `${name}.${extension === 'jpeg' ? 'jpg' : extension}` : name
})
const imageTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/avif', 'image/bmp']
let opener: HTMLButtonElement | undefined

function edit(source: StudioAsset, trigger: HTMLButtonElement) {
  const { name, description, prompt, imageUrl, imageKey, voice } = source
  asset.value = source
  kind.value = source.kind
  const fallbackDefault = modelCatalogList.value.find((m) => m.isDefault)?.id || modelCatalogList.value[0]?.id || 'gpt-image-2'
  selectedModelId.value = source.imageModelId && modelCatalogList.value.some((m) => m.id === source.imageModelId)
    ? source.imageModelId
    : fallbackDefault
  const tierVal = source.imageTier
  selectedTier.value = tierVal === 'web' || tierVal === '1k' || tierVal === '2k' || tierVal === '4k' ? tierVal : '1k'
  selectedRatio.value = source.kind === 'prop' ? '1:1' : '16:9'
  openEditor({ name, description, prompt, imageUrl, imageKey, voice }, trigger)
}

function create(initialKind: StudioAssetKind, trigger: HTMLButtonElement) {
  kind.value = initialKind
  selectedRatio.value = initialKind === 'prop' ? '1:1' : '16:9'
  openEditor({ name: '', description: '', prompt: '', voice: '' }, trigger)
}

function openEditor(fields: StudioAssetDraft, trigger: HTMLButtonElement) {
  draft.value = fields
  opener = trigger
  open.value = true
}

function selectKind(value?: string) {
  const option = assetKindOptions.find((item) => item.value === value)
  if (option) {
    kind.value = option.value
    selectedRatio.value = option.value === 'prop' ? '1:1' : '16:9'
  }
}

function close() {
  open.value = false
}

watch(open, (isOpen) => {
  if (isOpen) return

  asset.value = undefined
  draft.value = undefined
  picking.value = false
  imageError.value = ''
  imageNotice.value = ''
  loadingImage.value = false
  const trigger = opener
  opener = undefined
  requestAnimationFrame(() => trigger?.focus({ preventScroll: true }))
}, { flush: 'sync' })

function chooseImage(imageUrl: string, imageKey?: string) {
  if (!draft.value) return

  draft.value.imageUrl = imageUrl
  draft.value.imageKey = imageKey
  imageError.value = ''
  picking.value = false
}

function removeImage() {
  if (draft.value) {
    draft.value.imageUrl = undefined
    draft.value.imageKey = undefined
  }
  imageError.value = ''
  imageNotice.value = ''
}

async function upload(event: Event) {
  const input = event.currentTarget as HTMLInputElement
  const file = input.files?.[0]
  const target = draft.value
  input.value = ''
  if (!file || !target) return

  imageError.value = ''
  imageNotice.value = ''
  if (!imageTypes.includes(file.type)) {
    imageError.value = '请选择 JPG、PNG、WebP、GIF、AVIF 或 BMP 图片。'
    return
  }

  loadingImage.value = true
  try {
    if (props.persisted) {
      try {
        const uploaded = await uploadFileToOss(file, 'image')
        if (draft.value === target) {
          chooseImage(uploaded.url, uploaded.key)
          imageNotice.value = '图片已直传至阿里云 OSS。'
        }
        return
      } catch (err) {
        // OSS 尚未配置时降级为本地预览，并给出清晰提示。
        const msg = apiErrorMessage(err)
        if (!msg.includes('OSS')) {
          if (draft.value === target) imageError.value = msg
          return
        }
        if (draft.value === target) {
          imageNotice.value = '阿里云 OSS 尚未配置，已暂存本地预览（生视频需先配置 OSS 后重新上传）。'
        }
      }
    }

    const imageUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = () => reject(reader.error)
      reader.readAsDataURL(file)
    })
    const image = new Image()
    image.src = imageUrl
    await image.decode()
    if (draft.value === target) chooseImage(imageUrl, undefined)
  } catch {
    if (draft.value === target) imageError.value = '无法读取这张图片，请换一张。'
  } finally {
    if (draft.value === target) loadingImage.value = false
  }
}

function triggerAiImage() {
  if (!asset.value || !draft.value || !canGenerateAiImage.value) return
  emit('generateImage', asset.value, {
    modelId: selectedModelId.value,
    tier: selectedTier.value,
    ratio: selectedRatio.value,
    draft: { ...draft.value },
  })
}

const historyCount = computed(() => asset.value?.imageHistory?.length ?? 0)
const canOpenHistory = computed(
  () =>
    props.persisted
    && !!asset.value?.backendId
    && (historyCount.value >= 2 || (!draft.value?.imageUrl && historyCount.value >= 1)),
)
const lastJobAlert = computed<{ tone: 'error' | 'warning'; title: string; message: string } | null>(() => {
  if (props.generatingImage || !asset.value) return null
  if (asset.value.lastJobStatus === 'review') {
    return {
      tone: 'warning',
      title: '最近一次重绘待后台核对（积分冻结中）',
      message: asset.value.lastJobError || '系统核对完成后将自动入库或退还冻结积分。',
    }
  }
  if (asset.value.lastJobStatus === 'failed') {
    return {
      tone: 'error',
      title: '最近一次重绘失败',
      message: asset.value.lastJobError || '请检查提示词或稍后重试。',
    }
  }
  return null
})

function syncAsset(updated: StudioAsset) {
  if (!asset.value) return
  if (asset.value.backendId !== updated.backendId && asset.value.id !== updated.id) return
  asset.value = updated
  if (draft.value) {
    draft.value.imageUrl = updated.imageUrl
    draft.value.imageKey = updated.imageKey
  }
}

function submit() {
  if (!draft.value?.name.trim() || loadingImage.value) return

  if (asset.value) emit('save', asset.value.id, draft.value)
  else emit('create', kind.value, draft.value)
}

defineExpose({ create, edit, close, syncAsset })
</script>

<template>
  <UiDialog v-model:open="open" :title="picking ? '从资产库选择' : asset ? '编辑资产' : '增加资产'" size="landscape">
    <div v-if="picking" class="asset-library">
      <p class="asset-library-label">示例图片</p>
      <div class="asset-library-grid">
        <button v-for="image in library" :key="image.imageUrl" type="button" class="asset-library-item" @click="chooseImage(image.imageUrl)">
          <img :src="image.imageUrl" alt="" />
          <span>{{ image.name }}</span>
        </button>
      </div>
    </div>

    <form v-else-if="draft" :id="formId" class="asset-edit-form" @submit.prevent="submit">
      <div class="asset-edit-fields">
        <UiSelect v-if="!asset" :model-value="kind" label="类型" :options="assetKindOptions" required @update:model-value="selectKind" />
        <UiInput v-model="draft.name" label="名称" required />
        <div class="asset-description-field">
          <UiTextarea v-model="draft.description" label="描述" :rows="2" />
        </div>
        <div v-if="kind === 'character'" class="asset-voice-field">
          <UiTextarea v-model="draft.voice" label="音色" :rows="2" />
        </div>
        <div class="asset-prompt-field">
          <UiTextarea v-model="draft.prompt" label="文生图提示词" :rows="4" />
        </div>
        <div v-if="asset" class="asset-ai-bar">
          <div class="asset-ai-controls">
            <ImageModelPicker
              v-model="selectedModelId"
              :models="modelCatalogList"
              :tier="selectedTier"
              :disabled="generatingImage"
            />
            <ImageParamsPopover
              v-model:tier="selectedTier"
              v-model:ratio="selectedRatio"
              :model="currentModel"
              :default-ratio="defaultRatio"
              mode="single"
              :disabled="generatingImage"
            />
          </div>
          <div class="asset-cta-split" :class="{ 'is-solo': !estimatedAmount || generatingImage }">
            <span v-if="estimatedAmount && !generatingImage" class="asset-cta-cost">
              <Sparkles :size="13" class="asset-cta-cost-icon" aria-hidden="true" />
              <strong class="asset-cta-cost-num">{{ estimatedAmount }}</strong>
              <span class="asset-cta-cost-unit">积分</span>
            </span>
            <UiButton
              class="asset-regenerate"
              variant="primary"
              size="sm"
              :loading="generatingImage"
              :disabled="!canGenerateAiImage"
              :title="!draft.prompt.trim() ? '请先填写文生图提示词' : '使用沧元图片引擎生成形象并自动存入 OSS'"
              @click="triggerAiImage"
            >
              <template v-if="!generatingImage" #leading><Sparkles :size="14" aria-hidden="true" /></template>
              {{ draft.imageUrl ? '重新生成形象' : 'AI 生成形象' }}
            </UiButton>
          </div>
        </div>
      </div>

      <div class="asset-edit-image">
        <span class="ui-label">图片</span>
        <input ref="fileInput" type="file" :accept="imageTypes.join(',')" hidden @change="upload" />
        <div class="asset-edit-preview">
          <ImagePreview v-if="draft.imageUrl" :src="draft.imageUrl" :title="draft.name.trim() || '资产图片'">
            <template #trigger>
              <button type="button" class="asset-image-open" aria-label="预览资产图片">
                <img :src="draft.imageUrl" alt="" />
              </button>
            </template>
          </ImagePreview>
          <div v-else class="asset-image-empty">
            <ImageIcon :size="25" :stroke-width="1.5" aria-hidden="true" />
            <span>暂无图片</span>
            <div class="asset-image-actions">
              <UiButton variant="outline" size="sm" :loading="loadingImage" @click="fileInput?.click()">
                <template #leading><Upload :size="14" aria-hidden="true" /></template>本地上传
              </UiButton>
              <UiButton variant="outline" size="sm" :disabled="loadingImage" @click="picking = true">
                <template #leading><FolderOpen :size="14" aria-hidden="true" /></template>资产库选择
              </UiButton>
              <UiButton
                v-if="canOpenHistory && asset"
                variant="outline"
                size="sm"
                :disabled="loadingImage"
                @click="emit('openHistory', asset)"
              >
                <template #leading><History :size="14" aria-hidden="true" /></template>历史 · {{ historyCount }}
              </UiButton>
            </div>
          </div>
        </div>
        <div v-if="draft.imageUrl" class="asset-image-actions asset-image-actions--filled">
          <UiButton
            v-if="canOpenHistory && asset"
            variant="outline"
            size="sm"
            :disabled="loadingImage || generatingImage"
            @click="emit('openHistory', asset)"
          >
            <template #leading><History :size="14" aria-hidden="true" /></template>历史 · {{ historyCount }}
          </UiButton>
          <UiButton variant="outline" size="sm" :disabled="loadingImage" @click="removeImage">
            <template #leading><Trash2 :size="14" aria-hidden="true" /></template>删除
          </UiButton>
          <UiButton variant="outline" size="sm" :loading="loadingImage" title="上传图片替换" @click="fileInput?.click()">
            <template #leading><RefreshCw :size="14" aria-hidden="true" /></template>更换
          </UiButton>
          <a class="ui-button ui-button--outline ui-button--sm" :href="draft.imageUrl" :download="downloadName" target="_blank" rel="noopener">
            <Download :size="14" aria-hidden="true" />下载
          </a>
        </div>
        <UiAlert v-if="lastJobAlert" :tone="lastJobAlert.tone" :title="lastJobAlert.title">
          {{ lastJobAlert.message }}
        </UiAlert>
        <p v-if="imageError" class="ui-field-message is-error" role="alert">{{ imageError }}</p>
        <p v-else-if="imageNotice" class="asset-image-notice">{{ imageNotice }}</p>
      </div>
    </form>

    <template #footer>
      <UiButton v-if="picking" variant="ghost" size="sm" @click="picking = false">
        <template #leading><ArrowLeft :size="14" aria-hidden="true" /></template>返回编辑
      </UiButton>
      <template v-else>
        <UiButton variant="ghost" size="sm" @click="close">取消</UiButton>
        <UiButton variant="primary" size="sm" type="submit" :form="formId" :disabled="!draft?.name.trim() || loadingImage">
          <template #leading><Save :size="14" aria-hidden="true" /></template>保存
        </UiButton>
      </template>
    </template>
  </UiDialog>
</template>

<style scoped>
.asset-edit-form {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1.15fr);
  gap: 24px;
  min-height: 100%;
}
.asset-edit-fields, .asset-edit-image { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.asset-description-field :deep(.ui-textarea) { min-height: 74px; }
.asset-voice-field :deep(.ui-textarea) { min-height: 64px; }
.asset-prompt-field, .asset-prompt-field :deep(.ui-field) { display: flex; flex: 1; flex-direction: column; }
.asset-prompt-field :deep(.ui-textarea) { flex: 1; min-height: 160px; border-radius: 8px; }
.asset-ai-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  background: var(--color-canvas);
}
.asset-ai-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.asset-cta-split {
  display: inline-flex;
  align-items: stretch;
  height: 36px;
  border-radius: 9px;
  overflow: hidden;
  border: 1px solid rgb(240 184 75 / 55%);
  box-shadow: 0 2px 10px rgb(240 184 75 / 12%);
  flex-shrink: 0;
}
.asset-cta-split.is-solo {
  border-color: transparent;
  box-shadow: none;
}
.asset-cta-cost {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0 11px;
  background: #13151c;
  color: var(--color-gold-soft);
  user-select: none;
}
.asset-cta-cost-icon {
  color: var(--color-gold);
  flex-shrink: 0;
}
.asset-cta-cost-num {
  font-size: 15px;
  font-weight: 700;
  color: #f8cc66;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  line-height: 1;
}
.asset-cta-cost-unit {
  font-size: 11px;
  font-weight: 500;
  color: rgb(248 204 102 / 82%);
  line-height: 1;
}
.asset-regenerate.ui-button {
  min-height: 34px;
  height: 100%;
  padding: 0 14px;
  border: 0;
  border-radius: 0;
  flex-shrink: 0;
}
.asset-cta-split.is-solo .asset-regenerate.ui-button {
  border-radius: 9px;
}
.asset-edit-preview {
  position: relative;
  display: grid;
  flex: 1;
  place-items: center;
  min-height: 164px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--color-canvas);
}
.asset-image-open { position: absolute; inset: 0; border-radius: inherit; cursor: zoom-in; }
.asset-image-open:focus-visible { outline-offset: -2px; }
.asset-image-open img { width: 100%; height: 100%; object-fit: contain; }
.asset-image-empty { display: grid; justify-items: center; gap: 8px; padding: 12px; color: var(--color-muted); font-size: var(--font-size-caption); }
.asset-image-actions { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; }
.asset-image-actions--filled { justify-content: flex-end; }
.asset-image-actions .ui-button { gap: 5px; padding-inline: 9px; }
.asset-image-notice { margin: 0; color: var(--color-muted); font-size: 12px; }
.asset-library-label { margin: 0 0 10px; color: var(--color-muted); font-size: var(--font-size-caption); }
.asset-library-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 320px)); gap: 10px; }
.asset-library-item {
  display: grid;
  gap: 6px;
  min-width: 0;
  padding: 6px;
  border: 1px solid var(--border-control);
  border-radius: 8px;
  background: var(--color-surface);
  color: var(--color-text);
  font-size: var(--font-size-body);
  cursor: pointer;
}
.asset-library-item img { width: 100%; aspect-ratio: 4 / 3; border-radius: 4px; object-fit: cover; }
.asset-library-item span { padding: 2px 4px; overflow-wrap: anywhere; }
.asset-library-item:hover, .asset-library-item:focus-visible { border-color: var(--color-gold); color: var(--color-gold-soft); }
@media (max-width: 640px) {
  .asset-edit-form { grid-template-columns: minmax(0, 1fr); gap: 16px; }
  .asset-edit-preview { min-height: 0; aspect-ratio: 4 / 3; }
}
</style>
