# 前端目录结构草案

本文件只记录目录组织方案，不确定功能范围、业务边界、开发顺序或路由。
目录可以随着实际开发调整，不需要一次性创建。

## 项目目录

```text
FrameDrama/
├── docs/
│   └── frontend-architecture.md
└── frontend/
    ├── public/
    │   └── images/
    │       ├── home/
    │       ├── auth/
    │       └── workspace/
    ├── src/
    │   ├── layouts/
    │   │   └── WorkspaceLayout.vue
    │   ├── components/
    │   │   ├── ui/
    │   │   ├── site/
    │   │   ├── business/
    │   │   └── workspace/
    │   ├── features/                 # 按开发需要逐步建立
    │   │   ├── auth/                 # 规划，现有登录页尚未迁移
    │   │   ├── home/                 # 规划，现有官网首页尚未迁移
    │   │   ├── dashboard/
    │   │   ├── projects/
    │   │   ├── studio/
    │   │   ├── canvas/               # 规划
    │   │   ├── assets/               # 规划
    │   │   └── account/              # 规划
    │   ├── views/                    # 保留现有页面
    │   │   ├── HomeView.vue
    │   │   ├── AuthView.vue
    │   │   └── WorkspacePendingView.vue
    │   ├── router/
    │   │   ├── index.ts
    │   │   └── workspace.ts
    │   ├── stores/
    │   ├── lib/
    │   ├── styles/
    │   ├── dev/
    │   ├── App.vue
    │   └── main.ts
    ├── tests/
    ├── scripts/
    ├── artifacts/
    ├── .env.example
    ├── .gitignore
    ├── index.html
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    └── README.md
```

目录树省略了部分现有文件、依赖目录及构建产物。
`features` 下的名称只是当前组织草案，可以增删、合并或改名。

## 已实现组件的位置

```text
src/
├── layouts/
│   └── WorkspaceLayout.vue
├── components/workspace/
│   ├── WorkspaceSidebar.vue
│   ├── WorkspaceHeader.vue
│   ├── CreditBalance.vue
│   ├── UserMenu.vue
│   └── workspace-navigation.ts
└── features/
    ├── dashboard/
    │   ├── views/WorkspaceHomeView.vue
    │   └── components/
    │       ├── PromoCarousel.vue
    │       └── ToolEntryCard.vue
    ├── studio/
    │   └── components/ScriptCreationPanel.vue
    └── projects/
        ├── project-types.ts
        └── components/ProjectCard.vue
```

`WorkspacePendingView.vue` 是未实现页面共用的临时状态，不代表对应业务功能已经完成。
创作首页的独立写实配图位于 `public/images/workspace`；ComfyUI 提示词、比例与种子保存在 `scripts/workspace-v1-image-briefs.json`。

## 业务模块内部目录示例

模块较小时直接放文件；文件增加后，再按需要采用以下结构，不必全部创建：

```text
features/<模块名>/
├── views/
├── components/
├── composables/
├── stores/
├── api.ts
├── queries.ts
└── types.ts
```

## 当前处理方式

- 按实际开发创建文件，不提前创建空业务目录。
- 现有页面和组件保持原位，实际开发需要调整时再迁移。
- 文件目录不限定 URL；放在工作台相关目录的页面不必使用 `/workspace` 前缀。
- 后续按实际实现更新本文档，不为尚未确定的功能提前细分目录。
