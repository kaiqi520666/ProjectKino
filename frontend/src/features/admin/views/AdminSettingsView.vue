<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { CheckCircle2, Cloud, RefreshCw, Save, Settings2, UserPlus, XCircle } from 'lucide-vue-next'
import WorkspacePageHeader from '@/components/workspace/WorkspacePageHeader.vue'
import {
  getAdminSettings,
  updateAdminOssSettings,
  updateAdminRegistrationSettings,
} from '@/features/admin/api'
import { extractErrorMessage } from '@/features/admin/format'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

const loading = ref(false)
const ossSaving = ref(false)
const regSaving = ref(false)

const ossMeta = reactive({
  hasCredentials: false,
  configured: false,
})

const ossForm = reactive({
  endpoint: '',
  bucket: '',
  publicBaseUrl: '',
  prefix: 'framedrama',
  timeoutSeconds: 30,
  accessKeyId: '',
  accessKeySecret: '',
})

const regForm = reactive({
  initialCredits: '0',
  defaultUsageMultiplier: '1.00',
})

async function loadSettings() {
  loading.value = true
  try {
    const res = await getAdminSettings()
    ossForm.endpoint = res.oss.endpoint
    ossForm.bucket = res.oss.bucket
    ossForm.publicBaseUrl = res.oss.publicBaseUrl
    ossForm.prefix = res.oss.prefix || 'framedrama'
    ossForm.timeoutSeconds = res.oss.timeoutSeconds || 30
    ossForm.accessKeyId = ''
    ossForm.accessKeySecret = ''
    ossMeta.hasCredentials = res.oss.hasCredentials
    ossMeta.configured = res.oss.configured

    regForm.initialCredits = res.registration.initialCredits
    regForm.defaultUsageMultiplier = res.registration.defaultUsageMultiplier
  } catch (err) {
    ui.notify(extractErrorMessage(err, '加载系统设置失败'), 'error')
  } finally {
    loading.value = false
  }
}

async function saveOss() {
  if (!ossForm.endpoint.trim() || !ossForm.bucket.trim()) {
    ui.notify('请填写 OSS Endpoint 和 Bucket 名称', 'error')
    return
  }
  ossSaving.value = true
  try {
    const res = await updateAdminOssSettings({
      endpoint: ossForm.endpoint.trim(),
      bucket: ossForm.bucket.trim(),
      publicBaseUrl: ossForm.publicBaseUrl.trim(),
      prefix: ossForm.prefix.trim() || 'framedrama',
      timeoutSeconds: Number(ossForm.timeoutSeconds) || 30,
      accessKeyId: ossForm.accessKeyId.trim() || undefined,
      accessKeySecret: ossForm.accessKeySecret.trim() || undefined,
    })
    ossMeta.hasCredentials = res.hasCredentials
    ossMeta.configured = res.configured
    ossForm.accessKeyId = ''
    ossForm.accessKeySecret = ''
    ui.notify('阿里云 OSS 配置已保存', 'success')
  } catch (err) {
    ui.notify(extractErrorMessage(err, '保存 OSS 配置失败'), 'error')
  } finally {
    ossSaving.value = false
  }
}

async function saveRegistration() {
  const credits = Number(regForm.initialCredits)
  const mult = Number(regForm.defaultUsageMultiplier)
  if (!Number.isFinite(credits) || credits < 0) {
    ui.notify('注册赠送积分必须大于等于 0', 'error')
    return
  }
  if (!Number.isFinite(mult) || mult <= 0 || mult > 100) {
    ui.notify('默认计费倍率必须在 0 ~ 100 之间', 'error')
    return
  }
  regSaving.value = true
  try {
    const res = await updateAdminRegistrationSettings({
      initialCredits: String(regForm.initialCredits).trim(),
      defaultUsageMultiplier: String(regForm.defaultUsageMultiplier).trim(),
    })
    regForm.initialCredits = res.initialCredits
    regForm.defaultUsageMultiplier = res.defaultUsageMultiplier
    ui.notify('新用户注册策略已保存', 'success')
  } catch (err) {
    ui.notify(extractErrorMessage(err, '保存注册策略失败'), 'error')
  } finally {
    regSaving.value = false
  }
}

onMounted(loadSettings)
</script>

