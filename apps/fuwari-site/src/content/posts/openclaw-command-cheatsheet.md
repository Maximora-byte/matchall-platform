---
title: OpenClaw 常用命令合集
published: 2026-06-06
description: "一份面向日常使用、排错、模型切换、版本更新和服务维护的 OpenClaw 命令速查。"
tags: ["OpenClaw", "AI Agent", "CLI", "运维"]
category: OpenClaw
draft: false
---

OpenClaw 是一个面向个人自动化助手的本地运行环境。它可以连接微信、Google 日历、Gmail、Google Drive、远程服务器和各种自动化工具，让 AI 助手真正进入日常工作流。

这篇文章整理一份 OpenClaw 常用命令合集，适合用于首次配置、日常使用、排错、模型切换、版本更新和服务维护。

## OpenClaw Gateway 启动与状态检查

OpenClaw Gateway 是 OpenClaw 的核心网关服务。如果微信消息、工具调用、Google 日历或其他连接出现异常，可以优先检查它。

查看 OpenClaw Gateway 服务状态：

```bash
sudo systemctl status openclaw-gateway --no-pager -l
```

重启 OpenClaw Gateway：

```bash
sudo systemctl restart openclaw-gateway
```

查看实时日志：

```bash
journalctl -u openclaw-gateway -f
```

查看最近 100 条日志：

```bash
journalctl -u openclaw-gateway -n 100 --no-pager
```

注意：重启 `openclaw-gateway` 可能会中断当前正在运行的 OpenClaw / Codex 会话。建议先查看状态，再决定是否重启。

## 基础配置命令

进入 OpenClaw 交互式配置向导：

```bash
openclaw configure
```

这个命令可以用来配置或修改 OpenClaw 的基础设置，包括模型、Gateway、消息渠道、插件、Skills 和健康检查等。

第一次配置 OpenClaw 时，也可以使用：

```bash
openclaw onboard
```

初始化本地配置、工作区和会话目录：

```bash
openclaw setup
```

查看 OpenClaw 当前整体状态：

```bash
openclaw status
```

运行诊断和自动修复：

```bash
openclaw doctor --fix
```

## 模型管理命令

OpenClaw 支持配置多个模型，并可以切换默认模型或临时指定某一次对话使用的模型。

查看所有已配置模型：

```bash
openclaw models list
```

查看当前默认模型：

```bash
openclaw models current
```

切换默认模型：

```bash
openclaw models set yuanbao/hunyuan-turbo
```

临时切换单次对话，不改变默认模型：

```bash
openclaw chat --model yuanbao/hunyuan-turbo --prompt "测试"
```

这个命令适合测试某个模型是否可用，也适合临时让某个任务使用不同模型。

## 版本更新命令

OpenClaw 支持通过 `openclaw update` 更新版本，也可以切换正式版、beta 版或 dev 版更新通道。

查看当前版本和更新通道：

```bash
openclaw update status
```

更新当前通道版本：

```bash
openclaw update
```

更新到正式版 stable：

```bash
openclaw update --channel stable
```

更新到 beta 版本：

```bash
openclaw update --channel beta
```

更新到 dev 开发版：

```bash
openclaw update --channel dev
```

预览更新，不实际修改：

```bash
openclaw update --dry-run
```

非交互式更新，自动确认提示：

```bash
openclaw update --yes
```

更新但不重启 Gateway：

```bash
openclaw update --no-restart
```

更新到 beta，并自动确认：

```bash
openclaw update --channel beta --yes
```

更新到正式版，并自动确认：

```bash
openclaw update --channel stable --yes
```

使用交互式更新向导：

```bash
openclaw update wizard
```

说明：`--channel stable` 是正式版，`--channel beta` 是测试版，`--channel dev` 是开发版。日常使用建议 stable；想提前体验新功能可以用 beta。更新前可以先运行 `openclaw update --dry-run` 看看会发生什么。

## 微信对话常用指令

在微信里和 OpenClaw 助手对话时，可以直接发送控制指令。

查看当前状态：

```text
/status
```

查看 default 默认模式相关状态：

```text
/status default
```

开启一个新的会话：

```text
/new
```

`/new` 适合开始一个全新任务，避免旧上下文影响当前对话。

## 进入 OpenClaw 工作区

OpenClaw 的工作区通常在：

```bash
cd ~/.openclaw/workspace
```

查看工作区文件：

```bash
ls -la ~/.openclaw/workspace
```

常见的重要文件包括：

```bash
AGENTS.md
TOOLS.md
SOUL.md
USER.md
MEMORY.md
memory/
skills/
```

查看本地工具说明：

```bash
cat ~/.openclaw/workspace/TOOLS.md
```

查看长期记忆：

```bash
cat ~/.openclaw/workspace/MEMORY.md
```

查看每日记忆目录：

```bash
ls -la ~/.openclaw/workspace/memory
```

追加当天记录：

```bash
mkdir -p ~/.openclaw/workspace/memory
printf '\n- 这里写今天要记住的内容\n' >> ~/.openclaw/workspace/memory/$(date +%F).md
```

## Google / gog 常用命令

如果 OpenClaw 连接了 Google 日历、Gmail 或 Google Drive，`gog` 是很常用的排错工具。

检查 Google 授权状态：

```bash
gog auth doctor --json --no-input
```

查看授权账号：

```bash
gog auth list
```

重新授权 Google：

```bash
gog auth login
```

查看日历列表：

```bash
gog calendar list
```

查看近期日程：

