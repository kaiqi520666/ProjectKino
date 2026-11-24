# ProjectKino

AI 影视短剧创作工作台全栈工程，包含创作前端与正式后端服务。

## 目录结构

| 目录 | 说明 | 文档 |
| --- | --- | --- |
| `frontend/` | Vue 3 + TypeScript + Vite + Tailwind CSS v4 创作前端与管理后台 | [frontend/README.md](./frontend/README.md) |
| `backend/` | FastAPI + PostgreSQL + Redis + Taskiq 正式后端服务与异步 Worker | [backend/README.md](./backend/README.md) |

## 环境配置

各子目录均提供 `.env.example` 作为配置模板。本地开发时请复制为 `.env` 并自行填写数据库、Redis、对象存储及模型供应商凭证，**切勿将 `.env` 或密钥文件提交至仓库**。
