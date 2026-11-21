export interface DateRangeValue {
  start: string | null
  end: string | null
}

export type BuiltinDateRangePresetId = 'today' | '7d' | '30d'

export interface DateRangePresetOption {
  id: string
  label: string
  shortLabel?: string
  resolve: (today?: Date) => DateRangeValue
}

export interface CalendarCell {
  iso: string
  day: number
  inMonth: boolean
  isToday: boolean
  isFuture: boolean
}

const ISO_DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/

export function formatLocalDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function parseLocalDate(isoDate: string | null | undefined): Date | null {
  if (!isoDate) return null
  const match = ISO_DATE_RE.exec(isoDate.trim())
  if (!match) return null
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const parsed = new Date(year, month - 1, day)
  if (
    parsed.getFullYear() !== year
    || parsed.getMonth() !== month - 1
    || parsed.getDate() !== day
  ) {
    return null
  }
  return parsed
}

export function shiftLocalDays(date: Date, days: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days)
}

export function createDateRangePreset(
  preset: BuiltinDateRangePresetId,
  today: Date = new Date(),
): DateRangeValue {
  const end = formatLocalDate(today)
  if (preset === 'today') return { start: end, end }
  const offset = preset === '7d' ? -6 : -29
  return {
    start: formatLocalDate(shiftLocalDays(today, offset)),
    end,
  }
}

export const DEFAULT_DATE_RANGE_PRESETS: readonly DateRangePresetOption[] = [
  {
    id: 'today',
    label: '今天',
    shortLabel: '今天',
    resolve: (today) => createDateRangePreset('today', today),
  },
  {
    id: '7d',
    label: '近 7 天',
    shortLabel: '7天',
    resolve: (today) => createDateRangePreset('7d', today),
  },
  {
    id: '30d',
    label: '近 30 天',
    shortLabel: '30天',
    resolve: (today) => createDateRangePreset('30d', today),
  },
]

export function isDateRangeEqual(a: DateRangeValue, b: DateRangeValue): boolean {
  return (a.start ?? null) === (b.start ?? null) && (a.end ?? null) === (b.end ?? null)
}

export function normalizeDateRange(a: string, b: string): { start: string; end: string } {
  return a <= b ? { start: a, end: b } : { start: b, end: a }
}

export function matchDateRangePreset(
  range: DateRangeValue,
  presets: readonly DateRangePresetOption[] = DEFAULT_DATE_RANGE_PRESETS,
  today: Date = new Date(),
): string | null {
  if (!range.start && !range.end) return null
  for (const preset of presets) {
    if (isDateRangeEqual(range, preset.resolve(today))) {
      return preset.id
    }
  }
  return null
}

export function toUtcIsoBounds(range: DateRangeValue): { createdFrom?: string; createdTo?: string } {
  const startDate = parseLocalDate(range.start)
  const endDate = parseLocalDate(range.end)
  const result: { createdFrom?: string; createdTo?: string } = {}
  if (startDate) {
    result.createdFrom = new Date(
      startDate.getFullYear(),
      startDate.getMonth(),
      startDate.getDate(),
      0,
      0,
      0,
      0,
    ).toISOString()
  }
  if (endDate) {
    result.createdTo = new Date(
      endDate.getFullYear(),
      endDate.getMonth(),
      endDate.getDate() + 1,
      0,
      0,
      0,
      0,
    ).toISOString()
  }
  return result
}

export function buildCalendarMonthGrid(
  year: number,
  monthIndex: number,
  today: Date = new Date(),
): CalendarCell[] {
  const todayIso = formatLocalDate(today)
  const firstDay = new Date(year, monthIndex, 1)
  const leadingOffset = (firstDay.getDay() + 6) % 7
  const gridStart = new Date(year, monthIndex, 1 - leadingOffset)
  const cells: CalendarCell[] = []

  for (let i = 0; i < 42; i++) {
    const cellDate = shiftLocalDays(gridStart, i)
    const iso = formatLocalDate(cellDate)
    cells.push({
      iso,
      day: cellDate.getDate(),
      inMonth: cellDate.getMonth() === monthIndex && cellDate.getFullYear() === year,
      isToday: iso === todayIso,
      isFuture: iso > todayIso,
    })
  }
  return cells
}
