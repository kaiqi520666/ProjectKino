<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import XSender, { type AnyTagProps, type MentionItem } from 'x-sender'
import 'x-sender/lib/XSender.css'
import { canvasNodeLabels, outputKind, type CanvasNode } from '../canvas-model'

const props = defineProps<{ references: CanvasNode[]; expanded?: boolean }>()
const prompt = defineModel<string>({ default: '' })
const host = ref<HTMLElement>()
const busKey = 'canvasPrompt'
const referencePattern = /(\{\{ref:[\w-]+\}\})/g
let sender: XSender | undefined
let popup: HTMLDivElement | undefined

const mentions = computed<MentionItem[]>(() => props.references.map(node => ({
  id: node.id,
  name: node.data.title || (node.type && canvasNodeLabels[node.type]) || '文本',
  avatar: outputKind(node.type) === 'image' ? node.data.media?.url : undefined,
})))

function mentionConfig() {
  return { dialogTitle: '引用节点', callEvery: false, options: mentions.value }
}

function referenceHtml(id: string) {
  const item = mentions.value.find(entry => entry.id === id)
  const tag = document.createElement('span')
  tag.className = 'canvas-prompt-reference'
  tag.dataset.reference = id
  if (item?.avatar) {
    const image = document.createElement('img')
    image.src = String(item.avatar)
    image.alt = ''
    tag.append(image)
  }
  tag.append(item ? '@' + item.name : '@引用已断开')
  return tag.outerHTML
}

function toModel(value: string): AnyTagProps[][] {
  return value.split('\n').map(line => {
    const tags: AnyTagProps[] = []
    for (const part of line.split(referencePattern)) {
      if (!part) continue
      if (!part.startsWith('{{ref:') || !/^\{\{ref:[\w-]+\}\}$/.test(part)) {
        tags.push({ type: 'Write', text: part })
        continue
      }
      if (tags.at(-1)?.type !== 'Write') tags.push({ type: 'Write', text: '' })
      tags.push({ type: 'Custom', html: referenceHtml(part.slice(6, -2)) })
    }
    if (tags.at(-1)?.type !== 'Write') tags.push({ type: 'Write', text: '' })
    return tags
  })
}

function toText(model: AnyTagProps[][]) {
  return model.map(line => line.map(tag => {
    if (tag.type === 'Write' || tag.type === 'Input') return tag.text ?? ''
    if (tag.type === 'Custom') {
      const template = document.createElement('template')
      template.innerHTML = tag.html
      const id = template.content.querySelector<HTMLElement>('[data-reference]')?.dataset.reference
      return id ? '{{ref:' + id + '}}' : ''
    }
    return (tag.type === 'Mention' ? '@' : '') + tag.name
  }).join('')).join('\n')
}

function close() {
  sender?.bus.emit(XSender.EventSet.EVENT_COMMON_DIALOG_CLOSE)
}

async function insertMention(event: MouseEvent) {
  const id = (event.target as Element).closest<HTMLElement>('.chat-mention-dialog-item')?.dataset.id
  const instance = sender
  if (!instance || !id || !mentions.value.some(item => item.id === id)) return
  const cursor = instance.getCurrentNode()
  if (!cursor) return
  const write = cursor.node instanceof Element ? cursor.node : cursor.node.parentElement
  const mark = write?.closest('.chat-write-wrap')
  const row = mark?.closest('.chat-grid-wrap')
  if (!row || !mark || !row.parentElement) return
  const rowIndex = Array.from(row.parentElement.children).indexOf(row)
  const tagIndex = Array.from(row.children).indexOf(mark)
  const model = instance.getModel()
  const tags = model[rowIndex]
  const tag = tags?.[tagIndex]
  if (!tags || tag?.type !== 'Write') return
  const start = tag.text.lastIndexOf('@', cursor.offset - 1)
  if (start < 0 || start >= cursor.offset) return
  event.preventDefault()
  event.stopPropagation()
  close()
  tags.splice(tagIndex, 1,
    { type: 'Write', text: tag.text.slice(0, start) },
    { type: 'Custom', html: referenceHtml(id) },
    { type: 'Write', text: tag.text.slice(cursor.offset) },
  )
  await instance.reset({ chatNode: model, clearHistory: false })
  if (sender === instance) {
    prompt.value = toText(model)
    const replacement = instance.chatElement.richText.children[rowIndex]?.children[tagIndex + 2]?.querySelector('.chat-write-input')?.firstChild
    if (replacement) {
      instance.chatElement.richText.focus()
      window.getSelection()?.collapse(replacement, 0)
    }
  }
}

function handleKey(event: KeyboardEvent) {
  if (event.key === 'Escape') close()
  if (!popup || event.isComposing || !['ArrowUp', 'ArrowDown', 'Enter'].includes(event.key)) return
  const items = [...popup.querySelectorAll<HTMLElement>('.chat-mention-dialog-item')]
  if (!items.length || !items[0]?.getClientRects().length) return
  const active = items.findIndex(item => item.hasAttribute('data-canvas-active'))
  if (event.key === 'Enter') {
    event.preventDefault()
    event.stopImmediatePropagation()
    items[Math.max(0, active)]?.click()
    return
  }
  event.preventDefault()
  event.stopImmediatePropagation()
  items[active]?.removeAttribute('data-canvas-active')
  const step = event.key === 'ArrowDown' ? 1 : -1
  const index = active < 0 ? (step > 0 ? 0 : items.length - 1) : (active + step + items.length) % items.length
  const next = items[index]
  next?.setAttribute('data-canvas-active', '')
  next?.scrollIntoView({ block: 'nearest' })
}

