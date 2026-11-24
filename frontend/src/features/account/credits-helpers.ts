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

export function formatRateSpec(
  rateSnapshot?: Record<string, unknown> | null,
  tokenUsage?: Record<string, unknown> | null,
): string {
  if (rateSnapshot && typeof rateSnapshot === 'object') {
    const parts: string[] = []
    const tier = rateSnapshot.tier
    const ruleKey = rateSnapshot.ruleKey ?? rateSnapshot.rule_key
    const duration = rateSnapshot.durationSeconds ?? rateSnapshot.duration_seconds
    const unit = rateSnapshot.unit
    const basePrice = rateSnapshot.basePrice ?? rateSnapshot.base_price

    if (typeof tier === 'string' && tier) {
      parts.push(tier.toUpperCase())
    }
    if (typeof ruleKey === 'string' && ruleKey && ruleKey !== 'default') {
      parts.push(ruleKey)
    }
    if (duration !== undefined && duration !== null && Number(duration) > 0) {
      parts.push(`${Number(duration)}s`)
    }
    if (basePrice !== undefined && basePrice !== null && Number.isFinite(Number(basePrice))) {
      const suffix = unit === 'second' ? '积分/秒' : '积分/次'
      parts.push(`${formatCredits(String(basePrice))} ${suffix}`)
    }
    if (parts.length) return parts.join(' · ')
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
      item.reason || '-',
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
      item.reason || '-',
    ].map(escapeCsvCell).join(',')
  })
  return `\uFEFF${[header.join(','), ...rows].join('\n')}`
}
