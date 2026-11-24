<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Plus, Trash2 } from 'lucide-vue-next'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import {
  createAdminModel,
  updateAdminModel,
  type AdminImagePrice,
  type AdminModelItem,
  type AdminProvider,
} from '@/features/admin/api'
import { extractErrorMessage } from '@/lib/format'
import { useUiStore } from '@/stores/ui'

const ALL_RESOLUTIONS = ['480p', '720p', '1080p'] as const
const ALL_RATIOS = ['16:9', '9:16', '1:1', '4:3', '3:4', '21:9'] as const
const ALL_IMAGE_RATIOS = ['16:9', '9:16', '1:1', '4:3', '3:4', '3:2', '2:3', '5:4', '4:5', '21:9', '9:21', 'auto'] as const
const ALL_TIERS = ['web', '1k', '2k', '4k'] as const
const VIDEO_CATEGORY_PRESETS = ['Seedance 2.0', 'Seedance 2.5', 'Seedance 2.5 Flash', 'Wan 3.0'] as const
const IMAGE_CATEGORY_PRESETS = ['GPT Image 2', 'GPT Image 2.5', 'GPT Image 2.6', 'Gemini 图像'] as const
const TEXT_CATEGORY_PRESETS = ['OpenRouter'] as const
const IMAGE_PROTOCOL_OPTIONS = [
  { value: 'gpt_image', label: 'GPT Image（tier + quality）' },
  { value: 'gemini_quality', label: 'Gemini 图像（quality = 1k/2k/4k）' },
] as const
const IMAGE_SERIES_OPTIONS = [
  { value: '', label: '标准（无变体）' },
  { value: 'flare', label: 'Flare 极速' },
  { value: 'sunburst', label: 'Sunburst 精修' },
] as const
const IMAGE_QUALITY_OPTIONS = [
  { value: 'medium', label: 'medium' },
  { value: 'high', label: 'high' },
  { value: 'xhigh', label: 'xhigh' },
  { value: 'max', label: 'max' },
] as const

const enabledOptions = [
  { value: 'true', label: '启用' },
  { value: 'false', label: '停用' },
]

const defaultOptions = [
  { value: 'true', label: '设为默认' },
  { value: 'false', label: '非默认' },
]

const mediaTypeCreateOptions = [
  { value: 'video', label: '生视频' },
  { value: 'image', label: '生图' },
  { value: 'text', label: '文本' },
]

const tierOptions = [
  { value: 'web', label: 'web' },
  { value: '1k', label: '1k' },
  { value: '2k', label: '2k' },
  { value: '4k', label: '4k' },
]

const props = withDefaults(
  defineProps<{
    providers: AdminProvider[]
    target: AdminModelItem | null
    defaultMediaType?: 'text' | 'image' | 'video'
  }>(),
  {
    defaultMediaType: 'video',
  },
)

const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{
  saved: []
}>()

const ui = useUiStore()
const submitting = ref(false)

const isCreate = computed(() => props.target === null)
const providerSelectOptions = computed(() =>
  props.providers.map((p) => ({ value: p.key, label: `${p.displayName} (${p.key})` })),
)
const currentCategoryPresets = computed(() => {
  if (form.mediaType === 'image') return IMAGE_CATEGORY_PRESETS
  if (form.mediaType === 'text') return TEXT_CATEGORY_PRESETS
  return VIDEO_CATEGORY_PRESETS
})

const form = reactive({
  id: '',
  providerKey: 'cc',
  mediaType: 'video' as 'text' | 'image' | 'video',
  category: 'Seedance 2.0',
  displayName: '',
  description: '',
  upstreamModelId: '',
  enabled: 'true',
  isDefault: 'false',
  isDefaultLong: 'false',
  sort: '100',
  resolutions: ['720p'] as string[],
  ratios: [...ALL_RATIOS] as string[],
  minDuration: '4',
  maxDuration: '15',
  maxPromptChars: '5000',
  maxReferenceImages: '9',
  maxReferenceVideos: '3',
  maxReferenceAudios: '3',
  videoUnit: 'call' as 'call' | 'second',
  videoCreditPrice: '15',
  textInputPrice: '0',
  textCachedPrice: '0',
  textOutputPrice: '0',
  imageProtocol: 'gpt_image' as 'gpt_image' | 'gemini_quality',
  imageSeries: '' as '' | 'flare' | 'sunburst',
  imageQuality: 'high',
  imageRatios: [...ALL_IMAGE_RATIOS] as string[],
  imagePrices: [] as AdminImagePrice[],
})

