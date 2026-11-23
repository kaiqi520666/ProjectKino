<script setup lang="ts">
import { computed, h, nextTick, onBeforeUnmount, onMounted, reactive, ref, type FunctionalComponent } from 'vue'
import { ArrowLeft, Check, CloudAlert, Copy, FolderOpen, Grid2X2, Loader2, Magnet, Map as MapIcon, Maximize, Minus, Plus, Trash2, Unlink, Waypoints, X } from 'lucide-vue-next'
import { Background, ConnectionLineType, MiniMap, setupVueFlow, SimpleBezierEdge, VueFlow, type Connection, type Edge, type FinalConnectionState, type NodeProps, type Viewport, type XYPosition } from '@xyflow/vue'
import '@xyflow/vue/dist/style.css'
import UiIconButton from '@/components/ui/UiIconButton.vue'
import ImagePreview from '@/components/ui/ImagePreview.vue'
import VideoPreview from '@/components/ui/VideoPreview.vue'
import AssetLibraryDialog from '@/features/assets/AssetLibraryDialog.vue'
import type { AssetLibraryItem, AssetMediaKind } from '@/features/assets/asset-library-types'
import { useModelCatalog } from '@/features/studio/composables/useModelCatalog'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { apiErrorMessage } from '../api'
import { canvasNodeKinds, canvasNodeLabels, canConnectCanvasKinds, canConnectCanvasNodes, outputKind, type CanvasDocument, type CanvasGenerationSettings, type CanvasMedia, type CanvasNode, type CanvasNodeKind } from '../canvas-model'
import { canvasNodeIcons } from '../canvas-node-icons'
import { useCanvasStore, type CanvasJobWatchHooks } from '../canvas-store'
import CanvasWorkNode from './CanvasWorkNode.vue'

const props = defineProps<{ canvas: CanvasDocument }>()
const store = useCanvasStore()
const auth = useAuthStore()
const ui = useUiStore()
const modelCatalog = useModelCatalog()
const flow = setupVueFlow<CanvasNode>()
const stage = ref<HTMLElement>()
const menuElement = ref<HTMLElement>()
const initialViewport = props.canvas.viewport
const fitOnOpen = !initialViewport && props.canvas.nodes.length > 0
const fitOptions = { padding: { top: '64px', right: '28px', bottom: '214px', left: '28px' }, maxZoom: 1 } as const
const minZoom = 0.2
const maxZoom = 8
const zoom = ref(initialViewport?.zoom ?? 1)
const previewOpen = ref(false)
const previewMedia = ref<{ kind: 'image' | 'video'; media: CanvasMedia }>()
const grid = ref(true)
const minimap = ref(false)
const snap = ref(false)
const wires = ref(true)
const draggedNode = ref<string>()
const selecting = ref(false)
const connecting = ref(false)
const libraryOpen = ref(false)
const libraryTarget = ref<string>()
const libraryAllowedKinds = ref<AssetMediaKind[]>(['image', 'video', 'audio', 'text'])
let touchStart: { point: XYPosition; timer: number } | undefined
const selectedIds = computed(() => new Set(props.canvas.nodes.filter(node => node.selected).map(node => node.id)))
const connectedOutputs = computed(() => new Set(props.canvas.edges.map(edge => edge.source)))
const references = computed(() => {
  const sources = new Map(props.canvas.nodes.map(node => [node.id, { ...node, data: reactive(node.data) }]))
  const result = new Map<string, CanvasNode[]>()
  for (const edge of props.canvas.edges) {
    const source = sources.get(edge.source)
    if (source) {
      const items = result.get(edge.target) ?? []
      items.push(source)
      result.set(edge.target, items)
    }
  }
  for (const [target, items] of result) {
    const order = sources.get(target)?.data.referenceOrder
    if (!order?.length) continue
    const ranks = new Map(order.map((id, index) => [id, index]))
    items.sort((a, b) => (ranks.get(a.id) ?? order.length) - (ranks.get(b.id) ?? order.length))
  }
  return result
})
const menu = ref<{ x: number; y: number; position: XYPosition; node?: CanvasNode; edge?: Edge; from?: string; reverse?: boolean }>()
const menuKinds = computed(() => {
  const source = props.canvas.nodes.find(node => node.id === menu.value?.from)
  if (!source) return canvasNodeKinds
  return canvasNodeKinds.filter(kind => menu.value?.reverse
    ? canConnectCanvasKinds(kind, source.type)
    : canConnectCanvasKinds(source.type, kind))
})

