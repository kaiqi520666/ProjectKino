<script setup lang="ts">
import { useId } from 'vue'
import { LayoutGrid, Plus, Sparkles } from 'lucide-vue-next'
import UiAlert from '@/components/ui/UiAlert.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiTextarea from '@/components/ui/UiTextarea.vue'
import type { ModelCatalogItemOut } from '../api-types'
import type { ImageTier } from '../model-defaults'
import type { StoryboardClip } from '../studio-storyboard'
import ImageModelPicker from './ImageModelPicker.vue'
import ImageParamsPopover from './ImageParamsPopover.vue'

defineProps<{
  episodeNumber: number
  clip?: StoryboardClip
  clipCount: number
  readyCount: number
  submittingAction: boolean
  episodeActionsLocked: boolean
  addClipMaxDuration: number
  addClipDurationPresets: number[]
  addClipBusy: boolean
  hasStoryboardGrid: boolean
  plannedGridSummary: string
  imageModels: ModelCatalogItemOut[]
  currentGridModel: ModelCatalogItemOut | null
  defaultGridRatio: string
  isCurrentClipGridGenerating: boolean
  estimatedGridQuote: string | null
  clipToDelete?: number
}>()

const regenOpen = defineModel<boolean>('regenOpen', { required: true })
const regenScope = defineModel<'clip' | 'episode'>('regenScope', { required: true })
const regenRefreshRefs = defineModel<boolean>('regenRefreshRefs', { required: true })
const regenFeedback = defineModel<string>('regenFeedback', { required: true })

const addClipOpen = defineModel<boolean>('addClipOpen', { required: true })
const addClipFeedback = defineModel<string>('addClipFeedback', { required: true })
const addClipPosition = defineModel<'after' | 'end'>('addClipPosition', { required: true })
const addClipDuration = defineModel<number>('addClipDuration', { required: true })

const gridDialogOpen = defineModel<boolean>('gridDialogOpen', { required: true })
const gridModelId = defineModel<string>('gridModelId', { required: true })
const gridTier = defineModel<ImageTier>('gridTier', { required: true })
const gridRatio = defineModel<string>('gridRatio', { required: true })

const deleteOpen = defineModel<boolean>('deleteOpen', { required: true })

const emit = defineEmits<{
  submitRegen: []
  createBlankClip: []
  submitAiAddClip: []
  submitGrid: []
  confirmDelete: []
}>()

const regenFormId = useId()
const addClipFormId = useId()
</script>

