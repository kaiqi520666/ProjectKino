import axios from 'axios'

import type { OssUploadPolicyOut } from '@/features/studio/api-types'
import { http, unwrap } from '@/lib/http'
import { convertImageFileToWebp } from './webp-compress'

export interface ArtStyleItem {
  id: number
  code: string
  label: string
  prompt: string
  imageUrl: string
  isEnabled: boolean
  isDefault: boolean
  sortOrder: number
}

export interface AdminArtStyleItem extends ArtStyleItem {
  imageKey: string
  projectCount: number
  createdAt: string
  updatedAt: string
}

export interface AdminArtStyleCreatePayload {
  code: string
  label: string
  prompt: string
  imageKey: string
  imageUrl: string
  isEnabled?: boolean
  isDefault?: boolean
  sortOrder?: number
}

export interface AdminArtStyleUpdatePayload {
  label?: string
  prompt?: string
  imageKey?: string
  imageUrl?: string
  isEnabled?: boolean
  isDefault?: boolean
  sortOrder?: number
}

export function fetchArtStyles() {
  return unwrap<{ items: ArtStyleItem[] }>(http.get('/art-styles'))
}

export function listAdminArtStyles(
  params: {
    keyword?: string
    status?: 'all' | 'enabled' | 'disabled'
    limit?: number
    offset?: number
  } = {},
) {
  return unwrap<{ items: AdminArtStyleItem[]; total: number }>(
    http.get('/admin/art-styles', { params }),
  )
}

export function requestArtStyleUploadPolicy(body: {
  fileName: string
  mimeType: string
  size: number
  code?: string
}) {
  return unwrap<OssUploadPolicyOut>(http.post('/admin/art-styles/upload-policy', body))
}

export async function uploadArtStyleImageToOss(
  rawFile: File,
  code?: string,
): Promise<{ key: string; url: string; size: number; mimeType: string }> {
  const file = await convertImageFileToWebp(rawFile)
  const mimeType = file.type || 'image/webp'
  const policy = await requestArtStyleUploadPolicy({
    fileName: file.name,
    mimeType,
    size: file.size,
    code: code?.trim() || undefined,
  })
  const form = new FormData()
  for (const [key, value] of Object.entries(policy.fields)) {
    form.append(key, value)
  }
  form.append('file', file)
  await axios.post(policy.host, form, { timeout: 60_000 })
  return {
    key: policy.key,
    url: policy.url,
    size: file.size,
    mimeType,
  }
}

export function createAdminArtStyle(body: AdminArtStyleCreatePayload) {
  return unwrap<AdminArtStyleItem>(http.post('/admin/art-styles', body))
}

export function updateAdminArtStyle(id: number, body: AdminArtStyleUpdatePayload) {
  return unwrap<AdminArtStyleItem>(http.patch(`/admin/art-styles/${id}`, body))
}

export function deleteAdminArtStyle(id: number) {
  return unwrap<{ id: number; deleted: boolean }>(http.delete(`/admin/art-styles/${id}`))
}
