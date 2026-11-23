<script setup lang="ts">
import { computed, ref, useId, useTemplateRef, watch } from 'vue'
import {
  Download,
  FolderOpen,
  FolderPlus,
  History,
  ImageIcon,
  Plus,
  RefreshCw,
  Save,
  Sparkles,
  Trash2,
  Upload,
  X,
} from 'lucide-vue-next'
import ImagePreview from '@/components/ui/ImagePreview.vue'
import UiAlert from '@/components/ui/UiAlert.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import UiTextarea from '@/components/ui/UiTextarea.vue'
import AssetLibraryDialog from '@/features/assets/AssetLibraryDialog.vue'
import type { AssetLibraryItem } from '@/features/assets/asset-library-types'
import { useUserAssetsStore } from '@/features/assets/user-assets-store'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { apiErrorMessage, suggestVariantPromptApi, uploadFileToOss } from '../api'
import type { ModelCatalogItemOut } from '../api-types'
import {
  assetDisplayName,
  assetKindOptions,
  findParentAsset,
  variantLabelSuggestions,
} from '../studio-assets'
import type { StudioAsset, StudioAssetDraft, StudioAssetKind } from '../studio-assets'
import ImageModelPicker from './ImageModelPicker.vue'
import ImageParamsPopover from './ImageParamsPopover.vue'

interface ReferenceImageItem {
  url: string
  label: string
  isParent?: boolean
}

const props = withDefaults(
  defineProps<{
    projectId?: string
    imageModels?: ModelCatalogItemOut[]
    projectAssets?: StudioAsset[]
    persisted?: boolean
    generatingImage?: boolean
  }>(),
  {
    projectId: '',
    imageModels: () => [],
    projectAssets: () => [],
    persisted: false,
    generatingImage: false,
  },
)

const emit = defineEmits<{
  create: [kind: StudioAssetKind, draft: StudioAssetDraft]
  save: [id: string, draft: StudioAssetDraft]
  generateImage: [
    asset: StudioAsset,
    options: {
      modelId: string
      tier: 'web' | '1k' | '2k' | '4k'
      ratio: string
      referenceUrls: string[]
      draft: StudioAssetDraft
    },
  ]
  openHistory: [asset: StudioAsset]
}>()

const auth = useAuthStore()
const ui = useUiStore()
const userAssets = useUserAssetsStore()
const formId = useId()
const open = ref(false)
const asset = ref<StudioAsset>()
const parentForCreate = ref<StudioAsset>()
const kind = ref<StudioAssetKind>('character')
const draft = ref<StudioAssetDraft>()
const libraryOpen = ref(false)
const pickingTarget = ref<'image' | 'ref'>('image')
const loadingImage = ref(false)
const collectingAsset = ref(false)
const suggestingVariantPrompt = ref(false)
const imageError = ref('')
const imageNotice = ref('')
const selectedModelId = ref('gpt-image-2')
const selectedTier = ref<'web' | '1k' | '2k' | '4k'>('1k')
const selectedRatio = ref('16:9')
const selectedRefs = ref<ReferenceImageItem[]>([])
const fileInput = useTemplateRef<HTMLInputElement>('fileInput')

const labelSuggestions = computed(() => variantLabelSuggestions[kind.value])
const modelCatalogList = computed<ModelCatalogItemOut[]>(() => props.imageModels)

const resolvedParent = computed<StudioAsset | undefined>(() => {
  if (parentForCreate.value) return parentForCreate.value
  if (asset.value) return findParentAsset(props.projectAssets, asset.value)
  return undefined
})

const isVariant = computed(() => Boolean(parentForCreate.value || asset.value?.parentAssetId))

const currentModel = computed(
  () => modelCatalogList.value.find((m) => m.id === selectedModelId.value) ?? modelCatalogList.value[0] ?? null,
)

const maxRefImages = computed(() => {
  const raw = Number(currentModel.value?.capabilities?.maxReferenceImages)
  return Number.isFinite(raw) && raw > 0 ? Math.min(16, Math.round(raw)) : 9
})

const defaultRatio = computed(() => (kind.value === 'prop' ? '1:1' : '16:9'))

const estimatedAmount = computed(() => {
  const price = currentModel.value?.imagePrices.find((p) => p.tier === selectedTier.value)
  if (!price) return ''
  const num = Number(price.creditPrice)
  return Number.isFinite(num) ? String(Number(num.toFixed(2))) : ''
})

const canSuggestVariantPrompt = computed(
  () =>
    props.persisted
    && !!props.projectId
    && isVariant.value
    && !!resolvedParent.value?.backendId
    && !!(draft.value?.variantLabel ?? '').trim()
    && !suggestingVariantPrompt.value,
)

