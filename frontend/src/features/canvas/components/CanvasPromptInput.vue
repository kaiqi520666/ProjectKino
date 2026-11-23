<script setup lang="ts">
import { computed, watch } from 'vue'
import RichPromptInput from '@/components/business/RichPromptInput.vue'
import {
  buildModalitySlotLabels,
  migrateLegacyCanvasRefs,
  type PromptReferenceOption,
} from '@/components/business/prompt-references'
import { canvasNodeLabels, outputKind, type CanvasNode } from '../canvas-model'

const props = defineProps<{ references: CanvasNode[]; expanded?: boolean }>()
const prompt = defineModel<string>({ default: '' })

const slots = computed(() =>
  buildModalitySlotLabels(
    props.references.map((node) => ({
      id: node.id,
      kind: outputKind(node.type),
    })),
  ),
)

const slotByNodeId = computed(() => new Map(slots.value.map((s) => [s.id, s.slotLabel])))

const promptReferences = computed<PromptReferenceOption[]>(() =>
  props.references.map((node, idx) => {
    const slot = slots.value[idx]!
    const title = node.data.title || (node.type && canvasNodeLabels[node.type]) || '文本'
    return {
      tokenKey: slot.slotLabel,
      label: `${slot.slotLabel} · ${title}`,
      kind: slot.kind,
      thumbnailUrl: slot.kind === 'image' ? node.data.media?.url : undefined,
    }
  }),
)

watch(
  () => [prompt.value, props.references.length] as const,
  ([val]) => {
    if (!val || !val.includes('{{ref:')) return
    const migrated = migrateLegacyCanvasRefs(val, slotByNodeId.value)
    if (migrated !== val) prompt.value = migrated
  },
  { immediate: true },
)
</script>

<template>
  <RichPromptInput
    v-model="prompt"
    :references="promptReferences"
    :expanded="expanded"
    placeholder="输入提示词，输入 @ 引用已连接的节点"
    mention-title="引用节点"
  />
</template>