function primaryVideoPrice(m: AdminModelItem) {
  return m.videoPrices.find((p) => p.ruleKey === 'default') ?? m.videoPrices[0] ?? null
}

function initForm() {
  const m = props.target
  if (!m) {
    const createImage = props.defaultMediaType === 'image'
    const createText = props.defaultMediaType === 'text'
    form.id = ''
    form.providerKey = createImage ? 'cangyuan' : createText ? 'openrouter' : 'cc'
    form.mediaType = createImage ? 'image' : createText ? 'text' : 'video'
    form.category = createImage ? 'GPT Image 2.6' : createText ? 'OpenRouter' : 'Seedance 2.0'
    form.displayName = ''
    form.description = ''
    form.upstreamModelId = createImage ? 'gpt-image-2.6-x' : createText ? '@preset/ds-baidu' : ''
    form.enabled = 'true'
    form.isDefault = 'false'
    form.isDefaultLong = 'false'
    form.sort = '50'
    form.resolutions = ['720p']
    form.ratios = [...ALL_RATIOS]
    form.minDuration = '4'
    form.maxDuration = '15'
    form.maxPromptChars = '5000'
    form.maxReferenceImages = '9'
    form.maxReferenceVideos = '3'
    form.maxReferenceAudios = '3'
    form.videoUnit = 'call'
    form.videoCreditPrice = '15'
    form.textInputPrice = createText ? '2' : '0'
    form.textCachedPrice = createText ? '0.2' : '0'
    form.textOutputPrice = createText ? '3' : '0'
    form.imageProtocol = 'gpt_image'
    form.imageSeries = createImage ? 'flare' : ''
    form.imageQuality = 'high'
    form.imageRatios = [...ALL_IMAGE_RATIOS]
    form.imagePrices = [
      { tier: 'web', creditPrice: '2' },
      { tier: '1k', creditPrice: '3.5' },
      { tier: '2k', creditPrice: '6' },
      { tier: '4k', creditPrice: '10' },
    ]
    return
  }

  const caps = m.capabilities || {}
  const cfg = m.configuration || {}
  const vp = primaryVideoPrice(m)

  form.id = m.id
  form.providerKey = m.providerKey
  form.mediaType = m.mediaType
  form.category = m.category || ''
  form.displayName = m.displayName
  form.description = typeof caps.description === 'string' ? caps.description : ''
  form.upstreamModelId = m.upstreamModelId
  form.enabled = m.enabled ? 'true' : 'false'
  form.isDefault = m.isDefault ? 'true' : 'false'
  form.isDefaultLong = m.isDefaultLong ? 'true' : 'false'
  form.sort = String(m.sort)

  form.resolutions = Array.isArray(caps.resolutions) && caps.resolutions.length
    ? caps.resolutions.map(String)
    : ['720p']
  form.ratios = Array.isArray(caps.ratios) && caps.ratios.length
    ? caps.ratios.map(String)
    : [...ALL_RATIOS]
  form.minDuration = String(caps.minDuration ?? 4)
  form.maxDuration = String(caps.maxDuration ?? 15)
  form.maxPromptChars = String(caps.maxPromptChars ?? 5000)
  form.maxReferenceImages = String(caps.maxReferenceImages ?? 9)
  form.maxReferenceVideos = String(caps.maxReferenceVideos ?? 3)
  form.maxReferenceAudios = String(caps.maxReferenceAudios ?? 3)
  form.videoUnit = vp?.unit ?? 'call'
  form.videoCreditPrice = vp?.creditPrice ?? '0'

  form.textInputPrice = m.textPrice?.inputPricePerMillion ?? '0'
  form.textCachedPrice = m.textPrice?.cachedInputPricePerMillion ?? '0'
  form.textOutputPrice = m.textPrice?.outputPricePerMillion ?? '0'

  form.imageProtocol = cfg.protocol === 'gemini_quality' ? 'gemini_quality' : 'gpt_image'
  const rawSeries = cfg.series ?? caps.variant
  form.imageSeries = rawSeries === 'flare' || rawSeries === 'sunburst' ? rawSeries : ''
  form.imageQuality = typeof cfg.quality === 'string' && cfg.quality ? cfg.quality : 'high'
  form.imageRatios = Array.isArray(caps.ratios) && caps.ratios.length
    ? caps.ratios.map(String)
    : [...ALL_IMAGE_RATIOS]
  form.imagePrices = m.imagePrices.map((x) => ({ ...x }))
}

