<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Bell, RotateCw } from 'lucide-vue-next'
import MarkdownPreview from '@/components/ui/MarkdownPreview.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import { formatDateTime } from '@/lib/format'
import { useAuthStore } from '@/stores/auth'
import { computeFirstUnreadCursor } from '../announcement-helpers'
import { useAnnouncementStore } from '../announcement-store'
import { getAnnouncementIndex, listAnnouncements, type AnnouncementItem } from '../api'

const open = defineModel<boolean>('open', { required: true })

const auth = useAuthStore()
const store = useAnnouncementStore()

const items = ref<AnnouncementItem[]>([])
const loading = ref(false)
const loadError = ref(false)
const hasMore = ref(false)
const scrollArea = ref<HTMLElement | null>(null)

let revision = 0
let indexRevision = 0
let loadRevision = 0
let pendingAutoCursor: number | undefined
let observer: IntersectionObserver | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null
let disposed = false

function isCurrent(ver: number, tokenSnapshot: string | null): boolean {
  return !disposed && ver === revision && tokenSnapshot === auth.token && auth.isAuthenticated
}

async function refreshIndex() {
  if (!auth.isAuthenticated) return
  const ver = revision
  const tok = auth.token
  const req = ++indexRevision
  try {
    const res = await getAnnouncementIndex()
    if (!isCurrent(ver, tok) || req !== indexRevision) return
    store.setAvailableIds(res.ids)
    if (
      typeof document !== 'undefined'
      && document.visibilityState === 'visible'
      && !open.value
      && store.unreadCount > 0
      && store.claimLoginCheck()
    ) {
      pendingAutoCursor = computeFirstUnreadCursor(store.availableIds, store.readIds)
      open.value = true
    }
  } catch {
    // 轮询失败保持上次状态，用户手动打开弹窗可重试。
  }
}

async function loadItems(reset: boolean, beforeId?: number) {
  if (loading.value || !auth.isAuthenticated || !open.value) return
  const ver = revision
  const tok = auth.token
  const req = ++loadRevision
  loading.value = true
  loadError.value = false
  try {
    const cursor = reset ? beforeId : items.value.at(-1)?.id
    const res = await listAnnouncements(cursor)
    if (!isCurrent(ver, tok) || !open.value || req !== loadRevision) return
    items.value = reset ? res.items : [...items.value, ...res.items]
    hasMore.value = res.hasMore
    if (reset && scrollArea.value) {
      scrollArea.value.scrollTop = 0
    }
    await nextTick()
    observeVisible()
  } catch {
    if (isCurrent(ver, tok) && open.value && req === loadRevision) {
      loadError.value = true
    }
  } finally {
    if (isCurrent(ver, tok) && req === loadRevision) {
      loading.value = false
    }
  }
}

function markRead(id: number) {
  if (!open.value || (typeof document !== 'undefined' && document.visibilityState !== 'visible')) {
    return
  }
  if (items.value.some((item) => item.id === id)) {
    store.markRead(id)
  }
}

function observeVisible() {
  observer?.disconnect()
  observer = null
  if (
    !open.value
    || !scrollArea.value
    || (typeof document !== 'undefined' && document.visibilityState !== 'visible')
  ) {
    return
  }
  const container = scrollArea.value
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting || entry.intersectionRatio < 1) continue
        observer?.unobserve(entry.target)
        const id = Number((entry.target as HTMLElement).dataset.announcementId)
        if (Number.isSafeInteger(id) && id > 0) {
          markRead(id)
        }
      }
    },
    {
      root: container,
      threshold: 1,
      rootMargin: '0px 0px -32px 0px',
    },
  )

  for (const el of container.querySelectorAll<HTMLElement>('[data-announcement-id]')) {
    const id = Number(el.dataset.announcementId)
    if (Number.isSafeInteger(id) && !store.isRead(id)) {
      observer.observe(el)
    }
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(() => {
    if (auth.isAuthenticated && !open.value && document.visibilityState === 'visible') {
      void refreshIndex()
    }
  }, 60_000)
}

function handleVisibilityChange() {
  if (open.value) {
    observeVisible()
  } else if (document.visibilityState === 'visible' && auth.isAuthenticated) {
    void refreshIndex()
  }
}

watch(open, (next) => {
  if (next) {
    const cursor = pendingAutoCursor
    pendingAutoCursor = undefined
    items.value = []
    hasMore.value = false
    void refreshIndex()
    void loadItems(true, cursor)
  } else {
    loadRevision += 1
    loading.value = false
    observer?.disconnect()
    observer = null
    if (auth.isAuthenticated) {
      void refreshIndex()
    }
  }
})

