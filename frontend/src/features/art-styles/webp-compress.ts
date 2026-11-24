export interface FitDimensions {
  width: number
  height: number
}

export function computeFitDimensions(
  srcWidth: number,
  srcHeight: number,
  maxWidth: number,
  maxHeight: number,
): FitDimensions {
  if (srcWidth <= 0 || srcHeight <= 0) {
    return { width: maxWidth, height: maxHeight }
  }
  const scale = Math.min(1, maxWidth / srcWidth, maxHeight / srcHeight)
  return {
    width: Math.max(1, Math.round(srcWidth * scale)),
    height: Math.max(1, Math.round(srcHeight * scale)),
  }
}

export function replaceFileExtWithWebp(fileName: string): string {
  const cleaned = fileName.trim() || 'art-style'
  const base = cleaned.replace(/\.[^./\\]+$/u, '') || 'art-style'
  return `${base}.webp`
}

async function decodeImageSource(file: File): Promise<{
  width: number
  height: number
  draw: (ctx: CanvasRenderingContext2D, w: number, h: number) => void
  cleanup: () => void
}> {
  if (typeof createImageBitmap === 'function') {
    const bitmap = await createImageBitmap(file)
    return {
      width: bitmap.width,
      height: bitmap.height,
      draw: (ctx, w, h) => ctx.drawImage(bitmap, 0, 0, w, h),
      cleanup: () => bitmap.close(),
    }
  }
  const objectUrl = URL.createObjectURL(file)
  const img = await new Promise<HTMLImageElement>((resolve, reject) => {
    const el = new Image()
    el.onload = () => resolve(el)
    el.onerror = () => reject(new Error('无法解析所选图片文件'))
    el.src = objectUrl
  })
  return {
    width: img.naturalWidth || img.width,
    height: img.naturalHeight || img.height,
    draw: (ctx, w, h) => ctx.drawImage(img, 0, 0, w, h),
    cleanup: () => URL.revokeObjectURL(objectUrl),
  }
}

export async function convertImageFileToWebp(
  file: File,
  options: { maxWidth?: number; maxHeight?: number; quality?: number } = {},
): Promise<File> {
  const maxWidth = options.maxWidth ?? 960
  const maxHeight = options.maxHeight ?? 540
  const quality = options.quality ?? 0.84

  if (typeof document === 'undefined') {
    return file
  }

  const decoded = await decodeImageSource(file)
  try {
    const { width, height } = computeFitDimensions(decoded.width, decoded.height, maxWidth, maxHeight)
    // 如果本身已是较小 WebP 且未超限，直接复用避免二次有损压缩
    if (file.type === 'image/webp' && decoded.width <= maxWidth && decoded.height <= maxHeight && file.size <= 160 * 1024) {
      return file
    }

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    if (!ctx) return file

    ctx.imageSmoothingEnabled = true
    ctx.imageSmoothingQuality = 'high'
    decoded.draw(ctx, width, height)

    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob(resolve, 'image/webp', quality)
    })
    if (!blob || blob.type !== 'image/webp') {
      return file
    }
    return new File([blob], replaceFileExtWithWebp(file.name), {
      type: 'image/webp',
      lastModified: Date.now(),
    })
  } finally {
    decoded.cleanup()
  }
}
