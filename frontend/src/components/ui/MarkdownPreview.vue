<script setup lang="ts">
import { computed } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'

const props = defineProps<{
  content: string
}>()

let hookRegistered = false
if (!hookRegistered && typeof window !== 'undefined') {
  hookRegistered = true
  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (node.tagName === 'A') {
      const href = node.getAttribute('href') ?? ''
      if (href.startsWith('http://') || href.startsWith('https://')) {
        node.setAttribute('target', '_blank')
        node.setAttribute('rel', 'noopener noreferrer')
      }
    }
  })
}

const renderedHtml = computed(() => {
  const raw = (props.content ?? '').trim()
  if (!raw) return ''
  const html = marked.parse(raw, { async: false, gfm: true, breaks: true })
  return DOMPurify.sanitize(typeof html === 'string' ? html : '')
})
</script>

<template>
  <div class="md-preview" v-html="renderedHtml" />
</template>

<style scoped>
.md-preview {
  color: var(--color-text);
  font-size: 13.5px;
  line-height: 1.72;
  overflow-wrap: anywhere;
}

.md-preview :deep(> :first-child) {
  margin-top: 0;
}

.md-preview :deep(> :last-child) {
  margin-bottom: 0;
}

.md-preview :deep(h1),
.md-preview :deep(h2),
.md-preview :deep(h3),
.md-preview :deep(h4) {
  margin: 14px 0 8px;
  color: #f4f4f6;
  font-weight: 600;
  line-height: 1.35;
}

.md-preview :deep(h1) { font-size: 17px; }
.md-preview :deep(h2) { font-size: 15.5px; }
.md-preview :deep(h3) { font-size: 14px; }

.md-preview :deep(p) {
  margin: 8px 0;
}

.md-preview :deep(ul),
.md-preview :deep(ol) {
  margin: 8px 0;
  padding-left: 20px;
}

.md-preview :deep(li) {
  margin: 4px 0;
}

.md-preview :deep(a) {
  color: var(--color-gold-soft);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.md-preview :deep(blockquote) {
  margin: 10px 0;
  padding: 6px 12px;
  border-left: 2px solid rgb(240 184 75 / 45%);
  background: rgb(255 255 255 / 2.5%);
  color: var(--color-muted);
  border-radius: 0 6px 6px 0;
}

.md-preview :deep(code) {
  padding: 1px 5px;
  border-radius: 4px;
  background: rgb(255 255 255 / 7%);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12.5px;
}

.md-preview :deep(pre) {
  margin: 10px 0;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
  background: var(--color-canvas);
  overflow-x: auto;
}

.md-preview :deep(pre code) {
  padding: 0;
  background: transparent;
}

.md-preview :deep(hr) {
  margin: 12px 0;
  border: 0;
  border-top: 1px solid var(--border-subtle);
}

.md-preview :deep(table) {
  width: 100%;
  margin: 10px 0;
  border-collapse: collapse;
  font-size: 12.5px;
}

.md-preview :deep(th),
.md-preview :deep(td) {
  padding: 6px 10px;
  border: 1px solid var(--border-subtle);
  text-align: left;
}

.md-preview :deep(th) {
  background: rgb(255 255 255 / 4%);
  color: var(--color-muted);
  font-weight: 500;
}

.md-preview :deep(img) {
  max-width: 100%;
  border-radius: 8px;
}
</style>