async function suggestVariantPromptWithAi() {
  const parent = resolvedParent.value
  const label = (draft.value?.variantLabel ?? '').trim()
  if (!props.projectId || !parent?.backendId || !label || !draft.value || suggestingVariantPrompt.value) return
  suggestingVariantPrompt.value = true
  try {
    const customNote =
      draft.value.description.trim() && draft.value.description.trim() !== parent.description.trim()
        ? draft.value.description.trim()
        : ''
    const result = await suggestVariantPromptApi(props.projectId, parent.backendId, {
      variantLabel: label,
      note: customNote,
    })
    if (draft.value) {
      draft.value.prompt = result.prompt
      if (!customNote && result.description) {
        draft.value.description = result.description
      }
    }
    void auth.refreshBalance()
    ui.notify(`已根据「${label}」生成锁脸/锁景变体提示词`, 'success')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    suggestingVariantPrompt.value = false
  }
}

const canGenerateAiImage = computed(
  () =>
    props.persisted
    && !!asset.value?.backendId
    && !!currentModel.value
    && !!draft.value?.prompt.trim()
    && !loadingImage.value
    && !props.generatingImage,
)

const canSubmit = computed(() => {
  if (!draft.value?.name.trim() || loadingImage.value) return false
  if (isVariant.value && !(draft.value.variantLabel ?? '').trim()) return false
  return true
})

const dialogTitle = computed(() => {
  if (asset.value) return isVariant.value ? '编辑变体' : '编辑资产'
  return isVariant.value ? `${parentForCreate.value?.name ?? ''} · 新增变体` : '增加资产'
})

const selectedRefUrls = computed(() => selectedRefs.value.map((r) => r.url))
const selectedRefUrlSet = computed(() => new Set(selectedRefUrls.value))

const canUseCurrentImageAsRef = computed(
  () =>
    !!draft.value?.imageUrl
    && isHttpUrl(draft.value.imageUrl)
    && !selectedRefUrlSet.value.has(draft.value.imageUrl)
    && selectedRefs.value.length < maxRefImages.value,
)

const canCollectToLibrary = computed(
  () => props.persisted && !!draft.value?.imageUrl && isHttpUrl(draft.value.imageUrl),
)

const downloadName = computed(() => {
  const imageUrl = draft.value?.imageUrl ?? ''
  const extension = imageUrl.match(/^data:image\/(\w+);/u)?.[1] ?? imageUrl.match(/\.(\w+)$/u)?.[1]
  const name = draft.value?.name.trim() || asset.value?.name || '资产图片'
  return extension ? `${name}.${extension === 'jpeg' ? 'jpg' : extension}` : name
})

const imageTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/avif', 'image/bmp']
let opener: HTMLButtonElement | undefined

function isHttpUrl(url?: string | null): url is string {
  return typeof url === 'string' && /^https?:\/\//i.test(url.trim())
}

function openPicker(target: 'image' | 'ref') {
  pickingTarget.value = target
  libraryOpen.value = true
}

function handleLibrarySelect(item: AssetLibraryItem) {
  if (!item.mediaUrl) return
  chooseImage(item.mediaUrl, item.mediaKey)
}

function handleLibraryConfirm(items: AssetLibraryItem[]) {
  const parentUrl = resolvedParent.value?.imageUrl
  const next: ReferenceImageItem[] = []
  const seen = new Set<string>()
  for (const item of items) {
    if (!item.mediaUrl || !isHttpUrl(item.mediaUrl) || seen.has(item.mediaUrl)) continue
    seen.add(item.mediaUrl)
    next.push({
      url: item.mediaUrl,
      label: item.title,
      isParent: Boolean(parentUrl && item.mediaUrl === parentUrl),
    })
  }
  selectedRefs.value = next.slice(0, maxRefImages.value)
}

