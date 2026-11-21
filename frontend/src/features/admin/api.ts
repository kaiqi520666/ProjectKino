import { http, unwrap } from '@/lib/http'

export interface AdminProviderHealth {
  key: string
  displayName: string
  adapter: string
  baseUrl: string
  enabled: boolean
  hasApiKey: boolean
}

export interface AdminOverview {
  totalUsers: number
  activeUsers: number
  operatorCount: number
  adminCount: number
  activeProjects: number
  archivedProjects: number
  runningJobs: number
  reviewJobs: number
  failedJobs24h: number
  totalBalance: string
  totalFrozen: string
  ossConfigured: boolean
  providers: AdminProviderHealth[]
}

export interface AdminUserItem {
  id: number
  email: string
  nickname: string
  role: 'user' | 'operator' | 'admin'
  status: 'active' | 'disabled'
  balance: string
  frozen: string
  usageMultiplier: string
  projectCount: number
  jobCount: number
  createdAt: string
}

export interface AdminUserList {
  items: AdminUserItem[]
  total: number
}

export interface CreditLedgerItem {
  id: string
  operation: string
  balanceChange: string
  frozenChange: string
  balanceBefore: string
  balanceAfter: string
  frozenBefore: string
  frozenAfter: string
  tokenUsage?: Record<string, unknown> | null
  reason: string
  createdAt: string
}

export interface AdminUserLedgers {
  user: AdminUserItem
  items: CreditLedgerItem[]
  total: number
}

export interface AdminJobItem {
  id: string
  userId: number
  userEmail: string
  projectId?: string | null
  projectName?: string | null
  jobType: string
  targetId?: string | null
  status: 'queued' | 'running' | 'polling' | 'succeeded' | 'failed' | 'review'
  stepIndex: number
  stepTotal: number
  stepLabel: string
  progress: number
  providerTaskId?: string | null
  inputPayload: Record<string, unknown>
  resultPayload?: Record<string, unknown> | null
  errorCode?: string | null
  errorMessage?: string | null
  usageSummary?: Record<string, unknown> | null
  reservationId?: string | null
  reservationAmount?: string | null
  reservationStatus?: string | null
  createdAt: string
  startedAt?: string | null
  finishedAt?: string | null
}

export interface AdminJobList {
  items: AdminJobItem[]
  total: number
  reviewCount: number
}

export function getAdminOverview() {
  return unwrap<AdminOverview>(http.get('/admin/overview'))
}

export function listAdminUsers(params: {
  q?: string
  role?: string
  status?: string
  limit?: number
  offset?: number
} = {}) {
  return unwrap<AdminUserList>(http.get('/admin/users', { params }))
}

export function updateAdminUser(
  userId: number,
  patch: {
    nickname?: string
    role?: 'user' | 'operator' | 'admin'
    status?: 'active' | 'disabled'
    usageMultiplier?: string
  },
) {
  return unwrap<AdminUserItem>(http.patch(`/admin/users/${userId}`, patch))
}

export function getAdminUserLedgers(userId: number, params: { limit?: number; offset?: number } = {}) {
  return unwrap<AdminUserLedgers>(http.get(`/admin/users/${userId}/ledgers`, { params }))
}

export function adjustAdminUserCredits(userId: number, body: { amount: string; reason: string }) {
  return unwrap<CreditLedgerItem>(http.post(`/admin/users/${userId}/credits`, body))
}

export function listAdminJobs(params: {
  status?: string
  jobType?: string
  userId?: number
  limit?: number
  offset?: number
} = {}) {
  return unwrap<AdminJobList>(http.get('/admin/jobs', { params }))
}

export function refundAdminJob(jobId: string, reason: string) {
  return unwrap<{ jobId: string; refundedAmount: string; status: string }>(
    http.post(`/admin/jobs/${jobId}/refund`, { reason }),
  )
}

export function rescueAdminJobMedia(jobId: string, body: { mediaUrl: string; note?: string }) {
  return unwrap<{ jobId: string; url: string; key: string; settledReservation: boolean }>(
    http.post(`/admin/jobs/${jobId}/rescue-media`, body),
  )
}

export interface AdminProvider {
  id: number
  key: string
  displayName: string
  baseUrl: string
  adapter: string
  authType: string
  authHeader?: string | null
  enabled: boolean
  hasApiKey: boolean
  configuration: Record<string, unknown>
}

export interface AdminTextPrice {
  inputPricePerMillion: string
  cachedInputPricePerMillion: string
  outputPricePerMillion: string
}

export interface AdminImagePrice {
  tier: 'web' | '1k' | '2k' | '4k'
  creditPrice: string
}

export interface AdminVideoPrice {
  ruleKey: string
  unit: 'second' | 'call'
  creditPrice: string
}

export interface AdminModelItem {
  id: string
  providerId: number
  providerKey: string
  providerName: string
  mediaType: 'text' | 'image' | 'video'
  category: string
  displayName: string
  upstreamModelId: string
  enabled: boolean
  upstreamAvailable: boolean
  lastSyncedAt?: string | null
  isDefault: boolean
  sort: number
  capabilities: Record<string, unknown>
  defaults: Record<string, unknown>
  configuration?: Record<string, unknown>
  textPrice?: AdminTextPrice | null
  imagePrices: AdminImagePrice[]
  videoPrices: AdminVideoPrice[]
}

