# FrameDrama Agent Guidelines

## 代码检索规范（CodeGraph 优先）

- 只要当前工作区存在 `.codegraph/` 索引且已接入 `codegraph` MCP，定位代码、查调用链、排查问题或修改代码前，**必须优先调用 `codegraph_explore`**，不要先用 `Select-String` / `grep` + 批量 `read_file` 手动扫描。
- 仅在 `codegraph_explore` 未覆盖的非代码文件（配置、文档、Alembic 迁移、静态资源等）或工具提示文件刚被修改待同步时，再直接读取文件。

## 工程纪律

- **前端**（`frontend/`）：严格 TypeScript（禁止 `any` 和 `@ts-ignore`），修改后执行 `npm run lint`、`npm test`、`npm run build`。
- **UI 组件与样式规范**：严格使用已统一的 UI 组件（`UiButton`、`UiInput`、`UiSelect`、`UiDateRangePicker`、`UiBadge`、`UiSegmented`、`UiTabs`、`UiPagination`、`UiDataTable`、`UiDialog`、`UiSwitch` 等），禁止手写杂散尺寸与重复样式；如实现新功能确实需要新增基础组件，必须提前告知用户并征得同意后方可新增。
- **后端**（`backend/`）：使用 `uv run --locked` 运行工具，修改后执行 `uv run --locked ruff check app alembic tests` 与 `uv run --locked pytest -q`。
- **安全**：禁止在日志、终端输出或提交内容中暴露 `.env` 密钥、API Key 或 OSS 凭证。
