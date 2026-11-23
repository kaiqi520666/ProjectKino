<script setup lang="ts">
import { computed } from 'vue'
import RichPromptInput from '@/components/business/RichPromptInput.vue'
import type { PromptReferenceOption } from '@/components/business/prompt-references'
import { canvasNodeLabels, outputKind, type CanvasNode } from '../canvas-model'

const props = defineProps<{ references: CanvasNode[]; expanded?: boolean }>()
const prompt = defineModel<string>({ default: '' })

const promptReferences = computed<PromptReferenceOption[]>(() =>
  props.references.map((node) => {
    const kind = outputKind(node.type)
    return {
      tokenKey: node.id,
      label: node.data.title || (node.type && canvasNodeLabels[node.type]) || '文本',
      kind,
      thumbnailUrl: kind === 'image' ? node.data.media?.url : undefined,
    }
  }),
)
</script>

<template>
  <RichPromptInput
    v-model="prompt"
    syntax="canvas"
    :references="promptReferences"
    :expanded="expanded"
    placeholder="输入提示词，输入 @ 引用已连接的节点"
    mention-title="引用节点"
  />
</template>
