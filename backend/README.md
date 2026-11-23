# FrameDrama 后端

基于 FastAPI + PostgreSQL + Redis + Taskiq 的后端服务。以下命令均在 `backend` 目录下执行。

## 启动方式

启动前请确保已安装依赖（`uv sync --locked`）、配置好 `.env`，且 PostgreSQL 与 Redis 已运行。

### 1. API 服务

```powershell
uv run --locked uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

### 2. AI 异步 Worker（处理剧本 / 资产 / 分镜 / 生图 / 生视频及任务巡检）

```powershell
uv run --locked taskiq worker app.workers.broker:ai_broker app.workers.ai_tasks --workers 1 --max-async-tasks 20 --reload --reload-dir app
```

### 3. 媒体合成 Worker（按需启动，用于 FFmpeg 合成本集视频）

```powershell
uv run --locked taskiq worker app.workers.broker:media_broker app.workers.media_tasks --workers 1 --max-async-tasks 2 --reload --reload-dir app
```

## Docker 启动（可选）

```powershell
# 启动独立 PostgreSQL (5433) 与 Redis (6380)
docker compose --profile infra up -d

# 构建并启动 API 容器 (8000)
docker compose --profile app up -d --build
```

## 常用地址

- 接口文档：`http://127.0.0.1:8000/docs`（`production` 环境自动关闭）
- 存活探针：`GET http://127.0.0.1:8000/api/v1/health/live`
- 就绪探针：`GET http://127.0.0.1:8000/api/v1/health/ready`
