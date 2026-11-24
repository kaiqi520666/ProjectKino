<script setup lang="ts">
import { computed, ref } from 'vue'
import { Check, Clapperboard, Copy, ExternalLink, LayoutDashboard } from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import { JOB_STATUS_LABELS, JOB_TYPE_LABELS } from '@/features/admin/format'
import { formatCompactCount, formatCredits, formatDateTime, formatSignedCredits } from '@/lib/format'
import type { CreditBillItem, EnrichedCreditLedgerItem } from '../credits-api'
import {
  BILL_CATEGORY_LABELS,
  BILL_STATUS_LABELS,
  LEDGER_OP_LABELS_ACCOUNT,
} from '../credits-helpers'

export type CreditDetailPayload =
  | { kind: 'bill'; item: CreditBillItem }
  | { kind: 'ledger'; item: EnrichedCreditLedgerItem }

const props = defineProps<{
  detail: CreditDetailPayload | null
}>()

const open = defineModel<boolean>('open', { required: true })
const copiedJobId = ref(false)

const title = computed(() => {
  if (!props.detail) return '账单详情'
  return props.detail.kind === 'bill' ? '消费账单凭证' : '资金流水详情'
})

const currentItem = computed(() => props.detail?.item ?? null)

const sourceRoute = computed(() => {
  const item = currentItem.value
  if (!item) return null
  if (item.projectId) {
    return {
      label: item.projectName || '查看关联短剧项目',
      kind: 'project' as const,
      to: { name: 'studio-storyboard', params: { projectId: item.projectId } },
    }
  }
  if (item.canvasId) {
    return {
      label: item.canvasName || '查看关联画布',
      kind: 'canvas' as const,
      to: { name: 'canvas-editor', params: { canvasId: item.canvasId } },
    }
  }
  return null
})

const tokenBreakdown = computed(() => {
  const usage = currentItem.value?.tokenUsage
  if (!usage || typeof usage !== 'object') return null
  const input = Number(usage.inputTokens ?? usage.input_tokens ?? usage.prompt_tokens ?? 0)
  const cacheHit = Number(usage.cacheReadTokens ?? usage.cache_hit_tokens ?? usage.cache_read_tokens ?? 0)
  const output = Number(usage.outputTokens ?? usage.output_tokens ?? usage.completion_tokens ?? 0)
  const freshInput = Math.max(0, input - cacheHit)
  const multiplier = usage.usageMultiplier ?? usage.usage_multiplier
  return {
    input,
    freshInput,
    cacheHit,
    output,
    multiplier: multiplier !== undefined && multiplier !== null ? `${Number(multiplier).toFixed(2)}×` : null,
  }
})

const mediaRateBreakdown = computed(() => {
  const snap = currentItem.value?.rateSnapshot
  if (!snap || typeof snap !== 'object') return null
  const tier = typeof snap.tier === 'string' && snap.tier ? snap.tier.toUpperCase() : null
  const ruleKey = typeof snap.ruleKey === 'string' && snap.ruleKey && snap.ruleKey !== 'default' ? snap.ruleKey : null
  const duration = snap.durationSeconds !== undefined && snap.durationSeconds !== null ? Number(snap.durationSeconds) : null
  const unit = snap.unit === 'second' ? '秒' : snap.unit ? '次' : null
  const basePrice = snap.basePrice !== undefined && snap.basePrice !== null ? formatCredits(String(snap.basePrice)) : null
  const multiplier = snap.usageMultiplier !== undefined && snap.usageMultiplier !== null
    ? `${Number(snap.usageMultiplier).toFixed(2)}×`
    : null
  if (!tier && !ruleKey && !duration && !basePrice) return null
  return { tier, ruleKey, duration, unit, basePrice, multiplier }
})

async function copyJobId(jobId: string) {
  try {
    await navigator.clipboard.writeText(jobId)
    copiedJobId.value = true
    setTimeout(() => {
      copiedJobId.value = false
    }, 1800)
  } catch {
    // Ignore clipboard rejection in restricted contexts.
  }
}
</script>

