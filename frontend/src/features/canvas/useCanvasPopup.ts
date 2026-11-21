import { ref, useId, watch } from 'vue'

export function useCanvasPopup() {
  const open = ref(false)
  const triggerKey = useId()

  watch(open, (visible, _, onCleanup) => {
    if (!visible) return

    function dismissOutside(event: PointerEvent) {
      const trigger = document.querySelector(`[data-canvas-popup="${CSS.escape(triggerKey)}"]`)
      if (!trigger) return
      const contentId = trigger.getAttribute('aria-controls')
      const content = contentId ? document.getElementById(contentId) : null
      const path = event.composedPath()
      if (path.includes(trigger) || (content && path.includes(content))) return
      open.value = false
    }

    // Canvas controls can stop pointer events before they bubble to Reka UI.
    document.addEventListener('pointerdown', dismissOutside, true)
    onCleanup(() => document.removeEventListener('pointerdown', dismissOutside, true))
  })

  return { open, triggerKey }
}