function edit(source: StudioAsset, trigger: HTMLButtonElement) {
  const { name, description, prompt, imageUrl, imageKey, voice, parentAssetId, variantLabel } = source
  asset.value = source
  parentForCreate.value = undefined
  kind.value = source.kind

  const parent = findParentAsset(props.projectAssets, source)
  const initialRefs: ReferenceImageItem[] = []
  if (parent?.imageUrl && isHttpUrl(parent.imageUrl)) {
    initialRefs.push({ url: parent.imageUrl, label: `${parent.name}（主图）`, isParent: true })
  }
  selectedRefs.value = initialRefs

  const sunburstId = initialRefs.length
    ? modelCatalogList.value.find((m) => m.id === 'gpt-image-2.6-sunburst')?.id
    : undefined
  const fallbackDefault =
    sunburstId
    || modelCatalogList.value.find((m) => m.isDefault)?.id
    || modelCatalogList.value[0]?.id
    || 'gpt-image-2'
  selectedModelId.value = source.imageModelId && modelCatalogList.value.some((m) => m.id === source.imageModelId)
    ? source.imageModelId
    : fallbackDefault
  const tierVal = source.imageTier
  selectedTier.value = tierVal === 'web' || tierVal === '1k' || tierVal === '2k' || tierVal === '4k' ? tierVal : '1k'
  selectedRatio.value = source.kind === 'prop' ? '1:1' : '16:9'
  openEditor(
    { name, description, prompt, imageUrl, imageKey, voice, parentAssetId, variantLabel: variantLabel ?? '' },
    trigger,
  )
}

function create(initialKind: StudioAssetKind, trigger: HTMLButtonElement) {
  asset.value = undefined
  parentForCreate.value = undefined
  selectedRefs.value = []
  kind.value = initialKind
  selectedRatio.value = initialKind === 'prop' ? '1:1' : '16:9'
  openEditor({ name: '', description: '', prompt: '', voice: '', variantLabel: '' }, trigger)
}

function createVariant(parent: StudioAsset, trigger: HTMLButtonElement) {
  asset.value = undefined
  parentForCreate.value = parent
  selectedRefs.value =
    parent.imageUrl && isHttpUrl(parent.imageUrl)
      ? [{ url: parent.imageUrl, label: `${parent.name}（主图）`, isParent: true }]
      : []
  kind.value = parent.kind
  selectedRatio.value = parent.kind === 'prop' ? '1:1' : '16:9'
  openEditor(
    {
      name: parent.name,
      description: parent.description,
      prompt: parent.prompt,
      voice: parent.voice ?? '',
      parentAssetId: parent.backendId,
      variantLabel: '',
    },
    trigger,
  )
}

function openEditor(fields: StudioAssetDraft, trigger: HTMLButtonElement) {
  draft.value = fields
  opener = trigger
  libraryOpen.value = false
  loadingImage.value = false
  imageError.value = ''
  imageNotice.value = ''
  open.value = true
}

function selectKind(value: string | undefined) {
  if (value === 'character' || value === 'scene' || value === 'prop') {
    kind.value = value
    if (draft.value && value !== 'character') draft.value.voice = ''
    selectedRatio.value = value === 'prop' ? '1:1' : '16:9'
  }
}

function close() {
  open.value = false
}

watch(open, (isOpen) => {
  if (isOpen) return
  const trigger = opener
  opener = undefined
  asset.value = undefined
  parentForCreate.value = undefined
  draft.value = undefined
  selectedRefs.value = []
  libraryOpen.value = false
  loadingImage.value = false
  imageError.value = ''
  imageNotice.value = ''
  requestAnimationFrame(() => trigger?.focus({ preventScroll: true }))
}, { flush: 'sync' })

function chooseImage(imageUrl: string, imageKey?: string) {
  if (!draft.value) return
  draft.value.imageUrl = imageUrl
  draft.value.imageKey = imageKey
  imageError.value = ''
  libraryOpen.value = false
}

function toggleReference(url: string, label: string, isParent = false) {
  if (!isHttpUrl(url)) return
  const idx = selectedRefs.value.findIndex((item) => item.url === url)
  if (idx >= 0) {
    selectedRefs.value = selectedRefs.value.filter((item) => item.url !== url)
    return
  }
  if (selectedRefs.value.length >= maxRefImages.value) {
    ui.notify(`当前模型最多支持 ${maxRefImages.value} 张参考图`, 'info')
    return
  }
  selectedRefs.value = [...selectedRefs.value, { url, label, isParent }]
}

function removeReference(url: string) {
  selectedRefs.value = selectedRefs.value.filter((item) => item.url !== url)
}

function addCurrentImageAsRef() {
  if (!draft.value?.imageUrl || !canUseCurrentImageAsRef.value) return
  toggleReference(draft.value.imageUrl, '当前图片')
}

function removeImage() {
  if (draft.value) {
    draft.value.imageUrl = undefined
    draft.value.imageKey = undefined
  }
  imageError.value = ''
  imageNotice.value = ''
}