function setNodes(nodes?: CanvasNode[]) {
  if (nodes) store.replaceNodes(props.canvas, nodes)
}

function setEdges(edges?: Edge[]) {
  if (edges) props.canvas.edges = edges
}

function edgeIsActive(edge: Pick<Edge, 'source' | 'target'>) {
  return selectedIds.value.has(edge.source) || selectedIds.value.has(edge.target) ||
    draggedNode.value === edge.source || draggedNode.value === edge.target
}

async function openMenu(point: XYPosition, details: Pick<NonNullable<typeof menu.value>, 'node' | 'edge' | 'from' | 'reverse'> = {}) {
  const bounds = stage.value?.getBoundingClientRect()
  if (!bounds) return
  const position = flow.screenToFlowPosition(point)
  if (snap.value) {
    position.x = Math.round(position.x / 24) * 24
    position.y = Math.round(position.y / 24) * 24
  }
  menu.value = { x: point.x - bounds.left, y: point.y - bounds.top, position, ...details }
  if (details.from && !menuKinds.value.length) {
    menu.value = undefined
    return
  }
  await nextTick()
  if (!menu.value || !menuElement.value) return
  menu.value.x = Math.max(6, Math.min(menu.value.x, bounds.width - menuElement.value.offsetWidth - 6))
  menu.value.y = Math.max(6, Math.min(menu.value.y, bounds.height - menuElement.value.offsetHeight - 6))
  menuElement.value.querySelector<HTMLButtonElement>('button[role="menuitem"]')?.focus({ preventScroll: true })
}

function contextMenu(event: MouseEvent, details?: Parameters<typeof openMenu>[1]) {
  event.preventDefault()
  if ((event.target as Element).closest('input, textarea, [contenteditable]')) return
  void openMenu({ x: event.clientX, y: event.clientY }, details)
}

function stageKey(event: KeyboardEvent) {
  if (event.key === 'Escape' && menu.value) {
    menu.value = undefined
    stage.value?.focus()
  }
  if (event.target !== stage.value || (!((event.shiftKey && event.key === 'F10') || event.key === 'ContextMenu'))) return
  event.preventDefault()
  const bounds = stage.value.getBoundingClientRect()
  void openMenu({ x: bounds.left + bounds.width / 3, y: bounds.top + bounds.height / 3 })
}

function cancelTouchMenu() {
  if (!touchStart) return
  window.clearTimeout(touchStart.timer)
  touchStart = undefined
}

function stagePointerDown(event: PointerEvent) {
  if (!menuElement.value?.contains(event.target as Node)) menu.value = undefined
  cancelTouchMenu()
  if (event.pointerType !== 'touch' || !(event.target instanceof Element) ||
    !event.target.closest('.vue-flow__pane') || event.target.closest('.vue-flow__node, .vue-flow__edge')) return
  const point = { x: event.clientX, y: event.clientY }
  touchStart = { point, timer: window.setTimeout(() => {
    touchStart = undefined
    void openMenu(point)
  }, 500) }
}

function stagePointerMove(event: PointerEvent) {
  if (touchStart && Math.hypot(touchStart.point.x - event.clientX, touchStart.point.y - event.clientY) > 8) cancelTouchMenu()
}

