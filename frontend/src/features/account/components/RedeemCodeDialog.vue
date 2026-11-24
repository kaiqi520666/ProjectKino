<script setup lang="ts">
import { ref, watch } from 'vue'
import { ExternalLink, Ticket } from 'lucide-vue-next'
import UiButton from '@/components/ui/UiButton.vue'
import UiDialog from '@/components/ui/UiDialog.vue'
import UiInput from '@/components/ui/UiInput.vue'
import { extractErrorMessage, formatCredits } from '@/lib/format'
import { useUiStore } from '@/stores/ui'
import { redeemCreditCode, type RedeemCodeResult } from '../credits-api'

const props = defineProps<{
  purchaseUrl?: string
}>()

const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{
  redeemed: [result: RedeemCodeResult]
}>()

const ui = useUiStore()
const code = ref('')
const submitting = ref(false)
const errorText = ref('')

watch(open, (next) => {
  if (next) {
    errorText.value = ''
  } else {
    code.value = ''
    errorText.value = ''
  }
})

async function handleSubmit() {
  const cleaned = code.value.trim()
  if (!cleaned) {
    errorText.value = '请输入兑换码'
    return
  }
  submitting.value = true
  errorText.value = ''
  try {
    const result = await redeemCreditCode(cleaned)
    ui.notify(`已到账 +${formatCredits(result.credits)} 积分`, 'success')
    open.value = false
    emit('redeemed', result)
  } catch (error) {
    errorText.value = extractErrorMessage(error, '兑换失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <UiDialog v-model:open="open" title="兑换积分">
    <form class="redeem-form" @submit.prevent="handleSubmit">
      <UiInput
        v-model="code"
        label="兑换码"
        placeholder="输入兑换码，如 ABCD-EFGH-JKLM"
        autocomplete="off"
        :error="errorText"
        required
      />

      <div class="redeem-actions">
        <a
          v-if="props.purchaseUrl"
          :href="props.purchaseUrl"
          target="_blank"
          rel="noopener noreferrer"
          class="redeem-buy-link"
        >
          <span>购买兑换码</span>
          <ExternalLink :size="13" aria-hidden="true" />
        </a>
        <span v-else></span>

        <div class="redeem-btn-group">
          <UiButton type="button" variant="outline" size="sm" :disabled="submitting" @click="open = false">
            取消
          </UiButton>
          <UiButton type="submit" variant="primary" size="sm" :loading="submitting" :disabled="!code.trim()">
            <template #leading><Ticket :size="14" aria-hidden="true" /></template>
            立即兑换
          </UiButton>
        </div>
      </div>
    </form>
  </UiDialog>
</template>

<style scoped>
.redeem-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.redeem-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.redeem-buy-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-gold-soft);
  text-decoration: none;
  transition: opacity 0.16s ease;
}

.redeem-buy-link:hover {
  opacity: 0.85;
  text-decoration: underline;
}

.redeem-btn-group {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
</style>
