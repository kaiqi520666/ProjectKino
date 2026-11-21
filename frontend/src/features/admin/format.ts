export {
  extractErrorMessage,
  formatCredits,
  formatDateTime,
  formatSignedCredits,
  formatTokenUsage,
} from '@/lib/format'

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
