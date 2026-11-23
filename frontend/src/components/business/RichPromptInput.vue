<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import XSender, { type AnyTagProps, type MentionItem } from 'x-sender'
import 'x-sender/lib/XSender.css'
import {
  formatPromptToken,
  hasPromptToken,
  parsePromptLine,
  type PromptReferenceKind,
  type PromptReferenceOption,
} from './prompt-references'

const props = withDefaults(
  defineProps<{
    references: readonly PromptReferenceOption[]
    placeholder?: string
    mentionTitle?: string
    expanded?: boolean
    bordered?: boolean
    minHeight?: number
    maxHeight?: string
    disabled?: boolean
  }>(),
  {
    placeholder: '输入提示词，输入 @ 引用素材',
    mentionTitle: '引用素材',
    expanded: false,
    bordered: false,
    minHeight: 94,
    maxHeight: '194px',
    disabled: false,
  },
)

const prompt = defineModel<string>({ default: '' })
const host = ref<HTMLElement>()
const busKey = `richPrompt_${Math.random().toString(36).slice(2, 9)}`
let sender: XSender | undefined
let popup: HTMLDivElement | undefined

const SVG_NS = 'http://www.w3.org/2000/svg'

function svgDataUri(innerSvg: string, bg = '#1e2028', stroke = '#f0c66c'): string {
  const raw = `<svg xmlns="${SVG_NS}" width="28" height="28" viewBox="0 0 28 28"><rect width="28" height="28" rx="6" fill="${bg}"/><g transform="translate(6 6)" fill="none" stroke="${stroke}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${innerSvg}</g></svg>`
  return `data:image/svg+xml;utf8,${encodeURIComponent(raw)}`
}

const ICON_PATHS: Record<PromptReferenceKind | 'broken', string> = {
  image: '<rect x="2" y="2" width="12" height="12" rx="2"/><circle cx="6" cy="6" r="1.2"/><path d="m14 10-3.2-3.2L4 14"/>',
  video: '<rect x="1.5" y="3" width="13" height="10" rx="2"/><path d="m6.5 6 4 2-4 2V6Z"/>',
  audio: '<path d="M6 12V4.5l7-1.5v7.5"/><circle cx="4.5" cy="12" r="1.8"/><circle cx="11.5" cy="10.5" r="1.8"/>',
  text: '<path d="M3 3h10v10H3z"/><path d="M5.5 6.5h5M5.5 9.5h3.5"/>',
  broken: '<circle cx="8" cy="8" r="6"/><path d="M8 5v3.5M8 11h.01"/>',
}

const POPUP_AVATARS: Record<PromptReferenceKind, string> = {
  image: svgDataUri(ICON_PATHS.image, '#1e2028', '#f0c66c'),
  video: svgDataUri(ICON_PATHS.video, '#1a2234', '#7cc4ff'),
  audio: svgDataUri(ICON_PATHS.audio, '#162825', '#6ee7b7'),
  text: svgDataUri(ICON_PATHS.text, '#222229', '#c4c4cf'),
}

function createInlineIcon(kind: PromptReferenceKind | 'broken'): SVGSVGElement {
  const svg = document.createElementNS(SVG_NS, 'svg')
  svg.setAttribute('viewBox', '0 0 16 16')
  svg.setAttribute('width', '13')
  svg.setAttribute('height', '13')
  svg.setAttribute('fill', 'none')
  svg.setAttribute('stroke', 'currentColor')
  svg.setAttribute('stroke-width', '1.6')
  svg.setAttribute('stroke-linecap', 'round')
  svg.setAttribute('stroke-linejoin', 'round')
  svg.setAttribute('aria-hidden', 'true')
  svg.classList.add('rich-prompt-ref-icon')
  svg.innerHTML = ICON_PATHS[kind]
  return svg
}

const mentions = computed<MentionItem[]>(() =>
  props.references.map((item) => ({
    id: item.tokenKey,
    name: item.label,
    avatar: item.kind === 'image' && item.thumbnailUrl ? item.thumbnailUrl : POPUP_AVATARS[item.kind],
  })),
)

