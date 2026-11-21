# 帧剧后端验证

输入故事梗概、UTF-8 小说或剧本原稿。Pydantic AI 先规划分集（角色 / 场景 / 道具编号 + 逐集计划），再逐集生成**结构化剧本**。整条流水线对应前端三步：**剧本确认 → 资产生成 → 分镜制作**。

产出同时包含两份可用格式：

- **结构化节拍流**：`episodes[].scenes[].flow[]`，每拍要么是 `action`，要么是 `speaker + line + delivery`，可直接对接配音、分镜和时长统计。
- **纯文本剧本**：`episodes[].script`，按「第X场 / 内景 · 场景 · 夜 / 动作 / 角色：台词」渲染，现有前端不用改即可直接使用。

每集还带 `targetSeconds`、`hook`、`cliff`、`hookBeat`，以及确定性折算的 `seconds`。

## 本地运行

在 `backend-lab` 目录运行。通过本地 `.env` 或当前环境提供 `DEEPSEEK_API_KEY`。默认使用官方 API 的 `deepseek-flash`，对应 DeepSeek V4.1 Flash。可以通过 `DEEPSEEK_MODEL` 和 `DEEPSEEK_BASE_URL` 配置兼容接口。上传原稿的命令会将该原稿发送给配置的模型服务。

```powershell
uv sync --locked
uv run --locked python -m unittest discover -s tests -v
uv run --locked --env-file .env python -m framedrama_lab sample-settings.json --story '失忆法医发现线索都指向三年前死亡的自己。' --output output/story.json
uv run --locked --env-file .env python -m framedrama_lab sample-settings.json --source-file 'E:/App/codex/video-script/剧本.txt' --output output/adaptation.json --markdown output/adaptation.md
uv run --locked --env-file .env uvicorn framedrama_lab.api:app --reload --port 8000
```

`sample-settings.json` 默认 5 集。`--episode-seconds` 可以覆盖单集目标时长（默认 120 秒）。若使用当前环境变量，省略 `--env-file .env`。

单元测试通过模拟 HTTP 响应验证 JSON 模式、大纲校验、剧本质量门、时长折算和原稿工具，无需 API Key。

## 剧本质量门

写每一集后由代码确定性检查，不通过就带着具体问题让模型重写：

| 检查       | 规则                                                                                                                     |
| ---------- | ------------------------------------------------------------------------------------------------------------------------ |
| 集数与集号 | 大纲恰好 `episodeCount` 集，集号 1 起连续                                                                                |
| 时长预算   | 台词按 4.5 字/秒、动作按 2.5 秒/拍折算。±15% 是建议区间，±25% 是硬门槛；落在两者之间照常交付，并在该集 `warnings` 里提示 |
| 单句长度   | 每句台词非空白字符不超过 35 字                                                                                           |
| 说话人     | 必须是本场 `characters` 里的编号，画外音统一 `VO`                                                                        |
| 动作描写   | 不许混入引号台词                                                                                                         |
| 冷开场     | `hookBeat` 认领的钩子必须落在全集前 3 拍                                                                                 |
| 镜头时长   | 每切 2–5 秒；不足 2 秒的尾差并回上一镜，最多到 6 秒                                                                      |
| 节拍覆盖   | 每集所有节拍按顺序被镜头恰好覆盖一次，段内切点连续                                                                       |
| 场次可用   | 每场至少一个动作节拍；`sceneId` 必须来自大纲并属于本集计划                                                               |
| 角色对账   | 出场角色必须在大纲角色表且属于本集 `characterIds`                                                                        |

## 长篇小说

原文超过 24000 字时，先按章节标题切块（无标题则按长度切块）逐段摘要，规划阶段读摘要而不是全文；写作阶段仍然只拿每集 `sourceLines` 圈定的原文，并可以用 `read_source_excerpt` 回查。单集圈定的原文上限 1200 行。

## 字段说明

```jsonc
{
  "settings": {
    "name": "...",
    "ratio": "16:9",
    "visualStyle": "...",
    "episodeCount": 5,
    "secondsPerEpisode": 120,
    "backgroundMusic": true,
  },
  "outline": {
    "continuity": "全剧设定与悬念揭示顺序",
    "world": {
      "kind": "historical",
      "era": "1942 年，民国东北山村",
      "baseline": "土坯房、松木梁、纸窗、煤油灯；无电灯、无塑料、无现代织物",
    },
    "characters": [
      { "id": "C01", "name": "...", "role": "...", "voice": "..." },
    ],
    "scenes": [
      {
        "id": "S01",
        "name": "...",
        "kind": "内景",
        "time": "夜",
        "note": "...",
      },
    ],
    "props": [{ "id": "P01", "name": "...", "role": "在剧情里的用途" }],
    "episodes": [
      {
        "number": 1,
        "title": "...",
        "summary": "...",
        "hook": "...",
        "suspense": "...",
        "ending": "...",
        "characterIds": ["C01"],
        "sceneIds": ["S01"],
        "propIds": [],
        "sourceLines": [[1, 40]],
      },
    ],
  },
  "episodes": [
    {
      "number": 1,
      "title": "...",
      "summary": "...",
      "hook": "...",
      "cliff": "...",
      "hookBeat": [1, 1],
      "targetSeconds": 120,
      "seconds": 118.5,
      "scenes": [
        {
          "sceneId": "S01",
          "lighting": "...",
          "characters": ["C01"],
          "props": ["P01"],
          "flow": [
            { "action": "陈九河把烟袋往炕沿上一磕。" },
            {
              "speaker": "C01",
              "line": "坐着说。先喘匀了气。",
              "delivery": "声音不高",
            },
          ],
        },
      ],
      "script": "第一场\n\n内景 · 档案室 · 夜\n\n……",
    },
  ],
}
```