<template>
  <UiDialog v-model:open="open" :title="title" size="wide">
    <div v-if="detail && currentItem" class="credit-detail">
      <!-- 顶部金额与状态摘要 -->
      <div class="credit-detail-hero">
        <div class="credit-detail-hero-main">
          <span
            v-if="detail.kind === 'bill'"
            class="credit-detail-badge"
            :class="`is-${detail.item.status}`"
          >
            {{ BILL_STATUS_LABELS[detail.item.status] }}
          </span>
          <span v-else class="credit-detail-badge is-ledger">
            {{ LEDGER_OP_LABELS_ACCOUNT[detail.item.operation] || detail.item.operation }}
          </span>
          <h3>{{ detail.kind === 'bill' ? detail.item.title : (detail.item.reason || '积分流水') }}</h3>
          <p class="credit-detail-time">{{ formatDateTime(currentItem.createdAt) }}</p>
        </div>
        <div class="credit-detail-amount-box">
          <template v-if="detail.kind === 'bill'">
            <span
              v-if="detail.item.status === 'refunded'"
              class="credit-detail-amount-strike"
            >
              -{{ formatCredits(detail.item.originalAmount) }}
            </span>
            <strong
              class="credit-detail-amount"
              :class="`is-${detail.item.status}`"
            >
              {{ detail.item.status === 'refunded' ? '0' : formatSignedCredits(detail.item.amount) }}
            </strong>
            <span class="credit-detail-amount-sub">
              {{ detail.item.status === 'frozen' ? '任务冻结中' : detail.item.status === 'refunded' ? '失败已全额退还' : '积分变动' }}
            </span>
          </template>
          <template v-else>
            <strong
              class="credit-detail-amount"
              :class="Number(detail.item.balanceChange) > 0 ? 'is-credited' : Number(detail.item.balanceChange) < 0 ? 'is-charged' : ''"
            >
              {{ detail.item.operation === 'settle' ? `冻结 ${formatSignedCredits(detail.item.frozenChange)}` : formatSignedCredits(detail.item.balanceChange) }}
            </strong>
            <span class="credit-detail-amount-sub">
              可用余额 {{ formatCredits(detail.item.balanceBefore) }} → {{ formatCredits(detail.item.balanceAfter) }}
            </span>
          </template>
        </div>
      </div>

      <!-- 基础溯源信息 -->
      <dl class="credit-detail-grid">
        <div v-if="detail.kind === 'bill'">
          <dt>消费分类</dt>
          <dd>{{ BILL_CATEGORY_LABELS[detail.item.category] }}</dd>
        </div>
        <div v-if="currentItem.modelName || currentItem.modelId">
          <dt>使用模型</dt>
          <dd>
            <strong>{{ currentItem.modelName || currentItem.modelId }}</strong>
            <small v-if="currentItem.modelName && currentItem.modelId" class="credit-detail-sub">
              ({{ currentItem.modelId }})
            </small>
          </dd>
        </div>
        <div v-if="currentItem.jobType">
          <dt>关联任务</dt>
          <dd>
            {{ JOB_TYPE_LABELS[currentItem.jobType] || currentItem.jobType }}
            <span v-if="currentItem.jobStatus" class="credit-detail-inline-tag">
              {{ JOB_STATUS_LABELS[currentItem.jobStatus] || currentItem.jobStatus }}
            </span>
          </dd>
        </div>
        <div v-if="sourceRoute">
          <dt>创作来源</dt>
          <dd>
            <RouterLink :to="sourceRoute.to" class="credit-detail-link" @click="open = false">
              <Clapperboard v-if="sourceRoute.kind === 'project'" :size="13" aria-hidden="true" />
              <LayoutDashboard v-else :size="13" aria-hidden="true" />
              <span>{{ sourceRoute.label }}</span>
              <ExternalLink :size="12" aria-hidden="true" />
            </RouterLink>
          </dd>
        </div>
        <div v-if="currentItem.jobId" class="is-full">
          <dt>任务单号</dt>
          <dd class="credit-detail-copy-row">
            <code>{{ currentItem.jobId }}</code>
            <button type="button" class="credit-detail-copy-btn" @click="copyJobId(currentItem.jobId)">
              <Check v-if="copiedJobId" :size="12" aria-hidden="true" />
              <Copy v-else :size="12" aria-hidden="true" />
              {{ copiedJobId ? '已复制' : '复制' }}
            </button>
          </dd>
        </div>
        <div class="is-full">
          <dt>账务说明</dt>
          <dd>{{ currentItem.reason || '-' }}</dd>
        </div>
      </dl>

      <!-- LLM Token 拆解 -->
      <section v-if="tokenBreakdown" class="credit-detail-section">
        <h4>Token 计费拆解</h4>
        <div class="credit-detail-metrics">
          <div class="credit-detail-metric">
            <span>总输入 Token</span>
            <strong>{{ formatCompactCount(tokenBreakdown.input) }}</strong>
            <small>新输入 {{ formatCompactCount(tokenBreakdown.freshInput) }} · 缓存命中 {{ formatCompactCount(tokenBreakdown.cacheHit) }}</small>
          </div>
          <div class="credit-detail-metric">
            <span>输出 Token</span>
            <strong>{{ formatCompactCount(tokenBreakdown.output) }}</strong>
          </div>
          <div v-if="tokenBreakdown.multiplier" class="credit-detail-metric">
            <span>计费倍率</span>
            <strong>{{ tokenBreakdown.multiplier }}</strong>
          </div>
        </div>
      </section>

      <!-- 媒体单价快照 -->
      <section v-if="mediaRateBreakdown" class="credit-detail-section">
        <h4>计费规格快照</h4>
        <div class="credit-detail-metrics">
          <div v-if="mediaRateBreakdown.tier || mediaRateBreakdown.ruleKey" class="credit-detail-metric">
            <span>规格档位</span>
            <strong>{{ mediaRateBreakdown.tier || mediaRateBreakdown.ruleKey }}</strong>
          </div>
          <div v-if="mediaRateBreakdown.duration" class="credit-detail-metric">
            <span>视频时长</span>
            <strong>{{ mediaRateBreakdown.duration }} 秒</strong>
          </div>
          <div v-if="mediaRateBreakdown.basePrice" class="credit-detail-metric">
            <span>基准单价</span>
            <strong>{{ mediaRateBreakdown.basePrice }} 积分 / {{ mediaRateBreakdown.unit || '次' }}</strong>
          </div>
          <div v-if="mediaRateBreakdown.multiplier" class="credit-detail-metric">
            <span>计费倍率</span>
            <strong>{{ mediaRateBreakdown.multiplier }}</strong>
          </div>
        </div>
      </section>

      <!-- 资金轨迹 -->
      <section v-if="detail.kind === 'bill' && detail.item.timeline.length" class="credit-detail-section">
        <h4>资金变动轨迹</h4>
        <ol class="credit-detail-timeline">
          <li v-for="(ev, idx) in detail.item.timeline" :key="idx">
            <span class="credit-timeline-dot" :class="`is-${ev.operation}`" aria-hidden="true"></span>
            <div class="credit-timeline-body">
              <div class="credit-timeline-head">
                <strong>{{ LEDGER_OP_LABELS_ACCOUNT[ev.operation] || ev.operation }}</strong>
                <span class="credit-timeline-time">{{ formatDateTime(ev.createdAt) }}</span>
              </div>
              <p>{{ ev.reason }}</p>
              <div class="credit-timeline-deltas">
                <span>可用 {{ formatSignedCredits(ev.balanceChange) }}</span>
                <span v-if="Number(ev.frozenChange) !== 0">冻结 {{ formatSignedCredits(ev.frozenChange) }}</span>
              </div>
            </div>
          </li>
        </ol>
      </section>

      <section v-else-if="detail.kind === 'ledger'" class="credit-detail-section">
        <h4>余额变动快照</h4>
        <div class="credit-detail-metrics">
          <div class="credit-detail-metric">
            <span>可用余额</span>
            <strong>{{ formatCredits(detail.item.balanceBefore) }} → {{ formatCredits(detail.item.balanceAfter) }}</strong>
            <small>变动 {{ formatSignedCredits(detail.item.balanceChange) }}</small>
          </div>
          <div class="credit-detail-metric">
            <span>冻结额度</span>
            <strong>{{ formatCredits(detail.item.frozenBefore) }} → {{ formatCredits(detail.item.frozenAfter) }}</strong>
            <small>变动 {{ formatSignedCredits(detail.item.frozenChange) }}</small>
          </div>
        </div>
      </section>
    </div>

    <template #footer>
      <UiButton variant="outline" size="sm" @click="open = false">关闭</UiButton>
    </template>
  </UiDialog>