```bash
gog calendar events list --calendar primary
```

创建测试日程：

```bash
gog calendar events create \
  --calendar primary \
  --summary "OpenClaw Test Event" \
  --start "2026-06-06T10:00:00+08:00" \
  --end "2026-06-06T10:30:00+08:00"
```

搜索 Gmail：

```bash
gog gmail search 'newer_than:7d'
```

查看 Google Drive 文件：

```bash
gog drive list
```

如果 Google 日历、邮箱或网盘经常失效，优先运行：

```bash
gog auth doctor --json --no-input
```

## 文件搜索命令

在 OpenClaw 工作区里查找内容，推荐使用 `rg`。

搜索关键词：

```bash
rg "关键词" ~/.openclaw/workspace
```

列出所有文件：

```bash
rg --files ~/.openclaw/workspace
```

按文件名搜索：

```bash
rg --files ~/.openclaw/workspace | rg "文件名"
```

查找 Google、OAuth、日历相关配置：

```bash
rg "google|calendar|oauth|gog" ~/.openclaw -i
```

## Skills 技能管理

查看本地技能目录：

```bash
ls -la ~/.openclaw/workspace/skills
```

查看某个技能说明：

```bash
cat ~/.openclaw/workspace/skills/技能名/SKILL.md
```

搜索所有 Skill 文件：

```bash
find ~/.openclaw/workspace/skills -name SKILL.md
```

查看插件技能目录：

```bash
ls -la ~/.openclaw/plugin-skills
```

Skills 相当于 OpenClaw 助手的专业工作流说明，比如 Google Workspace、小红书、Excel、Word、天气、金融数据等。

## 进程、端口与服务排查

查看 OpenClaw 相关进程：

```bash
ps aux | grep -i openclaw
```

查看端口监听情况：

```bash
ss -lntup | grep -i openclaw
```

查看本机回调端口，例如 OAuth 授权时常见的 127.0.0.1 端口：

```bash
ss -lntup | grep 127.0.0.1
```

查看系统资源：

```bash
free -h
df -h
uptime
```

## 备份与清理

查看 OpenClaw 目录大小：

```bash
du -sh ~/.openclaw
```

查找大文件：

```bash
find ~/.openclaw -type f -size +100M -print
```

备份工作区：

```bash
tar -czf openclaw-workspace-backup-$(date +%F).tar.gz ~/.openclaw/workspace
```

删除文件前建议使用 `trash`，不要直接 `rm`：

```bash
trash 文件名
```

如果系统没有安装 trash-cli，可以安装：

```bash
sudo apt install trash-cli
```

## SSH 与远程节点维护

如果 OpenClaw 需要管理远程服务器，可以用 SSH 快速排查。

查看 SSH 配置：

```bash
cat ~/.ssh/config
```

测试 SSH 连接：

```bash
ssh 主机别名 'hostname && uptime'
```

查看远程服务状态：

```bash
ssh 主机别名 'systemctl status 服务名 --no-pager'
```

查看远程端口：

```bash
ssh 主机别名 'ss -lntup'
```

查看远程磁盘：

```bash
ssh 主机别名 'df -h'
```

查看远程内存：

```bash
ssh 主机别名 'free -h'
```

## 常见问题排查组合

OpenClaw Gateway 不响应：

```bash
sudo systemctl status openclaw-gateway --no-pager -l
journalctl -u openclaw-gateway -n 200 --no-pager
ss -lntup | grep -i openclaw
```

Google 日历失效：

```bash
gog auth doctor --json --no-input
gog calendar list
journalctl -u openclaw-gateway -n 100 --no-pager
```

Gmail 或 Google Drive 读不到：

```bash
gog auth doctor --json --no-input
gog drive list
gog gmail search 'newer_than:1d'
```

OAuth 链接经常过期：

```bash
gog auth doctor --json --no-input
ls -la ~/.local/share/gogcli
journalctl -u openclaw-gateway -n 100 --no-pager
```

工作区找不到文件：

```bash
pwd
rg --files ~/.openclaw/workspace
rg "关键词" ~/.openclaw/workspace
```

更新后服务异常：

```bash
openclaw update status
sudo systemctl status openclaw-gateway --no-pager -l
journalctl -u openclaw-gateway -n 200 --no-pager
```

配置异常或模型不可用：

```bash
openclaw configure
openclaw models list
openclaw models current
openclaw doctor --fix
```

## 建议的日常维护清单

每隔一段时间可以做一次快速检查：

```bash
sudo systemctl status openclaw-gateway --no-pager -l
gog auth doctor --json --no-input
openclaw update status
openclaw models current
du -sh ~/.openclaw
ls -la ~/.openclaw/workspace/memory
```

如果你经常调整模型、Google 授权、节点、服务配置，建议把重要变化记录到：

```bash
~/.openclaw/workspace/TOOLS.md
~/.openclaw/workspace/memory/日期.md
```

这样以后排查问题时，不需要重新发现一遍环境。

## 结语

OpenClaw 的价值不只是“和 AI 聊天”，而是把 AI 助手接入真实工作流：微信、日历、邮箱、网盘、服务器、模型切换和自动化任务。

掌握这些常用命令后，大多数 OpenClaw 使用问题都可以快速定位：服务是否正常、模型是否可用、Google 授权是否失效、文件在哪里、日志报了什么错、当前版本是否需要更新。命令行是维护 OpenClaw 最可靠的入口，也是让个人 AI 助手长期稳定运行的基础。