watch(
  () => auth.user?.id,
  (userId) => {
    revision += 1
    indexRevision += 1
    loadRevision += 1
    pendingAutoCursor = undefined
    open.value = false
    observer?.disconnect()
    observer = null
    items.value = []
    loading.value = false
    if (userId && auth.isAuthenticated) {
      store.activate(userId, window.location.hostname)
      void refreshIndex()
    }
  },
  { immediate: true },
)

onMounted(() => {
  startPolling()
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onBeforeUnmount(() => {
  disposed = true
  if (pollTimer) clearInterval(pollTimer)
  observer?.disconnect()
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>

<template>
  <UiDialog v-model:open="open" title="系统公告" size="wide">
    <div ref="scrollArea" class="ann-scroll">
      <div v-if="loading && !items.length" class="ann-state" role="status">
        加载中…
      </div>

      <div v-else-if="loadError && !items.length" class="ann-state is-error" role="alert">
        <span>公告加载失败</span>
        <UiButton variant="outline" size="sm" :loading="loading" @click="loadItems(true)">
          <template #leading><RotateCw :size="13" aria-hidden="true" /></template>
          重试
        </UiButton>
      </div>

      <div v-else-if="!loading && !items.length" class="ann-state">
        <Bell :size="24" :stroke-width="1.4" aria-hidden="true" />
        <span>暂无公告</span>
      </div>

      <ol v-else class="ann-timeline">
        <li
          v-for="item in items"
          :key="item.id"
          class="ann-item"
          :class="{ 'is-unread': !store.isRead(item.id) }"
        >
          <span class="ann-dot" aria-hidden="true"></span>
          <div class="ann-card">
            <header class="ann-head" :data-announcement-id="item.id">
              <h3>{{ item.title }}</h3>
              <div class="ann-meta">
                <time :datetime="item.publishedAt">{{ formatDateTime(item.publishedAt) }}</time>
                <span v-if="!store.isRead(item.id)" class="ann-unread-pill">未读</span>
              </div>
            </header>
            <MarkdownPreview class="ann-body" :content="item.content" />
          </div>
        </li>
      </ol>

      <div v-if="loadError && items.length" class="ann-more">
        <UiButton variant="outline" size="sm" :loading="loading" @click="loadItems(false)">
          <template #leading><RotateCw :size="13" aria-hidden="true" /></template>
          重试加载
        </UiButton>
      </div>
      <div v-else-if="hasMore" class="ann-more">
        <UiButton variant="outline" size="sm" :loading="loading" @click="loadItems(false)">
          加载更多
        </UiButton>
      </div>
    </div>
  </UiDialog>
</template>

<style scoped>
.ann-scroll {
  max-height: min(68dvh, 620px);
  overflow-y: auto;
  padding-right: 4px;
}

.ann-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 180px;
  color: var(--color-muted);
  font-size: 13px;
}

.ann-state.is-error {
  color: var(--color-error);
}

.ann-timeline {
  position: relative;
  margin: 0;
  padding: 4px 0 4px 18px;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ann-timeline::before {
  content: '';
  position: absolute;
  left: 5px;
  top: 12px;
  bottom: 12px;
  width: 1px;
  background: var(--border-subtle);
}

.ann-item {
  position: relative;
}

.ann-dot {
  position: absolute;
  left: -17px;
  top: 16px;
  width: 9px;
  height: 9px;
  border-radius: 999px;
  border: 2px solid var(--color-surface);
  background: var(--color-muted);
}

.ann-item.is-unread .ann-dot {
  background: var(--color-gold);
  box-shadow: 0 0 0 3px rgb(240 184 75 / 22%);
}

.ann-card {
  padding: 14px 16px;
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  background: rgb(255 255 255 / 2%);
}

.ann-item.is-unread .ann-card {
  border-color: rgb(240 184 75 / 32%);
  background: linear-gradient(180deg, rgb(240 184 75 / 5%), rgb(255 255 255 / 2%));
}

.ann-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding-bottom: 10px;
  margin-bottom: 10px;
  border-bottom: 1px solid var(--border-subtle);
}

.ann-head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #f4f4f6;
}

.ann-meta {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  font-size: 12px;
  color: var(--color-muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.ann-unread-pill {
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid rgb(240 184 75 / 40%);
  background: var(--gold-tint);
  color: var(--color-gold-soft);
  font-size: 11px;
  font-family: inherit;
}

.ann-more {
  display: flex;
  justify-content: center;
  padding: 14px 0 4px;
}
</style>