async function collectToLibrary() {
  if (!draft.value?.imageUrl || !canCollectToLibrary.value || collectingAsset.value) return
  collectingAsset.value = true
  try {
    const title = assetDisplayName({
      name: draft.value.name.trim() || asset.value?.name || '短剧资产图',
      variantLabel: draft.value.variantLabel,
    })
    await userAssets.createAsset({
      kind: 'image',
      title,
      mediaUrl: draft.value.imageUrl,
      mediaKey: draft.value.imageKey ?? null,
      mediaName: downloadName.value,
      sourceType: 'studio',
      sourceId: asset.value?.backendId ?? null,
    })
    ui.notify(`已收藏「${title}」到素材库`, 'success')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  } finally {
    collectingAsset.value = false
  }
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
    referenceUrls: selectedRefs.value.map((item) => item.url),
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
  if (!draft.value || !canSubmit.value) return
  if (asset.value) emit('save', asset.value.id, draft.value)
  else emit('create', kind.value, draft.value)
}

defineExpose({ create, createVariant, edit, close, syncAsset })
</script>

<template>
  <UiDialog v-model:open="open" :title="dialogTitle" size="landscape">
    <form v-if="draft" :id="formId" class="asset-edit-form" @submit.prevent="submit">
      <div class="asset-edit-fields">
        <UiSelect
          v-if="!asset && !isVariant"
          :model-value="kind"
          label="类型"
          :options="assetKindOptions"
          required
          @update:model-value="selectKind"
        />
        <div v-if="isVariant" class="asset-variant-box">
          <UiInput
            v-model="draft.variantLabel"
            label="状态标签"
            placeholder="例如：晚宴礼服、深夜、碎裂"
            required
          />
          <div class="asset-variant-suggestions">
            <button
              v-for="chip in labelSuggestions"
              :key="chip"
              type="button"
              class="asset-variant-chip"
              :class="{ 'is-active': draft.variantLabel === chip }"
              @click="draft.variantLabel = chip"
            >
              {{ chip }}
            </button>
          </div>
        </div>
        <UiInput v-model="draft.name" label="名称" required />
        <div class="asset-description-field">
          <UiTextarea v-model="draft.description" label="描述" :rows="2" />
        </div>
        <div v-if="kind === 'character'" class="asset-voice-field">
          <UiTextarea v-model="draft.voice" label="音色" :rows="2" />
        </div>
        <div class="asset-prompt-field">
          <div class="asset-prompt-head">
            <span class="ui-label">文生图提示词</span>
            <UiButton
              v-if="isVariant && persisted && resolvedParent?.backendId"
              type="button"
              variant="outline"
              size="sm"
              :loading="suggestingVariantPrompt"
              :disabled="!canSuggestVariantPrompt"
              title="根据状态标签自动改写参考图锁脸/锁景提示词"
              @click="suggestVariantPromptWithAi"
            >
              <template v-if="!suggestingVariantPrompt" #leading><Sparkles :size="13" aria-hidden="true" /></template>
              AI 生成变体提示词
            </UiButton>
          </div>
          <UiTextarea
            v-model="draft.prompt"
            aria-label="文生图提示词"
            :rows="4"
          />
        </div>
        <div v-if="asset" class="asset-ai-bar">
          <div v-if="persisted" class="asset-ref-bar">
            <div class="asset-ref-head">
              <span class="asset-ref-title">
                参考图（{{ selectedRefs.length }}/{{ maxRefImages }}）
              </span>
              <div class="asset-ref-actions">
                <button
                  v-if="canUseCurrentImageAsRef"
                  type="button"
                  class="asset-ref-action"
                  @click="addCurrentImageAsRef"
                >
                  + 用当前图微调
                </button>
                <button
                  type="button"
                  class="asset-ref-action"
                  :disabled="selectedRefs.length >= maxRefImages"
                  @click="openPicker('ref')"
                >
                  <Plus :size="11" aria-hidden="true" />选参考图
                </button>
              </div>
            </div>
            <div v-if="selectedRefs.length" class="asset-ref-list">
              <div v-for="refItem in selectedRefs" :key="refItem.url" class="asset-ref-chip" :title="refItem.label">
                <img :src="refItem.url" alt="" />
                <span>{{ refItem.isParent ? '主图' : refItem.label }}</span>
                <button type="button" aria-label="移除参考图" @click="removeReference(refItem.url)">
                  <X :size="11" aria-hidden="true" />
                </button>
              </div>
            </div>
          </div>

          <div class="asset-ai-row">
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
                @click="triggerAiImage"
              >
                <template v-if="!generatingImage" #leading><Sparkles :size="14" aria-hidden="true" /></template>
                {{ selectedRefs.length ? '垫图生成' : draft.imageUrl ? '重新生成形象' : 'AI 生成形象' }}
              </UiButton>
            </div>
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
              <UiButton variant="outline" size="sm" :disabled="loadingImage" @click="openPicker('image')">
                <template #leading><FolderOpen :size="14" aria-hidden="true" /></template>素材库
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
          <UiButton
            v-if="canCollectToLibrary"
            variant="outline"
            size="sm"
            :loading="collectingAsset"
            @click="collectToLibrary"
          >
            <template v-if="!collectingAsset" #leading><FolderPlus :size="14" aria-hidden="true" /></template>收藏
          </UiButton>
          <UiButton variant="outline" size="sm" :disabled="loadingImage" @click="openPicker('image')">
            <template #leading><FolderOpen :size="14" aria-hidden="true" /></template>素材库
          </UiButton>
          <UiButton variant="outline" size="sm" :disabled="loadingImage" @click="removeImage">
            <template #leading><Trash2 :size="14" aria-hidden="true" /></template>删除
          </UiButton>
          <UiButton variant="outline" size="sm" :loading="loadingImage" @click="fileInput?.click()">
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
      <UiButton variant="ghost" size="sm" @click="close">取消</UiButton>
      <UiButton variant="primary" size="sm" type="submit" :form="formId" :disabled="!canSubmit">
        <template #leading><Save :size="14" aria-hidden="true" /></template>保存
      </UiButton>
    </template>
  </UiDialog>

  <AssetLibraryDialog
    v-model:open="libraryOpen"
    :title="pickingTarget === 'ref' ? '选择参考图' : '素材库'"
    :mode="pickingTarget === 'ref' ? 'multiple' : 'single'"
    :allowed-kinds="['image']"
    :project-assets="projectAssets"
    :default-source="pickingTarget === 'ref' ? 'project' : 'personal'"
    :initial-selected-keys="pickingTarget === 'ref' ? selectedRefUrls : []"
    :max-by-kind="pickingTarget === 'ref' ? { image: maxRefImages } : undefined"
    :require-http-url="pickingTarget === 'ref'"
    @select="handleLibrarySelect"
    @confirm="handleLibraryConfirm"
  />