watch(
  () => [open.value, props.target, props.defaultMediaType] as const,
  ([isOpen]) => {
    if (isOpen) initForm()
  },
)

watch(
  () => form.maxDuration,
  (val) => {
    if ((Number.parseInt(val, 10) || 15) < 30 && form.isDefaultLong === 'true') {
      form.isDefaultLong = 'false'
    }
  },
)

function toggleResolution(res: string) {
  if (form.resolutions.includes(res)) {
    if (form.resolutions.length <= 1) return
    form.resolutions = form.resolutions.filter((r) => r !== res)
  } else {
    form.resolutions = [...form.resolutions, res]
  }
}

function toggleRatio(ratio: string) {
  if (form.ratios.includes(ratio)) {
    if (form.ratios.length <= 1) return
    form.ratios = form.ratios.filter((r) => r !== ratio)
  } else {
    form.ratios = [...form.ratios, ratio]
  }
}

function toggleImageRatio(ratio: string) {
  if (form.imageRatios.includes(ratio)) {
    if (form.imageRatios.length <= 1) return
    form.imageRatios = form.imageRatios.filter((r) => r !== ratio)
  } else {
    form.imageRatios = [...form.imageRatios, ratio]
  }
}

function addImagePriceRow() {
  const used = new Set(form.imagePrices.map((x) => x.tier))
  const next = ALL_TIERS.find((t) => !used.has(t))
  if (!next) {
    ui.notify('所有分辨率档位均已添加', 'info')
    return
  }
  form.imagePrices.push({ tier: next, creditPrice: '0' })
}

function removeImagePriceRow(index: number) {
  form.imagePrices.splice(index, 1)
}

