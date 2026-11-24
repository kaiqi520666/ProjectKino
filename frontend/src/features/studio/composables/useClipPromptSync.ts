import { onBeforeUnmount, watch, type ComputedRef } from 'vue'
import { useUiStore } from '@/stores/ui'
import { apiErrorMessage, updateClipApi } from '../api'
import type { StudioProject } from '../studio-project'
import type { StoryboardClip } from '../studio-storyboard'
import { useStudioStore } from '../studio-store'

interface UseClipPromptSyncOptions {
  project: ComputedRef<StudioProject>
  episodeNumber: ComputedRef<number>
  clip: ComputedRef<StoryboardClip | undefined>
  currentClipLocked: ComputedRef<boolean>
  isClipGenerating: (item?: StoryboardClip) => boolean
}

export function useClipPromptSync(options: UseClipPromptSyncOptions) {
  const studio = useStudioStore()
  const ui = useUiStore()

  let promptSaveTimer: ReturnType<typeof setTimeout> | null = null
  let pendingPromptSave: { clipId: string; prompt: string } | null = null

  async function flushPromptSave() {
    if (promptSaveTimer) {
      clearTimeout(promptSaveTimer)
      promptSaveTimer = null
    }
    if (pendingPromptSave && options.project.value.persisted) {
      const payload = pendingPromptSave
      pendingPromptSave = null
      await updateClipApi(options.project.value.id, payload.clipId, { prompt: payload.prompt })
    }
  }

  function updatePrompt(value: string) {
    const activeClip = options.clip.value
    if (!activeClip || options.currentClipLocked.value) return
    studio.saveClipPrompt(options.project.value.id, options.episodeNumber.value, activeClip.id, value)
    const backendClipId = activeClip.backendId
    if (options.project.value.persisted && backendClipId) {
      pendingPromptSave = { clipId: backendClipId, prompt: value }
      if (promptSaveTimer) clearTimeout(promptSaveTimer)
      promptSaveTimer = setTimeout(() => {
        promptSaveTimer = null
        if (!pendingPromptSave) return
        const payload = pendingPromptSave
        pendingPromptSave = null
        void updateClipApi(options.project.value.id, payload.clipId, { prompt: payload.prompt }).catch(() => {})
      }, 500)
    }
  }

  async function updateClipDuration(value?: string) {
    const activeClip = options.clip.value
    const parsed = Number(value)
    if (!activeClip || !Number.isInteger(parsed) || parsed < 1 || parsed > 60 || parsed === activeClip.durationSeconds) {
      return
    }
    if (options.currentClipLocked.value || options.isClipGenerating(activeClip)) return

    const previous = activeClip.durationSeconds
    const projectId = options.project.value.id
    const epNum = options.episodeNumber.value
    studio.saveClipDuration(projectId, epNum, activeClip.id, parsed)
    if (options.project.value.persisted && activeClip.backendId) {
      try {
        await updateClipApi(projectId, activeClip.backendId, { durationSeconds: parsed })
      } catch (error) {
        studio.saveClipDuration(projectId, epNum, activeClip.id, previous)
        ui.notify(apiErrorMessage(error), 'error')
      }
    }
  }

  async function commitClipDuration(seconds: number) {
    const activeClip = options.clip.value
    if (!activeClip || !Number.isInteger(seconds) || seconds < 1 || seconds > 60 || seconds === activeClip.durationSeconds) {
      return
    }
    await updateClipDuration(String(seconds))
  }

  watch(
    () => options.clip.value?.backendId,
    (nextId, prevId) => {
      if (prevId && nextId !== prevId) {
        void flushPromptSave().catch(() => {})
      }
    },
  )

  onBeforeUnmount(() => {
    void flushPromptSave().catch(() => {})
  })

  return {
    flushPromptSave,
    updatePrompt,
    commitClipDuration,
  }
}
