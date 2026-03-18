# skills_store

Lighthouse 的 GitHub Skills Store 镜像仓。

当前目标很简单：

- 镜像少量 Lighthouse 认可的官方 skills
- 为每个 skill 生成一个独立 zip
- 维护一个统一的 `index.json`
- 让 Lighthouse 客户端以后只读取这个仓，而不是直接读取多个上游 repo

## 目录结构

```text
skills_store/
├── README.md
├── LICENSE
├── official_sources.json
├── index.json
├── skills/
│   └── <skill-id>/
│       ├── SKILL.md
│       ├── meta.json
│       ├── LICENSE.txt
│       └── assets|scripts|references...
├── dist/
│   └── <skill-id>-<version>.zip
└── scripts/
    └── sync_official_skills.mjs
```

## 当前首批镜像来源

- `anthropics/skills`
- `openai/skills`

## 当前首批镜像 skill

- `anthropic-webapp-testing`
- `openai-pdf`
- `openai-playwright`
- `openai-spreadsheet`

## 设计原则

1. 客户端只读取 `index.json`
2. 每个 skill 一个独立 zip
3. 所有镜像 skill 都保留来源 repo、来源路径、来源 commit
4. 不直接信任上游 repo 作为客户端安装源

