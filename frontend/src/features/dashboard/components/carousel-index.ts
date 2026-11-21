export function wrapSlideIndex(index: number, count: number): number {
  if (!Number.isInteger(count) || count < 1 || !Number.isFinite(index)) return 0
  return ((Math.trunc(index) % count) + count) % count
}
