<script setup lang="ts">
import { nextTick, useTemplateRef, watch } from 'vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import type { StudioAsset } from '@/features/studio/studio-assets'
import AssetLibraryPanel from './AssetLibraryPanel.vue'
import type {
  AssetLibraryItem,
  AssetLibraryMode,
  AssetLibrarySource,
  AssetMediaKind,
} from './asset-library-types'

const props = withDefaults(
  defineProps<{
    title?: string
    mode?: AssetLibraryMode
    allowedKinds?: readonly AssetMediaKind[]
    projectAssets?: readonly StudioAsset[]
    defaultSource?: AssetLibrarySource
    initialSelectedKeys?: readonly string[]
    disabledKeys?: readonly string[]
    maxByKind?: Partial<Record<AssetMediaKind, number>>
    maxSelect?: number
    requireHttpUrl?: boolean
    deletable?: boolean
  }>(),
  {
    title: '素材库',
    mode: 'single',
    allowedKinds: () => ['image', 'video', 'audio'] as const,
    defaultSource: 'personal',
    initialSelectedKeys: () => [],
    disabledKeys: () => [],
    requireHttpUrl: false,
    deletable: true,
  },
)

const open = defineModel<boolean>('open', { default: false })

const emit = defineEmits<{
  select: [item: AssetLibraryItem]
  confirm: [items: AssetLibraryItem[]]
}>()

const panel = useTemplateRef<InstanceType<typeof AssetLibraryPanel>>('panel')

watch(open, (isOpen) => {
  if (isOpen) {
    void nextTick(() => panel.value?.resetState())
  } else {
    panel.value?.stopAudio()
  }
})

function handleSelect(item: AssetLibraryItem) {
  emit('select', item)
  open.value = false
}

function handleConfirm(items: AssetLibraryItem[]) {
  emit('confirm', items)
  open.value = false
}
</script>

<template>
  <UiDialog v-model:open="open" :title="title" size="landscape">
    <AssetLibraryPanel
      ref="panel"
      :mode="mode"
      :allowed-kinds="allowedKinds"
      :project-assets="projectAssets"
      :default-source="defaultSource"
      :initial-selected-keys="initialSelectedKeys"
      :disabled-keys="disabledKeys"
      :max-by-kind="maxByKind"
      :max-select="maxSelect"
      :require-http-url="requireHttpUrl"
      :deletable="deletable"
      @select="handleSelect"
      @confirm="handleConfirm"
      @cancel="open = false"
    />
  </UiDialog>
</template>