<template>
  <UiDialog
    v-model:open="regenOpen"
    title="重新生成分镜"
    :description="regenScope === 'clip' && clip ? `仅重写片段 ${clip.id}，保留其已生成的视频与历史记录。` : `重新按最新剧本生成第 ${episodeNumber} 集全部分镜。`"
  >
    <form :id="regenFormId" class="episode-modal-form" @submit.prevent="emit('submitRegen')">
      <div v-if="clip?.backendId" class="episode-scope-switch" role="radiogroup" aria-label="重生成范围">
        <button
          type="button"
          class="episode-scope-option"
          :class="{ 'is-active': regenScope === 'clip' }"
          @click="regenScope = 'clip'"
        >
          <strong>仅当前片段（片段 {{ clip.id }}）</strong>
          <span>保留已有视频，仅重写本段提示词</span>
        </button>
        <button
          type="button"
          class="episode-scope-option"
          :class="{ 'is-active': regenScope === 'episode' }"
          @click="regenScope = 'episode'"
        >
          <strong>整集分镜（第 {{ episodeNumber }} 集）</strong>
          <span>按最新剧本全量重切并覆盖</span>
        </button>
      </div>

      <label v-if="regenScope === 'clip' && clip?.backendId" class="episode-modal-check">
        <input v-model="regenRefreshRefs" type="checkbox" />
        <span>同时重新匹配参考素材（自动选用最新资产/变体；取消勾选则保留当前参考素材仅重写提示词）</span>
      </label>

      <UiAlert
        v-else
        tone="warning"
        :title="
          readyCount > 0
            ? `重生成整集将覆盖全部 ${clipCount} 个片段，并清空当前 ${readyCount} 个已生成的视频关联`
            : `重生成整集将按最新剧本覆盖本集全部 ${clipCount} 个片段及手动编辑内容`
        "
      />

      <UiTextarea
        v-model="regenFeedback"
        label="修改要求 / 导演意见（可选）"
        :rows="4"
        :maxlength="500"
        :placeholder="
          regenScope === 'clip'
            ? '可留空直接重写；或说明修改方向，例如：节奏放慢、多给女主面部特写、光线更压抑、换用手持跟拍'
            : '可留空按剧本重生成；或说明整集分镜方向，例如：开场前两镜更有压迫感、多用近景特写、林晓回家戏换便装'
        "
      />
    </form>
    <template #footer>
      <UiButton variant="ghost" :disabled="submittingAction" @click="regenOpen = false">取消</UiButton>
      <UiButton
        type="submit"
        :form="regenFormId"
        :variant="regenScope === 'episode' ? 'danger' : 'primary'"
        :disabled="submittingAction || episodeActionsLocked"
      >
        <template #leading><Sparkles :size="14" aria-hidden="true" /></template>
        {{ regenScope === 'clip' && clip ? `开始重生成片段 ${clip.id}` : `确认重生成第 ${episodeNumber} 集分镜` }}
      </UiButton>
    </template>
  </UiDialog>

  <UiDialog
    v-model:open="addClipOpen"
    title="新增片段"
    :description="`单片段时长支持 4–${addClipMaxDuration} 秒（跟随当前项目上限）。可用 AI 结合上下文生成，或直接创建空白片段。`"
  >
    <form :id="addClipFormId" class="episode-modal-form" @submit.prevent="emit('submitAiAddClip')">
      <UiTextarea
        v-model="addClipFeedback"
        label="片段内容 / 导演要求（可选）"
        :rows="4"
        :maxlength="500"
        placeholder="可留空由 AI 承接上一片段自然续写；或写一句剧情/画面意图，例如：补一段 6 秒悬念过渡，林晓推开档案室门，手电光扫过墙上的旧照片"
      />

      <div class="episode-add-grid">
        <div v-if="clip?.backendId" class="episode-add-field">
          <span class="ui-label">插入位置</span>
          <div class="episode-add-pills">
            <button
              type="button"
              class="episode-add-pill"
              :class="{ 'is-active': addClipPosition === 'after' }"
              @click="addClipPosition = 'after'"
            >
              当前片段后（片段 {{ clip.id + 1 }}）
            </button>
            <button
              type="button"
              class="episode-add-pill"
              :class="{ 'is-active': addClipPosition === 'end' }"
              @click="addClipPosition = 'end'"
            >
              本集末尾（片段 {{ clipCount + 1 }}）
            </button>
          </div>
        </div>

        <div class="episode-add-field">
          <span class="ui-label">目标时长（4–{{ addClipMaxDuration }} 秒）</span>
          <div class="episode-add-duration-row">
            <div class="episode-add-pills">
              <button
                v-for="sec in addClipDurationPresets"
                :key="sec"
                type="button"
                class="episode-add-pill"
                :class="{ 'is-active': addClipDuration === sec }"
                @click="addClipDuration = sec"
              >
                {{ sec }}s
              </button>
            </div>
            <label class="episode-add-duration-input">
              <input
                v-model.number="addClipDuration"
                type="number"
                min="4"
                :max="addClipMaxDuration"
                step="1"
                aria-label="自定义目标时长（秒）"
              />
              <span>秒</span>
            </label>
          </div>
        </div>
      </div>
    </form>
    <template #footer>
      <div class="episode-add-footer">
        <UiButton
          variant="outline"
          size="sm"
          :loading="addClipBusy"
          :disabled="addClipBusy || submittingAction || episodeActionsLocked"
          @click="emit('createBlankClip')"
        >
          <template #leading><Plus :size="14" aria-hidden="true" /></template>
          创建空白片段
        </UiButton>
        <div class="episode-add-footer-right">
          <UiButton variant="ghost" size="sm" :disabled="addClipBusy || submittingAction" @click="addClipOpen = false">取消</UiButton>
          <UiButton
            type="submit"
            :form="addClipFormId"
            variant="primary"
            size="sm"
            :disabled="addClipBusy || submittingAction || episodeActionsLocked"
          >
            <template #leading><Sparkles :size="14" aria-hidden="true" /></template>
            AI 生成新片段
          </UiButton>
        </div>
      </div>
    </template>
  </UiDialog>

  <UiDialog
    v-model:open="gridDialogOpen"
    :title="hasStoryboardGrid ? '重绘分镜宫格图' : '生成分镜宫格图'"
    :description="plannedGridSummary"
  >
    <div class="episode-grid-dialog-body">
      <div class="episode-grid-controls">
        <ImageModelPicker
          v-model="gridModelId"
          :models="imageModels"
          :tier="gridTier"
          :disabled="isCurrentClipGridGenerating"
        />
        <ImageParamsPopover
          v-model:tier="gridTier"
          v-model:ratio="gridRatio"
          :model="currentGridModel"
          :default-ratio="defaultGridRatio"
          mode="single"
          align="start"
          :disabled="isCurrentClipGridGenerating"
        />
      </div>
      <p v-if="estimatedGridQuote" class="episode-grid-quote">
        <Sparkles :size="13" aria-hidden="true" />
        图片费用 <strong>{{ estimatedGridQuote }}</strong> 积分/张（另含少量文本规划消耗）
      </p>
    </div>
    <template #footer>
      <UiButton variant="ghost" @click="gridDialogOpen = false">取消</UiButton>
      <div class="episode-cta-split" :class="{ 'is-solo': !estimatedGridQuote }">
        <span v-if="estimatedGridQuote" class="episode-cta-cost">
          <Sparkles :size="13" class="episode-cta-cost-icon" aria-hidden="true" />
          <strong class="episode-cta-cost-num">{{ estimatedGridQuote }}</strong>
          <span class="episode-cta-cost-unit">积分</span>
        </span>
        <UiButton
          class="episode-generate-btn"
          variant="primary"
          size="sm"
          :disabled="!currentGridModel || isCurrentClipGridGenerating"
          @click="emit('submitGrid')"
        >
          <template #leading><LayoutGrid :size="14" aria-hidden="true" /></template>
          {{ hasStoryboardGrid ? '确认重绘' : '开始生成' }}
        </UiButton>
      </div>
    </template>
  </UiDialog>

  <UiDialog v-model:open="deleteOpen" title="删除片段" :description="`确定删除本集的片段 ${clipToDelete} 吗？`">
    <template #footer>
      <UiButton variant="ghost" @click="deleteOpen = false">取消</UiButton>
      <UiButton variant="danger" @click="emit('confirmDelete')">确认删除</UiButton>
    </template>
  </UiDialog>