export interface AdminModelSyncLog {
  id: number
  providerKey: string
  modelId: string
  upstreamModelId: string
  eventType: 'offline' | 'restored'
  summary: string
  createdAt: string
}

export interface AdminModelSyncLogList {
  items: AdminModelSyncLog[]
  total: number
}

export interface AdminModelSyncResult {
  providerKey: string
  skipped: boolean
  reason?: string
  checked?: number
  upstreamCount?: number
  offline?: number
  restored?: number
}

export interface AdminOssSettings {
  endpoint: string
  bucket: string
  publicBaseUrl: string
  prefix: string
  timeoutSeconds: number
  hasCredentials: boolean
  configured: boolean
}

export interface AdminRegistrationSettings {
  initialCredits: string
  defaultUsageMultiplier: string
}

export interface AdminSettings {
  oss: AdminOssSettings
  registration: AdminRegistrationSettings
}

export interface AdminProjectItem {
  id: string
  userId: number
  userEmail: string
  name: string
  status: 'active' | 'archived'
  episodeCount: number
  assetCount: number
  clipCount: number
  jobCount: number
  activeJobCount: number
  createdAt: string
  updatedAt: string
}

export interface AdminProjectList {
  items: AdminProjectItem[]
  total: number
  archivedCount: number
}

export function listAdminProviders() {
  return unwrap<AdminProvider[]>(http.get('/admin/providers'))
}

export function updateAdminProvider(
  providerKey: string,
  body: {
    displayName?: string
    baseUrl?: string
    apiKey?: string
    enabled?: boolean
  },
) {
  return unwrap<{ key: string; displayName: string; baseUrl: string; enabled: boolean }>(
    http.put(`/admin/providers/${encodeURIComponent(providerKey)}`, body),
  )
}

export function listAdminModels() {
  return unwrap<AdminModelItem[]>(http.get('/admin/models'))
}

export function createAdminModel(body: {
  id: string
  providerKey: string
  mediaType: 'text' | 'image' | 'video'
  category: string
  displayName: string
  upstreamModelId: string
  enabled: boolean
  isDefault: boolean
  sort: number
  capabilities?: Record<string, unknown>
  defaults?: Record<string, unknown>
  configuration?: Record<string, unknown>
  textPrice?: AdminTextPrice
  imagePrices?: AdminImagePrice[]
  videoPrices?: AdminVideoPrice[]
}) {
  return unwrap<AdminModelItem>(http.post('/admin/models', body))
}

export function updateAdminModel(
  modelId: string,
  body: {
    category?: string
    displayName?: string
    upstreamModelId?: string
    enabled?: boolean
    isDefault?: boolean
    sort?: number
    capabilities?: Record<string, unknown>
    defaults?: Record<string, unknown>
    configuration?: Record<string, unknown>
    textPrice?: AdminTextPrice
    imagePrices?: AdminImagePrice[]
    videoPrices?: AdminVideoPrice[]
  },
) {
  return unwrap<AdminModelItem>(http.patch(`/admin/models/${encodeURIComponent(modelId)}`, body))
}

export function deleteAdminModel(modelId: string) {
  return unwrap<{ id: string; deleted: boolean }>(
    http.delete(`/admin/models/${encodeURIComponent(modelId)}`),
  )
}

export function reorderAdminModels(modelIds: string[]) {
  return unwrap<{ updated: number; sorts: Record<string, number> }>(
    http.put('/admin/models/reorder', { modelIds }),
  )
}

export function syncAdminModels(providerKey = 'cc') {
  return unwrap<AdminModelSyncResult>(http.post('/admin/models/sync', null, { params: { provider_key: providerKey } }))
}

export function listAdminModelSyncLogs(params: { provider_key?: string; limit?: number; offset?: number } = {}) {
  return unwrap<AdminModelSyncLogList>(http.get('/admin/models/sync-logs', { params }))
}

export function getAdminSettings() {
  return unwrap<AdminSettings>(http.get('/admin/settings'))
}

export function updateAdminOssSettings(body: {
  endpoint: string
  bucket: string
  accessKeyId?: string
  accessKeySecret?: string
  publicBaseUrl: string
  prefix: string
  timeoutSeconds: number
}) {
  return unwrap<AdminOssSettings>(http.put('/admin/settings/oss', body))
}

export function updateAdminRegistrationSettings(body: {
  initialCredits: string
  defaultUsageMultiplier: string
}) {
  return unwrap<AdminRegistrationSettings>(http.put('/admin/settings/registration', body))
}

export function listAdminProjects(params: {
  status?: string
  q?: string
  limit?: number
  offset?: number
} = {}) {
  return unwrap<AdminProjectList>(http.get('/admin/projects', { params }))
}

export function restoreAdminProject(projectId: string) {
  return unwrap<{ id: string; status: string }>(http.post(`/admin/projects/${projectId}/restore`))
}

export function purgeAdminProject(projectId: string) {
  return unwrap<{ id: string; purged: boolean; deletedOssCount: number }>(
    http.delete(`/admin/projects/${projectId}/purge`),
  )
}
