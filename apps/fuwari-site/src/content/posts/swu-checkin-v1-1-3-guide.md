---
title: SWU Check-in v1.1.3：从只读验证到自动签到的完整使用指南
published: 2026-09-22
description: "面向 Maximora 独立维护版：本地验证、Windows、systemd、GitHub Actions、状态码与安全排障一次讲清。"
tags: ["SWU", "Python", "自动化", "systemd", "GitHub Actions", "Windows"]
category: 教程
draft: false
---

`swu-checkin` 是一个用于西南大学钉钉查寝签到的 Python 工具。它最初来自开源社区，本文介绍的是由 Maximora 独立维护的版本：在保留基础功能的同时，重点补上了认证链校验、提交后回读、只读诊断、并发保护、跨平台部署和可复现发布。

项目地址：[Maximora-byte/swu-checkin](https://github.com/Maximora-byte/swu-checkin)

本文对应稳定版 `v1.1.3`。它是非官方社区工具，与西南大学、钉钉和原上游作者不存在隶属或背书关系。使用前请确认符合学校现行规则，并由你自己保管账号凭据。

## 先选对运行方式

项目支持四种常见场景：

| 场景 | 推荐方式 | 主要取舍 |
| --- | --- | --- |
| 第一次使用、只想验证 | 本地 CLI | 最容易观察结果，不自动定时 |
| 长期在线 Linux 主机 | systemd timer | 时间稳定、权限隔离、方便回滚 |
| 日常使用 Windows 电脑 | Windows 计划任务 | 密码由 DPAPI 保护，但触发时用户需登录 |
| 没有自己的主机 | GitHub Actions | 配置简单，但 scheduled workflow 可能排队延迟 |

我的建议是：**无论最终使用哪一种，都先在本地完成一次只读验证。** 不要刚填完账号密码就直接开启无人值守定时任务。

## 本地安装：固定到已发布版本

项目要求 Python 3.13，并使用 uv 锁定依赖。当前没有发布到 PyPI，不要安装来源不明的同名包。

```bash
git clone https://github.com/Maximora-byte/swu-checkin.git
cd swu-checkin
git checkout v1.1.3
uv sync --locked --no-dev --python 3.13
```

这里有两个值得保留的习惯：

1. 使用明确的 Release tag，而不是把生产任务长期指向不断变化的 `main`；
2. 使用 `uv sync --locked`，让代码与 `uv.lock` 保持同一版本，锁文件不一致时直接失败。

完整安装说明见仓库的[快速上手](https://github.com/Maximora-byte/swu-checkin/blob/main/docs/quickstart.md)。

## 第一步不是签到，而是只读检查

首先执行交互式配置验证：

```bash
uv run --locked --no-dev swu-checkin setup
```

它会读取学号和无回显密码，检查认证、请假、学生信息、宿舍数据结构和今日任务接口。它不会保存密码，也不会调用签到提交接口。

再运行 probe：

```bash
uv run --locked --no-dev swu-checkin probe
```

probe 只读取业务状态，不提交签到，也不写运行状态文件。v1.1.3 还明确保证：即使它发现 cached session 已失效，也不会删除 cache、重新登录或保存新 token。这样 `probe` 才真正符合“只读诊断”的含义。

常见结果：

| code | 含义 |
| ---: | --- |
| 0 | 今日无签到记录 |
| 2 | 学校端已经显示已签到 |
| 5 | 请假期间无需签到 |
| 6 | 发现待签到任务，但 probe 没有提交 |
| 3 | 登录失败 |
| 4 | 网络错误或服务端数据异常 |

`[6]` 不能当作签到成功，它只证明“任务存在、只读检查结束”。

## 确认后再正式运行

```bash
uv run --locked --no-dev swu-checkin run
```

正式流程并不是“拿到一个 HTTP 200 就结束”，它会依次：

```text
获取本机运行锁
    ↓
验证 cached session / 必要时 fresh authentication
    ↓
读取请假、学生、宿舍与今日任务
    ↓
确认待签到后提交一次
    ↓
回读学校接口确认最终状态
```

如果定时任务与手动命令同时启动，第二个正式进程会立即发现运行锁并本地跳过，不等待、不读取凭据，也不访问学校接口。

提交阶段还有一条重要安全边界：POST timeout、连接中断或 HTTP 5xx 可能意味着服务器已经收到请求，只是客户端没拿到明确结果。此时工具不会通过“删除 token、重新登录”再发一次 POST，而是保留不确定性并 fail closed，避免重复提交。

## 机器读取结果：使用 JSON，不要 grep 文本

自动化脚本可以运行：

```bash
swu-checkin run --json
swu-checkin probe --json
```

stdout 只包含一个 schema v1 JSON document，例如：

```json
{"schema_version":1,"mode":"checkin","status":"success","code":1,"message":"签到成功","attempts":1,"duration_ms":1842}
```

调用方应该完整解析 JSON，并校验 `schema_version`、`mode`、`status`、`code` 和必需字段。不要用 `tail -1` 或正则去猜正文中有没有“成功”两个字。

正式运行只有状态 1、2、5 是正常终态；probe 则把 0、2、5、6 视为正常只读结果。完整对照见 [CLI 与状态码参考](https://github.com/Maximora-byte/swu-checkin/blob/main/docs/cli-reference.md)。

## Windows：DPAPI + 一个固定计划任务

在稳定版本仓库根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\install.ps1
```

安装器会创建 `%LOCALAPPDATA%\SWUCheckin`，使用独立 Python 3.13 环境，并在 doctor 全部通过后创建 `SWUCheckin-Daily` 任务。任务包含北京时间 21:15、21:45 两个 trigger，重复安装只会更新同一个任务。

密码使用 Windows DPAPI 加密，只能由同一台机器、同一 Windows 用户解密；它不会出现在 JSON、任务参数或日志中。计划任务使用交互登录令牌，因此触发时该用户需要处于登录状态。

验证任务：

```powershell
Get-ScheduledTask -TaskName "SWUCheckin-Daily"
Get-ScheduledTaskInfo -TaskName "SWUCheckin-Daily"
```

详细安装、更新和卸载步骤见 [Windows 使用指南](https://github.com/Maximora-byte/swu-checkin/blob/main/docs/windows.md)。

## Linux：为什么推荐 systemd timer

长期在线 Linux 主机更适合使用仓库提供的 systemd units。标准部署采用：

- 版本化 release 目录；
- `/opt/swu-checkin` 原子 symlink；
- 无登录 shell 的 `swu-checkin` 专用用户；
- `/etc/swu-checkin/credentials.env`，权限 `0600 root:root`；
- `/var/lib/swu-checkin` 保存非敏感状态、token cache 和运行锁；
- 21:15、21:45 两次非持久 timer；
- 可选 21:50 Telegram 汇总。

timer 的 `Persistent=false` 很重要：如果服务器在签到窗口外才开机，不会为了“补上错过的 timer”而提交过期任务。

仓库提供无回显凭据录入器：

```bash
sudo swu-checkin-set-credentials
```

它会原子写入凭据文件，先启动只读 probe；只有探测成功才启用正式 timer。部署、升级、symlink 切换和回滚命令见 [Linux systemd 部署](https://github.com/Maximora-byte/swu-checkin/blob/main/DEPLOYMENT.md)。

## GitHub Actions：容易上手，但不是准点调度器

没有服务器时，可以 fork 仓库并在 **Settings → Secrets and variables → Actions** 添加：

- `SWU_USERNAME`
- `SWU_PASSWORD`

workflow 默认在北京时间 21:15、21:45 触发，并支持多账号 matrix 与可选异常邮件通知。但 GitHub cron 只表示“最早可调度时间”，不提供准点 SLA；公共 runner 高峰期可能延迟很久。

第一次应在 Actions 页面手动运行并检查完整 job。注意：`Run workflow` 执行的是正式签到，不是 probe。如果需要只读验证，先在本地运行 probe。

完整 Secrets、多账号、邮件和停用方法见 [GitHub Actions 指南](https://github.com/Maximora-byte/swu-checkin/blob/main/GITHUB_ACTIONS.md)。

## v1.1.3 解决了什么

实际运行中可能出现一种“部分失效 session”：身份接口仍接受旧 token，但后续业务只读接口明确返回 401/403。过去它容易被映射成笼统的 `DATA_ERROR`，删除 cache 后重新认证才恢复。

v1.1.3 将恢复条件收窄为：

```text
cached token
+ 提交前只读阶段
+ 明确 HTTP / 业务码 401 或 403
→ 删除旧 cache
→ fresh authentication 一次
→ 重新执行 pre-submit reads
```

它不会把 timeout、非 JSON、schema 变化、空数据或未知响应解释为 token 失效，也不会无限循环。probe 明确关闭这条恢复路径，因此仍保持 read-only。

## 遇到状态 4，不要先删东西

`[4] 网络错误或数据异常` 是一个 fail-closed 聚合状态，可能来自网络、HTTP、JSON、schema、请假、宿舍、任务或提交结果无法确认。推荐顺序：

```bash
swu-checkin doctor
swu-checkin probe
```

如果使用 systemd，再检查：

```bash
systemctl status swu-checkin.timer --no-pager -l
journalctl -u swu-checkin.service -n 100 --no-pager
swu-checkin status --file /var/lib/swu-checkin/status.json
```

不要连续手动执行正式签到，也不要把所有 `DATA_ERROR` 都当成 token 失效。只有明确 401/403 才满足安全的 cached-session fallback 条件。

提交 Issue 时只附版本、平台、状态码、exit code、异常类型和脱敏结构信息。账号、密码、验证码、token、ticket、OAuth 参数、完整回调 URL、宿舍地址和坐标都不应公开。

更完整的决策树见 [故障排查](https://github.com/Maximora-byte/swu-checkin/blob/main/docs/troubleshooting.md) 与 [安全模型](https://github.com/Maximora-byte/swu-checkin/blob/main/docs/security.md)。

## 更新时保持整套版本一致

无论哪种部署，都不要只复制单个 Python 文件。源码、`pyproject.toml`、`uv.lock`、Windows 脚本、systemd units 和文档应该来自同一 tag。

本地升级示例：

```bash
git fetch --tags origin
git checkout <新的稳定版本标签>
uv sync --locked --no-dev --python 3.13
uv run --locked --no-dev swu-checkin doctor
uv run --locked --no-dev swu-checkin probe
```

生产 Linux 部署应把新版本安装到独立 release 目录，通过 probe 后再切换 symlink，并保留上一版作为回滚点。

## 相关链接

- [项目仓库](https://github.com/Maximora-byte/swu-checkin)
- [最新 Release](https://github.com/Maximora-byte/swu-checkin/releases/latest)
- [文档中心](https://github.com/Maximora-byte/swu-checkin/blob/main/docs/README.md)
- [Issues](https://github.com/Maximora-byte/swu-checkin/issues)
- [原始项目 Sorynthia/swu-checkin](https://github.com/Sorynthia/swu-checkin)

自动化工具真正重要的不是“尽量提交”，而是知道什么时候应该停下来。先只读验证、对异常 fail closed、限制重新认证次数、避免 ambiguous submission 后重复 POST，再配合可回滚部署，才是这套维护版最核心的设计。