</template>

<style scoped>
.episode-modal-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.episode-scope-switch {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.episode-scope-option {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 10px 12px;
  border: 1px solid var(--border-control);
  border-radius: 8px;
  background: var(--color-canvas);
  color: var(--color-text);
  text-align: left;
  cursor: pointer;
  transition: border-color 140ms ease, background-color 140ms ease;
}

.episode-scope-option strong {
  font-size: 13px;
  font-weight: 600;
}

.episode-scope-option span {
  font-size: 11px;
  color: var(--color-muted);
}

.episode-scope-option:hover {
  border-color: rgb(240 184 75 / 45%);
}

.episode-scope-option.is-active {
  border-color: var(--color-gold);
  background: var(--gold-tint);
}

.episode-scope-option.is-active strong {
  color: var(--color-gold-soft);
}

.episode-modal-check {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--color-canvas);
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text);
  cursor: pointer;
  user-select: none;
}

.episode-modal-check input {
  width: 15px;
  height: 15px;
  margin-top: 2px;
  flex: none;
  accent-color: var(--color-gold);
  cursor: pointer;
}

.episode-add-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.episode-add-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.episode-add-duration-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.episode-add-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.episode-add-pill {
  padding: 4px 10px;
  border: 1px solid var(--border-control);
  border-radius: 6px;
  background: var(--color-canvas);
  color: var(--color-muted);
  font-size: 12px;
  cursor: pointer;
  transition: border-color 140ms ease, color 140ms ease, background-color 140ms ease;
}

.episode-add-pill:hover {
  border-color: rgb(240 184 75 / 45%);
  color: var(--color-text);
}

.episode-add-pill.is-active {
  border-color: var(--color-gold);
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-weight: 500;
}

.episode-add-duration-input {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border: 1px solid var(--border-control);
  border-radius: 6px;
  background: var(--color-canvas);
  font-size: 12px;
  color: var(--color-muted);
}

.episode-add-duration-input input {
  width: 46px;
  border: 0;
  background: transparent;
  color: var(--color-text);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  text-align: center;
  outline: none;
}

.episode-add-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
}

.episode-add-footer-right {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.episode-grid-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.episode-grid-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.episode-grid-quote {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  color: var(--color-muted);
  font-size: 12px;
}

.episode-grid-quote strong {
  color: var(--color-gold-soft);
  font-variant-numeric: tabular-nums;
}

.episode-cta-split {
  display: inline-flex;
  align-items: stretch;
  height: var(--control-height-sm);
  border-radius: var(--radius-control-sm);
  overflow: hidden;
  border: 1px solid rgb(240 184 75 / 55%);
  box-shadow: 0 2px 10px rgb(240 184 75 / 12%);
}

.episode-cta-split.is-solo {
  border-color: transparent;
  box-shadow: none;
}

.episode-cta-cost {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  padding: 0 12px;
  background: #13151c;
  color: var(--color-gold-soft);
  user-select: none;
}

.episode-cta-cost-icon {
  align-self: center;
  color: var(--color-gold);
  flex-shrink: 0;
}

.episode-cta-cost-num {
  align-self: center;
  font-size: 16px;
  font-weight: 700;
  color: #f8cc66;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  line-height: 1;
}

.episode-cta-cost-unit {
  align-self: center;
  font-size: 11px;
  font-weight: 500;
  color: rgb(248 204 102 / 82%);
  line-height: 1;
}

.episode-generate-btn.ui-button {
  min-height: 0;
  height: 100%;
  padding: 0 14px;
  border: 0;
  border-radius: 0;
}

.episode-cta-split.is-solo .episode-generate-btn.ui-button {
  border-radius: var(--radius-control-sm);
}
</style>
