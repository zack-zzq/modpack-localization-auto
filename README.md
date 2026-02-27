# Modpack Localization Auto
# 自动化 Minecraft 整合包本地化工具

本项目用于全自动翻译 Minecraft 整合包的外语文本。包括下载整合包、提取 Mod/KubeJS/FTB Quests 语言文件、使用已有汉化补丁或通过大语言模型 (LLM) 进行翻译，最终打包为即插即用的汉化资源包和配置覆盖包。

> **🔔 注意：**
> 考虑到基于 LLM 的翻译任务需要较长时间、且极其容易在 GitHub Actions 等 CI 环境超时中断，**强烈推荐在本地计算机上运行本工具！**

---

## 🚀 快速开始（本地运行指南）

### 0. 准备环境
确保你的电脑上安装了 Python（推荐 3.12+），并[安装 `uv`](https://docs.astral.sh/uv/getting-started/installation/) 包管理器。

### 1. 配置环境变量
项目根目录下存放着一个 `.env.example` 文件。请将其复制并重命名为 `.env`，然后填入你的各项密钥信息：
- `CURSEFORGE_API_KEY`: 必填，用于下载整合包的 API 密钥。
- `OPENAI_API_KEY`: 必填，大语言模型 API 密钥。可以通过火山引擎等渠道获取高性价比的通义/豆包等模型。

### 2. 配置翻译目标
编辑根目录下的 `config.toml`，在其中配置你需要翻译的整合包的 CurseForge slug。
```toml
# 目标整合包的 CurseForge Slugs
slugs = [
    "better-mc-neoforge-bmc5"
]

# 开启 LLM 翻译（缺失的词条交给大语言模型处理）
use_llm = true
```

### 3. 开始执行
一切就绪后，在项目根目录运行以下命令即可：
```bash
uv run modpack-localize
```
执行完毕后，生成的汉化文件将出现在 `output/` 对应整合包的目录下。

---

## 📦 如何使用生成的汉化包

在项目执行成功后，你会在 `output/<整合包slug>/` 文件夹中得到两个核心 ZIP 文件。根据以下步骤安装即可畅玩汉化版：

### 1. `<slug>-localization-resourcepack.zip` (资源包)
这是整个翻译的核心资源包（包含 Mod 原生界面的汉化以及 KubeJS 产出的各种提示等）。
- **用法：** 将此 zip 放入 Minecraft 安装目录下的 `resourcepacks` 文件夹中。
- 启动游戏，在“选项 -> 资源包”中启用它，并确保其层级位于顶部（或紧挨着汉化补丁）。

### 2. `<slug>-localization-overrides.zip` (配置覆盖包)
这个压缩包包含了不能通过资源包汉化、且必须修改配置的文本。例如 **FTB Quests (任务书)**。
- **用法：** 将它视作整合包的覆盖文件 (overrides)。解压该 zip 的内容，并把解压得到的 `config` 或其它文件夹**直接合入**你客户端的根目录（覆盖原文件）。
- 如果你是在发布汉化版整合包，直接把里面的文件合并到你的 overrides 压缩包里即可。

---

## 🤖 自动化发版 (GitHub Actions)

为了方便向玩家分发最终产出的汉化资源，本项目已配置 GitHub Actions 自动发布流程！

当你在本地成功运行完毕，并将 `output/` 目录中的新增翻译成果 **Push 推送** 到当前代码仓库时：
- GitHub Actions 会自动触发发布工作流。
- 它读取你提交的整合包产物，自动创建一个 GitHub Release。
- 并将生成的 `resourcepack.zip` 和 `overrides.zip` 作为附件附加在 Release 中供玩家下载！
