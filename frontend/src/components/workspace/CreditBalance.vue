<script setup lang="ts">
import { computed } from 'vue'
import { Coins, Plus } from 'lucide-vue-next'

const props = withDefaults(defineProps<{
  balance?: number | null
  loading?: boolean
  preview?: boolean
}>(), { balance: null })
defineEmits<{ recharge: [] }>()
const formattedBalance = computed(() => {
  if (props.loading) return '…'
  if (props.balance === null || !Number.isFinite(props.balance)) return '—'
  return new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(props.balance)
})
</script>

<template>
  <div class="credit-balance" :aria-busy="loading || undefined">
    <span class="credit-balance-value" :aria-label="`${preview ? '示例' : ''}剩余积分 ${formattedBalance}`" :title="preview ? '开发预览积分，非真实账户余额' : '剩余积分'">
      <Coins :size="16" :stroke-width="1.7" aria-hidden="true" />
      <span>{{ formattedBalance }}</span>
    </span>
    <button type="button" class="credit-recharge" @click="$emit('recharge')">
      <Plus :size="14" aria-hidden="true" /><span>充值</span>
    </button>
  </div>
</template>

<style scoped>
.credit-balance { display: inline-flex; align-items: center; gap: 10px; flex-shrink: 0; }
.credit-balance-value { display: inline-flex; align-items: center; gap: 7px; color: var(--color-gold-soft); font-size: 14px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.credit-recharge { display: inline-flex; align-items: center; justify-content: center; gap: 3px; min-height: 30px; padding: 0 10px; border: 1px solid #e8bc65; border-radius: 6px; background: linear-gradient(115deg, #ffdfa0, #edb64f); color: #30200a; font-size: 12px; font-weight: 600; box-shadow: 0 2px 12px rgb(240 184 75 / 10%); }
.credit-recharge:hover { background: #ffdfa0; }
@media (max-width: 480px) { .credit-balance { gap: 6px; } .credit-balance-value { gap: 4px; } .credit-recharge { padding-inline: 7px; } .credit-recharge > svg { display: none; } }
</style>
