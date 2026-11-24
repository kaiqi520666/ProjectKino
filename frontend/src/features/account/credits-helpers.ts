import { formatCredits, formatDateTime, formatSignedCredits, formatTokenUsage } from '../../lib/format.ts'
import type {
  CreditBillCategory,
  CreditBillItem,
  CreditBillStatus,
  CreditBreakdown,
  EnrichedCreditLedgerItem,
} from './credits-api.ts'

export const BILL_CATEGORY_LABELS: Record<CreditBillCategory, string> = {
  text: '文本模型',
  image: '图片生成',
  video: '视频生成',
  income: '充值/赠送',
}

export const BILL_STATUS_LABELS: Record<CreditBillStatus, string> = {
  charged: '已扣费',
  frozen: '冻结中',
  refunded: '已退还',
  credited: '已入账',
}

export const LEDGER_OP_LABELS_ACCOUNT: Record<string, string> = {
  grant: '积分赠送',
  redeem: '兑换码',
  adjust: '账户调账',
  freeze: '任务预扣',
  settle: '消费结算',
  release: '失败退还',
  llm_consume: '文本扣费',
}

export interface BreakdownSegment {
  key: 'text' | 'image' | 'video'
  label: string
  amount: number
  percent: number
}

export function computeBreakdownSegments(breakdown?: CreditBreakdown | null): BreakdownSegment[] {
  const text = Math.max(0, Number(breakdown?.textSpent ?? 0) || 0)
  const image = Math.max(0, Number(breakdown?.imageSpent ?? 0) || 0)
  const video = Math.max(0, Number(breakdown?.videoSpent ?? 0) || 0)
  const total = text + image + video

  const toPercent = (value: number) => (total > 0 ? Math.round((value / total) * 1000) / 10 : 0)

  return [
    { key: 'video', label: '视频生成', amount: video, percent: toPercent(video) },
    { key: 'image', label: '图片生成', amount: image, percent: toPercent(image) },
    { key: 'text', label: '文本/剧本', amount: text, percent: toPercent(text) },
  ]
}

function normalizeSpecBadge(raw: string): string {
  const trimmed = raw.trim()
  if (/^\d+k$/iu.test(trimmed)) return trimmed.toUpperCase()
  return trimmed
}

function formatClipLabel(raw: string): string {
  const match = /^片段\s*(\d+)$/u.exec(raw.trim())
  return match ? `片段 ${match[1]}` : raw.trim()
}

/**
 * 将数据库中的账单/流水说明转换为面向用户的自然中文：
 * - 兼容新格式（已是自然中文直接返回）与历史格式（LLM 任务消耗 / 预冻结内部模型 ID 等）；
 * - 保留 27s、2K 等通用规格缩写，剔除内部 job_type、step_key、model_id 与异常 code。
 */
