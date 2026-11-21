# FrameDrama Frontend

Vue 3 + TypeScript + Vite + Tailwind CSS v4 的黑金短剧创作前端工程，已完整接入正式后端（`backend`）的认证鉴权、项目持久化、剧本生成、资产库与批量生图、分镜与批量生视频、本集 FFmpeg 免费合成、积分流水以及管理后台。

## 本地运行

```powershell
cd E:\App\codex\FrameDrama\frontend
npm install
npm run dev
```

常用地址：

- 首页：`http://127.0.0.1:5173/`
- 登录／注册：`http://127.0.0.1:5173/login`
- 工作台：`http://127.0.0.1:5173/workspace`
- 管理后台（需管理员角色）：`http://127.0.0.1:5173/admin`
- 组件预览（仅开发环境）：`http://127.0.0.1:5173/__dev/components`

## 质量检查与构建

```powershell
npm run lint
npm run typecheck
npm test
npm run build
```

部署时需要将前端路由请求回退到 `index.html`，并将 `/api/v1` 代理至 FastAPI 后端。

## 目录结构

| 位置 | 用途 |
| --- | --- |
| `src/components/ui` | Reka UI 封装设计系统组件（按钮、表单、弹窗、数据表、预览等） |
| `src/components/business` | 任务状态、进度、文件选择、空状态、流程展示 |
| `src/components/workspace` | 工作台侧栏、顶部工具栏、页面标题、账号与积分菜单 |
| `src/components/site` | 官网导航、移动端菜单与页脚 |
| `src/layouts/WorkspaceLayout.vue` | 工作台与管理后台统一外壳布局（价格表、积分流水、侧栏角标） |
| `src/features/dashboard` | 创作首页、推广轮播、故事/剧本录入与快捷入口 |
| `src/features/projects` | 项目列表与项目卡片 |
| `src/features/studio` | 短剧创作工作流（剧本、资产、分镜、单集视频编辑）及共享 composables |
| `src/features/canvas` | 节点画布工作区与编辑器 |
| `src/features/admin` | 管理后台（概览、用户与调账、任务核对/补录、供应商与模型定价、项目、系统设置） |
| `src/stores` | Pinia 全局状态（`auth` 会话、`generation` 长任务、`ui` 通知） |
| `src/router` | 路由定义（`workspace.ts`、`admin.ts`、`canvas.ts`）与全局 `beforeEach` 权限守卫 |
| `src/lib` | Axios 实例与 401 拦截（`http.ts`）、通用格式化（`format.ts`）、文件校验 |
| `src/styles` | 主题变量（`tokens.css`）、组件/工作台/后台/官网样式 |
| `tests` | Node 原生单元测试（分页、文件校验、路由守卫、状态合并、批量任务状态机） |

## 认证与路由守卫

- `src/router/index.ts` 通过全局 `router.beforeEach` 统一拦截 `requiresAuth`（工作台、项目、分镜、画布、账户）与 `requiresAdmin`（`/admin/*`），单飞 `auth.hydrate()` 后放行，避免未登录闪烁。
- `src/lib/http.ts` 统一解包后端 `ApiEnvelope`，业务请求返回 `401` 时自动清理会话、项目缓存与模型目录缓存并回跳登录页（自动排除登录/注册/登出接口）。