</template>

<style scoped>
.credit-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.credit-detail-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border: 1px solid var(--border-subtle);
  border-radius: 9px;
  background: var(--color-canvas);
}

.credit-detail-hero-main {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}

.credit-detail-hero-main h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
}

.credit-detail-time {
  margin: 0;
  font-size: 12px;
  color: var(--color-muted);
  font-variant-numeric: tabular-nums;
}

.credit-detail-badge {
  align-self: flex-start;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  border: 1px solid var(--border-control);
  background: rgb(255 255 255 / 4%);
  color: var(--color-muted);
}

.credit-detail-badge.is-charged {
  border-color: rgb(248 113 113 / 32%);
  background: rgb(248 113 113 / 10%);
  color: #fca5a5;
}

.credit-detail-badge.is-frozen {
  border-color: rgb(240 184 75 / 38%);
  background: var(--gold-tint);
  color: var(--color-gold-soft);
}

.credit-detail-badge.is-refunded {
  border-color: rgb(148 163 184 / 35%);
  background: rgb(148 163 184 / 10%);
  color: #cbd5e1;
}

.credit-detail-badge.is-credited {
  border-color: rgb(74 222 128 / 35%);
  background: rgb(74 222 128 / 10%);
  color: var(--color-success);
}

.credit-detail-amount-box {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  flex-shrink: 0;
}

