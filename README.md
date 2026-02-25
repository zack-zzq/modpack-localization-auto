# Modpack Localization Auto

自动化 Minecraft 整合包本地化工具 — 自动下载、提取、翻译、打包。

## 使用方式

1. 在 `config.toml` 中配置整合包的 slug
2. 在 `.env` 中配置 API 密钥
3. 运行 `uv run modpack-localize`

## 环境变量

| 变量 | 说明 |
|------|------|
| `CURSEFORGE_API_KEY` | CurseForge API 密钥 |
| `OPENAI_BASE_URL` | OpenAI 兼容 API 端点 |
| `OPENAI_API_KEY` | API 密钥 |
| `OPENAI_MODEL_ID` | 模型 ID |
