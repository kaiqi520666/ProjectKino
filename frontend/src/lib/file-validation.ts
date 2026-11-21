export function validateFile(
  file: { name: string; size: number },
  extensions: readonly string[],
  maxBytes: number,
): string | null {
  if (!file.size) return '文件为空，请重新选择'
  if (file.size > maxBytes) return `文件不能超过 ${maxBytes / 1024 / 1024} MB`
  if (!extensions.some((extension) => file.name.toLowerCase().endsWith(extension.toLowerCase()))) {
    return `请选择 ${extensions.join('、')} 格式的文件`
  }
  return null
}