.credit-detail-amount {
  font-size: 22px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.credit-detail-amount.is-charged {
  color: #fca5a5;
}

.credit-detail-amount.is-frozen {
  color: var(--color-gold-soft);
}

.credit-detail-amount.is-credited {
  color: var(--color-success);
}

.credit-detail-amount.is-refunded {
  color: var(--color-muted);
}

.credit-detail-amount-strike {
  font-size: 12px;
  color: var(--color-muted);
  text-decoration: line-through;
  font-variant-numeric: tabular-nums;
}

.credit-detail-amount-sub {
  font-size: 11px;
  color: var(--color-muted);
  font-variant-numeric: tabular-nums;
}

.credit-detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 14px;
  margin: 0;
  padding: 12px 14px;
  border: 1px solid var(--border-subtle);
  border-radius: 9px;
  background: rgb(255 255 255 / 2%);
}

.credit-detail-grid > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.credit-detail-grid > div.is-full {
  grid-column: 1 / -1;
}

.credit-detail-grid dt {
  font-size: 11px;
  color: var(--color-muted);
}

.credit-detail-grid dd {
  margin: 0;
  font-size: 13px;
  color: var(--color-text);
  overflow-wrap: anywhere;
}

.credit-detail-sub {
  color: var(--color-muted);
  font-size: 11px;
  margin-left: 4px;
}

.credit-detail-inline-tag {
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgb(255 255 255 / 6%);
  color: var(--color-muted);
  font-size: 11px;
}

.credit-detail-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--color-gold-soft);
  text-decoration: none;
}

.credit-detail-link:hover {
  text-decoration: underline;
}

.credit-detail-copy-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.credit-detail-copy-row code {
  font-size: 12px;
  color: var(--color-muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.credit-detail-copy-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 7px;
  border: 1px solid var(--border-control);
  border-radius: 5px;
  background: transparent;
  color: var(--color-muted);
  font-size: 11px;
  cursor: pointer;
}

.credit-detail-copy-btn:hover {
  border-color: var(--color-gold);
  color: var(--color-gold-soft);
}

.credit-detail-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.credit-detail-section h4 {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-muted);
}

.credit-detail-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 8px;
}

.credit-detail-metric {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 10px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--color-canvas);
}

.credit-detail-metric span {
  font-size: 11px;
  color: var(--color-muted);
}

.credit-detail-metric strong {
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.credit-detail-metric small {
  font-size: 11px;
  color: var(--color-muted);
  font-variant-numeric: tabular-nums;
}

.credit-detail-timeline {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.credit-detail-timeline li {
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.credit-timeline-dot {
  width: 8px;
  height: 8px;
  margin-top: 5px;
  border-radius: 50%;
  background: var(--color-muted);
}

.credit-timeline-dot.is-freeze {
  background: var(--color-gold);
}

.credit-timeline-dot.is-settle {
  background: #60a5fa;
}

.credit-timeline-dot.is-release,
.credit-timeline-dot.is-grant {
  background: var(--color-success);
}

.credit-timeline-dot.is-llm_consume {
  background: #f87171;
}

.credit-timeline-body {
  padding: 8px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: var(--color-canvas);
}

.credit-timeline-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
}

.credit-timeline-time {
  color: var(--color-muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.credit-timeline-body p {
  margin: 4px 0 6px;
  font-size: 12px;
  color: var(--color-muted);
}

.credit-timeline-deltas {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 11px;
  color: var(--color-text);
  font-variant-numeric: tabular-nums;
}

@media (max-width: 600px) {
  .credit-detail-hero {
    flex-direction: column;
  }
  .credit-detail-amount-box {
    align-items: flex-start;
  }
  .credit-detail-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
