<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import { FileText, Upload, X } from 'lucide-vue-next'
import { validateFile } from '@/lib/file-validation'
import UiButton from '@/components/ui/UiButton.vue'

const props = withDefaults(defineProps<{
  label?: string
  extensions?: readonly string[]
  maxSizeMb?: number
  disabled?: boolean
}>(), {
  label: '上传剧本',
  extensions: () => ['.txt', '.md', '.pdf', '.doc', '.docx'],
  maxSizeMb: 20,
})
const emit = defineEmits<{ select: [file: File]; clear: []; error: [message: string] }>()
const input = ref<HTMLInputElement>()
const selected = ref<File>()
const dragging = ref(false)
const error = ref('')
const id = useId()
const accept = computed(() => props.extensions.join(','))

function choose(files: FileList | null) {
  if (props.disabled || !files?.length) return
  error.value = files.length > 1
    ? '请一次选择一个文件'
    : validateFile(files[0]!, props.extensions, props.maxSizeMb * 1024 * 1024) || ''
  if (error.value) {
    emit('error', error.value)
    return
  }
  selected.value = files[0]!
  emit('select', selected.value)
}

function onChange(event: Event) {
  const element = event.target as HTMLInputElement
  choose(element.files)
  element.value = ''
}

function onDrop(event: DragEvent) {
  dragging.value = false
  choose(event.dataTransfer?.files || null)
}

function clear() {
  selected.value = undefined
  error.value = ''
  emit('clear')
}
</script>

<template>
  <div class="file-dropzone-field">
    <div class="file-dropzone" :class="{ 'is-dragging': dragging && !disabled, 'is-disabled': disabled, 'has-error': error }"
      @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop">
      <input :id="id" ref="input" class="sr-only" type="file" :accept="accept" :disabled="disabled" tabindex="-1" :aria-label="label" @change="onChange" />
      <template v-if="selected">
        <FileText :size="26" class="file-dropzone-icon" aria-hidden="true" />
        <strong class="file-dropzone-name">{{ selected.name }}</strong>
        <span>{{ (selected.size / 1024).toFixed(1) }} KB</span>
        <button type="button" class="ui-icon-button file-dropzone-clear" aria-label="移除所选文件" :disabled="disabled" @click="clear"><X :size="16" /></button>
        <UiButton size="sm" :disabled="disabled" @click="input?.click()">重新选择</UiButton>
      </template>
      <template v-else>
        <Upload :size="25" class="file-dropzone-icon" :stroke-width="1.5" aria-hidden="true" />
        <strong>将文件拖到这里</strong>
        <span>{{ extensions.map((item) => item.slice(1).toUpperCase()).join(' / ') }} · 最大 {{ maxSizeMb }} MB</span>
        <UiButton size="sm" :disabled="disabled" @click="input?.click()">{{ label }}</UiButton>
      </template>
    </div>
    <p v-if="error" class="ui-field-message is-error" role="alert">{{ error }}</p>
  </div>
</template>