function mentionConfig() {
  return { dialogTitle: props.mentionTitle, callEvery: false, options: mentions.value }
}

function buildReferenceElement(tokenKey: string, removedLabel?: string): HTMLSpanElement {
  const tag = document.createElement('span')
  const item = !removedLabel
    ? props.references.find((entry) => entry.tokenKey === tokenKey)
    : undefined

  if (removedLabel || !item) {
    tag.className = 'rich-prompt-ref is-broken'
    if (removedLabel) {
      tag.dataset.removed = removedLabel
      tag.dataset.reference = ''
    } else {
      tag.dataset.reference = tokenKey
    }
    tag.append(createInlineIcon('broken'))
    const text = document.createElement('span')
    text.textContent = removedLabel ? `${removedLabel} · 已移除` : `${tokenKey} · 已移除`
    tag.append(text)
    return tag
  }

  tag.className = `rich-prompt-ref is-${item.kind}`
  tag.dataset.reference = item.tokenKey

  if (item.kind === 'image' && item.thumbnailUrl) {
    const img = document.createElement('img')
    img.src = item.thumbnailUrl
    img.alt = ''
    tag.append(img)
  } else {
    tag.append(createInlineIcon(item.kind))
  }

  const labelEl = document.createElement('span')
  labelEl.textContent = item.label
  tag.append(labelEl)
  return tag
}

function referenceHtml(tokenKey: string, removedLabel?: string): string {
  return buildReferenceElement(tokenKey, removedLabel).outerHTML
}

function toModel(value: string): AnyTagProps[][] {
  return value.split('\n').map((line) => {
    const tags: AnyTagProps[] = []
    for (const seg of parsePromptLine(line)) {
      if (seg.type === 'text') {
        tags.push({ type: 'Write', text: seg.text })
        continue
      }
      if (tags.at(-1)?.type !== 'Write') tags.push({ type: 'Write', text: '' })
      tags.push({ type: 'Custom', html: referenceHtml(seg.tokenKey, seg.removedLabel) })
    }
    if (tags.at(-1)?.type !== 'Write') tags.push({ type: 'Write', text: '' })
    return tags
  })
}

function toText(model: AnyTagProps[][]): string {
  return model
    .map((line) =>
      line
        .map((tag) => {
          if (tag.type === 'Write' || tag.type === 'Input') return tag.text ?? ''
          if (tag.type === 'Custom') {
            const template = document.createElement('template')
            template.innerHTML = tag.html
            const el = template.content.querySelector<HTMLElement>('[data-reference], [data-removed]')
            const removed = el?.dataset.removed
            if (removed) return formatPromptToken('', removed)
            const id = el?.dataset.reference
            return id ? formatPromptToken(id) : ''
          }
          return (tag.type === 'Mention' ? '@' : '') + tag.name
        })
        .join(''),
    )
    .join('\n')
}

function close() {
  sender?.bus.emit(XSender.EventSet.EVENT_COMMON_DIALOG_CLOSE)
}

async function insertMention(event: MouseEvent) {
  const id = (event.target as Element).closest<HTMLElement>('.chat-mention-dialog-item')?.dataset.id
  const instance = sender
  if (!instance || !id || !props.references.some((item) => item.tokenKey === id)) return
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
  tags.splice(
    tagIndex,
    1,
    { type: 'Write', text: tag.text.slice(0, start) },
    { type: 'Custom', html: referenceHtml(id) },
    { type: 'Write', text: tag.text.slice(cursor.offset) },
  )
  await instance.reset({ chatNode: model, clearHistory: false })
  if (sender === instance) {
    prompt.value = toText(model)
    const replacement =
      instance.chatElement.richText.children[rowIndex]?.children[tagIndex + 2]?.querySelector(
        '.chat-write-input',
      )?.firstChild
    if (replacement) {
      instance.chatElement.richText.focus()
      window.getSelection()?.collapse(replacement, 0)
    }
  }
}

