# FrameDrama Frontend

Vue 3 + TypeScript + Vite + Tailwind CSS 的黑金前端工程。当前包含图片展示型首页、独立登录／注册页、工作台公共框架与创作首页，以及开发用组件预览；短剧创作已接入本地 `framedrama_lab` 后端的剧本、资产、分镜三个阶段，认证、项目持久化与视频生成尚未接入。

## 本地运行

```powershell
cd E:\App\codex\FrameDrama\frontend
npm install
npm run dev
```

首页地址：`http://127.0.0.1:5173/`。登录／注册：`http://127.0.0.1:5173/login`。组件预览：`http://127.0.0.1:5173/__dev/components`。如果端口被占用，以终端显示的地址为准。

工作台：`http://127.0.0.1:5173/workspace`。项目卡片预览：`http://127.0.0.1:5173/__dev/components#workspace-components`。

```powershell
npm run typecheck
npm test
npm run build
```

组件预览仅在开发环境注册，生产构建默认展示首页。部署时需要将前端路由请求回退到 `index.html`。

## 目录

| 位置 | 用途 |
| --- | --- |
| `src/components/ui` | 按钮、图标按钮、输入框、文本域、选择器、复选框、开关、标签页、菜单、弹窗、提示、通知、滑块、图片、骨架屏 |
| `src/components/business` | 任务状态、任务进度、文件选择、空状态、图片卡片、功能介绍、流程步骤 |
| `src/components/workspace` | 工作台侧栏、顶部工具栏、积分与用户菜单 |
| `src/layouts/WorkspaceLayout.vue` | 工作台公共布局与子路由出口 |
| `src/features/dashboard` | 创作首页、推广轮播与快捷入口卡片 |
| `src/features/studio/components` | 上传剧本与故事输入面板 |
| `src/features/projects` | 项目卡片和项目概要类型 |
| `src/styles/tokens.css` | 主题颜色、字体和通用样式变量 |
| `src/styles/index.css` | 自定义组件样式与开发预览布局 |
| `src/styles/media.css` | 图片、骨架屏及内容展示组件样式 |
| `src/lib/http.ts` | Axios 实例 |
| `src/lib/query-client.ts` | TanStack Vue Query 缓存与重试策略 |
| `src/stores/ui.ts` | Pinia 通知状态 |
| `src/router/index.ts` | Vue Router 入口 |
| `src/router/workspace.ts` | 工作台子路由，使用独立的短 URL |
| `src/dev/ComponentPreview.vue` | 仅开发环境使用的组件交互预览 |
| `src/views/HomeView.vue` | 首屏、题材筛选、图片预览、功能介绍与创作流程 |
| `src/views/AuthView.vue` | 手机验证码登录／注册、密码登录与找回密码界面 |
| `src/components/site` | 公共导航、手机菜单和页脚 |
| `src/styles/home.css` | 首页样式 |
| `src/styles/site.css` | 公共导航、页脚与账号入口样式 |
| `src/styles/auth.css` | 登录／注册页及其移动端样式 |
| `src/styles/workspace.css` | 工作台布局、侧栏与顶部工具栏样式 |
| `public/images/home` | 已压缩的首页生成素材 |
| `public/images/auth` | 登录页桌面与手机背景素材 |
| `public/images/workspace` | 工作台轮播与快捷入口的独立写实素材 |

Reka UI 提供弹窗焦点管理、菜单键盘操作、选择器和通知等交互基础。外观由本项目定义，图标使用 Lucide Vue。

目录规划见 [前端目录结构草案](../docs/frontend-architecture.md)。

## 工作台

`/workspace` 默认展示创作首页。`/projects`、`/canvas`、`/assets`、`/account` 共用同一个父布局，但 URL 不带 `/workspace` 前缀。目前这些子页面只显示明确的未实现状态，没有项目管理、画布编辑、素材或账户业务。

侧栏与工具栏在子页面之间保留；手机端通过弹窗导航切换。创作首页使用独立的影视制作主题写实图片，包含可暂停的推广轮播、上传剧本、故事输入和快捷入口，不包含“创作设置”。轮播支持方向键、悬停及聚焦暂停、页面隐藏暂停，并尊重减少动态效果偏好。

