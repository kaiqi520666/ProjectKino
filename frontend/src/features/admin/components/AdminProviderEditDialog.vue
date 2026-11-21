<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import { updateAdminProvider, type AdminProvider } from '@/features/admin/api'
import { extractErrorMessage } from '@/lib/format'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{
  provider: AdminProvider | null
}>()

const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{
  saved: []
}>()

const ui = useUiStore()
const submitting = ref(false)

const enabledOptions = [
  { value: 'true', label: '启用' },
  { value: 'false', label: '停用' },
]

const form = reactive({
  displayName: '',
  baseUrl: '',
  apiKey: '',
  enabled: 'true',
})

watch(
  () => [open.value, props.provider] as const,
  ([isOpen, target]) => {
    if (!isOpen || !target) return
    form.displayName = target.displayName
    form.baseUrl = target.baseUrl
    form.apiKey = ''
    form.enabled = target.enabled ? 'true' : 'false'
  },
)

async function submit() {
  if (!props.provider) return
  if (!form.displayName.trim() || !form.baseUrl.trim()) {
    ui.notify('供应商名称和接口地址不能为空', 'error')
    return
  }
  submitting.value = true
  try {
    await updateAdminProvider(props.provider.key, {
      displayName: form.displayName.trim(),
      baseUrl: form.baseUrl.trim(),
      apiKey: form.apiKey.trim() || undefined,
      enabled: form.enabled === 'true',
    })
    ui.notify(`已更新供应商 ${props.provider.displayName}`, 'success')
    open.value = false
    emit('saved')
  } catch (err) {
    ui.notify(extractErrorMessage(err, '保存供应商失败'), 'error')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <UiDialog
    v-model:open="open"
    title="编辑供应商"
    :description="provider ? `${provider.key} · ${provider.adapter}` : ''"
  >
    <div class="admin-form-stack">
      <div class="ui-field">
        <label class="ui-label">名称 <span class="ui-required">*</span></label>
        <input v-model="form.displayName" class="ui-input" type="text" />
      </div>
      <div class="ui-field">
        <label class="ui-label">接口地址 <span class="ui-required">*</span></label>
        <input v-model="form.baseUrl" class="ui-input admin-mono" type="url" />
      </div>
      <div class="ui-field">
        <label class="ui-label">API Key</label>
        <input
          v-model="form.apiKey"
          class="ui-input admin-mono"
          type="password"
          autocomplete="off"
          :placeholder="provider?.hasApiKey ? '已配置，留空不修改' : '请输入 API Key'"
        />
      </div>
      <UiSelect v-model="form.enabled" label="启用状态" :options="enabledOptions" />
    </div>
    <template #footer>
      <button type="button" class="ui-button ui-button--secondary" @click="open = false">取消</button>
      <button type="button" class="ui-button ui-button--primary" :disabled="submitting" @click="submit">
        {{ submitting ? '保存中...' : '保存' }}
      </button>
    </template>
  </UiDialog>
</template>
