# Modpack Localization Auto

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

---

## 🛠️ 进阶操作与常见问题

如果你修改了某些配置或需要强制重新翻译某些内容，可以通过删除 `work/` 目录下的缓存文件来让程序重新执行特定步骤。

所有的中间处理文件都存放在 `work/<整合包slug>/` 目录下，主要分为 `extracted/`（已提取的英文原文）和 `translated/`（已汉化的结果）两个文件夹。

### 1. 如何重新翻译单个 Mod（并重新打包）？
如果你对某个模组（如 `ad_astra`）的翻译不满意，或者想要重新应用新的词典：
- 进入 `work/<整合包slug>/translated/mods/` 目录。
- 找到对应模组名称的文件夹（例如 `ad_astra/`）并将其**删除**。
- 下次运行 `uv run modpack-localize` 时，程序会发现该模组的汉化结果缺失，从而**仅针对该模组**重新进行词典匹配和 LLM 翻译，并最终重新生成资源包。

### 2. 如何重新提取/翻译 KubeJS 脚本？
如果你更新了整合包的 KubeJS 脚本文件，或者想要强制 LLM 重新翻译 KubeJS 提示词：
- **重新翻译**：删除 `work/<整合包slug>/translated/kubejs/` 文件夹。下次运行将重新把上次提取出来的英文发送给 LLM 翻译。
- **重新提取+翻译**：如果你修改了原整合包里的脚本，想要重新提取出里面新的英文句。请进入 `work/<整合包slug>/extracted/` 和 `translated/`，将两边的 `kubejs/` 文件夹**都删除**。下次运行就会重新扫描脚本文件并重新翻译。

### 3. 如何重新提取/翻译 FTB Quests 任务书？
操作逻辑与 KubeJS 完全一致：
- **重新翻译**：仅删除 `work/<整合包slug>/translated/ftbquests/`。
- **重新提取+翻译**：同时删除 `work/<整合包slug>/extracted/ftbquests/` 和 `work/<整合包slug>/translated/ftbquests/` 这两个文件夹。
- 再次运行程序后，最新生成的汉化任务书会被重新组装并打包到 `output/` 的 overrides 压缩包中。
