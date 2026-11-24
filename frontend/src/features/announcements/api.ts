import { http, unwrap } from '@/lib/http'

export interface AnnouncementItem {
  id: number
  title: string
  content: string
  publishedAt: string
}

export interface AdminAnnouncementItem extends AnnouncementItem {
  version: number
  updatedAt: string
}

export function getAnnouncementIndex() {
  return unwrap<{ ids: number[] }>(http.get('/announcements/index'))
}

export function listAnnouncements(beforeId?: number, limit = 20) {
  return unwrap<{ items: AnnouncementItem[]; hasMore: boolean }>(
    http.get('/announcements', {
      params: {
        beforeId: beforeId ?? undefined,
        limit,
      },
    }),
  )
}

export function listAdminAnnouncements(params: {
  keyword?: string
  limit?: number
  offset?: number
} = {}) {
  return unwrap<{ items: AdminAnnouncementItem[]; total: number }>(
    http.get('/admin/announcements', { params }),
  )
}

export function createAdminAnnouncement(body: { title: string; content: string }) {
  return unwrap<AdminAnnouncementItem>(http.post('/admin/announcements', body))
}

export function updateAdminAnnouncement(
  id: number,
  body: { title: string; content: string; version: number },
) {
  return unwrap<AdminAnnouncementItem>(http.patch(`/admin/announcements/${id}`, body))
}

export function deleteAdminAnnouncement(id: number, version: number) {
  return unwrap<{ id: number; deleted: boolean }>(
    http.delete(`/admin/announcements/${id}`, { params: { version } }),
  )
}
