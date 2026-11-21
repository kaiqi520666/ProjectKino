import { AudioLines, Clapperboard, FileText, Image, ImagePlus, Video } from 'lucide-vue-next'
import type { CanvasNodeKind } from './canvas-model'

export const canvasNodeIcons = {
  text: FileText,
  image: Image,
  video: Clapperboard,
  audio: AudioLines,
  'image-generation': ImagePlus,
  'video-generation': Video,
} satisfies Record<CanvasNodeKind, typeof Image>
