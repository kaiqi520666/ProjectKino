export function normalizeReadIds(raw: unknown): number[] {
  if (!Array.isArray(raw)) return []
  const unique = new Set<number>()
  for (const item of raw) {
    if (typeof item === 'number' && Number.isSafeInteger(item) && item > 0) {
      unique.add(item)
    }
  }
  return [...unique]
}

export function computeUnreadIds(availableIds: readonly number[], readIds: readonly number[]): number[] {
  if (!availableIds.length) return []
  const readSet = new Set(readIds)
  return availableIds.filter((id) => !readSet.has(id))
}

export function computeFirstUnreadCursor(availableIds: readonly number[], readIds: readonly number[]): number | undefined {
  const unread = computeUnreadIds(availableIds, readIds)
  const first = unread[0]
  return first === undefined ? undefined : first + 1
}