async function submit() {
  if (!form.displayName.trim() || !form.upstreamModelId.trim()) {
    ui.notify('模型名称和上游模型名不能为空', 'error')
    return
  }
  const sortNum = Number.parseInt(form.sort, 10)
  if (!Number.isFinite(sortNum)) {
    ui.notify('排序必须为整数', 'error')
    return
  }

  let capabilities: Record<string, unknown> = props.target ? { ...props.target.capabilities } : {}
  let defaults: Record<string, unknown> = props.target ? { ...props.target.defaults } : {}
  let configuration: Record<string, unknown> = props.target?.configuration
    ? { ...props.target.configuration }
    : {}

  if (form.mediaType === 'video') {
    const minD = Math.max(1, Number.parseInt(form.minDuration, 10) || 4)
    const maxD = Math.max(minD, Number.parseInt(form.maxDuration, 10) || 15)
    const maxPrompt = Math.max(100, Number.parseInt(form.maxPromptChars, 10) || 5000)
    const maxImg = Math.max(0, Number.parseInt(form.maxReferenceImages, 10) || 0)
    const maxVid = Math.max(0, Number.parseInt(form.maxReferenceVideos, 10) || 0)
    const maxAud = Math.max(0, Number.parseInt(form.maxReferenceAudios, 10) || 0)
    const orderedRes = ALL_RESOLUTIONS.filter((r) => form.resolutions.includes(r))
    const orderedRatios = ALL_RATIOS.filter((r) => form.ratios.includes(r))

    capabilities = {
      ...capabilities,
      description: form.description.trim(),
      resolutions: orderedRes.length ? orderedRes : ['720p'],
      ratios: orderedRatios.length ? orderedRatios : [...ALL_RATIOS],
      minDuration: minD,
      maxDuration: maxD,
      maxPromptChars: maxPrompt,
      maxReferenceImages: maxImg,
      maxReferenceVideos: maxVid,
      maxReferenceAudios: maxAud,
    }
    defaults = { ...defaults, resolution: orderedRes[0] ?? '720p' }
  } else if (form.mediaType === 'image') {
    const orderedTiers = ALL_TIERS.filter((t) => form.imagePrices.some((p) => p.tier === t))
    const orderedImgRatios = ALL_IMAGE_RATIOS.filter((r) => form.imageRatios.includes(r))
    const isGemini = form.imageProtocol === 'gemini_quality'
    const maxImgRefs = Math.max(0, Number.parseInt(form.maxReferenceImages, 10) || (isGemini ? 14 : 9))
    capabilities = {
      ...capabilities,
      description: form.description.trim(),
      variant: isGemini ? '' : form.imageSeries,
      tiers: orderedTiers.length ? orderedTiers : (isGemini ? ['1k', '2k', '4k'] : ['web', '1k', '2k', '4k']),
      ratios: orderedImgRatios.length ? orderedImgRatios : [...ALL_IMAGE_RATIOS],
      aspectRatios: { character: '16:9', scene: '16:9', prop: '1:1' },
      maxReferenceImages: maxImgRefs,
      supportsMask: !isGemini,
    }
    defaults = { ...defaults, tier: orderedTiers.includes('1k') ? '1k' : (orderedTiers[0] ?? '1k') }
    if (isGemini) {
      configuration = {
        ...configuration,
        protocol: 'gemini_quality',
        pollBySubmitEndpoint: true,
      }
      delete configuration.series
      delete configuration.quality
    } else {
      configuration = {
        ...configuration,
        quality: form.imageQuality || 'high',
      }
      delete configuration.protocol
      delete configuration.pollBySubmitEndpoint
      if (form.imageSeries) {
        configuration.series = form.imageSeries
      } else {
        delete configuration.series
      }
    }
  }

  const priceFields: {
    textPrice?: { inputPricePerMillion: string; cachedInputPricePerMillion: string; outputPricePerMillion: string }
    imagePrices?: AdminImagePrice[]
    videoPrices?: { ruleKey: string; unit: 'call' | 'second'; creditPrice: string }[]
  } = {}

  if (form.mediaType === 'text') {
    priceFields.textPrice = {
      inputPricePerMillion: String(form.textInputPrice).trim() || '0',
      cachedInputPricePerMillion: String(form.textCachedPrice).trim() || '0',
      outputPricePerMillion: String(form.textOutputPrice).trim() || '0',
    }
  } else if (form.mediaType === 'image') {
    priceFields.imagePrices = form.imagePrices.map((row) => ({
      tier: row.tier,
      creditPrice: String(row.creditPrice).trim() || '0',
    }))
  } else {
    priceFields.videoPrices = [
      {
        ruleKey: 'default',
        unit: form.videoUnit,
        creditPrice: String(form.videoCreditPrice).trim() || '0',
      },
    ]
  }

  submitting.value = true
  try {
    if (isCreate.value) {
      const modelId = form.id.trim() || form.upstreamModelId.trim()
      await createAdminModel({
        id: modelId,
        providerKey: form.providerKey,
        mediaType: form.mediaType,
        category: form.category.trim(),
        displayName: form.displayName.trim(),
        upstreamModelId: form.upstreamModelId.trim(),
        enabled: form.enabled === 'true',
        isDefault: form.isDefault === 'true',
        isDefaultLong: form.mediaType === 'video' && form.isDefaultLong === 'true',
        sort: sortNum,
        capabilities,
        defaults,
        configuration,
        ...priceFields,
      })
      ui.notify(`已新增模型 ${form.displayName.trim()}`, 'success')
    } else if (props.target) {
      await updateAdminModel(props.target.id, {
        category: form.category.trim(),
        displayName: form.displayName.trim(),
        upstreamModelId: form.upstreamModelId.trim(),
        enabled: form.enabled === 'true',
        isDefault: form.isDefault === 'true',
        isDefaultLong: form.mediaType === 'video' ? form.isDefaultLong === 'true' : false,
        sort: sortNum,
        capabilities,
        defaults,
        configuration,
        ...priceFields,
      })
      ui.notify(`已保存 ${form.displayName.trim()}`, 'success')
    }
    open.value = false
    emit('saved')
  } catch (err) {
    ui.notify(extractErrorMessage(err, '保存模型失败'), 'error')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <UiDialog
    v-model:open="open"
    size="wide"
    :title="isCreate ? '新建模型' : `配置模型 · ${target?.id}`"
  >
    <div class="admin-form-stack">
      <div v-if="isCreate" class="admin-form-grid-3">
        <div class="ui-field">
          <label class="ui-label">模型 ID <span class="ui-required">*</span></label>
          <input v-model="form.id" class="ui-input admin-mono" type="text" placeholder="如 cc-sd2.5-flash-720" />
        </div>
        <UiSelect v-model="form.providerKey" label="供应商" :options="providerSelectOptions" />
        <UiSelect v-model="form.mediaType" label="类型" :options="mediaTypeCreateOptions" />
      </div>

      <div class="admin-settings-grid">
        <div class="ui-field">
          <label class="ui-label">前端名称 <span class="ui-required">*</span></label>
          <input v-model="form.displayName" class="ui-input" type="text" placeholder="如 Seedance 2.5 Flash 720p" />
        </div>
        <div class="ui-field">
          <label class="ui-label">上游模型名 <span class="ui-required">*</span></label>
          <input v-model="form.upstreamModelId" class="ui-input admin-mono" type="text" placeholder="如 cc-sd2.5-flash-720" />
        </div>
      </div>

      <div v-if="form.mediaType === 'video' || form.mediaType === 'image'" class="ui-field">
        <label class="ui-label">模型简介</label>
        <input v-model="form.description" class="ui-input" type="text" placeholder="选填，一句话介绍特点，显示在前端模型卡片中" />
      </div>

      <div class="ui-field">
        <label class="ui-label">系列分类</label>
        <input v-model="form.category" class="ui-input" type="text" placeholder="自定义或点下方快捷填入" />
        <div class="admin-chip-group">
          <button
            v-for="preset in currentCategoryPresets"
            :key="preset"
            type="button"
            class="admin-chip"
            :class="{ 'is-active': form.category === preset }"
            @click="form.category = preset"
          >
            {{ preset }}
          </button>
        </div>
      </div>

      <template v-if="form.mediaType === 'video'">
        <div class="admin-settings-grid">
          <div class="ui-field">
            <label class="ui-label">计费方式</label>
            <div class="admin-chip-group">
              <button
                type="button"
                class="admin-chip"
                :class="{ 'is-active': form.videoUnit === 'call' }"
                @click="form.videoUnit = 'call'"
              >
                按条
              </button>
              <button
                type="button"
                class="admin-chip"
                :class="{ 'is-active': form.videoUnit === 'second' }"
                @click="form.videoUnit = 'second'"
              >
                按秒
              </button>
            </div>
          </div>
          <div class="ui-field">
            <label class="ui-label">售价（积分 / {{ form.videoUnit === 'call' ? '条' : '秒' }}）</label>
            <input v-model="form.videoCreditPrice" class="ui-input admin-mono" type="number" step="0.1" min="0" />
          </div>
        </div>

        <div class="ui-field">
          <label class="ui-label">支持分辨率（多选）</label>
          <div class="admin-chip-group">
            <button
              v-for="res in ALL_RESOLUTIONS"
              :key="res"
              type="button"
              class="admin-chip"
              :class="{ 'is-active': form.resolutions.includes(res) }"
              @click="toggleResolution(res)"
            >
              {{ res }}
            </button>
          </div>
        </div>

        <div class="ui-field">
          <label class="ui-label">支持比例（多选）</label>
          <div class="admin-chip-group">
            <button
              v-for="ratio in ALL_RATIOS"
              :key="ratio"
              type="button"
              class="admin-chip"
              :class="{ 'is-active': form.ratios.includes(ratio) }"
              @click="toggleRatio(ratio)"
            >
              {{ ratio }}
            </button>
          </div>
        </div>

        <div class="admin-form-grid-3">
          <div class="ui-field">
            <label class="ui-label">最短时长（秒）</label>
            <input v-model="form.minDuration" class="ui-input admin-mono" type="number" min="1" max="60" />
          </div>
          <div class="ui-field">
            <label class="ui-label">最长时长（秒）</label>
            <input v-model="form.maxDuration" class="ui-input admin-mono" type="number" min="1" max="120" />
          </div>
          <div class="ui-field">
            <label class="ui-label">提示词上限（字）</label>
            <input v-model="form.maxPromptChars" class="ui-input admin-mono" type="number" min="100" max="50000" />
          </div>
        </div>

        <div class="admin-form-grid-3">
          <div class="ui-field">
            <label class="ui-label">参考图上限</label>
            <input v-model="form.maxReferenceImages" class="ui-input admin-mono" type="number" min="0" max="50" />
          </div>
          <div class="ui-field">
            <label class="ui-label">参考视频上限</label>
            <input v-model="form.maxReferenceVideos" class="ui-input admin-mono" type="number" min="0" max="20" />
          </div>
          <div class="ui-field">
            <label class="ui-label">参考音频上限</label>
            <input v-model="form.maxReferenceAudios" class="ui-input admin-mono" type="number" min="0" max="20" />
          </div>
        </div>
      </template>

      <template v-else-if="form.mediaType === 'text'">
        <div class="admin-form-grid-3">
          <div class="ui-field">
            <label class="ui-label">普通输入 / M</label>
            <input v-model="form.textInputPrice" class="ui-input admin-mono" type="number" step="0.0001" min="0" />
          </div>
          <div class="ui-field">
            <label class="ui-label">缓存输入 / M</label>
            <input v-model="form.textCachedPrice" class="ui-input admin-mono" type="number" step="0.0001" min="0" />
          </div>
          <div class="ui-field">
            <label class="ui-label">输出 / M</label>
            <input v-model="form.textOutputPrice" class="ui-input admin-mono" type="number" step="0.0001" min="0" />
          </div>
        </div>
      </template>

      <template v-else-if="form.mediaType === 'image'">
        <div class="admin-settings-grid">
          <div class="ui-field">
            <label class="ui-label">参数协议</label>
            <div class="admin-chip-group">
              <button
                v-for="opt in IMAGE_PROTOCOL_OPTIONS"
                :key="opt.value"
                type="button"
                class="admin-chip"
                :class="{ 'is-active': form.imageProtocol === opt.value }"
                @click="form.imageProtocol = opt.value"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>
          <div class="ui-field">
            <label class="ui-label">最多参考图数</label>
            <input v-model="form.maxReferenceImages" class="ui-input admin-mono" type="number" min="0" max="20" />
          </div>
        </div>

        <div v-if="form.imageProtocol === 'gpt_image'" class="admin-settings-grid">
          <div class="ui-field">
            <label class="ui-label">变体通道（series）</label>
            <div class="admin-chip-group">
              <button
                v-for="opt in IMAGE_SERIES_OPTIONS"
                :key="opt.value"
                type="button"
                class="admin-chip"
                :class="{ 'is-active': form.imageSeries === opt.value }"
                @click="form.imageSeries = opt.value"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>
          <div class="ui-field">
            <label class="ui-label">非 Web 档画质（quality）</label>
            <div class="admin-chip-group">
              <button
                v-for="q in IMAGE_QUALITY_OPTIONS"
                :key="q.value"
                type="button"
                class="admin-chip"
                :class="{ 'is-active': form.imageQuality === q.value }"
                @click="form.imageQuality = q.value"
              >
                {{ q.label }}
              </button>
            </div>
          </div>
        </div>

        <div class="ui-field">
          <label class="ui-label">支持比例（多选）</label>
          <div class="admin-chip-group">
            <button
              v-for="ratio in ALL_IMAGE_RATIOS"
              :key="ratio"
              type="button"
              class="admin-chip"
              :class="{ 'is-active': form.imageRatios.includes(ratio) }"
              @click="toggleImageRatio(ratio)"
            >
              {{ ratio === 'auto' ? '自动' : ratio }}
            </button>
          </div>
        </div>

        <div class="admin-card-head" style="margin: 4px 0 0;">
          <span class="ui-label">图片档位单价 · 积分 / 张</span>
          <button type="button" class="ui-button ui-button--secondary ui-button--sm" @click="addImagePriceRow">
            <Plus :size="13" />
            <span>新增档位</span>
          </button>
        </div>
        <div v-for="(row, idx) in form.imagePrices" :key="idx" class="admin-price-row">
          <UiSelect v-model="row.tier" :options="tierOptions" />
          <input v-model="row.creditPrice" class="ui-input admin-mono" type="number" step="0.01" min="0" placeholder="积分/张" />
          <span class="admin-cell-sub">积分 / 张</span>
          <button type="button" class="ui-icon-button" aria-label="删除档位" @click="removeImagePriceRow(idx)">
            <Trash2 :size="15" />
          </button>
        </div>
      </template>

      <div class="admin-form-grid-3">
        <UiSelect v-model="form.enabled" label="后台开关" :options="enabledOptions" />
        <UiSelect
          v-model="form.isDefault"
          :label="form.mediaType === 'video' ? '15s 默认' : '是否默认'"
          :options="defaultOptions"
        />
        <UiSelect
          v-if="form.mediaType === 'video'"
          v-model="form.isDefaultLong"
          label="30s 默认"
          :options="defaultOptions"
          :disabled="(Number.parseInt(form.maxDuration, 10) || 15) < 30"
        />
        <div class="ui-field">
          <label class="ui-label">排序</label>
          <input v-model="form.sort" class="ui-input admin-mono" type="number" step="1" />
        </div>
      </div>
    </div>

    <template #footer>
      <button type="button" class="ui-button ui-button--secondary" @click="open = false">取消</button>
      <button type="button" class="ui-button ui-button--primary" :disabled="submitting" @click="submit">
        {{ submitting ? '保存中...' : '保存' }}
      </button>
    </template>
  </UiDialog>
</template>