<template>
  <section class="admin-section">
    <WorkspacePageHeader eyebrow="管理后台" title="系统与 OSS">
      <template #icon><Settings2 :size="19" :stroke-width="1.7" /></template>
      <template #actions>
        <button type="button" class="ui-button ui-button--secondary ui-button--sm" :disabled="loading" @click="loadSettings">
          <RefreshCw :size="14" :class="{ 'ui-spin': loading }" />
          <span>刷新</span>
        </button>
      </template>
    </WorkspacePageHeader>

    <div class="admin-settings-grid">
      <!-- 阿里云 OSS 配置 -->
      <form class="admin-card admin-form-stack" @submit.prevent="saveOss">
        <div class="admin-card-head" style="margin-bottom: 4px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <Cloud :size="17" />
            <h3>阿里云 OSS 对象存储</h3>
          </div>
          <span class="admin-badge" :class="ossMeta.configured ? 'admin-badge--success' : 'admin-badge--danger'">
            <CheckCircle2 v-if="ossMeta.configured" :size="13" />
            <XCircle v-else :size="13" />
            {{ ossMeta.configured ? '已配置' : '未配置' }}
          </span>
        </div>

        <div class="ui-field">
          <label class="ui-label">Endpoint <span class="ui-required">*</span></label>
          <input
            v-model="ossForm.endpoint"
            class="ui-input admin-mono"
            type="text"
            placeholder="例如：https://oss-cn-hangzhou.aliyuncs.com"
          />
        </div>

        <div class="ui-field">
          <label class="ui-label">Bucket 名称 <span class="ui-required">*</span></label>
          <input v-model="ossForm.bucket" class="ui-input admin-mono" type="text" placeholder="例如：my-bucket" />
        </div>

        <div class="ui-field">
          <label class="ui-label">对外访问域名</label>
          <input
            v-model="ossForm.publicBaseUrl"
            class="ui-input admin-mono"
            type="text"
            placeholder="选填，如 https://image.nodepass.net"
          />
        </div>

        <div class="admin-settings-grid">
          <div class="ui-field">
            <label class="ui-label">路径前缀</label>
            <input v-model="ossForm.prefix" class="ui-input admin-mono" type="text" placeholder="framedrama" />
          </div>
          <div class="ui-field">
            <label class="ui-label">超时秒数</label>
            <input v-model.number="ossForm.timeoutSeconds" class="ui-input admin-mono" type="number" min="5" max="120" />
          </div>
        </div>

        <div class="ui-field">
          <label class="ui-label">AccessKey ID</label>
          <input
            v-model="ossForm.accessKeyId"
            class="ui-input admin-mono"
            type="password"
            autocomplete="off"
            :placeholder="ossMeta.hasCredentials ? '已保存，留空不修改' : '请输入 AccessKey ID'"
          />
        </div>

        <div class="ui-field">
          <label class="ui-label">AccessKey Secret</label>
          <input
            v-model="ossForm.accessKeySecret"
            class="ui-input admin-mono"
            type="password"
            autocomplete="off"
            :placeholder="ossMeta.hasCredentials ? '已保存，留空不修改' : '请输入 AccessKey Secret'"
          />
        </div>

        <div style="display: flex; justify-content: flex-end; margin-top: 6px;">
          <button type="submit" class="ui-button ui-button--primary ui-button--sm" :disabled="ossSaving">
            <Save :size="14" />
            <span>{{ ossSaving ? '保存中...' : '保存 OSS 配置' }}</span>
          </button>
        </div>
      </form>

      <!-- 注册策略配置 -->
      <form class="admin-card admin-form-stack" @submit.prevent="saveRegistration">
        <div class="admin-card-head" style="margin-bottom: 4px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <UserPlus :size="17" />
            <h3>新用户注册策略</h3>
          </div>
          <span class="admin-badge admin-badge--gold">即时生效</span>
        </div>

        <div class="ui-field">
          <label class="ui-label">注册赠送积分</label>
          <input
            v-model="regForm.initialCredits"
            class="ui-input admin-mono"
            type="number"
            step="1"
            min="0"
            max="1000000"
          />
        </div>

        <div class="ui-field">
          <label class="ui-label">默认计费倍率</label>
          <input
            v-model="regForm.defaultUsageMultiplier"
            class="ui-input admin-mono"
            type="number"
            step="0.05"
            min="0.01"
            max="100"
          />
        </div>

        <div style="display: flex; justify-content: flex-end; margin-top: 6px;">
          <button type="submit" class="ui-button ui-button--primary ui-button--sm" :disabled="regSaving">
            <Save :size="14" />
            <span>{{ regSaving ? '保存中...' : '保存注册策略' }}</span>
          </button>
        </div>
      </form>
    </div>
  </section>
</template>
