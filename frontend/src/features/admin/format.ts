import type { AxiosError } from 'axios'

export const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  operator: '运营',
  user: '普通用户',
}

export const JOB_TYPE_LABELS: Record<string, string> = {
  parse_novel: '解析小说',
  extract_assets: '提取资产',
  generate_episodes: '生成分集',
  generate_storyboard: '生成分镜',
  regenerate_episode_storyboard: '重写单集分镜',
  asset_image: '生成资产图',
  clip_video: '生成分镜视频',
  compose_episode: '合成本集视频',
  compose_project: '合成全片',
}

export const JOB_STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  running: '执行中',
  polling: '轮询中',
  succeeded: '成功',
  failed: '失败',
  review: '待核对',
}

export const RESERVATION_STATUS_LABELS: Record<string, string> = {
  frozen: '已冻结',
  settled: '已结算',
  refunded: '已退还',
}

export const LEDGER_OP_LABELS: Record<string, string> = {
  register_grant: '注册赠送',
  admin_grant: '管理员调账',
  freeze: '预扣冻结',
  settle: '任务结算',
  refund: '失败退还',
  text_deduct: '文本扣费',
}

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

export function formatTokenUsage(usage?: Record<string, unknown> | null): string {
  if (!usage || typeof usage !== 'object') return ''
  const parts: string[] = []
  const input = usage.input_tokens ?? usage.prompt_tokens
  const output = usage.output_tokens ?? usage.completion_tokens
  const cacheHit = usage.cache_hit_tokens
  const model = usage.model
  if (model) parts.push(String(model))
  if (input !== undefined) parts.push(`入 ${input}`)
  if (output !== undefined) parts.push(`出 ${output}`)
  if (cacheHit !== undefined && Number(cacheHit) > 0) parts.push(`缓存命中 ${cacheHit}`)
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
