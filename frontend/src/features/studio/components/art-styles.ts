import type { ArtStyleItem } from '@/features/art-styles/api'

export interface ArtStyle {
  value: string
  label: string
  prompt: string
  imageUrl: string
}

export const defaultArtStyle = 'live-action'

export function toArtStyleOption(item: ArtStyleItem): ArtStyle {
  return {
    value: item.code,
    label: item.label,
    prompt: item.prompt,
    imageUrl: item.imageUrl,
  }
}
