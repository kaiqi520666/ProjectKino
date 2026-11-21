import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('../', import.meta.url))
const endpoint = 'http://127.0.0.1:8188'
const batch = process.argv[3] ?? 'photoreal-v2'
if (!/^[a-z0-9-]+$/.test(batch)) throw new Error('Invalid batch name.')
const outputDirectory = path.join(root, `artifacts/${batch}-originals`)
const manifestPath = path.join(root, `artifacts/${batch}-generation.json`)
const briefs = JSON.parse(await readFile(path.join(root, `scripts/${batch}-image-briefs.json`), 'utf8'))
const mode = process.argv[2] ?? 'status'

async function request(route, options) {
  const response = await fetch(`${endpoint}${route}`, { ...options, signal: AbortSignal.timeout(30000) })
  if (!response.ok) throw new Error(`${route}: HTTP ${response.status}: ${(await response.text()).slice(0, 1200)}`)
  return response.json()
}

if (mode === 'submit') {
  const workflow = JSON.parse(await readFile('D:/BlenderProjects/references/image_qwen_image_2_1_t2i.json', 'utf8'))
  await mkdir(path.dirname(manifestPath), { recursive: true })
  try {
    await readFile(manifestPath)
    throw new Error('Generation manifest already exists. Inspect existing jobs before submitting again.')
  } catch (error) {
    if (error.code !== 'ENOENT') throw error
  }
  const queue = await request('/queue')
  if (queue.queue_running.length || queue.queue_pending.length) throw new Error('ComfyUI already has queued work.')
  const jobs = []
  for (const brief of briefs) {
    const prompt = structuredClone(workflow)
    prompt['13'].inputs.aspect_ratio = brief.ratio
    prompt['459:452'].inputs.prompt = brief.prompt
    prompt['459:452'].inputs.negative_prompt = brief.negativePrompt ?? ''
    prompt['459:458'].inputs.seed = brief.seed
    prompt['461'].inputs.filename_prefix = `FrameDrama/${batch}/${brief.name}`
    const result = await request('/prompt', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, client_id: 'framedrama-homepage-assets' }),
    })
    jobs.push({ name: brief.name, promptId: result.prompt_id })
    await writeFile(manifestPath, `${JSON.stringify(jobs, null, 2)}\n`)
    console.log(`Queued ${brief.name}: ${result.prompt_id}`)
  }
} else {
  const jobs = JSON.parse(await readFile(manifestPath, 'utf8'))
  await mkdir(outputDirectory, { recursive: true })
  for (const job of jobs) {
    const history = await request(`/history/${encodeURIComponent(job.promptId)}`)
    const result = history[job.promptId]
    if (!result) { console.log(`${job.name}: pending or running`); continue }
    if (result.status?.status_str === 'error') {
      console.log(`${job.name}: failed ${JSON.stringify(result.status.messages).slice(0, 1600)}`)
      continue
    }
    const images = Object.values(result.outputs ?? {}).flatMap(output => output.images ?? [])
    if (!images.length) { console.log(`${job.name}: no output image`); continue }
    const image = images[0]
    const query = new URLSearchParams({ filename: image.filename, subfolder: image.subfolder ?? '', type: image.type ?? 'output' })
    const response = await fetch(`${endpoint}/view?${query}`, { signal: AbortSignal.timeout(30000) })
    if (!response.ok) throw new Error(`Image download failed: ${job.name}`)
    await writeFile(path.join(outputDirectory, `${job.name}.png`), Buffer.from(await response.arrayBuffer()))
    console.log(`${job.name}: saved`)
  }
}
