import type { ImageAspectRatio } from '@/components/ui/image-types'

export interface ProcessStep {
  id: string
  title: string
  description?: string
  imageSrc?: string
  imageAlt?: string
  aspectRatio?: ImageAspectRatio | number
}
