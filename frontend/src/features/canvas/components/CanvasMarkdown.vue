<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = defineProps<{ value: string; variant?: 'preview' | 'node' }>()
const html = computed(() => DOMPurify.sanitize(marked.parse(props.value, {
  async: false, gfm: true, breaks: true,
}), {
  ALLOWED_TAGS: ['p', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'em', 'strong', 'del', 'blockquote', 'code', 'pre', 'ul', 'ol', 'li', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td'],
  ALLOWED_ATTR: ['start'],
}))
</script>

<template>
  <div
    class="canvas-markdown"
    :class="{ 'canvas-markdown--formatted': props.variant, 'canvas-markdown--node': props.variant === 'node' }"
    v-html="html"
  />
</template>

<style scoped>
.canvas-markdown { overflow-wrap: anywhere; font-size: var(--font-size-body); line-height: 1.6; }
.canvas-markdown :deep(p) { margin: 0 0 8px; }
.canvas-markdown :deep(:last-child) { margin-bottom: 0; }
.canvas-markdown :deep(h1), .canvas-markdown :deep(h2), .canvas-markdown :deep(h3) { margin: 0 0 8px; font-size: 15px; font-weight: 650; }
.canvas-markdown :deep(ul), .canvas-markdown :deep(ol) { padding-inline-start: 20px; }
.canvas-markdown :deep(ul) { list-style: disc; }
.canvas-markdown :deep(ol) { list-style: decimal; }
.canvas-markdown :deep(pre) { overflow: auto; padding: 6px; background: var(--color-canvas); }
.canvas-markdown :deep(td), .canvas-markdown :deep(th) { padding: 3px 7px; border: 1px solid var(--border-control); }

.canvas-markdown--formatted :deep(:is(p, ul, ol, blockquote, pre)) {
  margin: 0 0 var(--markdown-block-spacing, 12px);
}

.canvas-markdown--formatted :deep(:is(h1, h2, h3, h4, h5, h6)) {
  margin: var(--markdown-heading-spacing, 20px) 0 8px;
  font-weight: 650;
  line-height: 1.4;
}

.canvas-markdown--formatted :deep(h1) { font-size: var(--markdown-h1-size, 22px); }
.canvas-markdown--formatted :deep(h2) { font-size: var(--markdown-h2-size, 18px); }
.canvas-markdown--formatted :deep(h3) { font-size: 16px; }
.canvas-markdown--formatted > :deep(:first-child) { margin-top: 0; }
.canvas-markdown--formatted > :deep(:last-child) { margin-bottom: 0; }

.canvas-markdown--formatted :deep(blockquote) {
  padding: 8px 12px;
  border-inline-start: 2px solid var(--color-gold);
  background: var(--gold-tint);
}

.canvas-markdown--formatted :deep(blockquote > :last-child) { margin-bottom: 0; }

.canvas-markdown--formatted :deep(:not(pre) > code) {
  padding: 2px 5px;
  border-radius: 4px;
  background: var(--color-elevated);
  color: var(--color-gold-soft);
}

.canvas-markdown--formatted :deep(pre) {
  padding: 10px 12px;
  overflow-x: auto;
  overflow-wrap: normal;
  white-space: pre;
  border: 1px solid var(--border-control);
  border-radius: 6px;
  background: var(--color-elevated);
}

.canvas-markdown--node {
  --markdown-block-spacing: 8px;
  --markdown-heading-spacing: 12px;
  --markdown-h1-size: 20px;
  --markdown-h2-size: 18px;
}
</style>