## HTTP 接口

```powershell
uv run --locked --env-file .env python -m framedrama_lab.api
```

开发时加 `--reload`，改完 Python 文件会自动重启：`python -m framedrama_lab.api --reload`。也可以直接用 uvicorn：`uvicorn framedrama_lab.api:app --reload`。

默认监听 `127.0.0.1:8000`，可用 `--port` 或 `PORT` 环境变量覆盖。

| 方法   | 路径              | 请求体                       | 返回               |
| ------ | ----------------- | ---------------------------- | ------------------ |
| `GET`  | `/api/health`     | —                            | `{ok, model}`      |
| `POST` | `/api/story`      | `{settings, mode, text}`     | `ScriptResult`     |
| `POST` | `/api/assets`     | `{script}`                   | `AssetResult`      |
| `POST` | `/api/storyboard` | `{script, assets, episode?}` | `StoryboardResult` |

- 无状态：每一阶段把上一阶段的 JSON 原样传回，不建项目库、不落盘。
- `mode` 为 `story`（梗概）或 `upload`（小说原文），`text` 是正文。
- 生成类请求是同步的：5 集可能跑几分钟。前端调用这些接口时要把 axios 超时放宽（默认 30 秒不够），或者后续改成任务轮询。
- 已允许 `127.0.0.1:5173` / `localhost:5173` 跨域；用 Vite 代理时把它指到 `http://127.0.0.1:8000` 即可。

## 世界基准

规划阶段从原文推断 `outline.world`，下游资产和分镜都按它约束年代、建筑、材质与器物：

| 字段          | 规则                                                                 |
| ------------- | -------------------------------------------------------------------- |
| `kind`        | `historical` / `modern` / `scifi` / `fantasy`                        |
| `era`         | 具体时空坐标；禁止单独写「古代 / 古装 / 架空 / 未来 / 现代」         |
| `era`（历史） | 必须带朝代或年份                                                     |
| `era`（现代） | 必须带当代、都市、乡村这类可画的时代锚                               |
| `era`（科幻） | 必须带年份或具体地点                                                 |
| `era`（奇幻） | 写「某朝风格 + 自设世界」或一个具体世界名                            |
| `baseline`    | 至少 20 字，并写明这个世界没有什么（用「无 / 没有 / 禁止」列排除项） |

校验不过会让规划阶段带着原因重写。老剧本没有 `world` 也能继续跑资产和分镜，只是提示词里少一行「世界观」。

## 前端对接

前端 `frontend/src/features/studio/` 的类型与后端产出的对应关系：

- `settings`：字段与 `DramaSettings` 同名，可直接使用。`language` 支持 `zh-CN` / `zh-TW` / `en`；`backgroundMusic` 控制是否生成配乐（默认 `true`）；后端额外补一个 `secondsPerEpisode`（默认 120），前端忽略即可。
- `outline.world`：世界基准，`kind` / `era` / `baseline`；老数据可能没有，展示前判空。
- `episodes`：后端是数组，前端存的是 `Partial<Record<number, StudioEpisode>>`，接入时按 `number` 建 map。`scenes`、`hook`、`seconds` 等额外字段可忽略；`script` 是渲染好的纯文本，直接放进 `StudioEpisode.script`。
- `assets`：`id` / `kind` / `name` / `description` / `prompt` 与 `StudioAsset` 同名同型。**必须沿用后端的 `C01` / `S01` / `P01`**，前端不要再生成 UUID，否则分镜里的 `assetIds` 匹配不上。`episodeNumbers` 是额外字段，可用于分组。
- `storyboard`：`clips[{id,durationSeconds,prompt,assetIds}]` 与 `StoryboardClip`、`assets[{id,kind,name}]` 与 `StoryboardAsset` 完全对齐；`imageUrl` 由前端出图后补。

## 资产生成（角色 / 场景 / 物品）

资产清单由代码从已确认的结构化剧本汇总：`scenes[].sceneId`、`characters`、`props` 就是实际出场记录。模型只写 `description` 和生图 `prompt`，不再逐集重新识别、再合并，也不增减条目。

```powershell
uv run --locked --env-file .env python -m framedrama_lab.analyze_assets output/story.json --output output/story-assets.json
```

