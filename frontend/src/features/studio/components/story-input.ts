export const storyMaxLength = 2000

export function validateStory(story: string): string | null {
  if (!story.trim()) return '请先输入故事梗概'
  if (story.length > storyMaxLength) return `故事梗概不能超过 ${storyMaxLength} 字`
  return null
}
