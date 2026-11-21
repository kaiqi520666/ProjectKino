<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ArrowDownToLine, ArrowRight, Bell, Blocks, Check, ChevronRight, Clapperboard,
  Coins, FileText, Film, Image, Layers3, ListOrdered, MoreHorizontal, Plus, RotateCcw, Search,
  Settings2, ShieldCheck, SlidersHorizontal, Sparkles, Type, Upload, WandSparkles,
} from 'lucide-vue-next'
import {
  EmptyState, FileDropzone, TaskProgress, TaskStatusBadge, UiAlert, UiButton, UiCheckbox,
  UiDialog, UiDropdown, UiIconButton, UiInput, UiRange, UiSelect, UiSwitch, UiTabs, UiTextarea,
} from '@/components'
import { useUiStore } from '@/stores/ui'
import type { TaskStatus } from '@/components'
import MediaComponentsPreview from './MediaComponentsPreview.vue'
import WorkspaceComponentsPreview from './WorkspaceComponentsPreview.vue'

const ui = useUiStore()
const mediaPreview = ref<InstanceType<typeof MediaComponentsPreview>>()
const workspacePreview = ref<InstanceType<typeof WorkspaceComponentsPreview>>()
const projectName = ref('')
const search = ref('')
const prompt = ref('')
const code = ref('12')
const model = ref('standard')
const resolution = ref('720p')
const agreed = ref(false)
const autoSave = ref(true)
const tab = ref('script')
const mode = ref('preview')
const duration = ref(5)
const progress = ref(42)
const open = ref(false)
const dialogName = ref('')
const dialogError = ref('')
const statuses: TaskStatus[] = ['pending', 'running', 'succeeded', 'failed', 'canceled']
const previewStatus = computed<TaskStatus>(() => progress.value === 100 ? 'succeeded' : 'running')
const sections = [
  { id: 'buttons', label: '按钮与操作', icon: WandSparkles, count: '02' },
  { id: 'forms', label: '表单与输入', icon: Type, count: '04' },
  { id: 'selection', label: '选择与导航', icon: SlidersHorizontal, count: '04' },
  { id: 'feedback', label: '弹窗与反馈', icon: Bell, count: '03' },
  { id: 'business', label: '业务组件', icon: Clapperboard, count: '04' },
  { id: 'images', label: '图片与占位', icon: Image, count: '02' },
  { id: 'showcase', label: '内容展示', icon: Layers3, count: '02' },
  { id: 'process', label: '流程步骤', icon: ListOrdered, count: '01' },
  { id: 'workspace-components', label: '项目卡片', icon: Clapperboard, count: '01' },
]

function saveExample() {
  if (!dialogName.value.trim()) {
    dialogError.value = '请输入示例名称'
    return
  }
  open.value = false
  ui.notify('示例已确认', 'success', dialogName.value.trim())
}

function reset() {
  mediaPreview.value?.reset()
  workspacePreview.value?.reset()
  projectName.value = ''
  search.value = ''
  prompt.value = ''
  code.value = '12'
  model.value = 'standard'
  resolution.value = '720p'
  agreed.value = false
  autoSave.value = true
  duration.value = 5
  progress.value = 42
  tab.value = 'script'
  mode.value = 'preview'
  ui.notify('组件参数已重置', 'info')
}
</script>

