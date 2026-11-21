import type { BackendBeat, BackendOutline, BackendOutlineCharacter, BackendOutlineScene, BackendScene } from './api-types.ts'

export const CHARS_PER_SECOND = 4.5
export const ACTION_SECONDS = 2.5

const CN_DIGITS = '零一二三四五六七八九'

export function chineseNumber(value: number): string {
  if (value < 10) return CN_DIGITS[value] ?? String(value)
  if (value < 20) return `十${value % 10 ? CN_DIGITS[value % 10] : ''}`
  if (value < 100) return `${CN_DIGITS[Math.floor(value / 10)]}十${value % 10 ? CN_DIGITS[value % 10] : ''}`
  return String(value)
}

export function lineChars(text: string): number {
  let count = 0
  for (const ch of text) {
    if (!/\s/u.test(ch)) count += 1
  }
  return count
}

export function beatSeconds(beat: BackendBeat): number {
  if (beat.line !== undefined && beat.line !== null) {
    return lineChars(beat.line) / CHARS_PER_SECOND
  }
  return ACTION_SECONDS
}

export function scenesSeconds(scenes: BackendScene[]): number {
  let total = 0
  for (const scene of scenes) {
    for (const beat of scene.flow) {
      total += beatSeconds(beat)
    }
  }
  return Math.round(total * 10) / 10
}

export function readOutlineCharacters(outline?: BackendOutline): BackendOutlineCharacter[] {
  const list = outline?.characters
  if (!Array.isArray(list)) return []
  return list.filter((item): item is BackendOutlineCharacter =>
    !!item && typeof item === 'object' && typeof item.id === 'string' && typeof item.name === 'string',
  )
}

export function readOutlineScenes(outline?: BackendOutline): BackendOutlineScene[] {
  const list = outline?.scenes
  if (!Array.isArray(list)) return []
  return list.filter((item): item is BackendOutlineScene =>
    !!item && typeof item === 'object' && typeof item.id === 'string' && typeof item.name === 'string',
  )
}

export function cloneScenes(scenes: BackendScene[]): BackendScene[] {
  return scenes.map((scene) => ({
    sceneId: scene.sceneId,
    lighting: scene.lighting ?? '',
    characters: [...scene.characters],
    props: [...scene.props],
    flow: scene.flow.map((beat) => ({ ...beat })),
  }))
}

export function normalizeScenes(scenes: BackendScene[]): BackendScene[] {
  return scenes.map((scene) => {
    const characters = [...scene.characters]
    const flow: BackendBeat[] = []
    for (const beat of scene.flow) {
      if (beat.action !== undefined && beat.action !== null) {
        const text = beat.action.trim()
        if (!text) continue
        flow.push({ action: text })
      } else {
        const line = (beat.line ?? '').trim()
        if (!line) continue
        const speaker = (beat.speaker ?? '').trim() || 'VO'
        const delivery = (beat.delivery ?? '').trim()
        if (speaker !== 'VO' && !characters.includes(speaker)) {
          characters.push(speaker)
        }
        flow.push(delivery ? { speaker, line, delivery } : { speaker, line })
      }
    }
    return {
      sceneId: scene.sceneId,
      lighting: (scene.lighting ?? '').trim(),
      characters,
      props: [...scene.props],
      flow,
    }
  })
}

export function validateStructuredScenes(scenes: BackendScene[]): string | null {
  if (!scenes.length) return '本集至少需要保留一场戏。'
  for (let i = 0; i < scenes.length; i += 1) {
    const scene = scenes[i]!
    if (!scene.flow.length) return `第${chineseNumber(i + 1)}场没有任何有效节拍，请补充动作或台词。`
    if (!scene.flow.some((beat) => beat.action !== undefined && beat.action !== null && beat.action.trim().length > 0)) {
      return `第${chineseNumber(i + 1)}场至少需要保留一条动作节拍，避免分镜阶段无画面可拍。`
    }
  }
  return null
}

export function renderStructuredScript(scenes: BackendScene[], outline?: BackendOutline): string {
  const sceneMap = new Map(readOutlineScenes(outline).map((card) => [card.id, card]))
  const charMap = new Map(readOutlineCharacters(outline).map((card) => [card.id, card.name]))
  const blocks: string[] = []

  for (let i = 0; i < scenes.length; i += 1) {
    const scene = scenes[i]!
    const lines: string[] = [`第${chineseNumber(i + 1)}场`]
    const card = sceneMap.get(scene.sceneId)
    if (card) {
      lines.push(`${card.kind} · ${card.name} · ${card.time}`)
    }
    for (const beat of scene.flow) {
      if (beat.action !== undefined && beat.action !== null) {
        if (beat.action.trim()) lines.push(beat.action.trim())
      } else if (beat.line !== undefined && beat.line !== null && beat.line.trim()) {
        const speakerId = beat.speaker ?? ''
        const speaker = speakerId === 'VO' ? '画外音' : (charMap.get(speakerId) ?? speakerId)
        lines.push(`${speaker}：${beat.line.trim()}`)
      }
    }
    blocks.push(lines.join('\n\n'))
  }
  return blocks.join('\n\n')
}