每项返回 `id`、`kind`（`character` / `scene` / `prop`）、`name`、`description`、`prompt`、`episodeNumbers`。角色的 `prompt` 由程序套进固定的**三视图设定图模板**（左侧大头照 + 右侧正面/侧面/背面三个无头身体视图、纯白背景、标准站姿），模型只写其中的人物描述；场景与道具的提示词仍由模型完整写。角色额外返回 `voice`（静态音色参数串，场景与道具留空）：描述这把嗓子本身，不写表演指导；每句台词的情绪由剧本 `delivery` 负责。生图提示词里不允许出现角色名，校验不过会带原因重写。

## 分镜制作

分三层：**段（一次视频生成，≤ `maxSegmentDuration`）→ 镜头（段内 2–5 秒的切）→ 分镜图提示词**。段不跨场；每切认领一段连续节拍。切分、时长、节拍归属都由代码算，模型只写每段的视频提示词与开场走位、每一镜的景别/运镜/分镜图提示词。

```powershell
uv run --locked --env-file .env python -m framedrama_lab.storyboard output/story.json --assets output/story-assets.json --output output/story-storyboard.json
```

`--episode 3` 只做某一集。每集返回 `assets[]` 与 `clips[]`。片段时长对外一律是**整数秒**（四舍五入），并且不会超过 `settings.maxSegmentDuration`；镜头本身仍保留 0.1 秒精度用于校验。

```jsonc
"clips": [{
  "id": 1, "durationSeconds": 12.5, "prompt": "段级视频提示词",
  "assetIds": ["S01", "C01", "P01"],
  "beats": [1, 5],                       // 认领本集第 1–5 拍
  "blocking": "陈九河蹲在坟前，老赵头站在他左后方两米处",
  "cuts": [
    { "index": 1, "seconds": 5.0, "shotSize": "中景", "camera": "缓推",
      "framePrompt": "分镜图提示词", "beats": [1, 2] },
    { "index": 2, "seconds": 4.5, "shotSize": "近景", "camera": "固定",
      "framePrompt": "分镜图提示词", "beats": [3, 5] }
  ]
}]
```

字段与前端 `EpisodeStoryboard` 对齐；`cuts` 与 `blocking` 是新增字段，旧分镜数据没有也能正常读取。

`references` 是这一段参考图的**唯一顺序合同**：`index` 对应提示词里的 `@[图片N]`，也对应实际附件的上传顺序。顺序固定为**角色 → 场景 → 道具**，与前端分镜页的资产栏一致；旧数据没有这个字段时，前端退回按 `assetIds` 展示。

`settings.backgroundMusic` 为 `false` 时，分镜不会输出配乐行（`music` 被忽略），并在【约束】里加一条「不生成背景音乐；只保留对白、环境音与动作音效」。为 `true` 时保持原样，有 `music` 就输出配乐。

整集设计按每 4 段分批请求，避免一次输出撞上模型 token 上限。

`prompt` 不是自由文本，而是按 Seedance 规范由程序拼装：先声明 `@[图片N] = 资产名`，再按本段有台词的角色输出【角色音色】块（音色绑定到参考图编号），然后写【人物关系与构图逻辑】，逐镜展开焦距 / 机位 / 构图 / 运镜 / 景别 / 画面 / 台词 / 视线落点 / 焦点 / 稳定性，末尾是声景 `<>`、配乐 `（）`、世界观、画风与【约束】。世界观只保留「时代 + 少量正向材质」，`baseline` 里的排除项（含「无 / 没有 / 禁」的短句）自动移进【约束】，避免每段重复长句。台词按 `台词（角色，情绪）：{原文}` 写，台词逐字进 `{}`，情绪取剧本 `delivery` 的第一个短句，模型不重写台词。画风与世界观明显冲突（如现代世界配古装画风）时，命令行会打印警告。`cuts[].framePrompt` 是同一镜头的静态分镜图提示词（这一层允许直接写角色名，供出图时挂参考图）。

## Skills（按前端三步流程）

| 技能              | 对应前端 | 输入 → 输出                                |
| ----------------- | -------- | ------------------------------------------ |
| `plan-episodes`   | 剧本确认 | 小说/梗概 → 分集大纲、角色/场景/道具编号表 |
| `write-episode`   | 剧本确认 | 单集计划 → 场次与节拍流                    |
| `analyze-assets`  | 资产生成 | 结构化剧本 → 描述与生图提示词              |
| `plan-storyboard` | 分镜制作 | 单集剧本 + 资产 → 片段提示词               |
| `condense-source` | 内部     | 长篇小说分块 → 摘要与事件清单              |

运行时从 `framedrama_lab/skills/` 加载 Skill。`upstream/` 保存供比对的原文及许可证。ZenStory `zenstory-ai/drama-skills` 取自 `bb1e7370d368bae9af8b6f3e092c47952b4abd3a`（MIT）。烁皓 `eternityspring/shuohao-skills` 取自 `8af10e0ea1a550e4575666884f4deef780bf38ff`（Apache-2.0，保留 `NOTICE`）。