</template>

<style scoped>
.asset-edit-form {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1.15fr);
  gap: 24px;
  min-height: 100%;
}
.asset-edit-fields, .asset-edit-image { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.asset-prompt-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.asset-variant-box {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--color-gold) 35%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--gold-tint) 45%, var(--color-canvas));
}
.asset-variant-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.asset-variant-chip {
  padding: 2px 8px;
  border: 1px solid var(--border-control);
  border-radius: 999px;
  background: var(--color-surface);
  color: var(--color-muted);
  font-size: 11px;
  cursor: pointer;
}
.asset-variant-chip:hover,
.asset-variant-chip.is-active {
  border-color: var(--color-gold);
  color: var(--color-gold-soft);
  background: var(--gold-tint);
}
.asset-description-field :deep(.ui-textarea) { min-height: 70px; }
.asset-voice-field :deep(.ui-textarea) { min-height: 60px; }
.asset-prompt-field, .asset-prompt-field :deep(.ui-field) { display: flex; flex: 1; flex-direction: column; }
.asset-prompt-field :deep(.ui-textarea) { flex: 1; min-height: 140px; border-radius: 8px; }
.asset-ai-bar {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  background: var(--color-canvas);
}
.asset-ref-bar {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}
.asset-ref-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
.asset-ref-title {
  font-size: 12px;
  color: var(--color-text);
  font-weight: 500;
}
.asset-ref-title small {
  margin-left: 6px;
  color: var(--color-muted);
  font-weight: 400;
}
.asset-ref-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.asset-ref-action {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 7px;
  border: 1px solid var(--border-control);
  border-radius: 5px;
  background: var(--color-surface);
  color: var(--color-muted);
  font-size: 11px;
  cursor: pointer;
}
.asset-ref-action:hover:not(:disabled) {
  border-color: var(--color-gold);
  color: var(--color-gold-soft);
}
.asset-ref-action:disabled { opacity: 0.45; cursor: not-allowed; }
.asset-ref-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.asset-ref-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 160px;
  padding: 2px 5px 2px 3px;
  border: 1px solid color-mix(in srgb, var(--color-gold) 40%, transparent);
  border-radius: 6px;
  background: var(--color-surface);
  font-size: 11px;
  color: var(--color-text);
}
.asset-ref-chip img {
  flex: none;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  object-fit: cover;
}
.asset-ref-chip span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.asset-ref-chip button {
  flex: none;
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  border-radius: 4px;
  color: var(--color-muted);
  cursor: pointer;
}
.asset-ref-chip button:hover { color: var(--color-error); }
.asset-ai-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
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
@media (max-width: 640px) {
  .asset-edit-form { grid-template-columns: 1fr; }
}
</style>
