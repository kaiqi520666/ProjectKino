import type { AdminJobItem } from './api'

export interface JobSpecDisplay {
  title: string
  meta: string[]
}

const TIER_LABELS: Record<string, string> = {
  web: 'Web',
  '1k': '1K',
  '2k': '2K',
  '4k': '4K',
}

function readString(obj: Record<string, unknown> | null | undefined, key: string): string | null {
  const value = obj?.[key]
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed || null
}

function readNumber(obj: Record<string, unknown> | null | undefined, key: string): number | null {
  const value = obj?.[key]
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function formatImageTier(raw: string | null): string | null {
  if (!raw) return null
  return TIER_LABELS[raw.toLowerCase()] ?? raw.toUpperCase()
}

function formatMediaSeconds(seconds: number | null): string | null {
  if (seconds === null || seconds <= 0) return null
  if (Math.abs(seconds - Math.round(seconds)) < 0.05) {
    return `${Math.round(seconds)}s`
  }
  return `${Number(seconds.toFixed(1))}s`
}

function formatCompactTokens(count: number): string {
  if (count >= 1000) {
    return `${(count / 1000).toFixed(1).replace(/\.0$/, '')}k`
  }
  return String(Math.round(count))
}

function resolveModelName(modelId: string | null, modelNames: Record<string, string>): string | null {
  if (!modelId) return null
  return modelNames[modelId] || modelId
}

export function formatJobSpec(
  job: Pick<AdminJobItem, 'jobType' | 'inputPayload' | 'resultPayload' | 'usageSummary'>,
  modelNames: Record<string, string> = {},
): JobSpecDisplay | null {
  const input = job.inputPayload
  const result = job.resultPayload
  const usage = job.usageSummary

  if (job.jobType === 'asset_image') {
    const modelId = readString(result, 'modelId') ?? readString(input, 'modelId')
    const tier = formatImageTier(readString(result, 'tier') ?? readString(input, 'tier'))
    const ratio = readString(result, 'ratio') ?? readString(input, 'ratio')
    const meta = [tier, ratio].filter((item): item is string => Boolean(item))
    const title = resolveModelName(modelId, modelNames)
    if (!title && !meta.length) return null
    return { title: title || '-', meta }
  }

  if (job.jobType === 'clip_video') {
    const modelId = readString(result, 'modelId') ?? readString(input, 'modelId')
    const resolution = readString(result, 'resolution') ?? readString(input, 'resolution')
    const ratio = readString(result, 'ratio') ?? readString(input, 'ratio')
    const duration = formatMediaSeconds(
      readNumber(result, 'duration') ?? readNumber(input, 'durationSeconds'),
    )
    const refUrls = input?.referenceUrls
    const refCount = Array.isArray(refUrls) ? refUrls.filter((u) => typeof u === 'string' && u.trim()).length : 0
    const meta = [
      resolution,
      ratio,
      duration,
      refCount > 0 ? `${refCount}参考图` : null,
    ].filter((item): item is string => Boolean(item))
    const title = resolveModelName(modelId, modelNames)
    if (!title && !meta.length) return null
    return { title: title || '-', meta }
  }

  if (job.jobType === 'episode_compose') {
    const episodeNumber = readNumber(result, 'episodeNumber') ?? readNumber(input, 'episodeNumber')
    const clipCount = readNumber(input, 'clipCount')
    const composedDuration = formatMediaSeconds(readNumber(result, 'composedDuration'))
    const meta = [
      clipCount && clipCount > 0 ? `${Math.round(clipCount)} 片段` : null,
      composedDuration,
    ].filter((item): item is string => Boolean(item))
    return {
      title: episodeNumber ? `第 ${Math.round(episodeNumber)} 集合成` : 'FFmpeg 合成',
      meta,
    }
  }

  const modelId = readString(usage, 'modelId') ?? readString(input, 'modelId')
  const modelName = resolveModelName(modelId, modelNames)
  const episodeNumber = readNumber(input, 'episodeNumber')
  const mode = readString(input, 'mode')
  const inputTokens = readNumber(usage, 'inputTokens') ?? 0
  const outputTokens = readNumber(usage, 'outputTokens') ?? 0
  const cacheReadTokens = readNumber(usage, 'cacheReadTokens') ?? 0

  const meta: string[] = []
  if (episodeNumber && modelName) meta.push(`第 ${Math.round(episodeNumber)} 集`)
  if (mode === 'incremental' && modelName) meta.push('增量补充')
  if (inputTokens > 0 || outputTokens > 0) {
    meta.push(`入 ${formatCompactTokens(inputTokens)} / 出 ${formatCompactTokens(outputTokens)}`)
  }
  if (cacheReadTokens > 0) {
    meta.push(`缓存 ${formatCompactTokens(cacheReadTokens)}`)
  }

  const fallbackTitle = episodeNumber
    ? `第 ${Math.round(episodeNumber)} 集`
    : mode === 'incremental'
      ? '增量补充'
      : ''

  const title = modelName || fallbackTitle
  if (!title && !meta.length) return null
  return { title: title || '-', meta }
}

export function readLlmCreditCost(usageSummary?: Record<string, unknown> | null): string | null {
  const cost = readNumber(usageSummary, 'cost')
  if (cost === null || cost <= 0) return null
  if (cost < 0.01) {
    return cost.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
  }
  return cost.toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}