function menuKey(event: KeyboardEvent) {
  if (!['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return
  const buttons = [...(menuElement.value?.querySelectorAll<HTMLButtonElement>('button[role="menuitem"]') ?? [])]
  if (!buttons.length) return
  event.preventDefault()
  const index = buttons.findIndex(button => button === document.activeElement)
  const step = event.key === 'ArrowDown' ? 1 : -1
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + step + buttons.length) % buttons.length
  buttons[next]?.focus()
}

function addNode(type: CanvasNodeKind) {
  const placement = menu.value
  if (!placement) return
  menu.value = undefined
  const node = store.addNode(props.canvas, type, placement.position.x, placement.position.y)
  if (placement.from) connect({
    source: placement.reverse ? node.id : placement.from,
    target: placement.reverse ? placement.from : node.id,
    sourceHandle: null,
    targetHandle: null,
  })
}

function duplicateNode(node: CanvasNode) {
  menu.value = undefined
  if (!node.type) return
  store.addNode(props.canvas, node.type, node.position.x + 32, node.position.y + 36, { ...node.data })
}

function deleteItem(node?: CanvasNode, edge?: Edge) {
  menu.value = undefined
  void flow.deleteElements({ nodes: node ? [node] : [], edges: edge ? [edge] : [] })
}

function unlink(target: string, source: string) {
  props.canvas.edges = props.canvas.edges.filter(edge => edge.target !== target || edge.source !== source)
  markEdited()
}

function appendAudio(id: string, file: File) {
  const base = props.canvas.nodes.find(node => node.id === id)
  if (!base) return
  const node = store.addNode(props.canvas, 'audio', base.position.x + 324, base.position.y)
  void uploadNodeMedia(node.id, file)
}

function connectionEnded(event: MouseEvent | TouchEvent, connection: FinalConnectionState) {
  connecting.value = false
  const from = connection.fromNode?.id
  if (connection.isValid || !from) return
  const point = 'changedTouches' in event ? event.changedTouches[0] : event
  if (!point) return
  const target = document.elementFromPoint(point.clientX, point.clientY)
  if (!target?.closest('.vue-flow__pane') || target.closest('.vue-flow__node, .vue-flow__handle, .vue-flow__edge')) return
  void openMenu({ x: point.clientX, y: point.clientY }, { from, reverse: connection.fromHandle?.type === 'target' })
}

async function collect(node: CanvasNode, title: string) {
  try {
    await store.collectAsset(props.canvas.id, node, title)
    ui.notify('已添加到素材库', 'success')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  }
}

async function uploadNodeMedia(nodeId: string, file: File) {
  try {
    await store.replaceMedia(props.canvas, nodeId, file)
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  }
}

function openLibrary(id?: string) {
  libraryTarget.value = id
  const nodeKind = id ? outputKind(props.canvas.nodes.find(node => node.id === id)?.type) : undefined
  libraryAllowedKinds.value = nodeKind ? [nodeKind] : ['image', 'video', 'audio', 'text']
  libraryOpen.value = true
}

function useLibraryItem(item: AssetLibraryItem) {
  const media: CanvasMedia | undefined = item.mediaUrl
    ? { url: item.mediaUrl, key: item.mediaKey, name: item.mediaName || item.title }
    : undefined
  const data = { title: item.title, media, text: item.text }
  const target = libraryTarget.value
  if (target) {
    store.updateNode(props.canvas, target, data)
  } else {
    const bounds = stage.value?.getBoundingClientRect()
    if (!bounds) return
    const where = flow.screenToFlowPosition({ x: bounds.left + bounds.width / 2 - 140, y: bounds.top + bounds.height / 2 - 75 })
    store.addNode(props.canvas, item.kind, where.x, where.y, data)
  }
  libraryOpen.value = false
}

function dropFiles(event: DragEvent) {
  if (!event.dataTransfer?.files.length) return
  const position = flow.screenToFlowPosition({ x: event.clientX, y: event.clientY })
  Array.from(event.dataTransfer.files).forEach((file, i) => {
    const kind = file.type.split('/')[0]
    if (kind === 'image' || kind === 'video' || kind === 'audio') {
      const node = store.addNode(props.canvas, kind, position.x + i * 26, position.y + i * 26)
      void uploadNodeMedia(node.id, file)
    }
  })
}

function canConnect(connection: Pick<Connection, 'source' | 'target'>) {
  const source = props.canvas.nodes.find(node => node.id === connection.source)
  const target = props.canvas.nodes.find(node => node.id === connection.target)
  return !!source && !!target && canConnectCanvasNodes(source, target)
}

function connect(connection: Connection) {
  if (!canConnect(connection) || props.canvas.edges.some(edge => edge.source === connection.source && edge.target === connection.target)) return
  props.canvas.edges = [...props.canvas.edges, { ...connection, id: crypto.randomUUID() }]
  markEdited()
}

function markEdited() {
  props.canvas.updatedAt = new Date().toISOString()
  store.scheduleSave(props.canvas)
}

function saveViewport(viewport: Viewport) {
  props.canvas.viewport = viewport
  store.scheduleSave(props.canvas, 1200)
}

async function fitCanvas() {
  if (props.canvas.nodes.length) await flow.fitView({ ...fitOptions, duration: 180 })
  else await flow.setViewport({ x: 0, y: 0, zoom: 1 }, { duration: 180 })
}

async function setCover(media: CanvasMedia) {
  try {
    await store.setCover(props.canvas, media)
    ui.notify('已设为画布封面', 'success')
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  }
}

async function retrySave() {
  try {
    await store.flushSave(props.canvas)
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
  }
}

const currentSaveStatus = computed(() => store.saveStatus[props.canvas.id] ?? 'saved')

function showPreview(kind: 'image' | 'video', media: CanvasMedia) {
  previewMedia.value = { kind, media }
  previewOpen.value = true
}

function createJobHooks(): CanvasJobWatchHooks {
  return {
    onSuccess(job) {
      if (job.jobType === 'canvas_text') ui.notify('画布文本已生成', 'success')
      else if (job.jobType === 'canvas_image') ui.notify('画布图片已生成', 'success')
      else if (job.jobType === 'canvas_video') ui.notify('画布视频已生成', 'success')
    },
    onError(message) {
      ui.notify(message, 'error')
    },
    onSettled() {
      void auth.refreshBalance()
    },
  }
}

async function handleGenerate(nodeId: string, effectiveSettings: CanvasGenerationSettings) {
  const node = props.canvas.nodes.find(item => item.id === nodeId)
  if (!node) return
  store.updateNode(props.canvas, nodeId, {
    settings: { ...node.data.settings, ...effectiveSettings },
  })
  try {
    await store.generateNode(props.canvas, nodeId, references.value.get(nodeId) ?? [], createJobHooks())
  } catch (error) {
    ui.notify(apiErrorMessage(error), 'error')
    void auth.refreshBalance()
  }
}

// A registered component keeps the media element mounted when drag or selection state changes.
const CanvasGraphNode: FunctionalComponent<NodeProps<CanvasNode>> = ({ id, type, data, selected }) => {
  const findNode = () => props.canvas.nodes.find(item => item.id === id)

  return h(CanvasWorkNode, {
    kind: type ?? 'text',
    data: reactive(data),
    selected,
    panelsVisible: selected && selectedIds.value.size === 1 && !draggedNode.value && !selecting.value && !connecting.value,
    generationState: store.generatingNodes[id],
    uploading: store.uploadingNodes[id] ?? false,
    connecting: connecting.value,
    outputConnected: connectedOutputs.value.has(id),
    references: references.value.get(id) ?? [],
    onEdit: value => store.updateNode(props.canvas, id, value),
    onReplace: file => void uploadNodeMedia(id, file),
    onGenerate: settings => void handleGenerate(id, settings),
    onCover: media => void setCover(media),
    onPreview: showPreview,
    onCollect: title => {
      const current = findNode()
      if (current) void collect(current, title)
    },
    onBrowse: () => openLibrary(id),
    onRemove: () => deleteItem(findNode()),
    onUnlink: source => unlink(id, source),
    onClipAudio: file => appendAudio(id, file),
  })
}
CanvasGraphNode.props = ['id', 'type', 'data', 'selected']
CanvasGraphNode.inheritAttrs = false
const nodeTypes = Object.fromEntries(canvasNodeKinds.map(kind => [kind, CanvasGraphNode]))

onMounted(() => {
  void modelCatalog.ensureLoaded()
  store.resumeActiveJobs(props.canvas, createJobHooks())
})

onBeforeUnmount(() => {
  cancelTouchMenu()
  props.canvas.nodes = props.canvas.nodes.map(node => node.selected ? { ...node, selected: false } : node)
  props.canvas.edges = props.canvas.edges.map(edge => edge.selected ? { ...edge, selected: false } : edge)
  void store.flushSave(props.canvas).catch(() => {})
})
</script>

<template>
  <main class="canvas-editor">
    <header class="canvas-editor-bar">
      <RouterLink :to="{ name: 'canvas' }" class="ui-icon-button canvas-editor-back" title="返回画布列表" aria-label="返回画布列表">
        <ArrowLeft :size="17" aria-hidden="true" />
      </RouterLink>
      <h1 :title="canvas.name">{{ canvas.name }}</h1>
      <button
        v-if="currentSaveStatus === 'error'"
        type="button"
        class="canvas-save-badge is-error"
        title="点击重试保存"
        @click="retrySave"
      >
        <CloudAlert :size="13" aria-hidden="true" />
        <span>重试保存</span>
      </button>
      <span v-else class="canvas-save-badge" :class="`is-${currentSaveStatus}`">
        <Loader2 v-if="currentSaveStatus === 'saving'" :size="12" class="ui-spin" aria-hidden="true" />
        <Check v-else :size="12" aria-hidden="true" />
        <span>{{ currentSaveStatus === 'saving' ? '保存中' : '已保存' }}</span>
      </span>
    </header>

    <div ref="stage" class="canvas-editor-stage" tabindex="0" aria-label="画布" @keydown="stageKey"
      @pointerdown.capture="stagePointerDown" @pointermove.capture="stagePointerMove" @pointerup.capture="cancelTouchMenu" @pointercancel.capture="cancelTouchMenu"
      @dragover.prevent @drop.prevent="dropFiles">
      <VueFlow
        :nodes="canvas.nodes"
        :node-types="nodeTypes"
        :edges="canvas.edges"
        :fit-view="fitOnOpen"
        :fit-view-options="fitOptions"
        :default-viewport="initialViewport"
        :min-zoom="minZoom"
        :max-zoom="maxZoom"
        :snap-to-grid="snap"
        :snap-grid="[24, 24]"
        :pro-options="{ hideAttribution: true }"
        :is-valid-connection="canConnect"
        :default-edge-options="{ type: 'reference', interactionWidth: 20 }"
        :connection-line-type="ConnectionLineType.SimpleBezier"
        :select-nodes-on-drag="false"
        :zoom-on-double-click="false"
        :edges-reconnectable="false"
        :delete-key-code="['Backspace', 'Delete']"
        color-mode="dark"
        @update:nodes="setNodes"
        @update:edges="setEdges"
        @connect="connect"
        @node-drag-start="draggedNode = $event.node.id"
        @node-drag-stop="draggedNode = undefined; markEdited()"
        @selection-start="selecting = true"
        @selection-end="selecting = false"
        @edges-delete="markEdited"
        @viewport-change="zoom = $event.zoom"
        @viewport-change-end="saveViewport"
        @pane-context-menu="contextMenu($event)"
        @node-context-menu="contextMenu($event.event, { node: $event.node })"
        @edge-context-menu="contextMenu($event.event, { edge: $event.edge })"
        @connect-start="connecting = true"
        @connect-end="connectionEnded($event.event, $event.connectionState)"
        :class="{ 'canvas-hide-edges': !wires }"
      >
        <Background v-if="grid" variant="dots" :gap="24" :size="1" pattern-color="#37373d" />
        <MiniMap v-if="minimap" pannable zoomable :style="{ bottom: 'var(--canvas-minimap-bottom, 54px)', width: '152px', height: '100px' }" node-color="#b48b47" mask-color="#0e0f12bb" />
        <template #edge-reference="edge">
          <g :class="{ 'canvas-edge-active': edgeIsActive(edge) }"><SimpleBezierEdge v-bind="edge" /></g>
        </template>
      </VueFlow>

      <div v-if="menu" ref="menuElement" class="canvas-node-menu" :style="{ left: menu.x + 'px', top: menu.y + 'px' }" role="menu" aria-label="画布右键菜单" @keydown="menuKey" @contextmenu.prevent>
        <div class="canvas-node-menu-label">
          {{ menu.node ? '节点操作' : menu.edge ? '连线操作' : '添加节点' }}
          <button type="button" title="关闭" aria-label="关闭菜单" @click="menu = undefined"><X :size="14" /></button>
        </div>
        <template v-if="menu.node">
          <button v-if="menu.node.type && ['image', 'video', 'audio'].includes(menu.node.type)" type="button" role="menuitem" class="canvas-node-option"
            @click="openLibrary(menu.node.id); menu = undefined"><FolderOpen :size="16" />从素材库选择</button>
          <button type="button" role="menuitem" class="canvas-node-option" @click="duplicateNode(menu.node)"><Copy :size="16" />复制节点</button>
          <button type="button" role="menuitem" class="canvas-node-option" @click="deleteItem(menu.node)"><Trash2 :size="16" />删除节点</button>
        </template>
        <button v-else-if="menu.edge" type="button" role="menuitem" class="canvas-node-option" @click="deleteItem(undefined, menu.edge)"><Unlink :size="16" />删除连线</button>
        <template v-else>
          <button v-for="kind in menuKinds" :key="kind" type="button" role="menuitem" class="canvas-node-option" @click="addNode(kind)">
            <component :is="canvasNodeIcons[kind]" :size="16" aria-hidden="true" />{{ canvasNodeLabels[kind] }}
          </button>
        </template>
      </div>

      <div class="canvas-tools" role="group" aria-label="画布工具">
        <div class="canvas-tool-group">
          <UiIconButton label="素材库" @click="openLibrary()"><FolderOpen :size="17" /></UiIconButton>
          <UiIconButton label="小地图" :active="minimap" @click="minimap = !minimap"><MapIcon :size="17" /></UiIconButton>
          <UiIconButton label="网格" :active="grid" @click="grid = !grid"><Grid2X2 :size="17" /></UiIconButton>
          <UiIconButton label="网格吸附" :active="snap" @click="snap = !snap"><Magnet :size="17" /></UiIconButton>
          <UiIconButton label="显示连线" :active="wires" @click="wires = !wires"><Waypoints :size="17" /></UiIconButton>
        </div>
        <div class="canvas-tool-group canvas-zoom-controls" role="group" aria-label="画布缩放">
          <UiIconButton label="缩小" :disabled="zoom <= minZoom" @click="flow.zoomOut({ duration: 140 })"><Minus :size="16" aria-hidden="true" /></UiIconButton>
          <button type="button" class="canvas-reset-zoom" title="重置为 100%" @click="flow.zoomTo(1, { duration: 140 })">{{ Math.round(zoom * 100) }}%</button>
          <UiIconButton label="放大" :disabled="zoom >= maxZoom" @click="flow.zoomIn({ duration: 140 })"><Plus :size="16" aria-hidden="true" /></UiIconButton>
          <UiIconButton label="适应画布" @click="fitCanvas"><Maximize :size="16" aria-hidden="true" /></UiIconButton>
        </div>
      </div>
    </div>

    <AssetLibraryDialog
      v-model:open="libraryOpen"
      title="素材库"
      mode="single"
      :allowed-kinds="libraryAllowedKinds"
      @select="useLibraryItem"
    />

    <ImagePreview v-if="previewMedia?.kind === 'image'" v-model:open="previewOpen" :src="previewMedia.media.url" :title="previewMedia.media.name" />
    <VideoPreview v-else-if="previewMedia" v-model:open="previewOpen" :src="previewMedia.media.url" :title="previewMedia.media.name" />
  </main>
</template>

<style scoped>
.canvas-editor {
  position: relative;
  display: grid;
  grid-template-rows: minmax(0, 1fr);
  width: 100%;
  height: 100dvh;
  overflow: hidden;
  background: var(--color-canvas);
  color: var(--color-text);
  isolation: isolate;
}
.canvas-editor-bar {
  position: absolute;
  top: 14px;
  left: 14px;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 7px;
  width: max-content;
  max-width: min(360px, calc(100% - 28px));
  padding: 3px 12px 3px 3px;
  border: 1px solid var(--border-control);
  border-radius: 8px;
  background: var(--color-surface);
}
.canvas-editor-bar h1 {
  min-width: 0;
  overflow: hidden;
  margin: 0;
  font-size: var(--font-size-body);
  font-weight: 600;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.canvas-editor-back { flex: none; width: 34px; height: 34px; border-radius: 6px; }
.canvas-save-badge { display: inline-flex; align-items: center; gap: 4px; flex: none; padding: 2px 7px; border-radius: 99px; border: 1px solid var(--border-subtle); background: rgb(255 255 255 / 3%); color: var(--color-muted); font-size: 11px; white-space: nowrap; }
.canvas-save-badge.is-saving { color: var(--color-gold-soft); border-color: rgb(240 184 75 / 28%); }
.canvas-save-badge.is-error { color: var(--color-error); border-color: rgb(239 146 146 / 38%); background: rgb(239 146 146 / 10%); cursor: pointer; }
.canvas-editor-stage { position: relative; min-width: 0; min-height: 0; }
.canvas-editor-stage :deep(.vue-flow) {
  --xy-background-color: #0c0d10;
  --xy-edge-stroke: #84858a;
  --xy-edge-stroke-width: 1.15px;
  --xy-edge-stroke-selected: #f0b84b;
  --xy-connectionline-stroke: #f0b84b;
  background: #0c0d10;
}
.canvas-editor-stage:focus { outline: none; }
.canvas-editor-stage :deep(.canvas-edge-active .vue-flow__edge-path),
.canvas-editor-stage :deep(.vue-flow__edge.selected .vue-flow__edge-path),
.canvas-editor-stage :deep(.vue-flow__connection-path) { stroke: var(--color-gold); stroke-dasharray: 5 5; }
.canvas-editor-stage :deep(.canvas-hide-edges .vue-flow__edge) { visibility: hidden; }
.canvas-node-menu {
  position: absolute;
  z-index: 60;
  width: 170px;
  max-height: calc(100% - 12px);
  overflow: auto;
  padding: 5px;
  border: 1px solid var(--border-control);
  border-radius: 8px;
  background: var(--color-elevated);
  color: var(--color-text);
  box-shadow: 0 10px 28px rgb(0 0 0 / 35%);
}
.canvas-node-menu-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 9px 7px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--color-muted);
  font-size: var(--font-size-caption);
}
.canvas-node-menu-label button { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 4px; cursor: pointer; }
.canvas-node-option {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 6px 9px;
  min-height: 34px;
  width: 100%;
  border-radius: 5px;
  font-size: var(--font-size-body);
  cursor: pointer;
}
.canvas-node-option svg { color: var(--color-muted); }
.canvas-node-option:is(:hover, :focus-visible), .canvas-node-menu-label button:hover { background: var(--gold-tint); color: var(--color-gold-soft); }
.canvas-tools {
  position: absolute;
  left: 14px;
  bottom: 14px;
  z-index: 5;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  width: max-content;
  max-width: calc(100% - 28px);
  gap: 3px;
  padding: 3px;
  border: 1px solid var(--border-control);
  border-radius: 8px;
  background: var(--color-surface);
}
.canvas-tool-group { display: flex; align-items: center; gap: 3px; }
.canvas-zoom-controls { margin-left: 3px; padding-left: 6px; border-left: 1px solid var(--border-control); }
.canvas-tools .ui-icon-button { width: 32px; height: 32px; border-radius: 5px; }
.canvas-tools .ui-icon-button[aria-pressed='true'] { background: var(--gold-tint); color: var(--color-gold-soft); }
.canvas-reset-zoom { width: 48px; height: 32px; border-radius: 5px; text-align: center; color: var(--color-muted); font-size: var(--font-size-caption); font-variant-numeric: tabular-nums; cursor: pointer; }
.canvas-reset-zoom:hover { background: var(--gold-tint); color: var(--color-gold-soft); }
@media (max-width: 375px) {
  .canvas-editor-stage { --canvas-minimap-bottom: 90px; }
  .canvas-tools { flex-direction: column; align-items: stretch; }
  .canvas-zoom-controls { margin-left: 0; padding-top: 3px; padding-left: 0; border-top: 1px solid var(--border-control); border-left: 0; }
}
</style>