`ScriptCreationPanel` 通过 `upload(File)` 和 `story({ story, language })` 事件交给页面处理；`busy` 与 `feedback` 由调用方传入。支持 `v-model:mode`、`v-model:story` 和 `v-model:language`。当前页面收到提交事件时只提示服务尚未接入，不上传文件、不提交故事、不模拟生成。

`ProjectCard` 通过 `open(id)`、`rename(id)`、确认后的 `remove(id)` 事件通知调用方，不自行请求接口或移除项目。卡片支持无封面、名称截断、更新时间、菜单与删除确认；示例数据仅位于开发预览，不用于创作首页。最近项目区域当前显示服务未接入状态。

开发环境顶部的 `38.34` 和“预览用户”是明确的预览数据；生产构建显示未知积分和未登录状态。价格、客服、公告、充值入口均显示尚未配置或尚未接入的状态，不发起真实业务操作。

**当前工作台路由可直接访问，并不代表已登录或具备访问控制。** 真实认证、权限校验和登录成功后的跳转尚未接入，正式运营前必须完成后端鉴权及相应的前端登录流程。

测试通过 `npm test` 执行，覆盖文件校验、故事输入边界、轮播索引以及工作台路由匹配；组件交互另需浏览器验证，单元测试不代表后端服务验收。

## 使用组件

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { UiButton, UiInput, TaskProgress } from '@/components'

const name = ref('')
</script>

<template>
  <UiInput v-model="name" label="项目名称" placeholder="请输入项目名称" />
  <UiButton variant="primary" size="lg">创建项目</UiButton>
  <TaskProgress title="视频生成" status="running" :progress="42" />
</template>
```

按钮支持 `primary / secondary / outline / ghost / danger`，尺寸为 `sm / md / lg`，以及 `loading / disabled` 状态。图标按钮通过必填 `label` 提供名称和悬停提示。`UiInput` 提供 `leading / trailing` 插槽；密码显隐按钮可放入 `trailing`，组件会预留输入区域。

文件组件仅选择本地文件并校验扩展名、大小，不发起上传。后续服务端仍需独立验证文件内容和权限。任务进度省略 `progress` 时可以展示运行中的不确定进度。

## 图片与内容展示

开发预览的 `#images`、`#showcase`、`#process` 分别提供图片状态、内容展示和流程示例。

```vue
<script setup lang="ts">
import { UiImage, UiSkeleton, ImageCard, FeatureItem, ProcessSteps } from '@/components'
import type { ProcessStep } from '@/components'

const steps: ProcessStep[] = [
  { id: 'story', title: '整理故事', description: '确定人物与场景。' },
  { id: 'visuals', title: '准备视觉', description: '选择角色与封面素材。' },
]
</script>

<template>
  <UiImage src="/brand/framedrama-logo.svg" alt="帧剧标识" aspect-ratio="9:16" fit="contain" />
  <div aria-busy="true" aria-label="内容加载中"><UiSkeleton shape="text" width="60%" /></div>
  <ImageCard src="/brand/framedrama-logo.svg" alt="帧剧标识" title="品牌素材" />
  <FeatureItem title="故事创作" description="集中整理故事梗概、人物与场景。" />
  <ProcessSteps :steps="steps" />
</template>
```

| 组件 | 主要约定 |
| --- | --- |
| `UiImage` | `alt` 必填；`aspectRatio` 支持 `16:9 / 4:3 / 3:4 / 1:1 / 9:16` 或正数宽高比，默认 `16:9`。`fit` 为 `cover / contain`；`position` 调整裁切位置。默认懒加载，首屏可设 `loading="eager"`。 |
| `UiImage` 状态 | 空地址显示占位，加载中显示骨架，失败提供重试；发出 `load / error / retry` 事件。`retryable=false` 隐藏重试按钮；重试重新请求相同地址，刷新签名地址等逻辑由调用方处理。 |
| `UiSkeleton` | `shape` 为 `rect / text / circle`，支持 CSS 字符串 `width / height`；`animated=false` 关闭动画。组件对辅助技术隐藏，应在内容容器标记加载状态。尊重减少动态效果设置。 |
| `ImageCard` | 必填 `title / alt`，默认 `4:3`；支持分类、说明、图片适配与透明背景。配置 `actionLabel` 才显示默认操作按钮，通过 `action` 事件处理；也可用 `actions` 插槽。 |
| `FeatureItem` | 支持标题、说明、`icon` 插槽或 `imageSrc / imageAlt` 配图，以及横向、纵向布局。图片优先于图标。 |
| `ProcessSteps` | `steps` 使用唯一 `id`；支持说明和可选配图、横向与纵向排列。窄屏自动纵排；空数组不渲染步骤。用于流程介绍，不承担表单进度控制。 |

