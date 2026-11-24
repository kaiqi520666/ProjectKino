import { http, unwrap } from '@/lib/http'

export type CreditBillCategory = 'text' | 'image' | 'video' | 'income'
export type CreditBillStatus = 'charged' | 'frozen' | 'refunded' | 'credited'
export type CreditLedgerOperation = 'grant' | 'freeze' | 'settle' | 'release' | 'llm_consume' | 'adjust'

export interface CreditBillTimelineEvent {
  operation: string
  balanceChange: string
  frozenChange: string
  reason: string
  createdAt: string
}

export interface CreditBillItem {
  id: string
  category: CreditBillCategory
  status: CreditBillStatus
  amount: string
  originalAmount: string
  balanceAfter: string
  title: string
  reason: string
  operation: string
  jobId?: string | null
  reservationId?: string | null
  jobType?: string | null
  jobStatus?: string | null
  modelId?: string | null
  modelName?: string | null
  projectId?: string | null
  projectName?: string | null
  canvasId?: string | null
  canvasName?: string | null
  tokenUsage?: Record<string, unknown> | null
  rateSnapshot?: Record<string, unknown> | null
  createdAt: string
  settledAt?: string | null
  timeline: CreditBillTimelineEvent[]
}

export interface CreditBillList {
  items: CreditBillItem[]
  total: number
}

export interface EnrichedCreditLedgerItem {
  id: string
  operation: string
  balanceChange: string
  frozenChange: string
  balanceBefore: string
  balanceAfter: string
  frozenBefore: string
  frozenAfter: string
  jobId?: string | null
  reservationId?: string | null
  tokenUsage?: Record<string, unknown> | null
  reason: string
  createdAt: string
  businessType?: CreditBillCategory | null
  modelId?: string | null
  modelName?: string | null
  jobType?: string | null
  jobStatus?: string | null
  projectId?: string | null
  projectName?: string | null
  canvasId?: string | null
  canvasName?: string | null
  rateSnapshot?: Record<string, unknown> | null
}

export interface EnrichedCreditLedgerList {
  items: EnrichedCreditLedgerItem[]
  total: number
}

export interface FrozenReservationItem {
  reservationId: string
  businessType: 'image' | 'video'
  amount: string
  modelId: string
  modelName?: string | null
  jobId: string
  jobType?: string | null
  jobStatus?: string | null
  projectId?: string | null
  projectName?: string | null
  canvasId?: string | null
  canvasName?: string | null
  rateSnapshot?: Record<string, unknown> | null
  reason: string
  createdAt: string
}

export interface CreditBreakdown {
  textSpent: string
  imageSpent: string
  videoSpent: string
}

export interface CreditSummary {
  balance: string
  frozen: string
  usageMultiplier: string
  totalSpent: string
  totalGranted: string
  totalRefunded: string
  billCount: number
  breakdown: CreditBreakdown
  activeFrozenItems: FrozenReservationItem[]
}

export function fetchCreditSummary(params?: { startAt?: string; endAt?: string }) {
  return unwrap<CreditSummary>(
    http.get('/credits/summary', {
      params: {
        start_at: params?.startAt,
        end_at: params?.endAt,
      },
    }),
  )
}

export function fetchCreditBills(params: {
  category?: CreditBillCategory
  status?: CreditBillStatus
  startAt?: string
  endAt?: string
  keyword?: string
  limit: number
  offset: number
}) {
  return unwrap<CreditBillList>(
    http.get('/credits/bills', {
      params: {
        category: params.category,
        status: params.status,
        start_at: params.startAt,
        end_at: params.endAt,
        keyword: params.keyword?.trim() || undefined,
        limit: params.limit,
        offset: params.offset,
      },
    }),
  )
}

export function fetchEnrichedCreditLedgers(params: {
  operation?: CreditLedgerOperation
  startAt?: string
  endAt?: string
  keyword?: string
  limit: number
  offset: number
}) {
  return unwrap<EnrichedCreditLedgerList>(
    http.get('/credits/ledgers', {
      params: {
        operation: params.operation,
        start_at: params.startAt,
        end_at: params.endAt,
        keyword: params.keyword?.trim() || undefined,
        limit: params.limit,
        offset: params.offset,
      },
    }),
  )
}