export function formatCreditReason(reason?: string | null): string {
  const text = (reason ?? '').trim()
  if (!text) return ''

  // 1. 历史 LLM 任务说明：LLM 任务消耗 (script_generate:ep5 / storyboard_generate/episode / assets_extract ...)
  const llmMatch = /^LLM\s*任务消耗\s*[（(]([^）)]+)[）)]$/u.exec(text)
  if (llmMatch) {
    const inner = llmMatch[1]!.trim()
    const [jobType, detail] = inner.split(/[:/]/u)
    if (jobType === 'script_generate' || jobType === 'script_regenerate') {
      const isRegen = jobType === 'script_regenerate'
      if (detail === 'outline') return isRegen ? '重生成全剧大纲' : '全剧大纲规划'
      const epMatch = /^ep(\d+)$/iu.exec(detail ?? '')
      if (epMatch) return isRegen ? `第 ${epMatch[1]} 集剧本重写` : `第 ${epMatch[1]} 集剧本生成`
      return isRegen ? '重生成剧本' : '剧本生成'
    }
    if (jobType === 'storyboard_generate') {
      if (detail === 'clip_regenerate') return '片段分镜重绘'
      if (detail === 'all') return '全剧分镜规划'
      return '单集分镜规划'
    }
    const llmJobLabels: Record<string, string> = {
      assets_extract: '项目资产识别',
      script_episode_regenerate: '单集剧本重写',
      canvas_text: '画布文本生成',
    }
    return llmJobLabels[jobType] ?? '文本模型生成'
  }

  // 2. 历史媒体预冻结说明：xxx预冻结 (目标 · model_id/规格)
  const freezeMatch = /^(批量)?(片段生视频|片段分镜宫格|资产生图|画布生图|画布生视频)预冻结\s*[（(]([^·]+?)\s*·\s*[^/）)]+\/([^）)]+)[）)]$/u.exec(text)
  if (freezeMatch) {
    const batchPrefix = freezeMatch[1] ?? ''
    const kind = freezeMatch[2]!
    const target = freezeMatch[3]!.trim()
    const spec = normalizeSpecBadge(freezeMatch[4]!)
    if (kind === '片段生视频') return `${batchPrefix}${formatClipLabel(target)} 视频生成（${spec}）`
    if (kind === '片段分镜宫格') return `${batchPrefix}${formatClipLabel(target)} 分镜宫格图（${spec}）`
    if (kind === '资产生图') return `${batchPrefix}资产「${target}」生图（${spec}）`
    if (kind === '画布生图') return `${batchPrefix}画布「${target}」生图（${spec}）`
    if (kind === '画布生视频') return `${batchPrefix}画布「${target}」视频生成（${spec}）`
  }

  // 3. 历史媒体完成结算说明：xxx完成结算 ([片段N · ]model_id/规格)
  const gridSettleMatch = /^片段分镜宫格完成结算\s*[（(]([^·]+?)\s*·\s*[^/）)]+\/([^）)]+)[）)]$/u.exec(text)
  if (gridSettleMatch) {
    return `${formatClipLabel(gridSettleMatch[1]!)} 分镜宫格完成结算（${normalizeSpecBadge(gridSettleMatch[2]!)}）`
  }
  const mediaSettleMatch = /^(画布生图|资产生图|画布视频|片段视频)完成结算\s*[（(][^/）)]+\/([^）)]+)[）)]$/u.exec(text)
  if (mediaSettleMatch) {
    return `${mediaSettleMatch[1]}完成结算（${normalizeSpecBadge(mediaSettleMatch[2]!)}）`
  }

  // 4. 历史失败退还说明：xxx失败退还冻结积分 (error_code)
  const releaseMatch = /^(画布生图|片段分镜宫格|资产生图|画布视频|片段视频)失败退还冻结积分\s*[（(][^）)]+[）)]$/u.exec(text)
  if (releaseMatch) {
    return `${releaseMatch[1]}失败，已退还冻结积分`
  }

  return text
}

