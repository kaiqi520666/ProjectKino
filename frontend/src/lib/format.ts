import type { AxiosError } from 'axios'

export function formatDateTime(iso?: string | null): string {
  if (!iso) return '-'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  const hh = String(date.getHours()).padStart(2, '0')
  const mm = String(date.getMinutes()).padStart(2, '0')
  const ss = String(date.getSeconds()).padStart(2, '0')
  return `${y}-${m}-${d} ${hh}:${mm}:${ss}`
}

export function formatCredits(value?: string | number | null): string {
  if (value === null || value === undefined || value === '') return '0'
  const num = Number(value)
  if (!Number.isFinite(num)) return String(value)
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

export function formatSignedCredits(value?: string | number | null): string {
  if (value === null || value === undefined || value === '') return '0'
  const num = Number(value)
  if (!Number.isFinite(num)) return String(value)
  if (num > 0) return `+${formatCredits(num)}`
  return formatCredits(num)
}

export function formatCompactCount(value: unknown): string {
  const num = Number(value)
  if (!Number.isFinite(num)) return String(value)
  if (Math.abs(num) >= 1_000_000) return `${(num / 1_000_000).toFixed(2).replace(/\.?0+$/, '')}M`
  if (Math.abs(num) >= 1_000) return `${(num / 1_000).toFixed(1).replace(/\.0$/, '')}k`
  return String(Math.round(num))
}

export function formatTokenUsage(usage?: Record<string, unknown> | null): string {
  if (!usage || typeof usage !== 'object') return ''
  const parts: string[] = []
  const input = usage.inputTokens ?? usage.input_tokens ?? usage.prompt_tokens
  const output = usage.outputTokens ?? usage.output_tokens ?? usage.completion_tokens
  const cacheHit = usage.cacheReadTokens ?? usage.cache_hit_tokens ?? usage.cache_read_tokens
  const model = usage.modelId ?? usage.model
  if (model) parts.push(String(model))
  if (input !== undefined && input !== null) parts.push(`输入 ${formatCompactCount(input)}`)
  if (cacheHit !== undefined && cacheHit !== null && Number(cacheHit) > 0) {
    parts.push(`缓存命中 ${formatCompactCount(cacheHit)}`)
  }
  if (output !== undefined && output !== null) parts.push(`输出 ${formatCompactCount(output)}`)
  return parts.join(' · ')
}

export function extractErrorMessage(err: unknown, fallback = '操作失败，请稍后重试'): string {
  const axiosErr = err as AxiosError<{ message?: string; detail?: string }>
  const apiMessage = axiosErr?.response?.data?.message || axiosErr?.response?.data?.detail
  if (typeof apiMessage === 'string' && apiMessage.trim()) {
    return apiMessage
  }
  if (err instanceof Error && err.message) {
    return err.message
  }
  return fallback
}
