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
  script_generate: '生成全剧剧本',
  script_regenerate: '重生成全剧剧本',
  episode_rewrite: '重写单集剧本',
  episode_append: '续写新分集',
  assets_extract: '提取项目资产',
  asset_image: '生成资产图',
  storyboard_generate: '生成单集分镜',
  clip_video: '生成分镜视频',
  episode_compose: '合成本集视频',
  canvas_text: '画布文本生成',
  canvas_image: '画布生图',
  canvas_video: '画布生视频',
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
  released: '已退还',
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