function closeOutside(event: PointerEvent) {
  if (event.target instanceof Node && !host.value?.contains(event.target) && !popup?.contains(event.target)) close()
}

onMounted(async () => {
  await nextTick()
  if (!host.value) return
  popup = document.createElement('div')
  popup.className = 'canvas-mention-layer'
  const dialog = host.value.closest('.ui-dialog')
  if (dialog) popup.classList.add('canvas-mention-layer--dialog')
  const container = dialog ?? document.body
  container.append(popup)
  popup.addEventListener('mousedown', event => event.preventDefault())
  popup.addEventListener('click', insertMention, true)
  host.value.addEventListener('keydown', handleKey, true)
  document.addEventListener('pointerdown', closeOutside, true)
  const instance = new XSender(host.value, {
    placeholder: '输入提示词，使用 @ 引用已连接的节点',
    autoFocus: false,
    chatStyle: { maxHeight: props.expanded ? '100%' : '194px', fontSize: '14px', lineHeight: '1.5' },
    getPopupContainer: () => popup!,
    mentionConfig: mentionConfig(),
    keyboardSendFun: () => false,
    keyboardWrapFun: event => event.key === 'Enter' && !event.isComposing,
  })
  sender = instance
  instance.chatElement.richText.setAttribute('aria-label', '提示词')
  instance.chatElement.richText.setAttribute('role', 'textbox')
  instance.chatElement.richText.setAttribute('aria-multiline', 'true')
  instance.bus.on(busKey, XSender.EventSet.EVENT_COMMON_CHANGE, () => {
    const value = toText(instance.getModel())
    if (prompt.value !== value) prompt.value = value
  })
  void instance.reset({ chatNode: toModel(prompt.value), clearHistory: true })
})

watch(mentions, () => {
  if (!sender) return
  sender.updateConfig({ mentionConfig: mentionConfig() })
  if (!prompt.value.includes('{{ref:')) return
  for (const tag of host.value?.querySelectorAll<HTMLElement>('[data-reference]') ?? []) {
    const template = document.createElement('template')
    template.innerHTML = referenceHtml(tag.dataset.reference ?? '')
    if (template.content.firstElementChild) tag.replaceChildren(...template.content.firstElementChild.childNodes)
  }
})
watch(prompt, value => {
  if (sender && value !== toText(sender.getModel())) void sender.reset({ chatNode: toModel(value), clearHistory: false })
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', closeOutside, true)
  sender?.bus.offKeyEvent(busKey)
  close()
  sender?.bus.emit(XSender.EventSet.EVENT_COMMON_DESTROY)
  popup?.remove()
})
</script>

<template>
  <div ref="host" class="canvas-prompt-input nodrag nopan nowheel" :data-has-prompt="!!prompt.trim()" :data-expanded="expanded"
    @pointerdown.stop @mousedown.stop @keydown.stop @wheel.stop />
</template>

<style>
.canvas-prompt-input, .canvas-mention-layer {
  --chat-text: var(--color-text);
  --chat-text-secondary: var(--color-muted);
  --chat-text-placeholder: var(--color-muted);
  --chat-box: var(--color-elevated);
  --chat-card: var(--color-surface);
  --chat-primary: var(--color-gold-soft);
  --chat-highlight-card: var(--gold-tint);
}
.canvas-prompt-input { --chat-rect-padding: 6px; position: relative; min-width: 0; color: var(--color-text); cursor: text; }
.canvas-prompt-input [contenteditable] { outline: 0; overflow-wrap: anywhere; cursor: text; }
.canvas-prompt-input .chat-rich-text > [contenteditable] { min-height: 94px; }
.canvas-prompt-input[data-expanded='true'] { display: flex; flex: 1; min-height: 0; }
.canvas-prompt-input[data-expanded='true'] .chat-rich-text { border: 1px solid var(--border-control); border-radius: 8px; background: var(--color-canvas); }
.canvas-prompt-input[data-expanded='true'] .chat-rich-text:focus-within { border-color: var(--color-gold); }
.canvas-prompt-input[data-expanded='true'] .chat-rich-text > [contenteditable] { min-height: 100%; }
.canvas-prompt-input[data-expanded='true'] { --chat-rect-padding: 12px; }
.canvas-prompt-input[data-expanded='true'] .chat-placeholder-wrap { inset: 1px 1px auto; width: auto; }
.canvas-prompt-input .chat-placeholder-wrap { font-size: var(--font-size-body); font-style: normal; }
.canvas-prompt-input[data-has-prompt='true'] .chat-placeholder-wrap { display: none; }
.canvas-prompt-reference { display: inline-flex; align-items: center; gap: 4px; padding: 0 5px; border-radius: 4px; background: var(--gold-tint); color: var(--color-gold-soft); font-size: 12px; vertical-align: baseline; }
.canvas-prompt-reference img { width: 16px; height: 14px; object-fit: cover; border-radius: 2px; }
.canvas-mention-layer { position: fixed; inset: 0; z-index: 120; pointer-events: none; }
.canvas-mention-layer--dialog { position: absolute; }
.canvas-mention-layer .chat-mention-dialog-wrap { pointer-events: auto; }
.ui-dialog:has(.canvas-mention-layer--dialog) { overflow: visible; }
.canvas-mention-layer .chat-mention-dialog-wrap { background: var(--color-elevated); color: var(--color-text); border-color: var(--border-control); }
.canvas-mention-layer .chat-mention-dialog-item[data-canvas-active] .chat-mention-dialog-item-name { color: var(--color-gold-soft); }
</style>
