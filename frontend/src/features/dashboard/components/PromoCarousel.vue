<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ArrowUpRight, ChevronLeft, ChevronRight, Pause, Play } from 'lucide-vue-next'
import UiIconButton from '@/components/ui/UiIconButton.vue'
import { wrapSlideIndex } from './carousel-index'
import type { PromoSlide } from './promo-types'

const props = withDefaults(defineProps<{
  slides: readonly PromoSlide[]
  autoplay?: boolean
  interval?: number
}>(), { autoplay: true, interval: 6500 })
const emit = defineEmits<{ select: [slide: PromoSlide] }>()
const model = defineModel<number>({ default: 0 })
const active = computed(() => wrapSlideIndex(model.value, props.slides.length))
const hovered = ref(false)
const focused = ref(false)
const paused = ref(false)
const hidden = ref(false)
const reducedMotion = ref(false)
const mounted = ref(false)
const carousel = ref<HTMLElement>()
let timer: ReturnType<typeof setInterval> | undefined
let motionQuery: MediaQueryList | undefined
const running = computed(() => props.autoplay && props.slides.length > 1 && !paused.value && !hovered.value && !focused.value && !hidden.value && !reducedMotion.value)

function move(offset: number) {
  model.value = wrapSlideIndex(active.value + offset, props.slides.length)
  restart()
}

function choose(index: number) {
  if (index === active.value) {
    const slide = props.slides[index]
    if (slide?.actionLabel) emit('select', slide)
  }
  else {
    model.value = index
    restart()
  }
}

function restart() {
  clearInterval(timer)
  if (mounted.value && running.value) {
    const delay = Number.isFinite(props.interval) ? Math.max(1000, props.interval) : 6500
    timer = setInterval(() => { model.value = wrapSlideIndex(active.value + 1, props.slides.length) }, delay)
  }
}

function slidePosition(index: number) {
  const distance = wrapSlideIndex(index - active.value, props.slides.length)
  if (distance === 0) return 'is-current'
  if (distance === 1) return 'is-next'
  if (distance === props.slides.length - 1) return 'is-previous'
  return 'is-hidden'
}

function onFocusOut(event: FocusEvent) {
  focused.value = event.currentTarget instanceof HTMLElement && event.relatedTarget instanceof Node
    ? event.currentTarget.contains(event.relatedTarget)
    : false
}

async function onArrow(event: KeyboardEvent, offset: number) {
  const focusSlide = event.target instanceof HTMLElement && event.target.classList.contains('promo-slide')
  move(offset)
  if (focusSlide) {
    await nextTick()
    carousel.value?.querySelector<HTMLButtonElement>('.promo-slide.is-current')?.focus()
  }
}

