export const imageAspectRatios = {
  '16:9': 16 / 9,
  '4:3': 4 / 3,
  '3:4': 3 / 4,
  '1:1': 1,
  '9:16': 9 / 16,
} as const

export type ImageAspectRatio = keyof typeof imageAspectRatios
export type ImageFit = 'cover' | 'contain'