async function insertReference(tokenKey: string) {
  const instance = sender
  if (!instance || props.disabled) return
  if (!props.references.some((item) => item.tokenKey === tokenKey)) return

  const model = instance.getModel()
  const cursor = instance.getCurrentNode()
  let rowIndex = Math.max(0, model.length - 1)
  let tagIndex = -1
  let offset = 0

  if (cursor) {
    const write = cursor.node instanceof Element ? cursor.node : cursor.node.parentElement
    const mark = write?.closest('.chat-write-wrap')
    const row = mark?.closest('.chat-grid-wrap')
    if (row && mark && row.parentElement) {
      rowIndex = Array.from(row.parentElement.children).indexOf(row)
      tagIndex = Array.from(row.children).indexOf(mark)
      offset = cursor.offset
    }
  }

  const tags = model[rowIndex] ?? [{ type: 'Write' as const, text: '' }]
  if (!model[rowIndex]) model[rowIndex] = tags

  const targetTag = tagIndex >= 0 ? tags[tagIndex] : undefined
  if (targetTag?.type === 'Write') {
    const currentText = targetTag.text ?? ''
    tags.splice(
      tagIndex,
      1,
      { type: 'Write', text: currentText.slice(0, offset) },
      { type: 'Custom', html: referenceHtml(tokenKey) },
      { type: 'Write', text: currentText.slice(offset) },
    )
  } else {
    if (tags.at(-1)?.type !== 'Write') tags.push({ type: 'Write', text: '' })
    tags.push({ type: 'Custom', html: referenceHtml(tokenKey) }, { type: 'Write', text: '' })
    tagIndex = tags.length - 3
  }

  await instance.reset({ chatNode: model, clearHistory: false })
  if (sender === instance) {
    prompt.value = toText(model)
    const replacement =
      instance.chatElement.richText.children[rowIndex]?.children[tagIndex + 2]?.querySelector(
        '.chat-write-input',
      )?.firstChild
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
  const active = items.findIndex((item) => item.hasAttribute('data-rich-active'))
  if (event.key === 'Enter') {
    event.preventDefault()
    event.stopImmediatePropagation()
    items[Math.max(0, active)]?.click()
    return
  }
  event.preventDefault()
  event.stopImmediatePropagation()
  items[active]?.removeAttribute('data-rich-active')
  const step = event.key === 'ArrowDown' ? 1 : -1
  const index =
    active < 0
      ? step > 0
        ? 0
        : items.length - 1
      : (active + step + items.length) % items.length
  const next = items[index]
  next?.setAttribute('data-rich-active', '')
  next?.scrollIntoView({ block: 'nearest' })
}

function handlePaste() {
  const instance = sender
  if (!instance) return
  window.setTimeout(() => {
    if (sender !== instance) return
    const text = toText(instance.getModel())
    const hasRawTokenInWrite = instance.getModel().some((line) =>
      line.some((tag) => tag.type === 'Write' && hasPromptToken(tag.text ?? '')),
    )
    if (hasRawTokenInWrite) {
      void instance.reset({ chatNode: toModel(text), clearHistory: false })
    }
    if (prompt.value !== text) prompt.value = text
  }, 0)
}

function closeOutside(event: PointerEvent) {
  if (
    event.target instanceof Node
    && !host.value?.contains(event.target)
    && !popup?.contains(event.target)
  ) {
    close()
  }
}

function syncEditableState() {
  if (!sender) return
  const editable = sender.chatElement.richText.querySelector<HTMLElement>('[contenteditable]')
  if (editable) {
    editable.setAttribute('contenteditable', props.disabled ? 'false' : 'true')
  }
}

function refreshRenderedChips() {
  if (!host.value) return
  for (const tag of host.value.querySelectorAll<HTMLElement>('[data-reference], [data-removed]')) {
    const removed = tag.dataset.removed
    const nextEl = buildReferenceElement(tag.dataset.reference ?? '', removed || undefined)
    tag.className = nextEl.className
    tag.replaceChildren(...nextEl.childNodes)
  }
}

onMounted(async () => {
  await nextTick()
  if (!host.value) return
  popup = document.createElement('div')
  const dialog = host.value.closest('.ui-dialog')
  popup.className = dialog ? 'rich-mention-layer rich-mention-layer--dialog' : 'rich-mention-layer'
  const container = dialog ?? document.body
  container.append(popup)
  popup.addEventListener('mousedown', (event) => event.preventDefault())
  popup.addEventListener('click', insertMention, true)
  host.value.addEventListener('keydown', handleKey, true)
  host.value.addEventListener('paste', handlePaste, true)
  document.addEventListener('pointerdown', closeOutside, true)

  const instance = new XSender(host.value, {
    placeholder: props.placeholder,
    autoFocus: false,
    chatStyle: {
      maxHeight: props.expanded ? '100%' : props.maxHeight,
      fontSize: '14px',
      lineHeight: '1.6',
    },
    getPopupContainer: () => popup!,
    mentionConfig: mentionConfig(),
    keyboardSendFun: () => false,
    keyboardWrapFun: (event) => event.key === 'Enter' && !event.isComposing,
  })
  sender = instance
  instance.chatElement.richText.setAttribute('aria-label', '提示词')
  instance.chatElement.richText.setAttribute('role', 'textbox')
  instance.chatElement.richText.setAttribute('aria-multiline', 'true')
  instance.bus.on(busKey, XSender.EventSet.EVENT_COMMON_CHANGE, () => {
    const value = toText(instance.getModel())
    if (prompt.value !== value) prompt.value = value
  })
  await instance.reset({ chatNode: toModel(prompt.value), clearHistory: true })
  syncEditableState()
})

watch(
  () => props.references,
  () => {
    if (!sender) return
    sender.updateConfig({ mentionConfig: mentionConfig() })
    if (!hasPromptToken(prompt.value)) return
    refreshRenderedChips()
  },
  { deep: true },
)

watch(
  () => props.disabled,
  () => syncEditableState(),
)

watch(prompt, (value) => {
  if (sender && value !== toText(sender.getModel())) {
    void sender.reset({ chatNode: toModel(value), clearHistory: false }).then(() => {
      syncEditableState()
    })
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', closeOutside, true)
  host.value?.removeEventListener('keydown', handleKey, true)
  host.value?.removeEventListener('paste', handlePaste, true)
  sender?.bus.offKeyEvent(busKey)
  close()
  sender?.bus.emit(XSender.EventSet.EVENT_COMMON_DESTROY)
  popup?.remove()
})

defineExpose({ insertReference })
</script>

<template>
  <div
    ref="host"
    class="rich-prompt-input nodrag nopan nowheel"
    :style="{ '--rich-prompt-min-height': `${minHeight}px` }"
    :data-has-prompt="!!prompt.trim()"
    :data-expanded="expanded"
    :data-bordered="bordered"
    :data-disabled="disabled"
    @pointerdown.stop
    @mousedown.stop
    @keydown.stop
    @wheel.stop
  />
</template>

<style>
.rich-prompt-input,
.rich-mention-layer {
  --chat-text: var(--color-text);
  --chat-text-secondary: var(--color-muted);
  --chat-text-placeholder: var(--color-muted);
  --chat-box: var(--color-elevated);
  --chat-card: var(--color-surface);
  --chat-primary: var(--color-gold-soft);
  --chat-highlight-card: var(--gold-tint);
}

.rich-prompt-input {
  --chat-rect-padding: 6px;
  position: relative;
  min-width: 0;
  color: var(--color-text);
  cursor: text;
}

.rich-prompt-input[data-disabled='true'] {
  opacity: 0.65;
  cursor: not-allowed;
}

.rich-prompt-input [contenteditable] {
  outline: 0;
  overflow-wrap: anywhere;
  cursor: text;
}

.rich-prompt-input[data-disabled='true'] [contenteditable] {
  cursor: not-allowed;
}

.rich-prompt-input .chat-rich-text > [contenteditable] {
  min-height: var(--rich-prompt-min-height, 94px);
}

.rich-prompt-input[data-bordered='true'] {
  --chat-rect-padding: 11px 12px;
}

.rich-prompt-input[data-bordered='true'] .chat-rich-text {
  border: 1px solid var(--border-control);
  border-radius: 8px;
  background: var(--color-canvas);
  transition: border-color 140ms ease;
}

.rich-prompt-input[data-bordered='true'] .chat-rich-text:focus-within {
  border-color: var(--color-gold);
}

.rich-prompt-input[data-bordered='true'] .chat-placeholder-wrap {
  inset: 1px 1px auto;
  width: auto;
}

.rich-prompt-input[data-expanded='true'] {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: var(--rich-prompt-min-height, 142px);
  --chat-rect-padding: 12px;
}

.rich-prompt-input[data-expanded='true'] .chat-area-wrap {
  display: flex;
  flex-direction: column;
  flex: 1;
  width: 100%;
  min-height: 0;
}

.rich-prompt-input[data-expanded='true'] .chat-rich-text {
  flex: 1;
  min-height: 0;
  height: 100%;
  border: 1px solid var(--border-control);
  border-radius: 8px;
  background: var(--color-canvas);
  transition: border-color 140ms ease;
}

.rich-prompt-input[data-expanded='true'] .chat-rich-text:focus-within {
  border-color: var(--color-gold);
}

.rich-prompt-input[data-expanded='true'] .chat-rich-text > [contenteditable] {
  min-height: 100%;
}

.rich-prompt-input[data-expanded='true'] .chat-placeholder-wrap {
  inset: 1px 1px auto;
  width: auto;
}

.rich-prompt-input .chat-scroll::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.rich-prompt-input .chat-scroll::-webkit-scrollbar-track {
  background: transparent;
  box-shadow: none;
}

.rich-prompt-input .chat-scroll::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgb(255 255 255 / 16%);
  box-shadow: none;
}

.rich-prompt-input .chat-scroll::-webkit-scrollbar-thumb:hover {
  background: rgb(255 255 255 / 28%);
}

.rich-prompt-input .chat-placeholder-wrap {
  font-size: var(--font-size-body);
  font-style: normal;
}

.rich-prompt-input[data-has-prompt='true'] .chat-placeholder-wrap {
  display: none;
}

.rich-prompt-ref {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 0 2px;
  padding: 1px 6px 1px 4px;
  border-radius: 5px;
  border: 1px solid rgb(240 184 75 / 26%);
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-size: 12px;
  line-height: 1.45;
  vertical-align: middle;
}

.rich-prompt-ref img {
  width: 18px;
  height: 14px;
  object-fit: cover;
  border-radius: 3px;
  display: block;
}

.rich-prompt-ref-icon {
  flex: none;
  display: block;
}

.rich-prompt-ref.is-video {
  border-color: rgb(124 196 255 / 32%);
  background: rgb(56 139 253 / 14%);
  color: #93d5ff;
}

.rich-prompt-ref.is-audio {
  border-color: rgb(110 231 183 / 32%);
  background: rgb(16 185 129 / 14%);
  color: #7ee8be;
}

.rich-prompt-ref.is-text {
  border-color: rgb(255 255 255 / 16%);
  background: rgb(255 255 255 / 7%);
  color: #dcdce4;
}

.rich-prompt-ref.is-broken {
  border-color: rgb(239 68 68 / 40%);
  background: rgb(239 68 68 / 12%);
  color: #fca5a5;
}

.rich-mention-layer {
  position: fixed;
  inset: 0;
  z-index: 140;
  pointer-events: none;
}

.rich-mention-layer--dialog {
  position: absolute;
}

.rich-mention-layer .chat-mention-dialog-wrap {
  pointer-events: auto;
  background: var(--color-elevated);
  color: var(--color-text);
  border-color: var(--border-control);
  box-shadow: 0 12px 32px rgb(0 0 0 / 45%);
}

.rich-mention-layer .chat-mention-dialog-item-avatar {
  border-radius: 4px;
  object-fit: cover;
}

.rich-mention-layer .chat-mention-dialog-item[data-rich-active] {
  background: var(--gold-tint);
}

.rich-mention-layer .chat-mention-dialog-item[data-rich-active] .chat-mention-dialog-item-name {
  color: var(--color-gold-soft);
}

.ui-dialog:has(.rich-mention-layer--dialog) {
  overflow: visible;
}
</style>