function formatCompactCount(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2).replace(/\.?0+$/u, '')}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1).replace(/\.0$/u, '')}k`
  return String(Math.round(value))
}

function readTokenInt(usage: Record<string, unknown>, ...keys: string[]): number {
  for (const key of keys) {
    const raw = usage[key]
    if (typeof raw === 'number' && Number.isFinite(raw) && raw > 0) return raw
    if (typeof raw === 'string' && raw.trim() && Number.isFinite(Number(raw)) && Number(raw) > 0) {
      return Number(raw)
    }
  }
  return 0
}

export function formatRateSpecTags(
  rateSnapshot?: Record<string, unknown> | null,
  tokenUsage?: Record<string, unknown> | null,
): string[] {
  if (rateSnapshot && typeof rateSnapshot === 'object') {
    const tags: string[] = []
    const tier = rateSnapshot.tier
    const ruleKey = rateSnapshot.ruleKey ?? rateSnapshot.rule_key
    const duration = rateSnapshot.durationSeconds ?? rateSnapshot.duration_seconds
    const unit = rateSnapshot.unit
    const basePrice = rateSnapshot.basePrice ?? rateSnapshot.base_price

    if (typeof tier === 'string' && tier) {
      tags.push(tier.toUpperCase())
    }
    if (typeof ruleKey === 'string' && ruleKey && ruleKey !== 'default') {
      tags.push(ruleKey)
    }
    if (duration !== undefined && duration !== null && Number(duration) > 0) {
      tags.push(`${Number(duration)}s`)
    }
    if (basePrice !== undefined && basePrice !== null && Number.isFinite(Number(basePrice))) {
      const suffix = unit === 'second' ? '积分/秒' : '积分/次'
      tags.push(`${formatCredits(String(basePrice))} ${suffix}`)
    }
    if (tags.length) return tags
  }

  if (tokenUsage && typeof tokenUsage === 'object') {
    const input = readTokenInt(tokenUsage, 'inputTokens', 'input_tokens', 'promptTokens', 'prompt_tokens')
    const output = readTokenInt(tokenUsage, 'outputTokens', 'output_tokens', 'completionTokens', 'completion_tokens')
    const cached = readTokenInt(tokenUsage, 'cachedInputTokens', 'cached_input_tokens', 'cachedTokens', 'cached_tokens')
    const tags: string[] = []
    if (input > 0 && output > 0) {
      tags.push(`入 ${formatCompactCount(input)} / 出 ${formatCompactCount(output)}`)
    } else if (input > 0) {
      tags.push(`入 ${formatCompactCount(input)}`)
    } else if (output > 0) {
      tags.push(`出 ${formatCompactCount(output)}`)
    }
    if (cached > 0) {
      tags.push(`缓存 ${formatCompactCount(cached)}`)
    }
    return tags
  }

  return []
}

export function formatRateSpec(
  rateSnapshot?: Record<string, unknown> | null,
  tokenUsage?: Record<string, unknown> | null,
): string {
  if (rateSnapshot && typeof rateSnapshot === 'object') {
    const tags = formatRateSpecTags(rateSnapshot, null)
    if (tags.length) return tags.join(' · ')
  }
  return formatTokenUsage(tokenUsage)
}

export function formatLedgerChangeDisplay(item: Pick<EnrichedCreditLedgerItem, 'operation' | 'balanceChange' | 'frozenChange'>): {
  primary: string
  secondary: string
  tone: 'pos' | 'neg' | 'neutral' | 'frozen'
} {
  const bal = Number(item.balanceChange)
  const frz = Number(item.frozenChange)

  if (item.operation === 'settle') {
    return {
      primary: `冻结 ${formatSignedCredits(frz)}`,
      secondary: '可用不变 · 已结算',
      tone: 'neutral',
    }
  }
  if (item.operation === 'freeze') {
    return {
      primary: formatSignedCredits(bal),
      secondary: `冻结 ${formatSignedCredits(frz)}`,
      tone: 'frozen',
    }
  }
  if (item.operation === 'release') {
    return {
      primary: formatSignedCredits(bal),
      secondary: `解冻 ${formatSignedCredits(frz)}`,
      tone: 'pos',
    }
  }
  return {
    primary: formatSignedCredits(bal),
    secondary: '',
    tone: bal > 0 ? 'pos' : bal < 0 ? 'neg' : 'neutral',
  }
}

function escapeCsvCell(value: string): string {
  const safe = value.replace(/\r?\n/gu, ' ')
  if (/[",]/u.test(safe)) {
    return `"${safe.replace(/"/gu, '""')}"`
  }
  return safe
}

export function buildBillsCsv(items: readonly CreditBillItem[]): string {
  const header = ['时间', '分类', '状态', '消费项', '关联来源', '模型', '规格/Token', '实付积分', '原冻结/金额', '结算后余额', '说明']
  const rows = items.map((item) => {
    const source = item.projectName ? `短剧：${item.projectName}` : item.canvasName ? `画布：${item.canvasName}` : '-'
    const spec = formatRateSpec(item.rateSnapshot, item.tokenUsage) || '-'
    return [
      formatDateTime(item.createdAt),
      BILL_CATEGORY_LABELS[item.category] || item.category,
      BILL_STATUS_LABELS[item.status] || item.status,
      item.title,
      source,
      item.modelName || item.modelId || '-',
      spec,
      formatSignedCredits(item.amount),
      formatCredits(item.originalAmount),
      formatCredits(item.balanceAfter),
      formatCreditReason(item.reason) || '-',
    ].map(escapeCsvCell).join(',')
  })
  return `\uFEFF${[header.join(','), ...rows].join('\n')}`
}

export function buildLedgersCsv(items: readonly EnrichedCreditLedgerItem[]): string {
  const header = ['时间', '操作类型', '可用变动', '冻结变动', '可用前', '可用后', '冻结前', '冻结后', '关联来源', '模型', '说明']
  const rows = items.map((item) => {
    const source = item.projectName ? `短剧：${item.projectName}` : item.canvasName ? `画布：${item.canvasName}` : '-'
    return [
      formatDateTime(item.createdAt),
      LEDGER_OP_LABELS_ACCOUNT[item.operation] || item.operation,
      formatSignedCredits(item.balanceChange),
      formatSignedCredits(item.frozenChange),
      formatCredits(item.balanceBefore),
      formatCredits(item.balanceAfter),
      formatCredits(item.frozenBefore),
      formatCredits(item.frozenAfter),
      source,
      item.modelName || item.modelId || '-',
      formatCreditReason(item.reason) || '-',
    ].map(escapeCsvCell).join(',')
  })
  return `\uFEFF${[header.join(','), ...rows].join('\n')}`
}
