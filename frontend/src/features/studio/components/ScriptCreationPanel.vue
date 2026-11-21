<script setup lang="ts">
import { computed, ref, shallowRef, useId, watch } from 'vue'
import { ArrowRight, FilePenLine, FileUp, Music, Plus } from 'lucide-vue-next'
import FileDropzone from '@/components/business/FileDropzone.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiInput from '@/components/ui/UiInput.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import UiSwitch from '@/components/ui/UiSwitch.vue'
import UiTextarea from '@/components/ui/UiTextarea.vue'
import ArtStylePicker from './ArtStylePicker.vue'
import { contentLanguages, initialDramaSettings, resolveDramaSettings, segmentDurations, videoRatios } from './drama-creation'
import type { DramaCreation } from './drama-creation'
import { storyMaxLength, validateStory } from './story-input'

const props = defineProps<{ busy?: boolean }>()
const emit = defineEmits<{ submit: [input: DramaCreation] }>()
const scriptFileExtensions = ['.txt', '.md'] as const
const id = useId()
const formId = `${id}-form`
const open = ref(false)
const mode = ref<DramaCreation['mode']>('story')
const draft = ref(initialDramaSettings())
const story = ref('')
const file = shallowRef<File>()
const settings = computed(() => resolveDramaSettings(draft.value))
const episodeCountInvalid = computed(() => draft.value.episodeCount !== '' &&
  (!Number.isSafeInteger(draft.value.episodeCount) || draft.value.episodeCount < 1))
const canSubmit = computed(() => settings.value !== null &&
  (mode.value === 'story' ? validateStory(story.value) === null : !!file.value))

function submit() {
  if (props.busy || !canSubmit.value || !settings.value) return
  if (mode.value === 'story') {
    emit('submit', { mode: 'story', settings: settings.value, story: story.value.trim() })
  } else if (file.value) {
    emit('submit', { mode: 'upload', settings: settings.value, file: file.value })
  }
}

watch(open, (isOpen) => {
  if (isOpen) return
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

    <UiDialog v-model:open="open" title="新建短剧" description="创作内容和项目设置均为必填" size="wide">
      <template #trigger>
        <UiButton variant="primary" class="script-entry-button">
          <template #leading><Plus :size="17" aria-hidden="true" /></template>
          新建短剧
        </UiButton>
      </template>

      <form :id="formId" class="drama-form" novalidate @submit.prevent="submit">
        <fieldset class="drama-section">
          <legend>创作内容</legend>
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
            :rows="3"
            :required="mode === 'story'"
          />
          <FileDropzone v-show="mode === 'upload'" label="选择文件" :extensions="scriptFileExtensions" @select="file = $event" @clear="file = undefined" />
        </fieldset>

        <fieldset class="drama-section drama-settings">
          <legend>项目设置</legend>
          <div class="drama-fields">
            <div class="drama-full">
              <UiInput v-model="draft.name" label="项目名称" placeholder="输入短剧名称" required />
            </div>
            <fieldset class="drama-choice drama-full">
              <legend class="ui-label">视频比例<span class="ui-required" aria-hidden="true">*</span></legend>
              <div class="drama-segments drama-ratios">
                <label v-for="ratio in videoRatios" :key="ratio">
                  <input v-model="draft.ratio" type="radio" :name="`${id}-ratio`" :value="ratio" required />
                  <span>{{ ratio }}</span>
                </label>
              </div>
            </fieldset>
            <fieldset class="drama-choice drama-full">
              <legend class="ui-label">单片段最长时长<span class="ui-required" aria-hidden="true">*</span></legend>
              <div class="drama-segments drama-durations">
                <label v-for="duration in segmentDurations" :key="duration">
                  <input v-model="draft.maxSegmentDuration" type="radio" :name="`${id}-duration`" :value="duration" required />
                  <span>{{ duration }} 秒</span>
                </label>
              </div>
            </fieldset>
            <UiSelect v-model="draft.language" label="内容语言" :options="contentLanguages" required />
            <div class="ui-field">
              <label class="ui-label" :for="`${id}-episodes`">集数<span class="ui-required" aria-hidden="true">*</span></label>
              <input
                :id="`${id}-episodes`"
                v-model.number="draft.episodeCount"
                type="number"
                class="ui-input"
                :class="{ 'is-invalid': episodeCountInvalid }"
                min="1"
                step="1"
                required
                :aria-invalid="episodeCountInvalid || undefined"
                :aria-describedby="episodeCountInvalid ? `${id}-episodes-error` : undefined"
              />
              <p v-if="episodeCountInvalid" :id="`${id}-episodes-error`" class="ui-field-message is-error">集数必须是正整数</p>
            </div>
            <ArtStylePicker v-model="draft.visualStyle" class="drama-full" />
            <div class="drama-switch-row drama-full" :class="{ 'is-active': draft.backgroundMusic }">
              <span class="drama-switch-icon" aria-hidden="true"><Music :size="15" :stroke-width="1.8" /></span>
              <UiSwitch v-model="draft.backgroundMusic" class="drama-switch-control" label="生成背景音乐" />
            </div>
          </div>
        </fieldset>

      </form>

      <template #footer>
        <UiButton variant="ghost" :disabled="busy" @click="open = false">取消</UiButton>
        <UiButton variant="primary" type="submit" :form="formId" :disabled="!canSubmit || busy" :loading="busy">
          {{ busy ? '正在生成剧本…' : '创建剧本' }}
          <template v-if="!busy" #trailing><ArrowRight :size="16" aria-hidden="true" /></template>
        </UiButton>
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
.drama-form { display: grid; gap: 20px; }
.drama-section, .drama-choice { min-width: 0; margin: 0; padding: 0; border: 0; }
.drama-section > legend { float: left; width: 100%; margin-bottom: 10px; padding: 0; font-weight: 600; }
.drama-modes { clear: left; margin-bottom: 12px; }
.drama-settings { padding-top: 16px; border-top: 1px solid var(--border-subtle); }
.drama-fields { clear: left; display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); align-items: start; gap: 12px; }
.drama-full { grid-column: 1 / -1; }
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
.drama-switch-row { display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 0 14px; border: 1px solid var(--border-control); border-radius: var(--radius-control); background: rgb(255 255 255 / 3%); transition: border-color .15s, background-color .15s; }
.drama-switch-row:hover { border-color: rgb(255 255 255 / 22%); }
.drama-switch-row.is-active { border-color: rgb(240 184 75 / 32%); background: rgb(240 184 75 / 6%); }
.drama-switch-icon { display: grid; place-items: center; width: 26px; height: 26px; flex-shrink: 0; border-radius: 7px; background: rgb(255 255 255 / 5%); color: var(--color-muted); transition: background-color .15s, color .15s; }
.drama-switch-row.is-active .drama-switch-icon { background: var(--gold-tint); color: var(--color-gold-soft); }
.drama-switch-control { flex: 1; min-width: 0; min-height: 0; }
.drama-switch-control :deep(label) { flex: 1; color: #c9cad3; font-weight: 500; }
.drama-switch-row.is-active .drama-switch-control :deep(label) { color: var(--color-text); }
.drama-form input.is-invalid { border-color: var(--color-error); }
.drama-form :deep(.file-dropzone) { min-height: 158px; padding-block: 12px; gap: 5px; }
.drama-form :deep(.ui-counter) { color: var(--color-muted); }
@media (max-width: 460px) {
  .drama-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .drama-form { gap: 16px; }
}
</style>