function onVisibilityChange() { hidden.value = document.hidden }
function onMotionChange() { reducedMotion.value = motionQuery?.matches ?? false }
watch([running, () => props.interval], restart)
watch(() => props.slides.length, (count) => {
  model.value = wrapSlideIndex(model.value, count)
  restart()
})
onMounted(() => {
  mounted.value = true
  motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  onMotionChange()
  onVisibilityChange()
  motionQuery.addEventListener('change', onMotionChange)
  document.addEventListener('visibilitychange', onVisibilityChange)
  restart()
})
onUnmounted(() => {
  clearInterval(timer)
  motionQuery?.removeEventListener('change', onMotionChange)
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<template>
  <section
    v-if="slides.length"
    ref="carousel"
    class="promo-carousel"
    aria-label="创作精选"
    aria-roledescription="轮播"
    @mouseenter="hovered = true"
    @mouseleave="hovered = false"
    @focusin="focused = true"
    @focusout="onFocusOut"
    @keydown.left.prevent="onArrow($event, -1)"
    @keydown.right.prevent="onArrow($event, 1)"
  >
    <div class="promo-carousel-track" :aria-live="running ? 'off' : 'polite'" aria-atomic="false">
      <component
        :is="slide.actionLabel ? 'button' : 'div'"
        v-for="(slide, index) in slides"
        :key="slide.id"
        :type="slide.actionLabel ? 'button' : undefined"
        class="promo-slide"
        :class="slidePosition(index)"
        :tabindex="index === active && slide.actionLabel ? 0 : -1"
        :aria-hidden="index !== active"
        :aria-label="slide.actionLabel ? `${slide.title}，${slide.actionLabel}` : undefined"
        @click="choose(index)"
      >
        <img :src="slide.imageUrl" :alt="slide.imageAlt" :style="{ objectPosition: slide.imagePosition || 'center' }" :loading="index === 0 ? 'eager' : 'lazy'" decoding="async" />
        <span class="promo-slide-shade" aria-hidden="true" />
        <span class="promo-slide-content">
          <strong>{{ slide.title }}</strong>
          <span v-if="slide.description" class="promo-slide-description">{{ slide.description }}</span>
          <span v-if="slide.actionLabel" class="promo-slide-action">{{ slide.actionLabel }}<ArrowUpRight :size="15" aria-hidden="true" /></span>
        </span>
      </component>
    </div>
    <div v-if="slides.length > 1" class="promo-carousel-controls">
      <UiIconButton label="上一张推广图片" @click="move(-1)"><ChevronLeft :size="15" /></UiIconButton>
      <div class="promo-carousel-dots" role="group" aria-label="选择推广图片">
        <button
          v-for="(slide, index) in slides"
          :key="slide.id"
          type="button"
          :class="{ 'is-active': index === active }"
          :aria-label="`第 ${index + 1} 张：${slide.title}`"
          :aria-current="index === active ? 'true' : undefined"
          @click="model = index; restart()"
        ><span /></button>
      </div>
      <UiIconButton label="下一张推广图片" @click="move(1)"><ChevronRight :size="15" /></UiIconButton>
      <UiIconButton v-if="autoplay && !reducedMotion" :label="paused ? '恢复自动轮播' : '暂停自动轮播'" @click="paused = !paused"><Play v-if="paused" :size="13" /><Pause v-else :size="13" /></UiIconButton>
    </div>
  </section>
</template>

<style scoped>
.promo-carousel { min-width: 0; }
.promo-carousel-track { position: relative; height: 248px; overflow: hidden; }
.promo-slide { position: absolute; top: 0; left: 50%; display: block; width: 68%; height: 100%; overflow: hidden; padding: 0; border: 1px solid rgb(255 255 255 / 10%); border-radius: 8px; background: #1b1b20; text-align: left; color: white; transform: translateX(-50%); transition: transform .5s ease, opacity .5s ease; }
.promo-slide img { display: block; width: 100%; height: 100%; object-fit: cover; }
.promo-slide-shade { position: absolute; inset: 0; background: linear-gradient(90deg, rgb(0 0 0 / 66%), rgb(0 0 0 / 9%) 80%); }
.promo-slide.is-current { z-index: 3; }
.promo-slide.is-previous { z-index: 1; opacity: .68; transform: translateX(-122%) scale(.87); }
.promo-slide.is-next { z-index: 1; opacity: .68; transform: translateX(22%) scale(.87); }
.promo-slide.is-hidden { visibility: hidden; opacity: 0; transform: translateX(-50%) scale(.8); }
.promo-slide-content { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: flex-start; justify-content: center; padding: 28px 36px; }
.promo-slide-content strong { max-width: 100%; font-size: 26px; font-weight: 600; line-height: 1.5; overflow-wrap: anywhere; }
.promo-slide-description { max-width: 360px; margin-top: 8px; color: #e0deda; font-size: 13px; line-height: 1.7; }
.promo-slide-action { display: inline-flex; align-items: center; gap: 12px; margin-top: 24px; color: #ffe0a1; font-size: 13px; }
.promo-carousel-controls { display: flex; align-items: center; justify-content: center; gap: 8px; height: 42px; }
.promo-carousel-controls .ui-icon-button { width: 24px; height: 24px; }
.promo-carousel-dots { display: flex; align-items: center; }
.promo-carousel-dots button { display: flex; align-items: center; justify-content: center; width: 24px; height: 24px; padding: 4px; border: 0; background: transparent; }
.promo-carousel-dots span { width: 5px; height: 5px; border-radius: 3px; background: #55535a; transition: width .2s, background .2s; }
.promo-carousel-dots .is-active span { width: 16px; background: var(--color-gold); }
@media (min-width: 1500px) { .promo-carousel-track { height: 280px; } }
@media (max-width: 960px) { .promo-slide { width: 80%; } .promo-slide-content { padding: 24px; } .promo-slide-content strong { font-size: 23px; } }
@media (max-width: 560px) {
  .promo-carousel-track { height: 206px; }
  .promo-slide { width: 100%; }
  .promo-slide.is-next, .promo-slide.is-previous { visibility: hidden; }
  .promo-slide-content { padding: 22px; }
  .promo-slide-content strong { font-size: 22px; }
  .promo-slide-description { max-width: 250px; font-size: 12px; }
  .promo-slide-action { margin-top: 20px; }
}
@media (prefers-reduced-motion: reduce) { .promo-slide { transition: none; } }
</style>