上述五种值是宽高比例，实际像素尺寸由容器决定。`checkerboard` 仅展示棋盘背景以便辨认透明区域，不会给图片生成透明通道。预览使用已有品牌 SVG 和透明背景 SVG，不调用 ComfyUI，也没有上传或生成图片。

## 首页与素材

首页显示图片，不加载视频。首屏通过 `picture` 分别提供桌面与手机图片，作品列表支持题材切换，点击可打开原比例图片并前后切换。

首页 6 张图片和登录页 2 张图片由用户提供的 Qwen Image 2.1 ComfyUI 工作流生成，采用真人电影摄影的写实风格。最终文件位于 `public/images/home` 和 `public/images/auth`，原始 PNG 保存在被忽略的 `artifacts/photoreal-v2-originals`。完整提示词、比例与种子位于 `scripts/photoreal-v2-image-briefs.json`。旧版插画原稿与生成记录保留在 `artifacts/homepage-originals` 和 `artifacts/homepage-generation.json`，不用于当前页面。

工作台另有 5 张 ComfyUI 写实素材：3 张轮播图对应剧本创作、分镜画布和素材整理，2 张快捷入口图对应短剧拍摄和分镜规划。JPEG 位于 `public/images/workspace`，原始 PNG 位于 `artifacts/workspace-v1-originals`，提示词、比例与种子位于 `scripts/workspace-v1-image-briefs.json`。这些是 AI 生成的网站配图，不是真实项目或用户作品。

本地生成工具仅用于制作网站素材，不会被打包或从浏览器调用：

```powershell
node scripts/generate-homepage-assets.mjs submit photoreal-v2
node scripts/generate-homepage-assets.mjs status photoreal-v2
pwsh -File scripts/optimize-homepage-assets.ps1 -Batch photoreal-v2
```

工作台素材使用同一套脚本，将上述批次参数 `photoreal-v2` 换成 `workspace-v1`。已有生成记录时不要重复提交，使用 `status` 获取对应批次的已有结果。

脚本使用本机 `127.0.0.1:8188` 和用户提供的 `D:/BlenderProjects/references/image_qwen_image_2_1_t2i.json`。提交前检查队列是否为空，并用生成记录阻止重复提交；`status` 下载已完成任务，不创建新任务。JPEG 压缩使用 Windows 自带的 System.Drawing。

`/login` 参考原站的全屏背景、左侧介绍与右侧表单布局；手机端纵向排列。默认显示手机验证码登录／注册，可切换密码登录，并提供密码显隐和找回密码弹窗。`/register` 跳转到同一个验证码入口，`/login?mode=password` 可直接打开密码登录。

认证界面仅提供前端交互和字段校验，不发送、持久保存或伪造认证数据。验证码按钮不会产生短信、倒计时或成功提示，当前显示短信服务尚未接入；提交时明确提示账号服务尚未开放。协议入口会说明条款尚未发布，不套用原站协议、积分赠送或数据安全承诺。正式运营前需要接入真实认证、协议、业务页面和运营信息。

## 接口约定

`VITE_API_BASE_URL` 默认为 `/api`，可参考 `.env.example` 配置。所有 `VITE_` 变量会暴露给浏览器，不能存放密钥。

Axios 负责请求，Vue Query 负责服务端数据缓存；默认缓存保鲜 30 秒，关闭窗口重新聚焦刷新和自动重试。短剧创作已接本地后端三个接口：`POST /api/story`、`POST /api/assets`、`POST /api/storyboard`，由 Vite 代理转发到 `127.0.0.1:8000`；生成类请求单次超时放宽到 15 分钟。认证、登录态、积分扣费、项目持久化与视频生成仍未接入。