<template>
  <div class="preview-shell">
    <aside class="preview-sidebar">
      <a class="preview-brand" href="/__dev/components" aria-label="FrameDrama 组件预览">
        <img class="preview-brand-icon" src="/brand/framedrama-logo.svg" alt="" width="40" height="40" />
        <span>帧剧<span class="preview-brand-sub">FRAMEDRAMA</span></span>
      </a>
      <div class="preview-library-label">组件库 <span>v0.1</span></div>
      <nav aria-label="组件分类" class="preview-nav">
        <a v-for="section in sections" :key="section.id" :href="`#${section.id}`">
          <component :is="section.icon" :size="16" />
          <span>{{ section.label }}</span><small>{{ section.count }}</small>
        </a>
      </nav>
      <div class="preview-sidebar-bottom"><span class="preview-status-dot" />开发预览<ShieldCheck :size="14" /></div>
    </aside>

    <div class="preview-workspace">
      <header class="preview-topbar">
        <div class="preview-breadcrumb"><Blocks :size="15" /><span>设计系统</span><ChevronRight :size="13" /><strong>组件预览</strong></div>
        <div class="preview-topbar-actions"><span class="preview-theme"><span />黑金</span><UiIconButton label="重置示例" @click="reset"><RotateCcw :size="16" /></UiIconButton></div>
      </header>

      <main class="preview-main">
        <div class="preview-page-heading">
          <div><div class="preview-eyebrow">FRAMEDRAMA / COMPONENTS</div><h1>基础与业务组件</h1></div>
          <span class="preview-version"><span />开发预览</span>
        </div>
        <div class="preview-palette" aria-label="主题颜色">
          <div><span style="background: var(--color-canvas)" /><small>背景</small><code>#090A0D</code></div>
          <div><span style="background: var(--color-surface)" /><small>面板</small><code>#101115</code></div>
          <div><span style="background: var(--color-gold)" /><small>主金色</small><code>#F0B84B</code></div>
          <div><span style="background: var(--color-gold-soft)" /><small>浅金色</small><code>#FFD98A</code></div>
        </div>

        <section id="buttons" class="preview-section">
          <div class="preview-section-heading"><h2>按钮与操作</h2><code>UiButton · UiIconButton</code></div>
          <div class="preview-button-row">
            <UiButton variant="primary" @click="ui.notify('主按钮已触发')"><template #leading><Plus :size="16" /></template>新建项目</UiButton>
            <UiButton @click="ui.notify('次按钮已触发', 'info')"><template #leading><Upload :size="16" /></template>上传剧本</UiButton>
            <UiButton variant="outline" @click="ui.notify('金色描边按钮已触发', 'info')"><template #leading><Coins :size="15" /></template>预计 12 积分</UiButton>
            <UiButton variant="ghost" @click="ui.notify('文字按钮已触发', 'info')">稍后再说<template #trailing><ArrowRight :size="14" /></template></UiButton>
            <UiButton variant="danger" @click="ui.notify('危险操作样式示例', 'info')">危险操作</UiButton>
          </div>
          <div class="preview-button-row preview-row-secondary">
            <span class="preview-example-label">状态</span>
            <UiButton size="sm" variant="primary">小尺寸</UiButton>
            <UiButton variant="primary" loading>生成中</UiButton>
            <UiButton disabled>不可用</UiButton>
            <UiIconButton label="下载" @click="ui.notify('下载按钮示例', 'info')"><ArrowDownToLine :size="17" /></UiIconButton>
            <UiIconButton label="设置" @click="open = true"><Settings2 :size="17" /></UiIconButton>
            <UiIconButton label="已选中" active><Check :size="17" /></UiIconButton>
          </div>
        </section>

        <section id="forms" class="preview-section">
          <div class="preview-section-heading"><h2>表单与输入</h2><code>UiInput · UiTextarea · UiSelect · UiRange</code></div>
          <div class="preview-grid">
            <div class="preview-stack">
              <UiInput v-model="projectName" label="项目名称" placeholder="给你的故事起个名字" :maxlength="40" required><template #leading><Clapperboard :size="16" /></template></UiInput>
              <UiInput v-model="search" label="搜索" placeholder="搜索角色、场景或道具"><template #leading><Search :size="16" /></template></UiInput>
              <UiInput v-model="code" label="校验错误" placeholder="请输入验证码" inputmode="numeric" :maxlength="6" :error="code.length === 6 ? '' : '请输入 6 位验证码'" />
            </div>
            <div class="preview-stack">
              <UiTextarea v-model="prompt" label="故事梗概" placeholder="写下人物、背景与故事中的冲突……" :maxlength="2000" :rows="5" />
              <div class="preview-grid preview-grid--compact">
                <UiSelect v-model="model" label="生成模型" :options="[{value:'standard',label:'标准模型'},{value:'quality',label:'高质量模型'},{value:'fast',label:'快速模型'}]" />
                <UiSelect v-model="resolution" label="分辨率" :options="[{value:'480p',label:'480P'},{value:'720p',label:'720P'},{value:'1080p',label:'1080P'}]" />
              </div>
            </div>
          </div>
          <div class="preview-range-row"><UiRange v-model="duration" label="镜头时长" :min="4" :max="15" unit="s" /></div>
        </section>

        <section id="selection" class="preview-section">
          <div class="preview-section-heading"><h2>选择与导航</h2><code>UiTabs · UiCheckbox · UiSwitch · UiDropdown</code></div>
          <div class="preview-grid">
            <div class="preview-stack">
              <UiTabs v-model="tab" label="内容分类" :tabs="[{value:'script',label:'剧本'},{value:'assets',label:'角色资产',count:8},{value:'shots',label:'分镜',count:12}]">
                <template #script><div class="preview-tab-example"><FileText :size="18" /><span>剧本内容</span></div></template>
                <template #assets><div class="preview-tab-example"><Layers3 :size="18" /><span>角色资产</span><span class="preview-muted">8 项</span></div></template>
                <template #shots><div class="preview-tab-example"><Film :size="18" /><span>分镜列表</span><span class="preview-muted">12 项</span></div></template>
              </UiTabs>
              <UiCheckbox v-model="agreed" label="已阅读并同意用户协议" />
              <UiCheckbox :model-value="true" label="不可更改的选项" disabled />
            </div>
            <div class="preview-stack">
              <UiTabs v-model="mode" variant="segment" label="预览方式" :tabs="[{value:'preview',label:'预览'},{value:'edit',label:'编辑'},{value:'history',label:'版本'}]">
                <template #preview><p class="preview-tab-copy">预览模式</p></template>
                <template #edit><p class="preview-tab-copy">编辑模式</p></template>
                <template #history><p class="preview-tab-copy">版本记录</p></template>
              </UiTabs>
              <UiSwitch v-model="autoSave" label="自动保存" description="保存当前编辑内容" />
              <UiDropdown :items="[{value:'rename',label:'重命名'},{value:'duplicate',label:'创建副本'},{value:'export',label:'导出',disabled:true},{value:'remove',label:'移除示例',danger:true,separator:true}]" @select="(value) => ui.notify(`菜单选择：${value}`, 'info')">
                <UiButton size="sm">更多操作<template #trailing><MoreHorizontal :size="16" /></template></UiButton>
              </UiDropdown>
            </div>
          </div>
        </section>

        <section id="feedback" class="preview-section">
          <div class="preview-section-heading"><h2>弹窗与反馈</h2><code>UiDialog · UiAlert · UiToastViewport</code></div>
          <div class="preview-grid">
            <div class="preview-stack">
              <UiAlert title="修改已保存" tone="success">内容已保存到当前示例。</UiAlert>
              <UiAlert title="积分不足" tone="warning">请检查账户额度后重试。</UiAlert>
              <UiAlert title="任务未完成" tone="error">暂时无法连接生成服务。</UiAlert>
            </div>
            <div class="preview-stack">
              <UiAlert title="参考素材" tone="info">生成结果将使用已绑定的角色与场景。</UiAlert>
              <div class="preview-button-row">
                <UiDialog v-model:open="open" title="编辑示例" description="此操作仅修改组件预览，不会提交任何业务数据。">
                  <template #trigger><UiButton @click="dialogError = ''"><template #leading><Settings2 :size="16" /></template>打开弹窗</UiButton></template>
                  <form id="example-form" @submit.prevent="saveExample"><UiInput v-model="dialogName" label="示例名称" placeholder="请输入名称" :error="dialogError" :maxlength="40" /></form>
                  <template #footer><UiButton variant="ghost" @click="open = false">取消</UiButton><UiButton variant="primary" type="submit" form="example-form">确认</UiButton></template>
                </UiDialog>
                <UiButton variant="outline" @click="ui.notify('通知组件示例', 'success', '可手动关闭，也会自动消失。')"><template #leading><Bell :size="15" /></template>显示通知</UiButton>
              </div>
            </div>
          </div>
        </section>

        <section id="business" class="preview-section">
          <div class="preview-section-heading"><h2>业务组件</h2><code>TaskStatusBadge · TaskProgress · FileDropzone · EmptyState</code></div>
          <div class="preview-status-row"><TaskStatusBadge v-for="status in statuses" :key="status" :status="status" /></div>
          <div class="preview-grid preview-business-grid">
            <div class="preview-stack">
              <TaskProgress title="镜头预览" :status="previewStatus" :progress="progress" description="进度组件示例" />
              <UiRange v-model="progress" label="示例进度" unit="%" />
              <FileDropzone @select="(file) => ui.notify('已选择本地文件', 'info', file.name)" />
            </div>
            <EmptyState title="暂无生成视频" description="生成完成的视频将在这里展示">
              <UiButton size="sm" @click="ui.notify('空状态操作示例', 'info')"><template #leading><Plus :size="14" /></template>添加素材</UiButton>
            </EmptyState>
          </div>
        </section>
        <MediaComponentsPreview ref="mediaPreview" />
        <WorkspaceComponentsPreview ref="workspacePreview" />
        <footer class="preview-footer"><span>FRAMEDRAMA</span><span>组件预览 / 不连接业务服务</span><Sparkles :size="14" /></footer>
      </main>
    </div>
  </div>
</template>
